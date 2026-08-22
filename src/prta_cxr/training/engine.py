from __future__ import annotations

import json
import math
import os
import random
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.optim.swa_utils import AveragedModel, get_ema_multi_avg_fn
from torch.utils.data import DataLoader

from prta_cxr.artifacts import replace_json_atomic, write_json_atomic
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.models.heads import (
    NativeH0Head,
    NativeH1Head,
    NativeH2Head,
    NativeH3StateAnchoredHead,
    NativeH4TransitionPrimaryGatedHead,
)
from prta_cxr.models.prta import (
    FrozenTailWithAdapters,
    PRTATemporalAdapter,
    PRTATrainingHeads,
    cmcp_margin_loss,
    opposite_direction_cost_loss,
    state_preservation_loss,
)
from prta_cxr.training.losses import progression_classification_loss


def _adapter_indices(model: Mapping[str, Any], *, tail_length: int) -> tuple[int, ...]:
    scope = str(model.get("adapter_scope", "tail4"))
    if scope in {"no_tail", "tail0", "none"}:
        if tail_length != 4:
            raise ValueError("no_tail scope requires the Block-8 cache")
        return ()
    if scope == "tail4":
        if tail_length != 4:
            raise ValueError("tail4 scope requires a four-block cached tail")
        return (0, 1, 2, 3)
    if scope in {"tail2", "last2"}:
        if tail_length != 4:
            raise ValueError("tail2 scope requires the Block-8 cache")
        return (2, 3)
    if scope == "tail6":
        if tail_length != 8:
            raise ValueError("tail6 scope requires the Block-4 cache")
        return tuple(range(2, 8))
    if scope == "tail8":
        if tail_length != 8:
            raise ValueError("tail8 scope requires the Block-4 cache")
        return tuple(range(8))
    if scope == "tail10":
        if tail_length != 10:
            raise ValueError("tail10 scope requires the Block-2 cache")
        return tuple(range(10))
    raise ValueError(
        "adapter_scope must be no_tail, tail2, tail4, tail6, tail8, or tail10"
    )


class PRTATrainModel(nn.Module):
    def __init__(
        self,
        frozen_tail: list[nn.Module],
        final_norm: nn.Module,
        config: Mapping[str, Any],
    ) -> None:
        super().__init__()
        self.config = dict(config)
        model = config["model"]
        components = dict(model.get("components", {}))
        width = int(model.get("width", 768))
        self.finding_conditioning = bool(components.get("finding_conditioning", True))
        self.dual_branch = bool(components.get("dual_branch", True))
        self.branch_mode = str(components.get("branch_mode", "legacy"))
        if self.branch_mode not in {
            "legacy",
            "training_auxiliary_state",
            "transition_only",
            "repaired_dual",
        }:
            raise ValueError(
                "model.components.branch_mode must be legacy, "
                "training_auxiliary_state, transition_only, or repaired_dual"
            )
        if self.branch_mode == "transition_only" and self.dual_branch:
            raise ValueError("transition_only branch mode requires dual_branch=false")
        if self.branch_mode == "repaired_dual" and not self.dual_branch:
            raise ValueError("repaired_dual branch mode requires dual_branch=true")
        if self.branch_mode == "training_auxiliary_state" and not self.dual_branch:
            raise ValueError(
                "training_auxiliary_state branch mode requires dual_branch=true"
            )
        self.adapter = PRTATemporalAdapter(
            frozen_tail,
            width=width,
            heads=int(model["heads"]),
            adapter_rank=int(model["adapter_rank"]),
            state_tokens=int(model["state_tokens"]),
            transition_tokens=int(model["transition_tokens"]),
            dropout=float(model.get("dropout", 0.0)),
            frozen_final_norm=final_norm,
            cross_time_alignment=bool(components.get("cross_time_alignment", True)),
            bounded_state_anchor=bool(components.get("bounded_state_anchor", False)),
            state_branch=self.branch_mode != "transition_only",
            adapter_indices=_adapter_indices(model, tail_length=len(frozen_tail)),
            learned_relation_residual_scale=bool(
                components.get("learned_relation_residual_scale", False)
            ),
            relation_residual_initial_scale=float(
                components.get("relation_residual_initial_scale", 1e-3)
            ),
            prior_reliability_gate=bool(
                components.get("prior_reliability_gate", False)
            ),
            unaligned_prior_mode=str(
                components.get("unaligned_prior_mode", "conditioned")
            ),
            temporal_relation_residual=bool(
                components.get("temporal_relation_residual", True)
            ),
        )
        self.training_heads = PRTATrainingHeads(visual_width=width)
        head_name = str(model.get("native_head", "H0"))
        if head_name == "H0":
            self.native_head: nn.Module = NativeH0Head(width)
        elif head_name == "H1":
            self.native_head = NativeH1Head(
                width, dropout=float(model.get("dropout", 0.0))
            )
        elif head_name == "H2":
            self.native_head = NativeH2Head(
                width, dropout=float(model.get("dropout", 0.0))
            )
        elif head_name == "H3":
            self.native_head = NativeH3StateAnchoredHead(
                width, dropout=float(model.get("dropout", 0.0))
            )
        elif head_name == "H4":
            self.native_head = NativeH4TransitionPrimaryGatedHead(
                width, dropout=float(model.get("dropout", 0.0))
            )
        else:
            raise ValueError("native_head must be H0, H1, H2, H3, or H4")
        if self.branch_mode == "transition_only" and head_name != "H0":
            raise ValueError("transition_only branch mode requires native_head=H0")
        if self.branch_mode == "training_auxiliary_state" and head_name != "H0":
            raise ValueError(
                "training_auxiliary_state branch mode requires native_head=H0"
            )
        if self.branch_mode == "repaired_dual":
            if head_name != "H4":
                raise ValueError("repaired_dual branch mode requires native_head=H4")
            if not bool(components.get("bounded_state_anchor", False)):
                raise ValueError(
                    "repaired_dual branch mode requires bounded_state_anchor=true"
                )

    def forward(
        self,
        prior: torch.Tensor,
        current: torch.Tensor,
        finding_text: torch.Tensor,
        *,
        deployment_prune_state: bool = False,
        force_zero_projected_query: bool = False,
    ) -> tuple[Any, torch.Tensor, torch.Tensor]:
        query = self.training_heads.finding_query(finding_text)
        if not self.finding_conditioning or force_zero_projected_query:
            query = torch.zeros_like(query)
        if deployment_prune_state and not isinstance(self.native_head, NativeH0Head):
            raise ValueError("deployment state pruning is valid only for native H0")
        output = self.adapter(
            prior,
            current,
            query,
            deployment_prune_state=deployment_prune_state,
        )
        if self.branch_mode == "legacy" and not self.dual_branch:
            output = replace(
                output,
                state_tokens=output.transition_tokens,
                state_embedding=output.transition_embedding,
            )
        logits = self.native_head(output, query)
        return output, logits, query


