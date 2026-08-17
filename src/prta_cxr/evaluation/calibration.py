from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import torch
from torch.nn import functional as F


def fit_temperature(logits: torch.Tensor, targets: torch.Tensor) -> float:
    if logits.ndim != 2 or targets.shape != (logits.shape[0],):
        raise ValueError("temperature fitting logits/targets do not align")
    if logits.shape[0] < 2 or not torch.isfinite(logits).all():
        raise ValueError("temperature fitting requires finite rows")
    logits = logits.detach().double()
    targets = targets.detach().long()
    log_temperature = torch.zeros((), dtype=torch.float64, requires_grad=True)
    optimizer = torch.optim.LBFGS(
        [log_temperature],
        lr=0.1,
        max_iter=100,
        line_search_fn="strong_wolfe",
    )

    def closure():
        optimizer.zero_grad()
        temperature = log_temperature.exp().clamp(0.05, 20.0)
        loss = F.cross_entropy(logits / temperature, targets)
        loss.backward()
        return loss

    optimizer.step(closure)
    value = float(log_temperature.detach().exp().clamp(0.05, 20.0))
    if not math.isfinite(value):
        raise ValueError("temperature fitting produced a non-finite value")
    return value


def calibration_metrics(
    probabilities: np.ndarray,
    targets: Sequence[int],
    *,
    bins: int = 15,
) -> dict[str, Any]:
    values = np.asarray(probabilities, dtype=np.float64)
    target = np.asarray(targets, dtype=np.int64)
    if values.ndim != 2 or target.shape != (values.shape[0],):
        raise ValueError("calibration probabilities/targets do not align")
    if bins < 2 or not np.isfinite(values).all():
        raise ValueError("calibration inputs must be finite with at least two bins")
    if not np.allclose(values.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("probability rows must sum to one")
    confidence = values.max(axis=1)
    prediction = values.argmax(axis=1)
    correct = prediction == target
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    reliability = []
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        selected = (confidence > lower) & (confidence <= upper)
        if index == 0:
            selected |= confidence == 0.0
        count = int(selected.sum())
        accuracy = float(correct[selected].mean()) if count else None
        mean_confidence = float(confidence[selected].mean()) if count else None
        if count:
            ece += count / len(target) * abs(accuracy - mean_confidence)
        reliability.append(
            {
                "lower": float(lower),
                "upper": float(upper),
                "count": count,
                "accuracy": accuracy,
                "confidence": mean_confidence,
            }
        )
    clipped = np.clip(values[np.arange(len(target)), target], 1e-12, 1.0)
    one_hot = np.eye(values.shape[1], dtype=np.float64)[target]
    adaptive_bins = []
    adaptive_ece = 0.0
    for selected_indices in np.array_split(np.argsort(confidence, kind="stable"), bins):
        count = int(len(selected_indices))
        if not count:
            continue
        accuracy = float(correct[selected_indices].mean())
        mean_confidence = float(confidence[selected_indices].mean())
        adaptive_ece += count / len(target) * abs(accuracy - mean_confidence)
        adaptive_bins.append(
            {
                "count": count,
                "accuracy": accuracy,
                "confidence": mean_confidence,
                "minimum_confidence": float(confidence[selected_indices].min()),
                "maximum_confidence": float(confidence[selected_indices].max()),
            }
        )

    classwise_values = []
    classwise_reliability = []
    for class_index in range(values.shape[1]):
        class_probability = values[:, class_index]
        class_target = target == class_index
        class_ece = 0.0
        class_bins = []
        for index in range(bins):
            lower, upper = edges[index], edges[index + 1]
            selected = (class_probability > lower) & (class_probability <= upper)
            if index == 0:
                selected |= class_probability == 0.0
            count = int(selected.sum())
            frequency = float(class_target[selected].mean()) if count else None
            mean_probability = (
                float(class_probability[selected].mean()) if count else None
            )
            if count:
                class_ece += (
                    count
                    / len(target)
                    * abs(float(frequency) - float(mean_probability))
                )
            class_bins.append(
                {
                    "lower": float(lower),
                    "upper": float(upper),
                    "count": count,
                    "frequency": frequency,
                    "probability": mean_probability,
                }
            )
        classwise_values.append(float(class_ece))
        classwise_reliability.append(
            {"class_index": class_index, "ece": float(class_ece), "bins": class_bins}
        )

    return {
        "nll": float(-np.log(clipped).mean()),
        "brier": float(np.square(values - one_hot).sum(axis=1).mean()),
        "ece": float(ece),
        "ece_bins": bins,
        "adaptive_ece": float(adaptive_ece),
        "adaptive_reliability": adaptive_bins,
        "classwise_ece": float(np.mean(classwise_values)),
        "per_class_ece": classwise_values,
        "classwise_reliability": classwise_reliability,
        "mean_confidence": float(confidence.mean()),
        "reliability": reliability,
    }


def risk_coverage_metrics(
    probabilities: np.ndarray,
    targets: Sequence[int],
    *,
    requested_coverages: Sequence[float] = (0.9, 0.8, 0.7),
) -> dict[str, Any]:
    values = np.asarray(probabilities, dtype=np.float64)
    target = np.asarray(targets, dtype=np.int64)
    if values.ndim != 2 or target.shape != (values.shape[0],):
        raise ValueError("risk-coverage probabilities/targets do not align")
    confidence = values.max(axis=1)
    errors = (values.argmax(axis=1) != target).astype(np.float64)
    order = np.argsort(-confidence, kind="stable")
    ordered_errors = errors[order]
    coverage = np.arange(1, len(target) + 1, dtype=np.float64) / len(target)
    risk = np.cumsum(ordered_errors) / np.arange(1, len(target) + 1)
    risk_at = {}
    for value in requested_coverages:
        if not 0 < value <= 1:
            raise ValueError("requested coverage must lie in (0,1]")
        index = max(0, math.ceil(value * len(target)) - 1)
        risk_at[str(value)] = float(risk[index])
    aurc = float(np.trapz(risk, coverage))
    error_count = int(errors.sum())
    optimal_errors = np.concatenate(
        [
            np.zeros(len(target) - error_count, dtype=np.float64),
            np.ones(error_count, dtype=np.float64),
        ]
    )
    optimal_risk = np.cumsum(optimal_errors) / np.arange(1, len(target) + 1)
    optimal_aurc = float(np.trapz(optimal_risk, coverage))
    return {
        "aurc": aurc,
        "optimal_aurc": optimal_aurc,
        "e_aurc": aurc - optimal_aurc,
        "risk_at_coverage": risk_at,
        "coverage": coverage.tolist(),
        "risk": risk.tolist(),
    }


def binary_detection_metrics(
    scores: Sequence[float], labels: Sequence[bool]
) -> dict[str, float | int | None]:
    """Measure whether a larger score detects a positive/error event."""

    values = np.asarray(scores, dtype=np.float64)
    target = np.asarray(labels, dtype=bool)
    if values.shape != target.shape or values.ndim != 1 or not len(values):
        raise ValueError("detection scores/labels must be non-empty aligned vectors")
    if not np.isfinite(values).all():
        raise ValueError("detection scores must be finite")
    positives = int(target.sum())
    negatives = int((~target).sum())
    if positives == 0 or negatives == 0:
        return {
            "positives": positives,
            "negatives": negatives,
            "auroc": None,
            "auprc": None,
            "fpr_at_80_tpr": None,
        }

    order_ascending = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    offset = 0
    while offset < len(values):
        end = offset + 1
        while (
            end < len(values)
            and values[order_ascending[end]] == values[order_ascending[offset]]
        ):
            end += 1
        ranks[order_ascending[offset:end]] = (offset + 1 + end) / 2.0
        offset = end
    rank_sum = float(ranks[target].sum())
    auroc = (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)

    order = np.argsort(-values, kind="stable")
    ordered_target = target[order].astype(np.int64)
    true_positive = np.cumsum(ordered_target)
    false_positive = np.cumsum(1 - ordered_target)
    precision = true_positive / np.arange(1, len(values) + 1)
    auprc = float(precision[ordered_target == 1].sum() / positives)
    qualifying = np.flatnonzero(true_positive / positives >= 0.8)
    fpr_at_80 = float(false_positive[qualifying[0]] / negatives)
    return {
        "positives": positives,
        "negatives": negatives,
        "auroc": float(auroc),
        "auprc": auprc,
        "fpr_at_80_tpr": fpr_at_80,
    }


def referral_metrics(
    uncertainty: Sequence[float],
    errors: Sequence[bool],
    *,
    referral_fractions: Sequence[float] = (0.05, 0.1, 0.2),
) -> dict[str, Any]:
    """Summarize error concentration when highest-uncertainty rows are referred."""

    values = np.asarray(uncertainty, dtype=np.float64)
    error = np.asarray(errors, dtype=bool)
    if values.shape != error.shape or values.ndim != 1 or not len(values):
        raise ValueError(
            "referral uncertainty/errors must be aligned non-empty vectors"
        )
    if not np.isfinite(values).all():
        raise ValueError("referral uncertainty must be finite")
    order = np.argsort(-values, kind="stable")
    output = {}
    for fraction in referral_fractions:
        if not 0 < fraction < 1:
            raise ValueError("referral fractions must lie in (0,1)")
        referred_count = min(len(values) - 1, max(1, math.ceil(fraction * len(values))))
        referred = order[:referred_count]
        retained = order[referred_count:]
        output[str(fraction)] = {
            "requested_fraction": float(fraction),
            "referred_rows": int(referred_count),
            "realized_fraction": float(referred_count / len(values)),
            "referred_error_rate": float(error[referred].mean()),
            "retained_error_rate": float(error[retained].mean()),
            "errors_captured_fraction": (
                None if not error.any() else float(error[referred].sum() / error.sum())
            ),
        }
    return output
