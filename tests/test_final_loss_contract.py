import json
from pathlib import Path

import pytest

from prta_cxr.training.engine import load_training_config


def _config() -> dict:
    return {
        "schema": "prta-cxr.training.v1",
        "seed": 17,
        "model": {},
        "optimization": {"epochs": 20},
        "loss_weights": {
            "classification": 1.0,
            "state": 0.025,
            "opposite_direction_cost": 0.05,
            "cmcp": 0.01,
        },
    }


@pytest.mark.parametrize(
    "loss_name",
    [
        "alignment",
        "branch_decorrelation",
        "direction_margin",
        "inversion",
        "prototype_alignment",
    ],
)
def test_nonzero_retired_loss_fails_closed(tmp_path, loss_name: str) -> None:
    value = _config()
    value["loss_weights"][loss_name] = 0.01
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="retired zero-weight losses"):
        load_training_config(path)


def test_frozen_zero_keys_remain_checkpoint_compatible(tmp_path) -> None:
    value = _config()
    value["loss_weights"].update(
        {
            "alignment": 0.0,
            "branch_decorrelation": 0.0,
            "direction_margin": 0.0,
            "inversion": 0.0,
            "prototype_alignment": 0.0,
        }
    )
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert load_training_config(path) == value


def test_retired_two_stage_training_fails_closed(tmp_path) -> None:
    value = _config()
    value["optimization"]["two_stage_training"] = True
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="retired two-stage training"):
        load_training_config(path)


def test_public_final_config_has_only_effective_method_fields() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "configs"
        / "final"
        / "prta_cxr_slim_s1.json"
    )
    value = load_training_config(path)
    components = value["model"]["components"]

    assert components["branch_mode"] == "training_auxiliary_state"
    assert value["model"]["native_head"] == "H0"
    assert components["dual_branch"] is True
    assert components["learned_relation_residual_scale"] is False
    assert "relation_residual_initial_scale" not in components
    assert value["loss_weights"] == {
        "classification": 1.0,
        "state": 0.025,
        "opposite_direction_cost": 0.05,
        "cmcp": 0.01,
    }
