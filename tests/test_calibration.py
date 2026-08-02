import numpy as np
import torch

from prta_cxr.evaluation.calibration import (
    calibration_metrics,
    fit_temperature,
    risk_coverage_metrics,
)


def test_temperature_and_calibration_metrics_are_finite():
    logits = torch.tensor([[4.0, 0.0], [3.0, 0.0], [0.0, 2.0], [2.0, 0.0]])
    targets = torch.tensor([0, 1, 1, 0])
    temperature = fit_temperature(logits, targets)
    probabilities = (logits / temperature).softmax(dim=-1).numpy()
    metrics = calibration_metrics(probabilities, targets.numpy(), bins=5)
    assert 0.05 <= temperature <= 20.0
    assert metrics["nll"] >= 0
    assert metrics["brier"] >= 0
    assert 0 <= metrics["ece"] <= 1


def test_risk_coverage_prefers_confident_correct_rows():
    probabilities = np.array(
        [[0.99, 0.01], [0.9, 0.1], [0.4, 0.6], [0.55, 0.45]], dtype=float
    )
    targets = [0, 0, 1, 1]
    result = risk_coverage_metrics(
        probabilities, targets, requested_coverages=(0.5, 1.0)
    )
    assert result["risk_at_coverage"]["0.5"] == 0.0
    assert result["risk_at_coverage"]["1.0"] == 0.25
