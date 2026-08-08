from __future__ import annotations

import math

import pytest

from prta_cxr.training.engine import _build_opposite_direction_cost


def test_opposite_direction_cost_defaults_to_disabled() -> None:
    assert _build_opposite_direction_cost({}) == {
        "name": "disabled",
        "weight": 0.0,
    }


def test_opposite_direction_cost_audit_binds_metric_pairs() -> None:
    assert _build_opposite_direction_cost({"opposite_direction_cost": 0.2}) == {
        "name": "negative_log_complement",
        "weight": 0.2,
        "penalized_pairs": [
            ["Improved", "Worse"],
            ["Worse", "Improved"],
            ["New", "Resolved"],
            ["Resolved", "New"],
        ],
        "reduction": "directional_targets_mean",
    }


@pytest.mark.parametrize("weight", [-0.1, math.inf, math.nan])
def test_opposite_direction_cost_rejects_invalid_weight(weight: float) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        _build_opposite_direction_cost({"opposite_direction_cost": weight})
