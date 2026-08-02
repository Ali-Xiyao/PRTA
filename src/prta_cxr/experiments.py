from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from prta_cxr.contracts import PROGRESSION_LABELS, ContractError, canonical_sha256


def _patient_order(patient_ids: Sequence[str], *, salt: str) -> list[str]:
    return sorted(
        patient_ids,
        key=lambda value: hashlib.sha256(
            f"{salt}|{value}".encode()
        ).hexdigest(),
    )


def nested_train_fraction(
    rows: Sequence[Mapping[str, Any]],
    *,
    fraction: float,
    salt: str = "prta-cxr-luna-primary-scaling-v1",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not 0 < fraction <= 1:
        raise ContractError("train fraction must lie in (0, 1]")
    train = [dict(row) for row in rows if row.get("split") == "train"]
    dev = [dict(row) for row in rows if row.get("split") == "dev"]
    if not train or not dev:
        raise ContractError("fraction input must contain labeled train and dev rows")
    patients = _patient_order(
        sorted({str(row["patient_id_hash"]) for row in train}), salt=salt
    )
    keep_count = max(1, round(len(patients) * fraction))
    selected_patients = set(patients[:keep_count])
    selected_train = [
        row
        for row in train
        if str(row["patient_id_hash"]) in selected_patients
    ]
    selected = selected_train + dev
    counts = Counter(str(row["progression_label"]) for row in selected_train)
    sources = Counter(str(row["source"]) for row in selected_train)
    if set(counts) != set(PROGRESSION_LABELS):
        raise ContractError("train fraction loses progression-label support")
    audit = {
        "schema": "prta-cxr.train-fraction-audit.v1",
        "fraction": fraction,
        "salt": salt,
        "train_patients": keep_count,
        "total_train_patients": len(patients),
        "train_rows": len(selected_train),
        "dev_rows": len(dev),
        "label_counts": {label: counts[label] for label in PROGRESSION_LABELS},
        "source_counts": dict(sorted(sources.items())),
        "selected_patient_sha256": canonical_sha256(sorted(selected_patients)),
        "selected_train_sample_sha256": canonical_sha256(
            sorted(str(row["sample_id"]) for row in selected_train)
        ),
        "patient_disjoint_from_dev": not selected_patients.intersection(
            str(row["patient_id_hash"]) for row in dev
        ),
    }
    if not audit["patient_disjoint_from_dev"]:
        raise ContractError("selected train patients overlap dev")
    return selected, audit


def materialize_classification_counts(
    config: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result = deepcopy(dict(config))
    counts = Counter(
        str(row["progression_label"])
        for row in rows
        if row.get("split") == "train"
    )
    if set(counts) != set(PROGRESSION_LABELS):
        raise ContractError("training rows do not support all progression labels")
    spec = dict(result.get("classification_loss", {"name": "weighted_ce"}))
    spec["class_counts"] = [counts[label] for label in PROGRESSION_LABELS]
    result["classification_loss"] = spec
    return result


def initial_development_specs() -> list[dict[str, Any]]:
    specs = []
    for experiment_id, fraction in (
        ("D201", 0.10),
        ("D202", 0.25),
        ("D203", 0.50),
        ("D204", 0.75),
        ("D205", 1.00),
    ):
        specs.append(
            {
                "experiment_id": experiment_id,
                "axis": "luna_primary_train_fraction",
                "train_fraction": fraction,
                "native_head": "H0",
                "classification_loss": "weighted_ce",
                "adapter_scope": "tail4",
                "seed": 17,
            }
        )
    for head in ("H1", "H2"):
        specs.append(
            {
                "experiment_id": f"M301-{head}",
                "axis": "native_head",
                "train_fraction": 1.0,
                "native_head": head,
                "classification_loss": "weighted_ce",
                "adapter_scope": "tail4",
                "seed": 17,
            }
        )
    return specs


def config_from_spec(
    base_config: Mapping[str, Any], spec: Mapping[str, Any]
) -> dict[str, Any]:
    result = deepcopy(dict(base_config))
    result["experiment_id"] = str(spec["experiment_id"])
    result["seed"] = int(spec["seed"])
    result.setdefault("data", {})["train_fraction"] = float(
        spec["train_fraction"]
    )
    result["data"]["fraction_salt"] = "prta-cxr-luna-primary-scaling-v1"
    result["model"]["native_head"] = str(spec["native_head"])
    result["model"]["adapter_scope"] = str(spec["adapter_scope"])
    result["classification_loss"] = {
        "name": str(spec["classification_loss"]),
        "beta": 0.9999,
        "gamma": 2.0,
    }
    result["development_axis"] = str(spec["axis"])
    return result
