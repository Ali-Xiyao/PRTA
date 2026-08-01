from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from prta_cxr.contracts import ContractError, canonical_sha256


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ContractError(f"invalid JSONL at line {line_number}") from error
            if not isinstance(value, dict):
                raise ContractError(f"JSONL line {line_number} is not an object")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def audit_patient_disjoint_splits(
    rows: Sequence[Mapping[str, Any]],
    *,
    patient_key: str = "patient_id_hash",
    split_key: str = "split",
) -> dict[str, Any]:
    split_patients: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        patient = str(row.get(patient_key, "")).strip()
        split = str(row.get(split_key, "")).strip()
        if not patient or not split:
            raise ContractError(f"rows require {patient_key} and {split_key}")
        split_patients[split].add(patient)
    overlaps = []
    names = sorted(split_patients)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            shared = sorted(split_patients[left] & split_patients[right])
            if shared:
                overlaps.append(
                    {"left": left, "right": right, "patients": shared}
                )
    if overlaps:
        raise ContractError(f"patient leakage detected: {overlaps}")
    return {
        "status": "PASS_PATIENT_DISJOINT",
        "rows": len(rows),
        "splits": {
            name: len(split_patients[name]) for name in sorted(split_patients)
        },
        "patient_overlap": 0,
        "manifest_sha256": canonical_sha256(list(rows)),
    }


def ensure_unique_ids(
    rows: Sequence[Mapping[str, Any]], *, key: str = "sample_id"
) -> None:
    values = [str(row.get(key, "")).strip() for row in rows]
    if any(not value for value in values):
        raise ContractError(f"all rows require {key}")
    if len(values) != len(set(values)):
        raise ContractError(f"duplicate {key}")
