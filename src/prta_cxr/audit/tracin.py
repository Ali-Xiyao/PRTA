from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset

from prta_cxr.contracts import INVERSION, PROGRESSION_LABELS

EXPECTED_TRAIN_ROWS = 91_065
EXPECTED_DEV_ROWS = 16_666
EXPECTED_PROBES = 300
SEEDS = (17, 29, 43)
PROTECTED_PATTERN = re.compile(
    r"(^|[\\/_. -])(internal[_. -]?test|gold|sealed)([\\/_. -]|$)",
    flags=re.IGNORECASE,
)


class AuditContractError(ValueError):
    """Raised before any audit work when a read-only contract is violated."""


def audit_path(path: Path | str, *, role: str) -> Path:
    """Reject every path whose spelling could address protected outcomes."""

    value = Path(path).expanduser().resolve()
    if PROTECTED_PATTERN.search(str(value)):
        raise AuditContractError(f"protected outcome path rejected for {role}")
    return value


def assert_private_output(output: Path, repo_root: Path) -> None:
    output = audit_path(output, role="output")
    repo_root = Path(repo_root).resolve()
    try:
        output.relative_to(repo_root)
    except ValueError:
        return
    raise AuditContractError("private audit output must be outside the Git repository")


def validate_open_manifest(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_train: int = EXPECTED_TRAIN_ROWS,
    expected_dev: int = EXPECTED_DEV_ROWS,
) -> dict[str, Any]:
    """Validate the only legal manifest surface: exact, unique Train and Dev."""

    if not rows:
        raise AuditContractError("open manifest is empty")
    split_counts = Counter(str(row.get("split", "")) for row in rows)
    if set(split_counts) != {"train", "dev"}:
        raise AuditContractError("audit manifest must contain only train and dev")
    if split_counts["train"] != expected_train:
        raise AuditContractError(
            "train row conservation failed: "
            f"{split_counts['train']} != {expected_train}"
        )
    if split_counts["dev"] != expected_dev:
        raise AuditContractError(
            f"dev row conservation failed: {split_counts['dev']} != {expected_dev}"
        )
    required = {
        "sample_id",
        "patient_id_hash",
        "split",
        "source",
        "finding",
        "progression_label",
        "prior_study_id",
        "current_study_id",
        "prior_image_path",
        "current_image_path",
        "prior_report",
        "current_report",
    }
    sample_ids: set[str] = set()
    for index, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            raise AuditContractError(
                f"open manifest row {index} fields missing: {sorted(missing)}"
            )
        sample_id = str(row["sample_id"])
        if not sample_id or sample_id in sample_ids:
            raise AuditContractError("open manifest sample IDs must be unique")
        sample_ids.add(sample_id)
        if str(row["progression_label"]) not in PROGRESSION_LABELS:
            raise AuditContractError("open manifest contains an unknown label")
    return {
        "train_rows": split_counts["train"],
        "dev_rows": split_counts["dev"],
        "total_rows": len(rows),
        "unique_sample_ids": len(sample_ids),
        "splits": sorted(split_counts),
    }


def rank_percentiles(values: Sequence[float]) -> np.ndarray:
    """Stable ascending percentile ranks in [0, 1], with high values near one."""

    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or not np.isfinite(array).all():
        raise AuditContractError("percentile inputs must be a finite vector")
    if len(array) == 0:
        return np.asarray([], dtype=np.float64)
    if len(array) == 1:
        return np.asarray([1.0], dtype=np.float64)
    order = np.argsort(array, kind="mergesort")
    result = np.empty(len(array), dtype=np.float64)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and array[order[end]] == array[order[start]]:
            end += 1
        average_rank = (start + end - 1) / 2.0
        result[order[start:end]] = average_rank / (len(array) - 1)
        start = end
    return result


def grouped_percentiles(
    rows: Sequence[Mapping[str, Any]], value_key: str
) -> np.ndarray:
    result = np.empty(len(rows), dtype=np.float64)
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[(str(row["source"]), str(row["progression_label"]))].append(index)
    for indices in groups.values():
        values = [float(rows[index][value_key]) for index in indices]
        result[indices] = rank_percentiles(values)
    return result


