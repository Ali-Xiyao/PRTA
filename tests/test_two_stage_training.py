from __future__ import annotations

import pytest
import torch

from prta_cxr.training.engine import (
    _apply_two_stage_epoch_policy,
    _build_two_stage_training,
    _two_stage_checkpoint_improved,
)


def _base_loss_weights() -> dict[str, float]:
    return {
        "classification": 1.0,
        "state": 0.0,
        "alignment": 0.0,
        "direction_margin": 0.1,
    }


def _enabled_audit() -> dict[str, object]:
    return _build_two_stage_training(
        {
            "two_stage_training": True,
            "stage_two_start_ratio": 0.5,
            "stage_two_learning_rate_ratio": 0.1,
            "stage_two_direction_margin_multiplier": 2.0,
            "stage_two_oder_ceiling": 0.00553522006963664,
        },
        _base_loss_weights(),
        epochs=20,
    )


def test_two_stage_training_defaults_to_disabled() -> None:
    assert _build_two_stage_training({}, _base_loss_weights(), epochs=20) == {
        "enabled": False,
        "stage_one_name": "macro_f1",
        "stage_two_name": "disabled",
    }


def test_two_stage_epoch_policy_changes_only_at_frozen_boundary() -> None:
    parameter = torch.nn.Parameter(torch.tensor(1.0))
    optimizer = torch.optim.AdamW([parameter], lr=1e-4)
    audit = _enabled_audit()

    stage_one_weights, stage_one_name = _apply_two_stage_epoch_policy(
        optimizer,
        _base_loss_weights(),
        audit,
        epoch=9,
        base_learning_rate=1e-4,
    )
    assert stage_one_name == "macro_f1"
    assert optimizer.param_groups[0]["lr"] == pytest.approx(1e-4)
    assert stage_one_weights["direction_margin"] == pytest.approx(0.1)

    stage_two_weights, stage_two_name = _apply_two_stage_epoch_policy(
        optimizer,
        _base_loss_weights(),
        audit,
        epoch=10,
        base_learning_rate=1e-4,
    )
    assert stage_two_name == "low_lr_oder_constrained"
    assert optimizer.param_groups[0]["lr"] == pytest.approx(1e-5)
    assert stage_two_weights["direction_margin"] == pytest.approx(0.2)


def test_two_stage_checkpoint_selection_is_fail_closed_on_oder() -> None:
    audit = _enabled_audit()
    high_oder = {"macro_f1": 0.55, "opposite_direction_error_rate": 0.006}
    qualified = {"macro_f1": 0.53, "opposite_direction_error_rate": 0.005}
    better_qualified = {
        "macro_f1": 0.54,
        "opposite_direction_error_rate": 0.0052,
    }

    assert _two_stage_checkpoint_improved(
        high_oder,
        audit,
        epoch=9,
        best_f1=0.54,
        min_delta=0.0,
        qualified_stage_two_best_found=False,
    ) == (True, False)
    assert _two_stage_checkpoint_improved(
        high_oder,
        audit,
        epoch=10,
        best_f1=0.55,
        min_delta=0.0,
        qualified_stage_two_best_found=False,
    ) == (False, False)
    assert _two_stage_checkpoint_improved(
        qualified,
        audit,
        epoch=10,
        best_f1=0.55,
        min_delta=0.0,
        qualified_stage_two_best_found=False,
    ) == (True, True)
    assert _two_stage_checkpoint_improved(
        better_qualified,
        audit,
        epoch=11,
        best_f1=0.53,
        min_delta=0.0,
        qualified_stage_two_best_found=True,
    ) == (True, True)


@pytest.mark.parametrize(
    ("optimization", "loss_weights", "message"),
    [
        ({"two_stage_training": True}, _base_loss_weights(), "oder_ceiling"),
        (
            {
                "two_stage_training": True,
                "learning_rate_schedule": "cosine",
                "stage_two_oder_ceiling": 0.005,
            },
            _base_loss_weights(),
            "constant learning rate",
        ),
        (
            {
                "two_stage_training": True,
                "stage_two_start_ratio": 1.0,
                "stage_two_oder_ceiling": 0.005,
            },
            _base_loss_weights(),
            "stage_two_start_ratio",
        ),
        (
            {
                "two_stage_training": True,
                "stage_two_learning_rate_ratio": 1.0,
                "stage_two_oder_ceiling": 0.005,
            },
            _base_loss_weights(),
            "stage_two_learning_rate_ratio",
        ),
        (
            {
                "two_stage_training": True,
                "stage_two_direction_margin_multiplier": 1.0,
                "stage_two_oder_ceiling": 0.005,
            },
            _base_loss_weights(),
            "direction_margin_multiplier",
        ),
        (
            {"two_stage_training": True, "stage_two_oder_ceiling": 2.0},
            _base_loss_weights(),
            "stage_two_oder_ceiling",
        ),
        (
            {"two_stage_training": True, "stage_two_oder_ceiling": 0.005},
            {**_base_loss_weights(), "direction_margin": 0.0},
            "direction-margin weight",
        ),
    ],
)
def test_two_stage_training_rejects_invalid_freezes(
    optimization: dict[str, object],
    loss_weights: dict[str, float],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _build_two_stage_training(optimization, loss_weights, epochs=20)
