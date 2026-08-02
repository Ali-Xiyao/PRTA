from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from prta_cxr.contracts import (
    PROGRESSION_LABELS,
    ContractError,
    canonical_sha256,
    sha256_file,
    validate_sample,
)

AI_LABELS = (*PROGRESSION_LABELS, "Unclear")
AI_OUTPUT_FIELDS = frozenset({"sample_id", "ai_label"})
EXTERNAL_ITEM_FIELDS = frozenset(
    {"sample_id", "finding", "prior_report", "current_report"}
)


def validate_independent_ai_record(row: Mapping[str, Any]) -> dict[str, str]:
    if set(row) != AI_OUTPUT_FIELDS:
        missing = sorted(AI_OUTPUT_FIELDS - set(row))
        extra = sorted(set(row) - AI_OUTPUT_FIELDS)
        raise ContractError(
            f"independent AI field mismatch; missing={missing}, extra={extra}"
        )
    sample_id = row["sample_id"]
    label = row["ai_label"]
    if not isinstance(sample_id, str) or not sample_id.strip():
        raise ContractError("independent AI sample_id must be non-empty")
    if label not in AI_LABELS:
        raise ContractError("unknown independent AI label")
    return {"sample_id": sample_id.strip(), "ai_label": str(label)}


def validate_independent_ai_batch(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    validated = [validate_independent_ai_record(row) for row in rows]
    identifiers = [row["sample_id"] for row in validated]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("duplicate sample_id in independent AI batch")
    return validated


def load_independent_ai_output(path: Path) -> list[dict[str, str]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"items"}:
        raise ContractError("independent AI output root must contain only items")
    if not isinstance(value["items"], list):
        raise ContractError("independent AI output items must be a list")
    return validate_independent_ai_batch(value["items"])


def prepare_independent_ai_batches(
    samples: Sequence[Mapping[str, Any]],
    *,
    batch_size: int,
    prompt_path: Path,
    schema_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if batch_size < 1 or batch_size > 30:
        raise ContractError("independent AI batch_size must be within [1, 30]")
    validated = [validate_sample(row) for row in samples]
    identifiers = [row["sample_id"] for row in validated]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("candidate sample_id values must be unique")
    prompt_hash = sha256_file(prompt_path)
    schema_hash = sha256_file(schema_path)
    batches = []
    for batch_index, start in enumerate(range(0, len(validated), batch_size)):
        selected = validated[start : start + batch_size]
        sample_id_map = {
            f"s{batch_index:05d}_{offset:02d}": row["sample_id"]
            for offset, row in enumerate(selected)
        }
        items = [
            {
                "sample_id": alias,
                "finding": row["finding"],
                "prior_report": row["prior_report"],
                "current_report": row["current_report"],
            }
            for alias, row in zip(sample_id_map, selected, strict=True)
        ]
        if any(set(item) != EXTERNAL_ITEM_FIELDS for item in items):
            raise ContractError("independent AI external item fields changed")
        batches.append(
            {
                "schema": "prta-cxr.independent-ai-input-batch.v1",
                "batch_id": f"batch_{batch_index:05d}",
                "prompt_sha256": prompt_hash,
                "output_schema_sha256": schema_hash,
                "items": items,
                "sample_id_map": sample_id_map,
                "input_sha256": canonical_sha256(items),
            }
        )
    receipt = {
        "schema": "prta-cxr.independent-ai-batch-preparation-receipt.v1",
        "samples": len(validated),
        "batches": len(batches),
        "batch_size": batch_size,
        "prompt_sha256": prompt_hash,
        "output_schema_sha256": schema_hash,
        "external_item_fields": sorted(EXTERNAL_ITEM_FIELDS),
        "rule_label_in_external_payload": False,
        "patient_identifiers_in_external_payload": False,
        "alias_map_in_external_payload": False,
        "candidate_manifest_sha256": canonical_sha256(validated),
    }
    return batches, receipt


def externalize_independent_batch(batch: Mapping[str, Any]) -> dict[str, Any]:
    if batch.get("schema") != "prta-cxr.independent-ai-input-batch.v1":
        raise ContractError("unsupported independent AI input batch")
    allowed_batch_fields = {
        "schema",
        "batch_id",
        "prompt_sha256",
        "output_schema_sha256",
        "items",
        "input_sha256",
        "sample_id_map",
    }
    if set(batch) != allowed_batch_fields:
        raise ContractError("independent AI input batch fields changed")
    items = batch["items"]
    if not isinstance(items, list) or not items:
        raise ContractError("independent AI batch items must be non-empty")
    if any(not isinstance(item, dict) for item in items):
        raise ContractError("independent AI items must be objects")
    if any(set(item) != EXTERNAL_ITEM_FIELDS for item in items):
        raise ContractError("independent AI external item fields changed")
    identifiers = [item["sample_id"] for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("duplicate alias in independent AI input batch")
    if canonical_sha256(items) != batch.get("input_sha256"):
        raise ContractError("independent AI input batch hash mismatch")
    return {key: value for key, value in batch.items() if key != "sample_id_map"}


def _group_audit(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    agreement = sum(row["silver_status"] == "accepted" for row in rows)
    unclear = sum(row["silver_status"] == "excluded_unclear" for row in rows)
    mismatch = total - agreement - unclear
    return {
        "rows": total,
        "accepted_exact_agreement": agreement,
        "excluded_mismatch": mismatch,
        "excluded_unclear": unclear,
        "agreement_rate": agreement / total if total else None,
    }


def merge_independent_silver(
    samples: Sequence[Mapping[str, Any]],
    ai_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    validated_samples = [validate_sample(row) for row in samples]
    validated_ai = validate_independent_ai_batch(ai_rows)
    sample_by_id = {row["sample_id"]: row for row in validated_samples}
    ai_by_id = {row["sample_id"]: row for row in validated_ai}
    if len(sample_by_id) != len(validated_samples):
        raise ContractError("duplicate sample_id in candidate samples")
    if set(ai_by_id) != set(sample_by_id):
        missing = sorted(set(sample_by_id) - set(ai_by_id))
        extra = sorted(set(ai_by_id) - set(sample_by_id))
        raise ContractError(
            f"independent AI IDs mismatch; missing={missing}, extra={extra}"
        )

    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    for sample_id in sorted(sample_by_id):
        sample = sample_by_id[sample_id]
        ai_label = ai_by_id[sample_id]["ai_label"]
        if ai_label == "Unclear":
            status = "excluded_unclear"
        elif ai_label == sample["progression_label"]:
            status = "accepted"
        else:
            status = "excluded_mismatch"
        comparison = {
            "sample_id": sample_id,
            "source": sample["source"],
            "finding": sample["finding"],
            "rule_label": sample["progression_label"],
            "ai_label": ai_label,
            "silver_status": status,
        }
        comparisons.append(comparison)
        if status == "accepted":
            accepted.append(
                sample
                | {
                    "label_source": "rule_ai_independent_exact_agreement",
                    "label_tier": "Silver",
                }
            )
        else:
            excluded.append(comparison)

    sources = {
        source: _group_audit(
            [row for row in comparisons if row["source"] == source]
        )
        for source in sorted({row["source"] for row in comparisons})
    }
    rule_labels = {
        label: _group_audit(
            [row for row in comparisons if row["rule_label"] == label]
        )
        for label in PROGRESSION_LABELS
    }
    audit = {
        "schema": "prta-cxr.independent-silver-merge-audit.v1",
        "status": "PASS_INDEPENDENT_SILVER_INTERSECTION",
        "overall": _group_audit(comparisons),
        "by_source": sources,
        "by_rule_label": rule_labels,
        "ai_label_counts": dict(
            sorted(Counter(row["ai_label"] for row in comparisons).items())
        ),
        "rule_label_was_externalized": False,
        "manual_label_edits": False,
        "agreement_is_ground_truth": False,
        "human_accuracy_audit": {
            "required": True,
            "required_rows_min": 200,
            "required_rows_max": 300,
            "stratification": "source_x_five_label",
            "completed": False,
        },
        "formal_training_authorized": False,
        "paper_use_authorized": False,
        "accepted_manifest_sha256": canonical_sha256(accepted),
        "excluded_manifest_sha256": canonical_sha256(excluded),
    }
    return accepted, excluded, audit