class _NativeTemporalBaseline(nn.Module):
    def __init__(
        self,
        frozen_tail: list[nn.Module],
        final_norm: nn.Module,
        config: Mapping[str, Any],
    ) -> None:
        super().__init__()
        self.config = dict(config)
        model = config["model"]
        self.width = int(model.get("width", 768))
        self.tail = FrozenTailWithAdapters(
            frozen_tail,
            width=self.width,
            adapter_rank=int(model["adapter_rank"]),
            dropout=float(model.get("dropout", 0.0)),
            final_norm=final_norm,
            adapter_indices=_adapter_indices(model, tail_length=len(frozen_tail)),
        )
        self.finding_projection = nn.Sequential(
            nn.LayerNorm(512), nn.Linear(512, self.width)
        )

    def _encode(self, value: torch.Tensor) -> torch.Tensor:
        return self.tail(value)


class CurrentOnlyTrainModel(_NativeTemporalBaseline):
    def __init__(self, frozen_tail, final_norm, config) -> None:
        super().__init__(frozen_tail, final_norm, config)
        self.head = nn.Sequential(
            nn.LayerNorm(self.width * 2),
            nn.Linear(self.width * 2, self.width),
            nn.GELU(),
            nn.Linear(self.width, len(PROGRESSION_LABELS)),
        )

    def forward(self, prior, current, finding_text):
        del prior
        query = self.finding_projection(finding_text)
        pooled = self._encode(current).mean(dim=1)
        return None, self.head(torch.cat((pooled, query), dim=-1)), query


class SiameseDiffTrainModel(_NativeTemporalBaseline):
    def __init__(self, frozen_tail, final_norm, config) -> None:
        super().__init__(frozen_tail, final_norm, config)
        self.head = nn.Sequential(
            nn.LayerNorm(self.width * 5),
            nn.Linear(self.width * 5, self.width),
            nn.GELU(),
            nn.Linear(self.width, len(PROGRESSION_LABELS)),
        )

    def forward(self, prior, current, finding_text):
        query = self.finding_projection(finding_text)
        prior_value = self._encode(prior).mean(dim=1)
        current_value = self._encode(current).mean(dim=1)
        signed = current_value - prior_value
        features = torch.cat(
            (current_value, prior_value, signed, signed.abs(), query), dim=-1
        )
        return None, self.head(features), query


class TILATrainModel(_NativeTemporalBaseline):
    def __init__(self, frozen_tail, final_norm, config) -> None:
        super().__init__(frozen_tail, final_norm, config)
        model = config["model"]
        self.attention = nn.MultiheadAttention(
            self.width,
            int(model["heads"]),
            dropout=float(model.get("dropout", 0.0)),
            batch_first=True,
        )
        self.norm = nn.LayerNorm(self.width)
        self.head = nn.Sequential(
            nn.LayerNorm(self.width * 4),
            nn.Linear(self.width * 4, self.width),
            nn.GELU(),
            nn.Linear(self.width, len(PROGRESSION_LABELS)),
        )

    def forward(self, prior, current, finding_text):
        query = self.finding_projection(finding_text)
        prior_value = self._encode(prior)
        current_value = self._encode(current)
        attended, _ = self.attention(
            self.norm(current_value + query.unsqueeze(1)),
            self.norm(prior_value + query.unsqueeze(1)),
            self.norm(prior_value),
            need_weights=False,
        )
        current_pool = current_value.mean(dim=1)
        attended_pool = attended.mean(dim=1)
        features = torch.cat(
            (current_pool, attended_pool, current_pool - attended_pool, query),
            dim=-1,
        )
        return None, self.head(features), query


