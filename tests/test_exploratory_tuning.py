import json

import pytest

from prta_cxr.contracts import ContractError
from prta_cxr.exploratory_tuning import (
    build_loss_screen_configs,
    prepare_loss_screen,
)


def _parent():
    return {
        "schema": "prta-cxr.training.v1",
        "seed": 17,
        "experiment_id": "A509-S17",
        "development_axis": "minimum_contribution_wave_v1",
        "classification_loss": {
            "name": "class_balanced_focal",
            "beta": 0.9999,
            "gamma": 2.0,
            "class_counts": [10, 9, 8, 7, 6],
        },
        "model": {"family": "prta", "native_head": "H0"},
        "optimization": {"learning_rate": 0.0001},
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.0,
            "cmcp": 0.0,
            "inversion": 0.0,
            "state": 0.0,
        },
    }


def test_loss_screen_changes_only_predeclared_loss_fields():
    parent = _parent()
    configs = build_loss_screen_configs(parent)
    assert [value["experiment_id"] for value in configs] == [
        "TUNE-FG1-S17",
        "TUNE-WCE-S17",
        "TUNE-BS-S17",
        "TUNE-CE-S17",
    ]
    for value in configs:
        assert value["model"] == parent["model"]
        assert value["optimization"] == parent["optimization"]
        assert value["loss_weights"] == parent["loss_weights"]


def test_prepare_loss_screen_binds_route_stop_and_case_study(tmp_path):
    parent = tmp_path / "parent.json"
    decision = tmp_path / "decision.json"
    case = tmp_path / "case.json"
    parent.write_text(json.dumps(_parent()), encoding="utf-8")
    decision.write_text(
        json.dumps({"decision": "STOP_CURRENT_PRTA_ROUTE"}), encoding="utf-8"
    )
    case.write_text(
        json.dumps(
            {
                "status": "PASS_EXPLORATORY_DEV_CASE_STUDY",
                "protected_outcome_read_count": 0,
            }
        ),
        encoding="utf-8",
    )
    receipt = prepare_loss_screen(
        parent_config=parent,
        previous_decision=decision,
        case_study_receipt=case,
        output_root=tmp_path / "screen",
    )
    assert receipt["status"] == "PASS_EXPLORATORY_LOSS_SCREEN_PREPARED"
    assert receipt["run_count"] == 4
    assert receipt["training_started"] is False


def test_loss_screen_rejects_non_classification_parent():
    parent = _parent()
    parent["loss_weights"]["alignment"] = 0.1
    with pytest.raises(ContractError, match="classification-only"):
        build_loss_screen_configs(parent)
