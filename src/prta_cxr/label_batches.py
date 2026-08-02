from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
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


def select_stratified_pilot(
    samples: Sequence[Mapping[str, Any]],
    *,
    pilot_size: int,
    salt: str = "prta-cxr-luna-pilot-v1",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if pilot_size < 1:
        raise ContractError("pilot_size must be positive")
    validated = [validate_sample(row) for row in samples]
    if pilot_size > len(validated):
        raise ContractError("pilot_size exceeds candidate count")
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(
        list
    )
    for row in validated:
        key = (
            row["source"],
            row["finding"],
            row["progression_label"],
            row["interval_basis"],
        )
        groups[key].append(row)

    def rank(value: str) -> str:
        return hashlib.sha256(f"{salt}|{value}".encode()).hexdigest()

    ordered_groups = sorted(groups, key=lambda key: rank("|".join(key)))
    for key in ordered_groups:
        groups[key].sort(key=lambda row: rank(row["sample_id"]))
    offsets = {key: 0 for key in ordered_groups}
    selected = []
    selected_patients: set[str] = set()
    while len(selected) < pilot_size:
        progress = False
        for key in ordered_groups:
            rows = groups[key]
            offset = offsets[key]
            while offset < len(rows):
                row = rows[offset]
                offset += 1
                if row["patient_id_hash"] in selected_patients:
                    continue
                selected.append(row)
                selected_patients.add(row["patient_id_hash"])
                progress = True
                break
            offsets[key] = offset
            if len(selected) == pilot_size:
                break
        if not progress:
            raise ContractError(
                "not enough unique patients to fill the stratified pilot"
            )
    selected.sort(key=lambda row: row["sample_id"])
    audit = {
        "schema": "prta-cxr.stratified-luna-pilot-audit.v1",
        "pilot_size": len(selected),
        "unique_patients": len(selected_patients),
        "available_strata": len(groups),
        "represented_strata": len(
            {
                (
                    row["source"],
                    row["finding"],
                    row["progression_label"],
                    row["interval_basis"],
                )
                for row in selected
            }
        ),
        "sources": dict(sorted(Counter(row["source"] for row in selected).items())),
        "findings": dict(
            sorted(Counter(row["finding"] for row in selected).items())
        ),
        "labels": dict(
            sorted(Counter(row["progression_label"] for row in selected).items())
        ),
        "interval_bases": dict(
            sorted(Counter(row["interval_basis"] for row in selected).items())
        ),
        "salt": salt,
        "pilot_sha256": canonical_sha256(selected),
    }
    return selected, audit


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
        sample_id_map = {
            f"s{batch_index:05d}_{offset:02d}": row["sample_id"]
            for offset, row in enumerate(selected)
        }
        items = []
        for alias, row in zip(sample_id_map, selected, strict=True):
            items.append(
                {
                    "sample_id": alias,
                    "finding": row["finding"],
                    "rule_candidate_label": row["progression_label"],
                    "prior_report": row["prior_report"],
                    "current_report": row["current_report"],
                    "prior_datetime": row["prior_datetime"],
                    "current_datetime": row["current_datetime"],
                    "interval_basis": row["interval_basis"],
                    "calendar_interval_available": row[
                        "calendar_interval_available"
                    ],
                    "interval_semantics": row["interval_semantics"],
                }
            )
        batches.append(
            {
                "schema": "prta-cxr.luna-input-batch.v1",
                "batch_id": f"batch_{batch_index:05d}",
                "prompt_sha256": prompt_hash,
                "output_schema_sha256": schema_hash,
                "items": items,
                "sample_id_map": sample_id_map,
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