def opposite_direction_error(target: str, prediction: str) -> bool:
    return target != prediction and INVERSION.get(target) == prediction


def add_prediction_summary(
    rows: list[dict[str, Any]], seed_predictions: Mapping[int, Mapping[str, np.ndarray]]
) -> None:
    """Attach three-seed predictions without changing row ordering."""

    expected = len(rows)
    for seed in SEEDS:
        values = seed_predictions[seed]
        for name in ("prediction", "confidence", "nll"):
            if len(values[name]) != expected:
                raise AuditContractError(f"seed {seed} {name} mapping is misaligned")
    for index, row in enumerate(rows):
        target = str(row["progression_label"])
        predictions: list[str] = []
        nlls: list[float] = []
        for seed in SEEDS:
            values = seed_predictions[seed]
            predicted = str(values["prediction"][index])
            confidence = float(values["confidence"][index])
            nll = float(values["nll"][index])
            if not math.isfinite(confidence) or not math.isfinite(nll):
                raise AuditContractError("prediction summary contains NaN or infinity")
            row[f"seed{seed}_prediction"] = predicted
            row[f"seed{seed}_confidence"] = confidence
            row[f"seed{seed}_nll"] = nll
            row[f"seed{seed}_wrong"] = int(predicted != target)
            row[f"seed{seed}_opposite_direction_error"] = int(
                opposite_direction_error(target, predicted)
            )
            predictions.append(predicted)
            nlls.append(nll)
        row["wrong_seed_count"] = sum(value != target for value in predictions)
        row["opposite_direction_error_seed_count"] = sum(
            opposite_direction_error(target, value) for value in predictions
        )
        row["seed_disagreement"] = len(set(predictions)) - 1
        row["mean_nll"] = float(np.mean(nlls))


def select_dev_probes(
    rows: Sequence[Mapping[str, Any]], *, per_stratum: int = 30
) -> list[int]:
    """Select exactly 30 errors per source x label, deterministically."""

    selected: list[int] = []
    sources = sorted({str(row["source"]) for row in rows})
    if len(sources) != 2:
        raise AuditContractError("probe selection requires exactly two sources")
    for source in sources:
        for label in PROGRESSION_LABELS:
            candidates = [
                index
                for index, row in enumerate(rows)
                if str(row["source"]) == source
                and str(row["progression_label"]) == label
                and int(row["wrong_seed_count"]) >= 1
            ]
            if len(candidates) < per_stratum:
                raise AuditContractError(
                    f"insufficient Dev errors for probe stratum {source}/{label}: "
                    f"{len(candidates)} < {per_stratum}"
                )
            candidates.sort(
                key=lambda index: (
                    -int(rows[index]["opposite_direction_error_seed_count"]),
                    -int(rows[index]["wrong_seed_count"] >= 2),
                    -float(rows[index]["mean_nll"]),
                    -int(rows[index]["seed_disagreement"]),
                    str(rows[index]["sample_id"]),
                )
            )
            selected.extend(candidates[:per_stratum])
    expected = len(sources) * len(PROGRESSION_LABELS) * per_stratum
    if len(selected) != expected or len(set(selected)) != expected:
        raise AuditContractError("probe selection count or uniqueness failed")
    return selected


