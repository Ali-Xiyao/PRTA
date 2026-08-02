from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from prta_cxr.contracts import (
    ContractError,
    canonical_sha256,
    sha256_file,
    validate_luna_batch,
    validate_sample,
)


def prepare_luna_batches(
    samples: Sequence[Mapping[str, Any]],
    *,
    batch_size: int,
    prompt_path: Path,
    schema_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if batch_size < 1 or batch_size > 30:
        raise ContractError("Luna batch_size must be within [1, 30]")
    validated = [validate_sample(row) for row in samples]
    identifiers = [row["sample_id"] for row in validated]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("candidate sample_id values must be unique")
    prompt_hash = sha256_file(prompt_path)
    schema_hash = sha256_file(schema_path)
    batches = []
    for batch_index, start in enumerate(range(0, len(validated), batch_size)):
        selected = validated[start : start + batch_size]
        items = [
            {
                "sample_id": row["sample_id"],
                "finding": row["finding"],
                "rule_candidate_label": row["progression_label"],
                "prior_report": row["prior_report"],
                "current_report": row["current_report"],
                "prior_datetime": row["prior_datetime"],
                "current_datetime": row["current_datetime"],
            }
            for row in selected
        ]
        batches.append(
            {
                "schema": "prta-cxr.luna-input-batch.v1",
                "batch_id": f"batch_{batch_index:05d}",
                "prompt_sha256": prompt_hash,
                "output_schema_sha256": schema_hash,
                "items": items,
                "input_sha256": canonical_sha256(items),
            }
        )
    receipt = {
        "schema": "prta-cxr.luna-batch-preparation-receipt.v1",
        "samples": len(validated),
        "batches": len(batches),
        "batch_size": batch_size,
        "prompt_sha256": prompt_hash,
        "output_schema_sha256": schema_hash,
        "patient_identifiers_in_batches": False,
        "candidate_manifest_sha256": canonical_sha256(validated),
    }
    return batches, receipt


def load_luna_output(path: Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"items"}:
        raise ContractError("Luna output root must contain only items")
    if not isinstance(value["items"], list):
        raise ContractError("Luna output items must be a list")
    return validate_luna_batch(value["items"])
