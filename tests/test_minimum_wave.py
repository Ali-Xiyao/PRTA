from copy import deepcopy

import pytest

from prta_cxr.audit.tracin import AuditContractError
from prta_cxr.minimum_wave import (
    _aligned_rows,
    build_minimum_wave_configs,
    patient_bootstrap_deltas,
)


def _parent(family: str) -> dict:
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "parent",
        "seed": 17,
        "development_axis": "parent",
        "data": {"train_fraction": 1.0},
        "model": {"family": family},
        "optimization": {"epochs": 20},
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.1 if family == "prta" else 0.0,
            "cmcp": 0.1 if family == "prta" else 0.0,
            "inversion": 0.1 if family == "prta" else 0.0,
            "state": 0.1 if family == "prta" else 0.0,
        },
    }


def test_minimum_wave_configs_change_only_authorized_fields():
    prta = _parent("prta")
    b403 = _parent("tila")
    configs = build_minimum_wave_configs(prta_parent=prta, b403_parent=b403)
    assert [row["experiment_id"] for row in configs] == [
        "A508-S17",
        "A509-S17",
        "B403-S28",
        "B403-S43",
    ]
    assert configs[0]["loss_weights"] == {
        **prta["loss_weights"],
        "alignment": 0.0,
    }
    assert configs[1]["loss_weights"] == {
        "classification": 1.0,
        "alignment": 0.0,
        "cmcp": 0.0,
        "inversion": 0.0,
        "state": 0.0,
    }
    assert configs[2]["seed"] == 28
    assert configs[3]["seed"] == 43
    assert prta == _parent("prta")
    assert b403 == _parent("tila")


def _prediction(patient: str, sample: str, target: str, prediction: str) -> dict:
    return {
        "patient_id": patient,
        "observation_id": sample,
        "target": target,
        "prediction": prediction,
        "source": "source",
        "finding": "finding",
    }


def test_patient_bootstrap_is_deterministic_and_detects_positive_delta():
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    prta = []
    b403 = []
    for index in range(25):
        target = labels[index % len(labels)]
        prta.append(_prediction(f"p{index}", f"s{index}", target, target))
        wrong = labels[(index + 1) % len(labels)]
        b403.append(_prediction(f"p{index}", f"s{index}", target, wrong))
    first = patient_bootstrap_deltas(prta, b403, repetitions=200, seed=7)
    second = patient_bootstrap_deltas(prta, b403, repetitions=200, seed=7)
    assert first == second
    assert first["macro_f1"]["ci95_low"] > 0


def test_paired_rows_fail_closed_on_metadata_or_id_drift():
    row = _prediction("p", "s", "Stable", "Stable")
    changed = deepcopy(row)
    changed["patient_id"] = "other"
    with pytest.raises(AuditContractError, match="metadata differs"):
        _aligned_rows([row], [changed])
    changed = deepcopy(row)
    changed["observation_id"] = "other"
    with pytest.raises(AuditContractError, match="IDs differ"):
        _aligned_rows([row], [changed])