def structural_reasons(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if str(row.get("prior_study_id", "")) == str(row.get("current_study_id", "")):
        reasons.append("SAME_STUDY_ID")
    if str(row.get("prior_image_path", "")) == str(row.get("current_image_path", "")):
        reasons.append("SAME_IMAGE_PATH")
    if bool(row.get("calendar_interval_available", False)):
        try:
            interval = float(row.get("interval_days"))
            if not math.isfinite(interval) or interval <= 0:
                reasons.append("NONPOSITIVE_CALENDAR_INTERVAL")
        except (TypeError, ValueError):
            reasons.append("INVALID_CALENDAR_INTERVAL")
    before = row.get("prior_datetime")
    after = row.get("current_datetime")
    if before and after:
        try:
            if datetime.fromisoformat(str(before)) >= datetime.fromisoformat(
                str(after)
            ):
                reasons.append("NONINCREASING_DATETIME")
        except ValueError:
            reasons.append("UNPARSEABLE_DATETIME")
    for field in ("prior_report", "current_report"):
        if not str(row.get(field, "")).strip():
            reasons.append(f"EMPTY_{field.upper()}")
    return reasons


def tier_dev_rows(rows: list[dict[str, Any]]) -> None:
    nll_percentiles = grouped_percentiles(rows, "mean_nll")
    for index, row in enumerate(rows):
        reasons = structural_reasons(row)
        high_loss = nll_percentiles[index] >= 0.95
        unstable = int(row["seed_disagreement"]) >= 2
        repeated_error = int(row["wrong_seed_count"]) >= 2
        if high_loss:
            reasons.append("DEV_MEAN_NLL_TOP5_PERCENT")
        if unstable:
            reasons.append("THREE_SEED_PREDICTION_DISAGREEMENT")
        if repeated_error:
            reasons.append("MISCLASSIFIED_BY_AT_LEAST_TWO_SEEDS")
        row["mean_nll_percentile_within_source_label"] = float(nll_percentiles[index])
        row["risk_tier"] = "Tier C" if reasons else "Context"
        row["selection_reasons"] = reasons


def tier_train_rows(rows: list[dict[str, Any]]) -> None:
    """Apply preregistered seed-stability tiers to every Train row in place."""

    for seed in SEEDS:
        for key in ("negative_influence_magnitude", "self_influence"):
            column = f"seed{seed}_{key}"
            percentiles = grouped_percentiles(rows, column)
            for index, row in enumerate(rows):
                row[f"{column}_percentile_within_source_label"] = float(
                    percentiles[index]
                )
    nll_percentiles = grouped_percentiles(rows, "mean_nll")
    for index, row in enumerate(rows):
        negative_percentiles = [
            float(
                row[
                    f"seed{seed}_negative_influence_magnitude_"
                    "percentile_within_source_label"
                ]
            )
            for seed in SEEDS
        ]
        self_percentiles = [
            float(row[f"seed{seed}_self_influence_percentile_within_source_label"])
            for seed in SEEDS
        ]
        adapter_percentiles = [
            float(row[f"seed{seed}_adapter_negative_percentile_within_source_label"])
            for seed in SEEDS
        ]
        negative_hits = sum(value >= 0.95 for value in negative_percentiles)
        self_top10 = sum(value >= 0.90 for value in self_percentiles)
        self_top5 = sum(value >= 0.95 for value in self_percentiles)
        reasons = structural_reasons(row)
        repeated_error = int(row["wrong_seed_count"]) >= 2
        high_loss = nll_percentiles[index] >= 0.95
        high_disagreement = int(row["seed_disagreement"]) >= 2
        adapter_unstable = bool(row.get("adapter_confirmation_unstable", False))
        if negative_hits >= 2 and (self_top10 >= 1 or repeated_error):
            tier = "Tier A"
            reasons.append("NEGATIVE_INFLUENCE_TOP5_IN_AT_LEAST_TWO_SEEDS")
            if self_top10:
                reasons.append("SELF_INFLUENCE_TOP10")
            if repeated_error:
                reasons.append("MISCLASSIFIED_BY_AT_LEAST_TWO_SEEDS")
        elif negative_hits >= 2 or self_top5 >= 2:
            tier = "Tier B"
            if negative_hits >= 2:
                reasons.append("NEGATIVE_INFLUENCE_TOP5_IN_AT_LEAST_TWO_SEEDS")
            if self_top5 >= 2:
                reasons.append("SELF_INFLUENCE_TOP5_IN_AT_LEAST_TWO_SEEDS")
        elif reasons or high_loss or high_disagreement or adapter_unstable:
            tier = "Tier C"
            if high_loss:
                reasons.append("MEAN_NLL_TOP5_PERCENT")
            if high_disagreement:
                reasons.append("THREE_SEED_PREDICTION_DISAGREEMENT")
            if adapter_unstable:
                reasons.append("UNSTABLE_INFLUENCE")
        else:
            tier = "Context"
        row["negative_influence_seed_hits_top5"] = negative_hits
        row["self_influence_seed_hits_top10"] = self_top10
        row["self_influence_seed_hits_top5"] = self_top5
        row["negative_influence_median_percentile_three_seed"] = float(
            np.median(negative_percentiles)
        )
        row["negative_influence_percentile_range_three_seed"] = float(
            np.ptp(negative_percentiles)
        )
        row["self_influence_median_percentile_three_seed"] = float(
            np.median(self_percentiles)
        )
        row["self_influence_percentile_range_three_seed"] = float(
            np.ptp(self_percentiles)
        )
        row["adapter_negative_median_percentile_three_seed"] = float(
            np.median(adapter_percentiles)
        )
        row["adapter_negative_percentile_range_three_seed"] = float(
            np.ptp(adapter_percentiles)
        )
        row["mean_nll_percentile_within_source_label"] = float(nll_percentiles[index])
        row["risk_tier"] = tier
        row["selection_reasons"] = sorted(set(reasons))


class CaptumClassificationLoss(nn.Module):
    """The frozen checkpoint's classification loss with Captum sum reduction."""

    reduction = "sum"

    def __init__(self, spec: Mapping[str, Any]) -> None:
        super().__init__()
        self.spec = dict(spec)

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        name = str(self.spec.get("name", "cross_entropy"))
        counts = torch.as_tensor(
            self.spec.get("class_counts", ()),
            dtype=logits.dtype,
            device=logits.device,
        )
        if name == "cross_entropy":
            return F.cross_entropy(logits, target, reduction="sum")
        if counts.shape != (len(PROGRESSION_LABELS),):
            raise AuditContractError("checkpoint loss lacks five class counts")
        if name == "weighted_ce":
            weights = counts.sum() / (len(PROGRESSION_LABELS) * counts)
            return F.cross_entropy(logits, target, weight=weights, reduction="sum")
        if name == "balanced_softmax":
            return F.cross_entropy(
                logits + counts.log().unsqueeze(0), target, reduction="sum"
            )
        if name != "class_balanced_focal":
            raise AuditContractError(f"unsupported audit loss: {name}")
        beta = float(self.spec.get("beta", 0.9999))
        gamma = float(self.spec.get("gamma", 2.0))
        weights = (1 - beta) / (1 - beta**counts)
        weights = weights / weights.sum() * len(PROGRESSION_LABELS)
        log_probabilities = F.log_softmax(logits, dim=-1)
        probabilities = log_probabilities.exp()
        row = torch.arange(target.shape[0], device=target.device)
        return (
            -weights[target]
            * (1 - probabilities[row, target]).pow(gamma)
            * log_probabilities[row, target]
        ).sum()


class LogitsOnly(nn.Module):
    def __init__(self, model: nn.Module) -> None:
        super().__init__()
        self.model = model
        self.captum_detached_logits = False

    def forward(
        self, prior: torch.Tensor, current: torch.Tensor, finding: torch.Tensor
    ) -> torch.Tensor:
        if self.captum_detached_logits:
            with torch.no_grad():
                logits = self.model(prior, current, finding)[1]
            return logits.detach().requires_grad_(True)
        return self.model(prior, current, finding)[1]


class CaptumTupleDataset(Dataset[tuple[torch.Tensor, ...]]):
    def __init__(self, dataset: Dataset[Mapping[str, Any]]) -> None:
        self.dataset = dataset

    def __len__(self) -> int:
        return len(self.dataset)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, ...]:
        row = self.dataset[index]
        return (
            row["prior"],
            row["current"],
            row["finding_text"],
            torch.as_tensor(row["target"], dtype=torch.long),
        )