class EarlyConcatenationTrainModel(_NativeTemporalBaseline):
    """Jointly attend over concatenated prior/current tokens."""

    def __init__(self, frozen_tail, final_norm, config) -> None:
        super().__init__(frozen_tail, final_norm, config)
        model = config["model"]
        self.modality_embedding = nn.Parameter(torch.empty(2, self.width))
        nn.init.normal_(self.modality_embedding, std=0.02)
        self.attention = nn.MultiheadAttention(
            self.width,
            int(model["heads"]),
            dropout=float(model.get("dropout", 0.0)),
            batch_first=True,
        )
        self.norm = nn.LayerNorm(self.width)
        self.head = nn.Sequential(
            nn.LayerNorm(self.width * 2),
            nn.Linear(self.width * 2, self.width),
            nn.GELU(),
            nn.Linear(self.width, len(PROGRESSION_LABELS)),
        )

    def forward(self, prior, current, finding_text):
        query = self.finding_projection(finding_text)
        prior_value = self._encode(prior) + self.modality_embedding[0]
        current_value = self._encode(current) + self.modality_embedding[1]
        tokens = torch.cat((prior_value, current_value), dim=1)
        conditioned = tokens + query.unsqueeze(1)
        attended, _ = self.attention(
            self.norm(conditioned),
            self.norm(conditioned),
            self.norm(tokens),
            need_weights=False,
        )
        pooled = (tokens + attended).mean(dim=1)
        return None, self.head(torch.cat((pooled, query), dim=-1)), query


class SymmetricCrossAttentionTrainModel(_NativeTemporalBaseline):
    """Apply one shared cross-attention module in both temporal directions."""

    def __init__(self, frozen_tail, final_norm, config) -> None:
        super().__init__(frozen_tail, final_norm, config)
        model = config["model"]
        self.attention = nn.MultiheadAttention(
            self.width,
            int(model["heads"]),
            dropout=float(model.get("dropout", 0.0)),
            batch_first=True,
        )
        self.norm = nn.LayerNorm(self.width)
        self.head = nn.Sequential(
            nn.LayerNorm(self.width * 7),
            nn.Linear(self.width * 7, self.width),
            nn.GELU(),
            nn.Linear(self.width, len(PROGRESSION_LABELS)),
        )

    def _cross(self, query, context, condition):
        attended, _ = self.attention(
            self.norm(query + condition.unsqueeze(1)),
            self.norm(context + condition.unsqueeze(1)),
            self.norm(context),
            need_weights=False,
        )
        return attended

    def forward(self, prior, current, finding_text):
        query = self.finding_projection(finding_text)
        prior_value = self._encode(prior)
        current_value = self._encode(current)
        current_from_prior = self._cross(current_value, prior_value, query)
        prior_from_current = self._cross(prior_value, current_value, query)
        current_pool = current_value.mean(dim=1)
        prior_pool = prior_value.mean(dim=1)
        current_cross_pool = current_from_prior.mean(dim=1)
        prior_cross_pool = prior_from_current.mean(dim=1)
        cross_difference = current_cross_pool - prior_cross_pool
        features = torch.cat(
            (
                current_pool,
                prior_pool,
                current_cross_pool,
                prior_cross_pool,
                cross_difference,
                cross_difference.abs(),
                query,
            ),
            dim=-1,
        )
        return None, self.head(features), query


