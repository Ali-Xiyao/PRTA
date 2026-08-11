from copy import deepcopy

import pytest

from prta_cxr.repaired_ablation import (
    NEW_VARIANTS,
    build_repaired_ablation_configs,
    cache_entry_block,
)


def _parent() -> dict[str, object]:
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "PARENT",
        "seed": 17,
        "model": {
            "family": "prta",
            "native_head": "H0",
            "adapter_scope": "tail8",
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


def test_repaired_matrix_is_complete_and_parent_is_unchanged():
    parent = _parent()
    original = deepcopy(parent)
    configs = build_repaired_ablation_configs(parent)
    assert parent == original
    assert len(configs) == 33
    assert {(row["ablation_variant"], row["seed"]) for row in configs} == {
        (variant, seed) for seed in (17, 28, 43) for variant in NEW_VARIANTS
    }
    for config in configs:
        model = config["model"]
        components = model["components"]
        assert model["native_head"] == "H4"
        assert components["branch_mode"] == "repaired_dual"
        assert components["bounded_state_anchor"] is True
        assert components["dual_branch"] is True
        assert config["cache_entry_block"] == cache_entry_block(config)


def test_component_and_scope_changes_are_isolated():
    rows = {
        row["ablation_variant"]: row
        for row in build_repaired_ablation_configs(_parent())
        if row["seed"] == 17
    }
    assert rows["no_finding"]["model"]["components"]["finding_conditioning"] is False
    assert (
        rows["no_cross_time_alignment"]["model"]["components"]["cross_time_alignment"]
        is False
    )
    assert rows["no_direction_margin"]["loss_weights"]["direction_margin"] == 0
    assert (
        rows["no_opposite_direction_cost"]["loss_weights"]["opposite_direction_cost"]
        == 0
    )
    assert all(
        value == 0
        for name, value in rows["classification_only"]["loss_weights"].items()
        if name != "classification"
    )
    assert rows["scope_no_tail"]["cache_entry_block"] == 8
    assert rows["scope_tail2"]["cache_entry_block"] == 8
    assert rows["scope_tail4"]["cache_entry_block"] == 8
    assert rows["scope_tail6"]["cache_entry_block"] == 4
    assert rows["scope_tail10"]["cache_entry_block"] == 2


def test_repaired_parent_contract_rejects_drift():
    parent = _parent()
    parent["loss_weights"]["state"] = 0.0
    with pytest.raises(ValueError, match="state weight drift"):
        build_repaired_ablation_configs(parent)