@dataclass(frozen=True)
class FastInfluenceResult:
    signed: np.ndarray
    positive: np.ndarray
    negative: np.ndarray
    self_influence: np.ndarray


def make_tracincp_fast(
    wrapper: LogitsOnly,
    final_layer: nn.Module,
    dataset: Dataset[tuple[torch.Tensor, ...]],
    loss: nn.Module,
) -> Any:
    """Construct the pinned Captum engine used by the streaming implementation."""

    try:
        from captum.influence import TracInCPFast
    except ImportError as error:  # pragma: no cover - dependency gate
        raise AuditContractError("captum is required for the TracIn audit") from error

    def unused_loader(model: nn.Module, checkpoint: str) -> float:
        del model, checkpoint
        return 1.0

    return TracInCPFast(
        wrapper,
        final_layer,
        dataset,
        ["streamed-by-audit"],
        unused_loader,
        loss,
        batch_size=1,
        vectorize=False,
    )


def captum_fast_embeddings(
    influence: Any,
    batch: tuple[torch.Tensor, ...],
) -> tuple[torch.Tensor, torch.Tensor]:
    """Use Captum's TracInCPFast primitive; kept isolated for version pinning/tests."""

    from captum.influence._core.tracincp_fast_rand_proj import (
        _basic_computation_tracincp_fast,
    )

    return _basic_computation_tracincp_fast(
        influence,
        batch[:-1],
        batch[-1],
        influence.loss_fn,
        influence.reduction_type,
    )


