from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from prta_cxr.contracts import ContractError, canonical_sha256
from prta_cxr.data.manifests import audit_patient_disjoint_splits


def _tie_hash(salt: str, patient: str) -> str:
    return hashlib.sha256(f"{salt}|{patient}".encode()).hexdigest()


def patient_stratified_split(
    rows: Sequence[Mapping[str, Any]],
    *,
    fractions: Mapping[str, float],
    salt: str = "prta-cxr-full-repartition-v1",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    split_names = tuple(fractions)
    if set(split_names) != {"train", "dev", "internal_test"}:
        raise ContractError("fractions must define train/dev/internal_test")
    weights = np.asarray([float(fractions[name]) for name in split_names])
    if bool((weights <= 0).any()) or not np.isclose(weights.sum(), 1.0):
        raise ContractError("split fractions must be positive and sum to one")
    if not rows:
        raise ContractError("cannot split an empty manifest")

    patient_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        patient = str(row.get("patient_id_hash", "")).strip()
        source = str(row.get("source", "")).strip()
        label = str(row.get("progression_label", "UNLABELED")).strip()
        finding = str(row.get("finding", "UNSPECIFIED")).strip()
        if not patient or not source:
            raise ContractError("split rows require patient_id_hash and source")
        patient_rows[patient].append(row)
        row["_stratum"] = f"{source}|{finding}|{label}"
    if len(patient_rows) < len(split_names):
        raise ContractError("fewer patients than requested splits")

    strata = sorted(
        {
            row["_stratum"]
            for values in patient_rows.values()
            for row in values
        }
    )
    stratum_index = {value: index for index, value in enumerate(strata)}
    patient_vectors = {}
    for patient, values in patient_rows.items():
        vector = np.zeros(len(strata), dtype=np.float64)
        for row in values:
            vector[stratum_index[row["_stratum"]]] += 1.0
        patient_vectors[patient] = vector
    total = sum(patient_vectors.values(), np.zeros(len(strata)))
    target_strata = weights[:, None] * total[None, :]
    target_rows = weights * len(rows)
    target_patients = weights * len(patient_rows)
    current_strata = np.zeros_like(target_strata)
    current_rows = np.zeros(len(split_names), dtype=np.float64)
    current_patients = np.zeros(len(split_names), dtype=np.float64)
    assignment: dict[str, str] = {}
    raw_capacities = weights * len(patient_rows)
    patient_capacities = np.floor(raw_capacities).astype(np.int64)
    remaining = len(patient_rows) - int(patient_capacities.sum())
    remainder_order = sorted(
        range(len(split_names)),
        key=lambda index: (
            -(raw_capacities[index] - patient_capacities[index]),
            index,
        ),
    )
    for index in remainder_order[:remaining]:
        patient_capacities[index] += 1
    if bool((patient_capacities <= 0).any()):
        raise ContractError("split fractions produced an empty patient partition")

    ordered = sorted(
        patient_rows,
        key=lambda patient: (
            -len(patient_rows[patient]),
            -float(patient_vectors[patient].max()),
            _tie_hash(salt, patient),
        ),
    )
    for patient in ordered:
        vector = patient_vectors[patient]
        candidates = []
        for split_index in range(len(split_names)):
            if current_patients[split_index] >= patient_capacities[split_index]:
                continue
            next_strata = current_strata.copy()
            next_rows = current_rows.copy()
            next_patients = current_patients.copy()
            next_strata[split_index] += vector
            next_rows[split_index] += len(patient_rows[patient])
            next_patients[split_index] += 1
            stratum_scale = np.maximum(target_strata, 1.0)
            stratum_cost = float(
                np.square((next_strata - target_strata) / stratum_scale).sum()
            )
            row_cost = float(
                np.square(
                    (next_rows - target_rows) / np.maximum(target_rows, 1.0)
                ).sum()
            )
            patient_cost = float(
                np.square(
                    (next_patients - target_patients)
                    / np.maximum(target_patients, 1.0)
                ).sum()
            )
            candidates.append(
                (
                    stratum_cost + 0.25 * row_cost + 0.05 * patient_cost,
                    split_index,
                )
            )
        if not candidates:
            raise RuntimeError("split patient capacities were exhausted early")
        _, chosen = min(candidates)
        split = split_names[chosen]
        assignment[patient] = split
        current_strata[chosen] += vector
        current_rows[chosen] += len(patient_rows[patient])
        current_patients[chosen] += 1

    output = []
    for patient in sorted(patient_rows):
        for value in patient_rows[patient]:
            value.pop("_stratum")
            value["split"] = assignment[patient]
            output.append(value)
    output.sort(
        key=lambda row: (
            split_names.index(row["split"]),
            row["patient_id_hash"],
            str(row.get("sample_id", row.get("pair_id", ""))),
        )
    )
    leakage = audit_patient_disjoint_splits(output)
    split_summary = {}
    for split in split_names:
        selected = [row for row in output if row["split"] == split]
        split_summary[split] = {
            "rows": len(selected),
            "patients": len({row["patient_id_hash"] for row in selected}),
            "sources": dict(sorted(Counter(row["source"] for row in selected).items())),
            "labels": dict(
                sorted(
                    Counter(
                        str(row.get("progression_label", "UNLABELED"))
                        for row in selected
                    ).items()
                )
            ),
        }
    audit = {
        "schema": "prta-cxr.patient-split-audit.v1",
        "status": "PASS_NEW_PATIENT_DISJOINT_REPARTITION",
        "salt": salt,
        "fractions": dict(fractions),
        "patient_capacities": {
            name: int(patient_capacities[index])
            for index, name in enumerate(split_names)
        },
        "debug_roster_inherited": False,
        "patient_overlap": leakage["patient_overlap"],
        "splits": split_summary,
        "assignment_sha256": canonical_sha256(dict(sorted(assignment.items()))),
        "manifest_sha256": canonical_sha256(output),
    }
    return output, audit
