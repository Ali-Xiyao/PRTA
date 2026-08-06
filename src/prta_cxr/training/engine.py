from __future__ import annotations

import json
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
from torch.utils.data import DataLoader

from prta_cxr.artifacts import replace_json_atomic, write_json_atomic
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.models.heads import (
    NativeH0Head,
    NativeH1Head,
    NativeH2Head,
    NativeH3StateAnchoredHead,
)
from prta_cxr.models.prta import (
    FrozenTailWithAdapters,
    PRTATemporalAdapter,
    PRTATrainingHeads,
    cmcp_margin_loss,
    opposite_direction_margin_loss,
    state_preservation_loss,
    temporal_inversion_loss,
    transition_alignment_loss,
)
from prta_cxr.training.losses import progression_classification_loss


def _adapter_indices(model: Mapping[str, Any]) -> tuple[int, ...]:
    scope = str(model.get("adapter_scope", "tail4"))
    if scope == "tail4":
        return (0, 1, 2, 3)
    if scope == "last2":
        return (2, 3)
    raise ValueError("adapter_scope must be tail4 or last2")


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
        self.finding_conditioning = bool(
            components.get("finding_conditioning", True)
        )
        self.dual_branch = bool(components.get("dual_branch", True))
        self.adapter = PRTATemporalAdapter(
            frozen_tail,
            width=width,
            heads=int(model["heads"]),
            adapter_rank=int(model["adapter_rank"]),
            state_tokens=int(model["state_tokens"]),
            transition_tokens=int(model["transition_tokens"]),
            dropout=float(model.get("dropout", 0.0)),
            frozen_final_norm=final_norm,
            cross_time_alignment=bool(
                components.get("cross_time_alignment", True)
            ),
            bounded_state_anchor=bool(
                components.get("bounded_state_anchor", False)
            ),
            adapter_indices=_adapter_indices(model),
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
        else:
            raise ValueError("native_head must be H0, H1, H2, or H3")

    def forward(
        self, prior: torch.Tensor, current: torch.Tensor, finding_text: torch.Tensor
    ) -> tuple[Any, torch.Tensor, torch.Tensor]:
        query = self.training_heads.finding_query(finding_text)
        if not self.finding_conditioning:
            query = torch.zeros_like(query)
        output = self.adapter(prior, current, query)
        if not self.dual_branch:
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
            adapter_indices=_adapter_indices(model),
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
    direction_weight = float(weights.get("direction_margin", 0.0))
    if direction_weight:
        direction_spec = dict(model.config.get("direction_margin", {}))
        total = total + direction_weight * opposite_direction_margin_loss(
            logits,
            target,
            margin=float(direction_spec.get("margin", 0.2)),
        )
    auxiliary_requested = any(
        float(weights.get(name, 0.0))
        for name in ("alignment", "state", "inversion", "cmcp")
    )
    if output is None:
        if auxiliary_requested:
            raise ValueError("native baselines require zero auxiliary-loss weights")
        return total, logits
    projected_text = model.training_heads.transition_text(transition_text)
    total = total + float(weights.get("alignment", 0.0)) * transition_alignment_loss(
        output.transition_embedding, projected_text
    )
    total = total + float(weights.get("state", 0.0)) * state_preservation_loss(
        output.state_embedding, output.frozen_current_embedding
    )
    inversion_weight = float(weights.get("inversion", 0.0))
    if inversion_weight:
        _, reverse_logits, _ = model(current, prior, finding)
        total = total + inversion_weight * temporal_inversion_loss(
            logits, reverse_logits
        )
    cmcp_weight = float(weights.get("cmcp", 0.0))
    if cmcp_weight and prior.shape[0] > 1:
        counterfactual, _, _ = model(prior.roll(1, dims=0), current, finding)
        total = total + cmcp_weight * cmcp_margin_loss(
            output.transition_embedding,
            counterfactual.transition_embedding,
            projected_text,
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
        "opposite_direction_error_rate": ordinary[
            "opposite_direction_error_rate"
        ],
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
    optimizer = torch.optim.AdamW(
        parameters,
        lr=float(config["optimization"]["learning_rate"]),
        weight_decay=float(config["optimization"].get("weight_decay", 0.0)),
    )
    start_epoch = 0
    best_f1 = -1.0
    best_epoch = -1
    history: list[dict[str, Any]] = []
    if resume_path is not None:
        if Path(resume_path).resolve().parent != output_root.resolve():
            raise ValueError("resume checkpoint must belong to the output directory")
        checkpoint = torch.load(resume_path, map_location="cpu", weights_only=True)
        if checkpoint.get("config") != dict(config):
            raise ValueError("resume checkpoint config mismatch")
        if checkpoint.get("input_hashes") != dict(input_hashes):
            raise ValueError("resume checkpoint input hash mismatch")
        model.load_state_dict(checkpoint["model_state"])
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        start_epoch = int(checkpoint["epoch"]) + 1
        best_f1 = float(checkpoint["best_dev_macro_f1"])
        best_epoch = int(checkpoint.get("best_epoch", checkpoint["epoch"]))
        history = list(checkpoint.get("history", []))
    epochs = int(config["optimization"]["epochs"])
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
    }
    replace_json_atomic(output_root / "training_progress.json", state)
    stopped_early = False
    for epoch in range(start_epoch, epochs):
        model.train()
        train_losses = []
        for step, batch in enumerate(train_loader, start=1):
            optimizer.zero_grad(set_to_none=True)
            loss, _ = _loss(model, batch, config["loss_weights"], device)
            if not torch.isfinite(loss):
                raise RuntimeError("training loss is not finite")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                parameters,
                float(config["optimization"].get("gradient_clip_norm", 1.0)),
            )
            optimizer.step()
            train_losses.append(float(loss.detach()))
            if step % 100 == 0 or step == len(train_loader):
                state.update(
                    {
                        "current_epoch": epoch,
                        "completed_steps_in_epoch": step,
                        "latest_train_loss": train_losses[-1],
                    }
                )
                replace_json_atomic(output_root / "training_progress.json", state)
        metrics = evaluate_loader(
            model,
            dev_loader,
            weights=config["loss_weights"],
            device=device,
        )
        metrics["epoch"] = epoch
        metrics["train_loss"] = sum(train_losses) / len(train_losses)
        history.append(metrics)
        improved = float(metrics["macro_f1"]) > best_f1 + min_delta
        if improved:
            best_f1 = float(metrics["macro_f1"])
            best_epoch = epoch
        checkpoint = {
            "schema": "prta-cxr.checkpoint.v1",
            "epoch": epoch,
            "best_dev_macro_f1": best_f1,
            "best_epoch": best_epoch,
            "history": history,
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "config": dict(config),
            "input_hashes": dict(input_hashes),
        }
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
            }
        )
        replace_json_atomic(output_root / "training_progress.json", state)
        if epoch + 1 >= min_epochs and epoch - best_epoch >= patience:
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
            weights=config["loss_weights"],
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
        "checkpoint_path": "best.pt",
        "fraction_audit": dict(fraction_audit or {}),
        "dev_prior_audit": dev_prior_audit,
        "start_time": started,
        "end_time": ended,
        "internal_test_opened": False,
        "protected_outcomes_opened": False,
    }
    write_json_atomic(output_root / "training_receipt.json", receipt)
    state.update({"status": "PASS_TRAINING_FINISHED", "end_time": ended})
    replace_json_atomic(output_root / "training_progress.json", state)
    return receipt