def _compute_streaming_fast_influence_impl(
    influence: Any,
    train_loader: DataLoader,
    probe_loader: DataLoader,
    *,
    learning_rate: float,
    device: torch.device,
    progress: Callable[[str, int, int], None] | None = None,
) -> FastInfluenceResult:
    """One checkpoint contribution, with checkpoint outside the data loop.

    This is algebraically the TracInCPFast last-layer dot product, streamed as
    train-batch x 300-probe blocks so the full pairwise matrix is never retained.
    """

    probe_jacobians: list[torch.Tensor] = []
    probe_inputs: list[torch.Tensor] = []
    for batch_index, batch in enumerate(probe_loader, 1):
        moved = tuple(value.to(device, non_blocking=True) for value in batch)
        jacobian, layer_input = captum_fast_embeddings(influence, moved)
        probe_jacobians.append(jacobian.detach())
        probe_inputs.append(layer_input.detach())
        if progress is not None and (
            batch_index % 10 == 0 or batch_index == len(probe_loader)
        ):
            progress("fast_probe_embeddings", batch_index, len(probe_loader))
    probe_jacobian = torch.cat(probe_jacobians, dim=0)
    probe_input = torch.cat(probe_inputs, dim=0)
    signed_parts: list[np.ndarray] = []
    positive_parts: list[np.ndarray] = []
    negative_parts: list[np.ndarray] = []
    self_parts: list[np.ndarray] = []
    for batch_index, batch in enumerate(train_loader, 1):
        moved = tuple(value.to(device, non_blocking=True) for value in batch)
        train_jacobian, train_input = captum_fast_embeddings(influence, moved)
        pairwise = (
            (train_jacobian @ probe_jacobian.T)
            * (train_input @ probe_input.T)
            * float(learning_rate)
        )
        signed_parts.append(pairwise.sum(dim=1).detach().cpu().numpy())
        positive_parts.append(pairwise.clamp_min(0).sum(dim=1).detach().cpu().numpy())
        negative_parts.append(pairwise.clamp_max(0).sum(dim=1).detach().cpu().numpy())
        self_parts.append(
            (
                train_jacobian.square().sum(dim=1)
                * train_input.square().sum(dim=1)
                * float(learning_rate)
            )
            .detach()
            .cpu()
            .numpy()
        )
        if progress is not None and (
            batch_index % 100 == 0 or batch_index == len(train_loader)
        ):
            progress("fast_train_scores", batch_index, len(train_loader))
    return FastInfluenceResult(
        signed=np.concatenate(signed_parts).astype(np.float64),
        positive=np.concatenate(positive_parts).astype(np.float64),
        negative=np.concatenate(negative_parts).astype(np.float64),
        self_influence=np.concatenate(self_parts).astype(np.float64),
    )


def compute_streaming_fast_influence(
    influence: Any,
    train_loader: DataLoader,
    probe_loader: DataLoader,
    *,
    learning_rate: float,
    device: torch.device,
    progress: Callable[[str, int, int], None] | None = None,
) -> FastInfluenceResult:
    """Run the exact Captum primitive without retaining the frozen-ViT graph."""

    previous = bool(influence.model.captum_detached_logits)
    influence.model.captum_detached_logits = True
    try:
        return _compute_streaming_fast_influence_impl(
            influence,
            train_loader,
            probe_loader,
            learning_rate=learning_rate,
            device=device,
            progress=progress,
        )
    finally:
        influence.model.captum_detached_logits = previous


