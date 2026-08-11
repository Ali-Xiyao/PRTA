from copy import deepcopy

import pytest

from prta_cxr.dual_branch_repair import (
    BRANCH_DECORRELATION_WEIGHT,
    build_dual_branch_repair_configs,
    evaluate_dual_branch_gate,
)


def _parent() -> dict[str, object]:
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "PARENT",
        "seed": 17,
        "model": {
            "family": "prta",
            "native_head": "H0",
            "adapter_scope": "tail4",
            "components": {
                "finding_conditioning": True,
                "cross_time_alignment": True,
                "dual_branch": True,
            },
        },
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.0,
            "cmcp": 0.0,
            "inversion": 0.0,
            "direction_margin": 0.01,
            "opposite_direction_cost": 0.05,
            "state": 0.025,
        },
    }


def test_repair_matrix_is_frozen_paired_and_parent_is_unchanged():
    parent = _parent()
    original = deepcopy(parent)
    configs = build_dual_branch_repair_configs(parent)

    assert parent == original
    assert len(configs) == 6
    assert [(row["seed"], row["repair_variant"]) for row in configs] == [
        (17, "transition_only"),
        (17, "repaired_dual"),
        (28, "transition_only"),
        (28, "repaired_dual"),
        (43, "transition_only"),
        (43, "repaired_dual"),
    ]
    for config in configs:
        assert config["model"]["adapter_scope"] == "tail8"
        assert config["loss_weights"]["direction_margin"] == 0.01
        assert config["loss_weights"]["opposite_direction_cost"] == 0.05
        if config["repair_variant"] == "transition_only":
            assert config["model"]["native_head"] == "H0"
            assert config["loss_weights"]["state"] == 0.0
            assert config["loss_weights"]["branch_decorrelation"] == 0.0
        else:
            assert config["model"]["native_head"] == "H4"
            assert config["loss_weights"]["state"] == 0.025
            assert config["loss_weights"]["branch_decorrelation"] == (
                BRANCH_DECORRELATION_WEIGHT
            )


def test_repair_parent_contract_rejects_method_drift():
    parent = _parent()
    parent["model"]["native_head"] = "H1"
    with pytest.raises(ValueError, match="native_head=H0"):
        build_dual_branch_repair_configs(parent)


def _metrics(deltas: tuple[float, float, float]):
    rows = []
    for seed, delta in zip((17, 28, 43), deltas, strict=True):
        rows.append(
            {
                "repair_variant": "transition_only",
                "seed": seed,
                "macro_f1": 0.55,
            }
        )
        rows.append(
            {
                "repair_variant": "repaired_dual",
                "seed": seed,
                "macro_f1": 0.55 + delta,
            }
        )
    return rows


def test_repair_gate_requires_practical_mean_and_two_seed_wins():
    passed = evaluate_dual_branch_gate(_metrics((0.004, 0.003, -0.001)))
    assert passed["status"] == "PASS_DUAL_BRANCH_REPAIR_CONTRIBUTES"
    assert passed["selection_performed"] is False
    assert passed["repaired_seed_wins"] == 2

    small = evaluate_dual_branch_gate(_metrics((0.001, 0.001, 0.001)))
    assert small["status"] == "HOLD_DUAL_BRANCH_REPAIR_NO_STABLE_CONTRIBUTION"

    unstable = evaluate_dual_branch_gate(_metrics((0.008, -0.001, -0.001)))
    assert unstable["status"] == "HOLD_DUAL_BRANCH_REPAIR_NO_STABLE_CONTRIBUTION"


def test_repair_gate_rejects_incomplete_rows():
    with pytest.raises(ValueError, match="incomplete"):
        evaluate_dual_branch_gate(_metrics((0.004, 0.003, -0.001))[:-1])
