from __future__ import annotations

import pytest
import torch
from torch import nn

from prta_cxr.training.engine import (
    _build_weight_averaging,
    _maybe_update_weight_averaging,
    _weight_averaged_evaluation_model,
)


def _scalar_model(value: float) -> nn.Linear:
    model = nn.Linear(1, 1, bias=False)
    with torch.no_grad():
        model.weight.fill_(value)
    return model


def test_weight_averaging_defaults_to_disabled() -> None:
    averaged_model, audit = _build_weight_averaging(
        _scalar_model(1.0),
        {},
        epochs=4,
    )

    assert averaged_model is None
    assert audit == {"name": "none", "update_interval": "disabled"}


def test_ema_updates_only_after_optimizer_steps() -> None:
    model = _scalar_model(1.0)
    averaged_model, audit = _build_weight_averaging(
        model,
        {"weight_averaging": "ema", "ema_decay": 0.5},
        epochs=4,
    )
    assert averaged_model is not None

    assert not _maybe_update_weight_averaging(
        averaged_model,
        model,
        audit,
        event="epoch",
        epoch=0,
    )
    assert _maybe_update_weight_averaging(
        averaged_model,
        model,
        audit,
        event="optimizer_step",
        epoch=0,
    )
    with torch.no_grad():
        model.weight.fill_(3.0)
    assert _maybe_update_weight_averaging(
        averaged_model,
        model,
        audit,
        event="optimizer_step",
        epoch=0,
    )

    assert averaged_model.n_averaged.item() == 2
    assert averaged_model.module.weight.item() == pytest.approx(2.0)


def test_swa_starts_at_frozen_epoch_and_uses_equal_average() -> None:
    model = _scalar_model(1.0)
    averaged_model, audit = _build_weight_averaging(
        model,
        {"weight_averaging": "swa", "swa_start_ratio": 0.5},
        epochs=4,
    )
    assert averaged_model is not None
    assert audit["start_epoch"] == 2

    assert not _maybe_update_weight_averaging(
        averaged_model,
        model,
        audit,
        event="epoch",
        epoch=1,
    )
    assert _weight_averaged_evaluation_model(model, averaged_model) is model
    assert _maybe_update_weight_averaging(
        averaged_model,
        model,
        audit,
        event="epoch",
        epoch=2,
    )
    assert (
        _weight_averaged_evaluation_model(model, averaged_model)
        is averaged_model.module
    )
    with torch.no_grad():
        model.weight.fill_(3.0)
    assert _maybe_update_weight_averaging(
        averaged_model,
        model,
        audit,
        event="epoch",
        epoch=3,
    )

    assert averaged_model.n_averaged.item() == 2
    assert averaged_model.module.weight.item() == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("optimization", "message"),
    [
        ({"weight_averaging": "ema", "ema_decay": 1.0}, "ema_decay"),
        ({"weight_averaging": "swa", "swa_start_ratio": 1.0}, "swa_start_ratio"),
        ({"weight_averaging": "other"}, "weight_averaging"),
    ],
)
def test_weight_averaging_rejects_invalid_freezes(
    optimization: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _build_weight_averaging(_scalar_model(1.0), optimization, epochs=4)