@torch.no_grad()
def predict_dataset(
    wrapper: LogitsOnly,
    loader: DataLoader,
    *,
    device: torch.device,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, np.ndarray]:
    predictions: list[np.ndarray] = []
    confidences: list[np.ndarray] = []
    nlls: list[np.ndarray] = []
    wrapper.eval()
    for batch_index, batch in enumerate(loader, 1):
        prior, current, finding, target = (
            value.to(device, non_blocking=True) for value in batch
        )
        logits = wrapper(prior, current, finding)
        log_probabilities = logits.log_softmax(dim=-1)
        probabilities = log_probabilities.exp()
        confidence, prediction = probabilities.max(dim=-1)
        row = torch.arange(target.shape[0], device=device)
        predictions.append(prediction.cpu().numpy())
        confidences.append(confidence.cpu().numpy())
        nlls.append((-log_probabilities[row, target]).cpu().numpy())
        if progress is not None and (
            batch_index % 100 == 0 or batch_index == len(loader)
        ):
            progress("prediction", batch_index, len(loader))
    prediction_indices = np.concatenate(predictions)
    return {
        "prediction_index": prediction_indices,
        "prediction": np.asarray(
            [PROGRESSION_LABELS[int(value)] for value in prediction_indices],
            dtype=object,
        ),
        "confidence": np.concatenate(confidences).astype(np.float64),
        "nll": np.concatenate(nlls).astype(np.float64),
    }


def selected_adapter_parameters(wrapper: LogitsOnly) -> dict[str, torch.Tensor]:
    selected = {
        name: parameter
        for name, parameter in wrapper.named_parameters()
        if name.startswith("model.native_head.") or ".tail.adapters." in name
    }
    adapter_groups = {
        name.split(".tail.adapters.", 1)[1].split(".", 1)[0]
        for name in selected
        if ".tail.adapters." in name
    }
    if adapter_groups != {"0", "1", "2", "3"}:
        raise AuditContractError("adapter confirmation requires exactly four adapters")
    if not any(name.startswith("model.native_head.") for name in selected):
        raise AuditContractError("adapter confirmation is missing the native head")
    return selected


def aggregate_probe_gradient(
    wrapper: LogitsOnly,
    probe_loader: DataLoader,
    loss: nn.Module,
    *,
    device: torch.device,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, torch.Tensor]:
    selected = selected_adapter_parameters(wrapper)
    totals = {name: torch.zeros_like(value) for name, value in selected.items()}
    for batch_index, batch in enumerate(probe_loader, 1):
        prior, current, finding, target = (
            value.to(device, non_blocking=True) for value in batch
        )
        logits = wrapper(prior, current, finding)
        gradients = torch.autograd.grad(
            loss(logits, target),
            tuple(selected.values()),
            retain_graph=False,
            create_graph=False,
        )
        for name, gradient in zip(selected, gradients, strict=True):
            totals[name].add_(gradient.detach())
        if progress is not None and (
            batch_index % 10 == 0 or batch_index == len(probe_loader)
        ):
            progress("adapter_probe_gradient", batch_index, len(probe_loader))
    return totals


