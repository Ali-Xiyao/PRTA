import pytest

from prta_cxr.prta_v2 import SEEDS, VARIANTS, build_prta_v2_configs


@pytest.fixture
def parent():
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "PARENT",
        "seed": 17,
        "model": {
            "family": "prta",
            "width": 768,
            "adapter_rank": 32,
            "heads": 12,
            "state_tokens": 20,
            "transition_tokens": 20,
            "dropout": 0.1,
            "native_head": "H0",
            "adapter_scope": "tail4",
            "components": {
                "finding_conditioning": True,
                "cross_time_alignment": True,
                "dual_branch": True,
            },
        },
        "optimization": {"epochs": 20},
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.0,
            "state": 0.025,
            "inversion": 0.0,
            "cmcp": 0.0,
        },
    }


def test_prta_v2_builder_freezes_full_three_seed_matrix(parent):
    configs = build_prta_v2_configs(parent)
    assert len(configs) == len(SEEDS) * len(VARIANTS) == 18
    assert {config["seed"] for config in configs} == set(SEEDS)
    assert {config["prta_v2_variant"] for config in configs} == set(VARIANTS)
    assert all(config["model"]["native_head"] == "H0" for config in configs)
    assert all(config["model"]["adapter_scope"] == "tail8" for config in configs)


def test_prta_v2_components_are_strictly_cumulative(parent):
    configs = {
        config["prta_v2_variant"]: config
        for config in build_prta_v2_configs(parent)
        if config["seed"] == 17
    }
    assert configs["V0"]["loss_weights"]["prototype_alignment"] == 0
    assert configs["V1"]["loss_weights"]["prototype_alignment"] == 0.01
    assert configs["V2"]["model"]["components"]["matched_hard_cmcp"]
    assert configs["V3"]["model"]["components"][
        "learned_relation_residual_scale"
    ]
    assert configs["V4"]["model"]["components"]["prior_reliability_gate"]
    assert configs["V5"]["model"]["components"]["selective_state_anchor"]
