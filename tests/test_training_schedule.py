from __future__ import annotations

import pytest
import torch

from prta_cxr.training.engine import (
    _build_learning_rate_scheduler,
    _cosine_warmup_multiplier,
)


def test_constant_schedule_preserves_optimizer_learning_rate() -> None:
    parameter = torch.nn.Parameter(torch.tensor(1.0))
    optimizer = torch.optim.AdamW([parameter], lr=1e-4)

    scheduler, audit = _build_learning_rate_scheduler(
        optimizer,
        {},
        total_steps=100,
    )

    assert scheduler is None
    assert optimizer.param_groups[0]["lr"] == pytest.approx(1e-4)
    assert audit == {
        "name": "constant",
        "total_steps": 100,
        "warmup_ratio": 0.0,
        "warmup_steps": 0,
        "minimum_learning_rate_ratio": 1.0,
    }


def test_cosine_warmup_multiplier_has_frozen_endpoints() -> None:
    values = [
        _cosine_warmup_multiplier(
            step,
            total_steps=100,
            warmup_steps=10,
            minimum_ratio=0.05,
        )
        for step in range(100)
    ]

    assert values[0] == pytest.approx(0.1)
    assert values[9] == pytest.approx(1.0)
    assert values[10] == pytest.approx(1.0)
    assert values[-1] == pytest.approx(0.05)
    assert all(
        left >= right for left, right in zip(values[10:-1], values[11:], strict=True)
    )


def test_cosine_scheduler_round_trips_state() -> None:
    first_parameter = torch.nn.Parameter(torch.tensor(1.0))
    first_optimizer = torch.optim.AdamW([first_parameter], lr=1e-4)
    first_scheduler, audit = _build_learning_rate_scheduler(
        first_optimizer,
        {
            "learning_rate_schedule": "cosine",
            "warmup_ratio": 0.1,
            "minimum_learning_rate_ratio": 0.05,
        },
        total_steps=100,
    )
    assert first_scheduler is not None
    assert audit["warmup_steps"] == 10
    for _ in range(17):
        first_optimizer.step()
        first_scheduler.step()

    second_parameter = torch.nn.Parameter(torch.tensor(1.0))
    second_optimizer = torch.optim.AdamW([second_parameter], lr=1e-4)
    second_scheduler, _ = _build_learning_rate_scheduler(
        second_optimizer,
        {
            "learning_rate_schedule": "cosine",
            "warmup_ratio": 0.1,
            "minimum_learning_rate_ratio": 0.05,
        },
        total_steps=100,
    )
    assert second_scheduler is not None
    second_optimizer.load_state_dict(first_optimizer.state_dict())
    second_scheduler.load_state_dict(first_scheduler.state_dict())

    assert second_scheduler.last_epoch == first_scheduler.last_epoch
    assert second_optimizer.param_groups[0]["lr"] == pytest.approx(
        first_optimizer.param_groups[0]["lr"]
    )


@pytest.mark.parametrize(
    ("optimization", "message"),
    [
        ({"learning_rate_schedule": "linear"}, "constant or cosine"),
        (
            {"learning_rate_schedule": "constant", "warmup_ratio": 0.1},
            "cannot use warmup",
        ),
        (
            {"learning_rate_schedule": "cosine", "warmup_ratio": 1.0},
            "warmup_ratio",
        ),
    ],
)
def test_invalid_schedule_fails_closed(
    optimization: dict[str, float | str],
    message: str,
) -> None:
    parameter = torch.nn.Parameter(torch.tensor(1.0))
    optimizer = torch.optim.AdamW([parameter], lr=1e-4)

    with pytest.raises(ValueError, match=message):
        _build_learning_rate_scheduler(
            optimizer,
            optimization,
            total_steps=100,
        )
