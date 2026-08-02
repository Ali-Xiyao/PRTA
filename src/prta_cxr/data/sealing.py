from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from prta_cxr.contracts import ContractError, canonical_sha256

CACHE_INPUT_FIELDS = (
    "sample_id",
    "source",
    "finding",
    "prior_image_path",
    "current_image_path",
    "split",
)
SEALED_OUTCOME_FIELDS = frozenset(
    {"progression_label", "label_source", "label_tier", "patient_id_hash"}
)


def outcome_free_roster_cache_rows(
    roster: Sequence[Mapping[str, Any]],
    silver_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    roster_ids = [str(row["sample_id"]) for row in roster]
    if len(roster_ids) != len(set(roster_ids)):
        raise ContractError("cache roster sample IDs must be unique")
    if any(
        row.get("clinician_label") is not None
        and str(row.get("clinician_label", "")).strip()
        for row in roster
    ):
        raise ContractError("pre-freeze cache roster contains clinician outcomes")
    if any("human_label" in row for row in roster):
        raise ContractError("pre-freeze cache roster contains human labels")
    silver = {str(row["sample_id"]): row for row in silver_rows}
    if not set(roster_ids).issubset(silver):
        raise ContractError("cache roster is not contained in Silver")
    fields = (
        "sample_id",
        "source",
        "finding",
        "prior_image_path",
        "current_image_path",
    )
    output = [
        {
            **{field: silver[sample_id][field] for field in fields},
            "split": "gold_cache",
        }
        for sample_id in roster_ids
    ]
    audit = {
        "schema": "prta-cxr.outcome-free-roster-cache.v1",
        "status": "PASS_OUTCOME_FREE_ROSTER_CACHE_INPUT",
        "rows": len(output),
        "fields": sorted(output[0]),
        "sample_ids_sha256": canonical_sha256(sorted(roster_ids)),
        "manifest_sha256": canonical_sha256(output),
        "contains_human_outcomes": False,
        "contains_luna_labels": False,
        "contains_patient_identifiers": False,
    }
    return output, audit


def seal_split_surfaces(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, str]],
    dict[str, Any],
]:
    if not rows:
        raise ContractError("cannot seal an empty split manifest")
    train_dev: list[dict[str, Any]] = []
    internal_test: list[dict[str, Any]] = []
    cache_input: list[dict[str, str]] = []
    ids: set[str] = set()
    for raw in rows:
        row = dict(raw)
        sample_id = str(row.get("sample_id", "")).strip()
        split = str(row.get("split", "")).strip()
        if not sample_id or sample_id in ids:
            raise ContractError("split sealing requires unique sample IDs")
        ids.add(sample_id)
        if split in {"train", "dev"}:
            train_dev.append(row)
        elif split == "internal_test":
            internal_test.append(row)
        else:
            raise ContractError(f"unknown split while sealing: {split}")
        missing = set(CACHE_INPUT_FIELDS) - set(row)
        if missing:
            raise ContractError(f"cache input fields missing: {sorted(missing)}")
        cache_input.append(
            {field: str(row[field]) for field in CACHE_INPUT_FIELDS}
        )
    if not train_dev or not internal_test:
        raise ContractError("split sealing produced an empty protected surface")
    if any(SEALED_OUTCOME_FIELDS & set(row) for row in cache_input):
        raise ContractError("outcome-free cache input contains a sealed field")
    if len(train_dev) + len(internal_test) != len(rows):
        raise ContractError("split sealing row conservation failed")
    audit = {
        "schema": "prta-cxr.split-surface-seal.v1",
        "status": "PASS_SPLIT_SURFACES_SEALED",
        "source_rows": len(rows),
        "train_dev_rows": len(train_dev),
        "internal_test_rows": len(internal_test),
        "cache_input_rows": len(cache_input),
        "split_counts": dict(sorted(Counter(row["split"] for row in rows).items())),
        "cache_input_fields": list(CACHE_INPUT_FIELDS),
        "cache_input_forbidden_fields": sorted(SEALED_OUTCOME_FIELDS),
        "cache_input_contains_outcomes": False,
        "sample_ids_conserved": len(ids) == len(rows),
        "source_manifest_sha256": canonical_sha256(list(rows)),
        "train_dev_manifest_sha256": canonical_sha256(train_dev),
        "internal_test_manifest_sha256": canonical_sha256(internal_test),
        "cache_input_manifest_sha256": canonical_sha256(cache_input),
        "internal_test_opened_for_development": False,
    }
    return train_dev, internal_test, cache_input, audit
