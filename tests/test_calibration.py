import numpy as np
import torch

from prta_cxr.evaluation.calibration import (
    binary_detection_metrics,
    calibration_metrics,
    fit_temperature,
    referral_metrics,
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
    assert 0 <= metrics["adaptive_ece"] <= 1
    assert 0 <= metrics["classwise_ece"] <= 1
    assert len(metrics["per_class_ece"]) == 2


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
    assert result["e_aurc"] >= 0


def test_binary_detection_and_referral_reward_ranked_errors():
    uncertainty = [0.9, 0.8, 0.2, 0.1]
    errors = [True, True, False, False]
    detection = binary_detection_metrics(uncertainty, errors)
    assert detection["auroc"] == 1.0
    assert detection["auprc"] == 1.0
    assert detection["fpr_at_80_tpr"] == 0.0
    referral = referral_metrics(uncertainty, errors, referral_fractions=(0.5,))
    assert referral["0.5"]["referred_error_rate"] == 1.0
    assert referral["0.5"]["retained_error_rate"] == 0.0
    assert referral["0.5"]["errors_captured_fraction"] == 1.0


def test_binary_detection_degenerate_labels_return_null_rates():
    result = binary_detection_metrics([0.2, 0.1], [False, False])
    assert result["positives"] == 0
    assert result["auroc"] is None
    assert result["auprc"] is None
    assert result["fpr_at_80_tpr"] is None