class BioViLTAdaptedTrainModel(_NativeTemporalBaseline):
    """Paper-faithful temporal-token adaptation of BioViL-T for five classes."""

    def __init__(self, frozen_tail, final_norm, config) -> None:
        super().__init__(frozen_tail, final_norm, config)
        model = config["model"]
        self.temporal_position = nn.Parameter(torch.empty(3, self.width))
        nn.init.normal_(self.temporal_position, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=self.width,
            nhead=int(model["heads"]),
            dim_feedforward=self.width * 4,
            dropout=float(model.get("dropout", 0.0)),
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.temporal_pooler = nn.TransformerEncoder(layer, num_layers=2)
        self.head = nn.Sequential(
            nn.LayerNorm(self.width * 4),
            nn.Linear(self.width * 4, self.width),
            nn.GELU(),
            nn.Linear(self.width, len(PROGRESSION_LABELS)),
        )

    def forward(self, prior, current, finding_text):
        query = self.finding_projection(finding_text)
        prior_value = self._encode(prior).mean(dim=1)
        current_value = self._encode(current).mean(dim=1)
        temporal = torch.stack(
            (prior_value, current_value, current_value - prior_value), dim=1
        )
        temporal = self.temporal_pooler(
            temporal + self.temporal_position.unsqueeze(0) + query.unsqueeze(1)
        )
        features = torch.cat(
            (temporal[:, 0], temporal[:, 1], temporal[:, 2], query), dim=-1
        )
        return None, self.head(features), query


class CheXRelNetAdaptedTrainModel(_NativeTemporalBaseline):
    """Relation-network adaptation for finding-conditioned interval change."""

    def __init__(self, frozen_tail, final_norm, config) -> None:
        super().__init__(frozen_tail, final_norm, config)
        dropout = float(config["model"].get("dropout", 0.0))
        self.relation = nn.Sequential(
            nn.LayerNorm(self.width * 6),
            nn.Linear(self.width * 6, self.width * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(self.width * 2, self.width),
            nn.GELU(),
        )
        self.head = nn.Sequential(
            nn.LayerNorm(self.width), nn.Linear(self.width, len(PROGRESSION_LABELS))
        )

    def forward(self, prior, current, finding_text):
        query = self.finding_projection(finding_text)
        prior_value = self._encode(prior).mean(dim=1)
        current_value = self._encode(current).mean(dim=1)
        signed = current_value - prior_value
        features = torch.cat(
            (
                prior_value,
                current_value,
                signed,
                signed.abs(),
                prior_value * current_value,
                query,
            ),
            dim=-1,
        )
        return None, self.head(self.relation(features)), query


def build_train_model(
    frozen_tail: list[nn.Module],
    final_norm: nn.Module,
    config: Mapping[str, Any],
) -> nn.Module:
    family = str(config["model"].get("family", "prta"))
    registry = {
        "prta": PRTATrainModel,
        "current_only": CurrentOnlyTrainModel,
        "siamese_diff": SiameseDiffTrainModel,
        "tila": TILATrainModel,
        "early_concat": EarlyConcatenationTrainModel,
        "symmetric_cross_attention": SymmetricCrossAttentionTrainModel,
        "biovilt_adapted": BioViLTAdaptedTrainModel,
        "chexrelnet_adapted": CheXRelNetAdaptedTrainModel,
    }
    if family not in registry:
        raise ValueError(f"unsupported model family: {family}")
    return registry[family](frozen_tail, final_norm, config)


def load_training_config(path: Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"schema", "seed", "model", "optimization", "loss_weights"}
    missing = required - set(config)
    if missing:
        raise ValueError(f"training config fields missing: {sorted(missing)}")
    if config["schema"] != "prta-cxr.training.v1":
        raise ValueError("unsupported training config schema")
    if int(config["optimization"]["epochs"]) <= 0:
        raise ValueError("epochs must be positive")
    retired_losses = (
        "alignment",
        "branch_decorrelation",
        "direction_margin",
        "inversion",
        "prototype_alignment",
    )
    nonzero_retired = {
        name: float(config["loss_weights"].get(name, 0.0))
        for name in retired_losses
        if float(config["loss_weights"].get(name, 0.0)) != 0.0
    }
    if nonzero_retired:
        raise ValueError(
            "final PRTA-CXR does not support retired zero-weight losses: "
            f"{sorted(nonzero_retired)}"
        )
    if bool(config["optimization"].get("two_stage_training", False)):
        raise ValueError("final PRTA-CXR does not support retired two-stage training")
    return config


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _loss(
    model: nn.Module,
    batch: Mapping[str, Any],
    weights: Mapping[str, float],
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    prior = batch["prior"].to(device)
    current = batch["current"].to(device)
    finding = batch["finding_text"].to(device)
    transition_text = batch["transition_text"].to(device)
    target = batch["target"].to(device)
    output, logits, _ = model(prior, current, finding)
    total = float(weights.get("classification", 1.0)) * progression_classification_loss(
        logits, target, model.config.get("classification_loss")
    )
    direction_cost_weight = float(weights.get("opposite_direction_cost", 0.0))
    if direction_cost_weight:
        total = total + direction_cost_weight * opposite_direction_cost_loss(
            logits,
            target,
        )
    auxiliary_requested = any(
        float(weights.get(name, 0.0))
        for name in ("state", "cmcp")
    )
    if output is None:
        if auxiliary_requested:
            raise ValueError(
                "native baselines require zero PRTA auxiliary-loss weights"
            )
        return total, logits
    projected_text = model.training_heads.transition_text(transition_text)
    components = dict(model.config["model"].get("components", {}))
    state_weights = None
    if bool(components.get("selective_state_anchor", False)):
        if output.change_energy is None:
            raise ValueError("selective state anchor requires change energy")
        beta = float(components.get("selective_state_beta", 1.0))
        if beta <= 0:
            raise ValueError("selective state beta must be positive")
        state_weights = torch.exp(-beta * output.change_energy.detach())
    total = total + float(weights.get("state", 0.0)) * state_preservation_loss(
        output.state_embedding,
        output.frozen_current_embedding,
        sample_weights=state_weights,
    )
    cmcp_weight = float(weights.get("cmcp", 0.0))
    if cmcp_weight:
        matching = str(model.config.get("cmcp", {}).get("matching", "in_batch_roll_v1"))
        offline = matching in {"offline_hard_v1", "offline_random_v1"}
        if offline:
            if "counterfactual_prior" not in batch:
                raise ValueError(f"{matching} CMCP requires counterfactual priors")
            counterfactual_prior = batch["counterfactual_prior"].to(device)
        elif prior.shape[0] > 1:
            counterfactual_prior = prior.roll(1, dims=0)
        else:
            counterfactual_prior = None
        if counterfactual_prior is not None:
            counterfactual, _, _ = model(counterfactual_prior, current, finding)
            cmcp_spec = dict(model.config.get("cmcp", {}))
            total = total + cmcp_weight * cmcp_margin_loss(
                output.transition_embedding,
                counterfactual.transition_embedding,
                projected_text,
                margin=float(cmcp_spec.get("margin", 0.2)),
            )
    return total, logits


@torch.no_grad()
def evaluate_loader(
    model: nn.Module,
    loader: DataLoader,
    *,
    weights: Mapping[str, float],
    device: torch.device,
) -> dict[str, Any]:
    model.eval()
    loss_sum = 0.0
    correct = 0
    count = 0
    metric_rows: list[dict[str, str]] = []
    nll_sum = 0.0
    brier_sum = 0.0
    for batch in loader:
        loss, logits = _loss(model, batch, weights, device)
        prediction = logits.argmax(dim=-1).cpu()
        target = batch["target"].cpu()
        batch_count = target.numel()
        loss_sum += float(loss) * batch_count
        correct += int((prediction == target).sum())
        count += batch_count
        probabilities = logits.softmax(dim=-1).cpu()
        one_hot = F.one_hot(target, num_classes=len(PROGRESSION_LABELS)).float()
        nll_sum += float(F.cross_entropy(logits.cpu(), target, reduction="sum"))
        brier_sum += float(((probabilities - one_hot) ** 2).sum())
        for sample_id, patient, truth, predicted in zip(
            batch["sample_id"],
            batch["patient_id_hash"],
            target.tolist(),
            prediction.tolist(),
            strict=True,
        ):
            metric_rows.append(
                {
                    "patient_id": str(patient),
                    "observation_id": str(sample_id),
                    "target": PROGRESSION_LABELS[int(truth)],
                    "prediction": PROGRESSION_LABELS[int(predicted)],
                }
            )
    metrics = classification_metrics(metric_rows, labels=PROGRESSION_LABELS)
    ordinary = metrics["ordinary"]
    return {
        "loss": loss_sum / count,
        "accuracy": correct / count,
        "macro_f1": ordinary["macro_f1"],
        "balanced_accuracy": ordinary["balanced_accuracy"],
        "min_class_recall": ordinary["min_class_recall"],
        "opposite_direction_error_rate": ordinary["opposite_direction_error_rate"],
        "nll": nll_sum / count,
        "brier": brier_sum / count,
        "patient_balanced": metrics["patient_balanced"],
        "ordinary": ordinary,
        "patients": metrics["patients"],
        "rows": count,
    }


def _save_checkpoint(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        torch.save(dict(value), temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _cosine_warmup_multiplier(
    step: int,
    *,
    total_steps: int,
    warmup_steps: int,
    minimum_ratio: float,
) -> float:
    if total_steps < 1:
        raise ValueError("total scheduler steps must be positive")
    if not 0 <= warmup_steps < total_steps:
        raise ValueError("warmup steps must be in [0, total_steps)")
    if not 0.0 <= minimum_ratio <= 1.0:
        raise ValueError("minimum learning-rate ratio must be in [0, 1]")
    bounded_step = min(max(int(step), 0), total_steps - 1)
    if warmup_steps and bounded_step < warmup_steps:
        return float(bounded_step + 1) / float(warmup_steps)
    decay_steps = total_steps - warmup_steps
    decay_index = bounded_step - warmup_steps
    progress = float(decay_index) / float(max(decay_steps - 1, 1))
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
    return minimum_ratio + (1.0 - minimum_ratio) * cosine


def _build_learning_rate_scheduler(
    optimizer: torch.optim.Optimizer,
    optimization: Mapping[str, Any],
    *,
    total_steps: int,
) -> tuple[torch.optim.lr_scheduler.LambdaLR | None, dict[str, Any]]:
    schedule = str(optimization.get("learning_rate_schedule", "constant"))
    warmup_ratio = float(optimization.get("warmup_ratio", 0.0))
    minimum_ratio = float(optimization.get("minimum_learning_rate_ratio", 0.05))
    if schedule == "constant":
        if warmup_ratio != 0.0:
            raise ValueError("constant learning rate cannot use warmup")
        return None, {
            "name": schedule,
            "total_steps": total_steps,
            "warmup_ratio": 0.0,
            "warmup_steps": 0,
            "minimum_learning_rate_ratio": 1.0,
        }
    if schedule != "cosine":
        raise ValueError("learning_rate_schedule must be constant or cosine")
    if not 0.0 <= warmup_ratio < 1.0:
        raise ValueError("warmup_ratio must be in [0, 1)")
    warmup_steps = int(total_steps * warmup_ratio)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lr_lambda=lambda step: _cosine_warmup_multiplier(
            step,
            total_steps=total_steps,
            warmup_steps=warmup_steps,
            minimum_ratio=minimum_ratio,
        ),
    )
    return scheduler, {
        "name": schedule,
        "total_steps": total_steps,
        "warmup_ratio": warmup_ratio,
        "warmup_steps": warmup_steps,
        "minimum_learning_rate_ratio": minimum_ratio,
    }


def _build_weight_averaging(
    model: nn.Module,
    optimization: Mapping[str, Any],
    *,
    epochs: int,
) -> tuple[AveragedModel | None, dict[str, Any]]:
    mode = str(optimization.get("weight_averaging", "none"))
    if mode == "none":
        return None, {
            "name": mode,
            "update_interval": "disabled",
        }
    if mode == "ema":
        decay = float(optimization.get("ema_decay", 0.999))
        if not 0.0 <= decay < 1.0:
            raise ValueError("ema_decay must be in [0, 1)")
        averaged_model = AveragedModel(
            model,
            multi_avg_fn=get_ema_multi_avg_fn(decay),
            use_buffers=False,
        )
        return averaged_model, {
            "name": mode,
            "decay": decay,
            "update_interval": "optimizer_step",
        }
    if mode == "swa":
        start_ratio = float(optimization.get("swa_start_ratio", 0.5))
        if not 0.0 <= start_ratio < 1.0:
            raise ValueError("swa_start_ratio must be in [0, 1)")
        start_epoch = min(int(epochs * start_ratio), epochs - 1)
        return AveragedModel(model, use_buffers=False), {
            "name": mode,
            "start_ratio": start_ratio,
            "start_epoch": start_epoch,
            "update_interval": "epoch",
        }
    raise ValueError("weight_averaging must be none, ema, or swa")


def _maybe_update_weight_averaging(
    averaged_model: AveragedModel | None,
    model: nn.Module,
    audit: Mapping[str, Any],
    *,
    event: str,
    epoch: int,
) -> bool:
    if averaged_model is None:
        return False
    mode = str(audit["name"])
    should_update = mode == "ema" and event == "optimizer_step"
    should_update = should_update or (
        mode == "swa" and event == "epoch" and epoch >= int(audit["start_epoch"])
    )
    if should_update:
        averaged_model.update_parameters(model)
    return should_update


def _weight_averaged_evaluation_model(
    model: nn.Module,
    averaged_model: AveragedModel | None,
) -> nn.Module:
    if averaged_model is None or int(averaged_model.n_averaged.item()) == 0:
        return model
    return averaged_model.module


def _build_opposite_direction_cost(
    loss_weights: Mapping[str, float],
) -> dict[str, Any]:
    weight = float(loss_weights.get("opposite_direction_cost", 0.0))
    if not math.isfinite(weight) or weight < 0.0:
        raise ValueError(
            "opposite-direction-cost weight must be finite and non-negative"
        )
    if weight == 0.0:
        return {
            "name": "disabled",
            "weight": 0.0,
        }
    return {
        "name": "negative_log_complement",
        "weight": weight,
        "penalized_pairs": [
            ["Improved", "Worse"],
            ["Worse", "Improved"],
            ["New", "Resolved"],
            ["Resolved", "New"],
        ],
        "reduction": "directional_targets_mean",
    }


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    dev_loader: DataLoader,
    *,
    config: Mapping[str, Any],
    output_root: Path,
    device: torch.device,
    input_hashes: Mapping[str, str],
    resume_path: Path | None = None,
    fraction_audit: Mapping[str, Any] | None = None,
    wrong_prior_dev_loader: DataLoader | None = None,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists() and resume_path is None:
        raise FileExistsError(f"refusing to overwrite training output: {output_root}")
    if output_root.exists() and not output_root.is_dir():
        raise FileExistsError(f"training output is not a directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=resume_path is not None)
    seed = int(config["seed"])
    seed_everything(seed)
    model.to(device)
    parameters = [value for value in model.parameters() if value.requires_grad]
    parameter_audit = {
        "total_parameters": sum(value.numel() for value in model.parameters()),
        "trainable_parameters": sum(value.numel() for value in parameters),
    }
    optimizer = torch.optim.AdamW(
        parameters,
        lr=float(config["optimization"]["learning_rate"]),
        weight_decay=float(config["optimization"].get("weight_decay", 0.0)),
    )
    epochs = int(config["optimization"]["epochs"])
    total_optimizer_steps = epochs * len(train_loader)
    scheduler, scheduler_audit = _build_learning_rate_scheduler(
        optimizer,
        config["optimization"],
        total_steps=total_optimizer_steps,
    )
    averaged_model, weight_averaging_audit = _build_weight_averaging(
        model,
        config["optimization"],
        epochs=epochs,
    )
    direction_cost_audit = _build_opposite_direction_cost(config["loss_weights"])
    start_epoch = 0
    best_f1 = -1.0
    best_epoch = -1
    last_improvement_epoch = -1
    history: list[dict[str, Any]] = []
    if resume_path is not None:
        if Path(resume_path).resolve().parent != output_root.resolve():
            raise ValueError("resume checkpoint must belong to the output directory")
        checkpoint = torch.load(resume_path, map_location="cpu", weights_only=True)
        if checkpoint.get("config") != dict(config):
            raise ValueError("resume checkpoint config mismatch")
        if checkpoint.get("input_hashes") != dict(input_hashes):
            raise ValueError("resume checkpoint input hash mismatch")
        model.load_state_dict(
            checkpoint.get("training_model_state", checkpoint["model_state"])
        )
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        checkpoint_scheduler = checkpoint.get("scheduler_state")
        if scheduler is not None:
            if checkpoint_scheduler is None:
                raise ValueError("resume checkpoint scheduler state missing")
            scheduler.load_state_dict(checkpoint_scheduler)
        elif checkpoint_scheduler is not None:
            raise ValueError("resume checkpoint has unexpected scheduler state")
        checkpoint_averaging_updates = checkpoint.get("weight_averaging_updates")
        if averaged_model is not None:
            if checkpoint_averaging_updates is None:
                raise ValueError("resume checkpoint weight-averaging state missing")
            averaged_model.module.load_state_dict(checkpoint["model_state"])
            averaged_model.n_averaged.fill_(int(checkpoint_averaging_updates))
        elif checkpoint_averaging_updates is not None:
            raise ValueError("resume checkpoint has unexpected weight-averaging state")
        start_epoch = int(checkpoint["epoch"]) + 1
        best_f1 = float(checkpoint["best_dev_macro_f1"])
        best_epoch = int(checkpoint.get("best_epoch", checkpoint["epoch"]))
        last_improvement_epoch = int(
            checkpoint.get("last_improvement_epoch", best_epoch)
        )
        history = list(checkpoint.get("history", []))
    optimizer_steps = start_epoch * len(train_loader)
    patience = int(config["optimization"].get("early_stopping_patience", epochs))
    min_epochs = int(config["optimization"].get("minimum_epochs", 1))
    min_delta = float(config["optimization"].get("early_stopping_min_delta", 0.0))
    if patience < 1 or not 1 <= min_epochs <= epochs or min_delta < 0:
        raise ValueError("invalid early-stopping configuration")
    started = datetime.now(UTC).isoformat()
    state = {
        "schema": "prta-cxr.training-progress.v1",
        "status": "RUNNING",
        "pid": os.getpid(),
        "experiment_id": str(config.get("experiment_id", "")),
        "start_time": started,
        "current_epoch": start_epoch,
        "total_epochs": epochs,
        "completed_steps_in_epoch": 0,
        "steps_in_epoch": len(train_loader),
        "best_dev_macro_f1": best_f1,
        "best_epoch": best_epoch,
        "input_hashes": dict(input_hashes),
        "config_sha256": canonical_sha256(config),
        "learning_rate_schedule": scheduler_audit,
        "weight_averaging": weight_averaging_audit,
        "opposite_direction_cost": direction_cost_audit,
        "current_learning_rate": float(optimizer.param_groups[0]["lr"]),
        "completed_optimizer_steps": optimizer_steps,
    }
    replace_json_atomic(output_root / "training_progress.json", state)
    stopped_early = False
    active_loss_weights = {
        name: float(value) for name, value in config["loss_weights"].items()
    }
    training_stage = "macro_f1"
    for epoch in range(start_epoch, epochs):
        model.train()
        train_losses = []
        for step, batch in enumerate(train_loader, start=1):
            optimizer.zero_grad(set_to_none=True)
            loss, _ = _loss(model, batch, active_loss_weights, device)
            if not torch.isfinite(loss):
                raise RuntimeError("training loss is not finite")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                parameters,
                float(config["optimization"].get("gradient_clip_norm", 1.0)),
            )
            optimizer.step()
            _maybe_update_weight_averaging(
                averaged_model,
                model,
                weight_averaging_audit,
                event="optimizer_step",
                epoch=epoch,
            )
            if scheduler is not None:
                scheduler.step()
            optimizer_steps += 1
            train_losses.append(float(loss.detach()))
            if step % 100 == 0 or step == len(train_loader):
                state.update(
                    {
                        "current_epoch": epoch,
                        "completed_steps_in_epoch": step,
                        "latest_train_loss": train_losses[-1],
                        "current_learning_rate": float(optimizer.param_groups[0]["lr"]),
                        "completed_optimizer_steps": optimizer_steps,
                        "training_stage": training_stage,
                        "active_loss_weights": active_loss_weights,
                    }
                )
                replace_json_atomic(output_root / "training_progress.json", state)
        _maybe_update_weight_averaging(
            averaged_model,
            model,
            weight_averaging_audit,
            event="epoch",
            epoch=epoch,
        )
        evaluation_model = _weight_averaged_evaluation_model(model, averaged_model)
        metrics = evaluate_loader(
            evaluation_model,
            dev_loader,
            weights=active_loss_weights,
            device=device,
        )
        metrics["epoch"] = epoch
        metrics["train_loss"] = sum(train_losses) / len(train_losses)
        metrics["training_stage"] = training_stage
        metrics["active_loss_weights"] = active_loss_weights
        history.append(metrics)
        improved = float(metrics["macro_f1"]) > best_f1 + min_delta
        if improved:
            best_f1 = float(metrics["macro_f1"])
            best_epoch = epoch
            last_improvement_epoch = epoch
        evaluation_model_state = evaluation_model.state_dict()
        checkpoint = {
            "schema": "prta-cxr.checkpoint.v1",
            "epoch": epoch,
            "best_dev_macro_f1": best_f1,
            "best_epoch": best_epoch,
            "history": history,
            "model_state": evaluation_model_state,
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": (
                scheduler.state_dict() if scheduler is not None else None
            ),
            "completed_optimizer_steps": optimizer_steps,
            "last_improvement_epoch": last_improvement_epoch,
            "weight_averaging_updates": (
                int(averaged_model.n_averaged.item())
                if averaged_model is not None
                else None
            ),
            "config": dict(config),
            "input_hashes": dict(input_hashes),
            "parameter_audit": parameter_audit,
        }
        if averaged_model is not None:
            checkpoint["training_model_state"] = model.state_dict()
        _save_checkpoint(output_root / "last.pt", checkpoint)
        if improved:
            _save_checkpoint(output_root / "best.pt", checkpoint)
        state.update(
            {
                "current_epoch": epoch,
                "completed_steps_in_epoch": len(train_loader),
                "best_dev_macro_f1": best_f1,
                "best_epoch": best_epoch,
                "latest_dev_metrics": metrics,
                "training_stage": training_stage,
                "active_loss_weights": active_loss_weights,
            }
        )
        replace_json_atomic(output_root / "training_progress.json", state)
        if epoch + 1 >= min_epochs and epoch - last_improvement_epoch >= patience:
            stopped_early = True
            break
    dev_prior_audit: dict[str, Any] = {}
    if wrong_prior_dev_loader is not None:
        best_checkpoint = torch.load(
            output_root / "best.pt", map_location="cpu", weights_only=True
        )
        model.load_state_dict(best_checkpoint["model_state"])
        model.to(device)
        wrong_metrics = evaluate_loader(
            model,
            wrong_prior_dev_loader,
            weights=next(
                value["active_loss_weights"]
                for value in history
                if int(value["epoch"]) == best_epoch
            ),
            device=device,
        )
        true_metrics = next(
            value for value in history if int(value["epoch"]) == best_epoch
        )
        dev_prior_audit = {
            "intervention": "matched_source_finding_view_interval_wrong_patient",
            "true_prior_macro_f1": float(true_metrics["macro_f1"]),
            "matched_wrong_prior_macro_f1": float(wrong_metrics["macro_f1"]),
            "true_minus_wrong_prior_gap": float(true_metrics["macro_f1"])
            - float(wrong_metrics["macro_f1"]),
            "matched_wrong_metrics": wrong_metrics,
        }
    ended = datetime.now(UTC).isoformat()
    receipt = {
        "schema": "prta-cxr.training-receipt.v1",
        "status": "PASS_TRAINING_FINISHED",
        "formal_experiment": True,
        "seed": seed,
        "maximum_epochs": epochs,
        "completed_epochs": len(history),
        "stopped_early": stopped_early,
        "best_dev_macro_f1": best_f1,
        "best_epoch": best_epoch,
        "history": history,
        "config_sha256": canonical_sha256(config),
        "input_hashes": dict(input_hashes),
        "parameter_audit": parameter_audit,
        "checkpoint_path": "best.pt",
        "fraction_audit": dict(fraction_audit or {}),
        "dev_prior_audit": dev_prior_audit,
        "learning_rate_schedule": {
            **scheduler_audit,
            "completed_optimizer_steps": optimizer_steps,
            "final_learning_rate": float(optimizer.param_groups[0]["lr"]),
        },
        "weight_averaging": {
            **weight_averaging_audit,
            "updates": (
                int(averaged_model.n_averaged.item())
                if averaged_model is not None
                else 0
            ),
        },
        "training_stage": "macro_f1",
        "opposite_direction_cost": direction_cost_audit,
        "start_time": started,
        "end_time": ended,
        "internal_test_opened": False,
        "protected_outcomes_opened": False,
    }
    write_json_atomic(output_root / "training_receipt.json", receipt)
    state.update({"status": "PASS_TRAINING_FINISHED", "end_time": ended})
    replace_json_atomic(output_root / "training_progress.json", state)
    return receipt
