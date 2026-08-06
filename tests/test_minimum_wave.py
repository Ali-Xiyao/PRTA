from copy import deepcopy

import pytest

from prta_cxr.audit.tracin import AuditContractError
from prta_cxr.minimum_wave import (
    _aligned_rows,
    build_minimum_wave_configs,
    build_minimum_wave_decision,
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


def _training_receipt(macro_f1: float, oder: float) -> dict:
    return {
        "status": "PASS_TRAINING_FINISHED",
        "best_epoch": 0,
        "best_dev_macro_f1": macro_f1,
        "history": [
            {
                "epoch": 0,
                "macro_f1": macro_f1,
                "accuracy": 0.6,
                "balanced_accuracy": 0.5,
                "min_class_recall": 0.4,
                "opposite_direction_error_rate": oder,
                "nll": 1.0,
            }
        ],
        "dev_prior_audit": {"true_minus_wrong_prior_gap": 0.1},
        "protected_outcomes_opened": False,
        "internal_test_opened": False,
    }


def test_minimum_wave_decision_stops_route_without_independent_advantage():
    parent = {
        "CLN1-PRTA-S17": _training_receipt(0.528, 0.0075),
        "CLN1-PRTA-S28": _training_receipt(0.530, 0.0055),
        "CLN1-PRTA-S43": _training_receipt(0.528, 0.0055),
        "CLN1-B403-S17": _training_receipt(0.526, 0.0055),
    }
    wave = {
        "A508-S17": _training_receipt(0.525, 0.0060),
        "A509-S17": _training_receipt(0.527, 0.0061),
        "B403-S28": _training_receipt(0.527, 0.0082),
        "B403-S43": _training_receipt(0.521, 0.0060),
    }
    paired = {
        "status": "PASS_MINIMUM_WAVE_PAIRED_DEV_ANALYSIS",
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "true_condition": {"macro_f1_delta": 0.002},
        "patient_bootstrap": {
            "macro_f1": {"ci95_low": -0.008, "ci95_high": 0.013},
            "opposite_direction_error_rate": {
                "ci95_low": 0.0002,
                "ci95_high": 0.0037,
            },
        },
        "prior_interventions": {
            name: {
                "prta": {"macro_f1_drop_from_true": prta_drop},
                "b403": {"macro_f1_drop_from_true": b403_drop},
            }
            for name, prta_drop, b403_drop in (
                ("matched_wrong", 0.177, 0.167),
                ("null", 0.371, 0.305),
                ("reversed", 0.340, 0.337),
            )
        },
    }
    result = build_minimum_wave_decision(
        previous_gate={
            "status": "HOLD_DEVELOPMENT_GATE",
            "seed_macro_f1": [0.528, 0.530, 0.528],
        },
        parent_receipts=parent,
        wave_receipts=wave,
        paired_analysis=paired,
    )
    assert result["decision"] == "STOP_CURRENT_PRTA_ROUTE"
    assert result["checks"]["comparable_performance"] is True
    assert result["checks"]["mechanism_trust_advantage"] is False
    assert result["previous_hold_unchanged"] is True


def test_minimum_wave_decision_rejects_protected_receipt():
    receipt = _training_receipt(0.5, 0.01)
    receipt["protected_outcomes_opened"] = True
    parent = {
        "CLN1-PRTA-S17": receipt,
        "CLN1-PRTA-S28": _training_receipt(0.5, 0.01),
        "CLN1-PRTA-S43": _training_receipt(0.5, 0.01),
        "CLN1-B403-S17": _training_receipt(0.5, 0.01),
    }
    wave = {
        experiment_id: _training_receipt(0.5, 0.01)
        for experiment_id in (
            "A508-S17",
            "A509-S17",
            "B403-S28",
            "B403-S43",
        )
    }
    with pytest.raises(AuditContractError, match="protected outcome opened"):
        build_minimum_wave_decision(
            previous_gate={
                "status": "HOLD_DEVELOPMENT_GATE",
                "seed_macro_f1": [0.5, 0.5, 0.5],
            },
            parent_receipts=parent,
            wave_receipts=wave,
            paired_analysis={},
        )
