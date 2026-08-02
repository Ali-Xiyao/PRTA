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
    return {
        "nll": float(-np.log(clipped).mean()),
        "brier": float(np.square(values - one_hot).sum(axis=1).mean()),
        "ece": float(ece),
        "ece_bins": bins,
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
    return {
        "aurc": float(np.trapz(risk, coverage)),
        "risk_at_coverage": risk_at,
        "coverage": coverage.tolist(),
        "risk": risk.tolist(),
    }
