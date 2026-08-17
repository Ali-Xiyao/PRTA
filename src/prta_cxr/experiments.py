from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from prta_cxr.contracts import PROGRESSION_LABELS, ContractError, canonical_sha256


def filter_train_dev_sources(
    rows: Sequence[Mapping[str, Any]],
    *,
    train_sources: Sequence[str] | None = None,
    dev_sources: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    available = {str(row.get("source")) for row in rows}
    train_allowed = set(available if train_sources is None else map(str, train_sources))
    dev_allowed = set(available if dev_sources is None else map(str, dev_sources))
    unknown = (train_allowed | dev_allowed) - available
    if unknown:
        raise ContractError(f"source filter names are absent: {sorted(unknown)}")
    selected = [
        dict(row)
        for row in rows
        if (row.get("split") == "train" and str(row.get("source")) in train_allowed)
        or (row.get("split") == "dev" and str(row.get("source")) in dev_allowed)
    ]
    train = [row for row in selected if row.get("split") == "train"]
    dev = [row for row in selected if row.get("split") == "dev"]
    if not train or not dev:
        raise ContractError("source filter must retain non-empty Train and Dev")
    train_patients = {str(row["patient_id_hash"]) for row in train}
    dev_patients = {str(row["patient_id_hash"]) for row in dev}
    if train_patients & dev_patients:
        raise ContractError("source-filtered Train and Dev patients overlap")
    audit = {
        "schema": "prta-cxr.source-filter-audit.v1",
        "train_sources": sorted(train_allowed),
        "dev_sources": sorted(dev_allowed),
        "train_rows": len(train),
        "dev_rows": len(dev),
        "train_sample_sha256": canonical_sha256(
            sorted(str(row["sample_id"]) for row in train)
        ),
        "dev_sample_sha256": canonical_sha256(
            sorted(str(row["sample_id"]) for row in dev)
        ),
        "patient_disjoint": True,
    }
    return selected, audit


def inject_train_label_noise(
    rows: Sequence[Mapping[str, Any]],
    *,
    rate: float,
    family: str,
    salt: str = "prta-cxr-label-noise-v1",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not 0 <= rate < 1:
        raise ContractError("label-noise rate must lie in [0, 1)")
    if family not in {"symmetric", "plausible"}:
        raise ContractError("label-noise family must be symmetric or plausible")
    result = [dict(row) for row in rows]
    train = [row for row in result if row.get("split") == "train"]
    if not train:
        raise ContractError("label-noise input has no Train rows")
    ordered = sorted(
        train,
        key=lambda row: hashlib.sha256(
            f"{salt}|select|{row['sample_id']}".encode()
        ).hexdigest(),
    )
    noise_count = round(len(ordered) * rate)
    selected = {str(row["sample_id"]) for row in ordered[:noise_count]}
    plausible = {
        "Improved": ("Resolved",),
        "Resolved": ("Improved",),
        "Worse": ("New",),
        "New": ("Worse",),
        "Stable": ("Improved", "Worse"),
    }
    changes = []
    for row in result:
        if row.get("split") != "train" or str(row["sample_id"]) not in selected:
            continue
        old = str(row["progression_label"])
        candidates = (
            tuple(label for label in PROGRESSION_LABELS if label != old)
            if family == "symmetric"
            else plausible[old]
        )
        digest = hashlib.sha256(f"{salt}|target|{row['sample_id']}".encode()).digest()
        new = candidates[int.from_bytes(digest[:8], "big") % len(candidates)]
        row["clean_progression_label"] = old
        row["progression_label"] = new
        changes.append((str(row["sample_id"]), old, new))
    audit = {
        "schema": "prta-cxr.train-label-noise-audit.v1",
        "rate": rate,
        "family": family,
        "salt": salt,
        "train_rows": len(train),
        "changed_rows": len(changes),
        "changed_fraction": len(changes) / len(train),
        "change_sha256": canonical_sha256(changes),
        "dev_label_changes": 0,
    }
    return result, audit


def _patient_order(patient_ids: Sequence[str], *, salt: str) -> list[str]:
    return sorted(
        patient_ids,
        key=lambda value: hashlib.sha256(f"{salt}|{value}".encode()).hexdigest(),
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
        row for row in train if str(row["patient_id_hash"]) in selected_patients
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
        str(row["progression_label"]) for row in rows if row.get("split") == "train"
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
    result.setdefault("data", {})["train_fraction"] = float(spec["train_fraction"])
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