def adapter_directional_scores(
    wrapper: LogitsOnly,
    loader: DataLoader,
    loss: CaptumClassificationLoss,
    direction: Mapping[str, torch.Tensor],
    *,
    learning_rate: float,
    device: torch.device,
    epsilon: float = 1e-4,
    progress: Callable[[str, int, int], None] | None = None,
) -> np.ndarray:
    """Selected-parameter directional check using symmetric finite differences.

    Captum remains the exact last-layer audit. This confirmation includes the
    classifier and all four adapters. A unit parameter-space direction keeps the
    perturbation bounded; the original direction norm is restored in the score.
    """

    if epsilon <= 0:
        raise AuditContractError("adapter finite-difference epsilon must be positive")
    selected = selected_adapter_parameters(wrapper)
    if set(selected) != set(direction):
        raise AuditContractError("adapter direction parameters are misaligned")
    squared_norm = sum(
        float(value.detach().double().square().sum().item())
        for value in direction.values()
    )
    norm = math.sqrt(squared_norm)
    if not math.isfinite(norm) or norm <= 0:
        raise AuditContractError("adapter direction has zero or invalid norm")
    unit = {name: value / norm for name, value in direction.items()}
    originals = {name: value.detach().clone() for name, value in selected.items()}
    parts: list[np.ndarray] = []
    spec = dict(loss.spec)

    def per_sample_loss(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        name = str(spec.get("name", "cross_entropy"))
        if name == "cross_entropy":
            return F.cross_entropy(logits, target, reduction="none")
        counts = torch.as_tensor(
            spec["class_counts"], dtype=logits.dtype, device=logits.device
        )
        if name == "weighted_ce":
            weights = counts.sum() / (len(PROGRESSION_LABELS) * counts)
            return F.cross_entropy(logits, target, weight=weights, reduction="none")
        if name == "balanced_softmax":
            return F.cross_entropy(
                logits + counts.log().unsqueeze(0), target, reduction="none"
            )
        beta = float(spec.get("beta", 0.9999))
        gamma = float(spec.get("gamma", 2.0))
        weights = (1 - beta) / (1 - beta**counts)
        weights = weights / weights.sum() * len(PROGRESSION_LABELS)
        log_probabilities = F.log_softmax(logits, dim=-1)
        probabilities = log_probabilities.exp()
        row = torch.arange(target.shape[0], device=target.device)
        return (
            -weights[target]
            * (1 - probabilities[row, target]).pow(gamma)
            * log_probabilities[row, target]
        )

    try:
        with torch.no_grad():
            for name, parameter in selected.items():
                parameter.copy_(originals[name] + epsilon * unit[name])
            for batch_index, batch in enumerate(loader, 1):
                prior, current, finding, target = (
                    value.to(device, non_blocking=True) for value in batch
                )
                logits = wrapper(prior, current, finding)
                parts.append(per_sample_loss(logits, target).detach().cpu().numpy())
                if progress is not None and (
                    batch_index % 100 == 0 or batch_index == len(loader)
                ):
                    progress("adapter_plus", batch_index, len(loader))
            plus = np.concatenate(parts).astype(np.float64)
            parts.clear()
            for name, parameter in selected.items():
                parameter.copy_(originals[name] - epsilon * unit[name])
            for batch_index, batch in enumerate(loader, 1):
                prior, current, finding, target = (
                    value.to(device, non_blocking=True) for value in batch
                )
                logits = wrapper(prior, current, finding)
                parts.append(per_sample_loss(logits, target).detach().cpu().numpy())
                if progress is not None and (
                    batch_index % 100 == 0 or batch_index == len(loader)
                ):
                    progress("adapter_minus", batch_index, len(loader))
            minus = np.concatenate(parts).astype(np.float64)
    finally:
        with torch.no_grad():
            for name, parameter in selected.items():
                parameter.copy_(originals[name])
    tangent = (plus - minus) * (norm / (2.0 * epsilon))
    tangent *= float(learning_rate)
    if not np.isfinite(tangent).all():
        raise AuditContractError("adapter finite-difference scores are non-finite")
    return tangent


def top_overlap(
    left: Sequence[float], right: Sequence[float], fraction: float = 0.05
) -> float:
    if len(left) != len(right) or not left:
        raise AuditContractError("overlap inputs must be non-empty and aligned")
    count = max(1, int(math.ceil(len(left) * fraction)))
    left_top = set(np.argsort(np.asarray(left))[-count:].tolist())
    right_top = set(np.argsort(np.asarray(right))[-count:].tolist())
    return len(left_top & right_top) / count


def ensure_finite_columns(
    rows: Iterable[Mapping[str, Any]], keys: Sequence[str]
) -> None:
    for row in rows:
        for key in keys:
            try:
                value = float(row[key])
            except (KeyError, TypeError, ValueError) as error:
                raise AuditContractError(
                    f"missing or invalid numeric field: {key}"
                ) from error
            if not math.isfinite(value):
                raise AuditContractError(f"non-finite numeric field: {key}")
