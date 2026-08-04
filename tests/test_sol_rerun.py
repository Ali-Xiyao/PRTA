from copy import deepcopy

import pytest

from prta_cxr.audit.tracin import AuditContractError, audit_path
from prta_cxr.sol_rerun import build_rerun_configs, compare_gate_results


def _config(family="prta"):
    return {
        "experiment_id": "OLD",
        "seed": 17,
        "development_axis": "old",
        "data": {"train_fraction": 1.0},
        "classification_loss": {"class_counts": [1, 1, 1, 1, 1]},
        "model": {"family": family},
        "optimization": {"epochs": 20},
        "loss_weights": {"classification": 1.0},
    }


def test_rerun_configs_have_new_ids_and_equal_budget():
    prta = _config()
    b402 = _config("siamese_diff")
    b403 = _config("tila")
    original = deepcopy(prta)
    configs = build_rerun_configs(
        prta_parent=prta,
        baseline_parents={"siamese_diff": b402, "tila": b403},
        train_class_counts={
            "Stable": 10,
            "Improved": 20,
            "Worse": 30,
            "New": 40,
            "Resolved": 50,
        },
    )
    assert [value["seed"] for value in configs] == [17, 29, 43, 17, 17]
    assert [value["model"]["family"] for value in configs] == [
        "prta",
        "prta",
        "prta",
        "siamese_diff",
        "tila",
    ]
    assert all(value["optimization"] == {"epochs": 20} for value in configs)
    assert configs[0]["classification_loss"]["class_counts"] == [
        10,
        20,
        30,
        40,
        50,
    ]
    assert prta == original


@pytest.mark.parametrize(
    "path", ["private/internal-test.jsonl", "sealed/split.jsonl", "Gold.jsonl"]
)
def test_rerun_path_firewall_rejects_protected_outcomes(path):
    with pytest.raises(AuditContractError):
        audit_path(path, role="test")


def test_gate_comparison_reports_exact_deltas():
    new = {
        "status": "GO_DEVELOPMENT_GATE",
        "mean_macro_f1": 0.53,
        "seed17_gain_vs_strongest_temporal": 0.04,
        "checks": {"a": True, "b": True},
    }
    old = {
        "status": "STOP_DEVELOPMENT_GATE",
        "mean_macro_f1": 0.46,
        "seed17_gain_vs_strongest_temporal": 0.01,
    }
    result = compare_gate_results(new, old)
    assert result["mean_macro_f1_delta"] == pytest.approx(0.07)
    assert result["seed17_gain_delta"] == pytest.approx(0.03)
    assert result["all_frozen_checks_passed"] is True
