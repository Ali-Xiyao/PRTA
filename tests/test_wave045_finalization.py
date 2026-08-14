from __future__ import annotations

import pytest

from prta_cxr.wave045_finalization import (
    Wave045FinalizationError,
    _best_history_metrics,
    _mean_sd,
)


def _metric_row(macro_f1: float) -> dict[str, object]:
    scalars = {
        "accuracy": 0.6,
        "balanced_accuracy": 0.5,
        "macro_f1": macro_f1,
        "min_class_recall": 0.4,
        "opposite_direction_error_rate": 0.01,
        "per_class_f1": {},
        "per_class_recall": {},
        "support": {},
    }
    return {
        "epoch": 2,
        "ordinary": scalars,
        "patient_balanced": scalars,
        "train_loss": 0.4,
    }


def test_mean_sd_uses_sample_standard_deviation() -> None:
    summary = _mean_sd([1.0, 2.0, 3.0])
    assert summary["mean"] == pytest.approx(2.0)
    assert summary["sample_sd"] == pytest.approx(1.0)
    assert summary["count"] == 3


def test_best_history_metrics_uses_only_frozen_best_epoch() -> None:
    receipt = {
        "best_epoch": 2,
        "best_dev_macro_f1": 0.55,
        "history": [_metric_row(0.55), {**_metric_row(0.2), "epoch": 3}],
    }
    metrics = _best_history_metrics(receipt)
    assert metrics["best_epoch"] == 2
    assert metrics["ordinary"]["macro_f1"] == pytest.approx(0.55)


def test_best_history_metrics_rejects_best_value_drift() -> None:
    receipt = {
        "best_epoch": 2,
        "best_dev_macro_f1": 0.6,
        "history": [_metric_row(0.55)],
    }
    with pytest.raises(Wave045FinalizationError, match="best Dev macro-F1"):
        _best_history_metrics(receipt)
