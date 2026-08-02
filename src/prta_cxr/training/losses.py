from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import torch
from torch.nn import functional as F

from prta_cxr.contracts import PROGRESSION_LABELS

LOSS_NAMES = frozenset(
    {"cross_entropy", "weighted_ce", "balanced_softmax", "class_balanced_focal"}
)


def _class_counts(spec: Mapping[str, Any], logits: torch.Tensor) -> torch.Tensor:
    raw: Sequence[object] = spec.get("class_counts", ())
    if len(raw) != len(PROGRESSION_LABELS):
        raise ValueError("classification loss requires five class counts")
    counts = torch.as_tensor(raw, dtype=logits.dtype, device=logits.device)
    if not torch.isfinite(counts).all() or bool((counts <= 0).any()):
        raise ValueError("classification class counts must be finite and positive")
    return counts


def progression_classification_loss(
    logits: torch.Tensor,
    target: torch.Tensor,
    spec: Mapping[str, Any] | None = None,
) -> torch.Tensor:
    value = dict(spec or {})
    name = str(value.get("name", "cross_entropy"))
    if name not in LOSS_NAMES:
        raise ValueError(f"unsupported classification loss: {name}")
    if name == "cross_entropy":
        return F.cross_entropy(logits, target)
    counts = _class_counts(value, logits)
    if name == "weighted_ce":
        weights = counts.sum() / (len(PROGRESSION_LABELS) * counts)
        return F.cross_entropy(logits, target, weight=weights)
    if name == "balanced_softmax":
        return F.cross_entropy(logits + counts.log().unsqueeze(0), target)
    beta = float(value.get("beta", 0.9999))
    gamma = float(value.get("gamma", 2.0))
    if not 0 <= beta < 1 or gamma < 0:
        raise ValueError("class-balanced focal requires beta in [0,1), gamma >= 0")
    weights = (1 - beta) / (1 - beta**counts)
    weights = weights / weights.sum() * len(PROGRESSION_LABELS)
    log_probabilities = F.log_softmax(logits, dim=-1)
    probabilities = log_probabilities.exp()
    row = torch.arange(target.shape[0], device=target.device)
    target_log_probability = log_probabilities[row, target]
    target_probability = probabilities[row, target]
    return (
        -weights[target]
        * (1 - target_probability).pow(gamma)
        * target_log_probability
    ).mean()
