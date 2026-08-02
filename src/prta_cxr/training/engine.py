from __future__ import annotations

import json
import os
import random
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256
from prta_cxr.models.heads import NativeH0Head, NativeH1Head
from prta_cxr.models.prta import (
    PRTATemporalAdapter,
    PRTATrainingHeads,
    cmcp_margin_loss,
    state_preservation_loss,
    temporal_inversion_loss,
    transition_alignment_loss,
)


class PRTATrainModel(nn.Module):
    def __init__(
        self,
        frozen_tail: list[nn.Module],
        final_norm: nn.Module,
        config: Mapping[str, Any],
    ) -> None:
        super().__init__()
        model = config["model"]
        self.adapter = PRTATemporalAdapter(
            frozen_tail,
            width=768,
            heads=int(model["heads"]),
            adapter_rank=int(model["adapter_rank"]),
            state_tokens=int(model["state_tokens"]),
            transition_tokens=int(model["transition_tokens"]),
            dropout=float(model.get("dropout", 0.0)),
            frozen_final_norm=final_norm,
        )
        self.training_heads = PRTATrainingHeads()
        head_name = str(model.get("native_head", "H0"))
        if head_name == "H0":
            self.native_head: nn.Module = NativeH0Head()
        elif head_name == "H1":
            self.native_head = NativeH1Head(dropout=float(model.get("dropout", 0.0)))
        else:
            raise ValueError("native_head must be H0 or H1")

    def forward(
        self, prior: torch.Tensor, current: torch.Tensor, finding_text: torch.Tensor
    ) -> tuple[Any, torch.Tensor, torch.Tensor]:
        query = self.training_heads.finding_query(finding_text)
        output = self.adapter(prior, current, query)
        logits = self.native_head(output, query)
        return output, logits, query


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
    model: PRTATrainModel,
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
    total = float(weights.get("classification", 1.0)) * F.cross_entropy(
        logits, target
    )
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
    model: PRTATrainModel,
    loader: DataLoader,
    *,
    weights: Mapping[str, float],
    device: torch.device,
) -> dict[str, Any]:
    model.eval()
    loss_sum = 0.0
    correct = 0
    count = 0
    targets: list[int] = []
    predictions: list[int] = []
    for batch in loader:
        loss, logits = _loss(model, batch, weights, device)
        prediction = logits.argmax(dim=-1).cpu()
        target = batch["target"].cpu()
        batch_count = target.numel()
        loss_sum += float(loss) * batch_count
        correct += int((prediction == target).sum())
        count += batch_count
        targets.extend(target.tolist())
        predictions.extend(prediction.tolist())
    f1 = []
    for label in range(len(PROGRESSION_LABELS)):
        pairs = list(zip(targets, predictions, strict=True))
        tp = sum(t == label and p == label for t, p in pairs)
        fp = sum(t != label and p == label for t, p in pairs)
        fn = sum(t == label and p != label for t, p in pairs)
        denominator = 2 * tp + fp + fn
        f1.append(0.0 if denominator == 0 else 2 * tp / denominator)
    return {
        "loss": loss_sum / count,
        "accuracy": correct / count,
        "macro_f1": sum(f1) / len(f1),
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
    model: PRTATrainModel,
    train_loader: DataLoader,
    dev_loader: DataLoader,
    *,
    config: Mapping[str, Any],
    output_root: Path,
    device: torch.device,
    input_hashes: Mapping[str, str],
    resume_path: Path | None = None,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite training output: {output_root}")
    output_root.mkdir(parents=True)
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
    if resume_path is not None:
        checkpoint = torch.load(resume_path, map_location="cpu", weights_only=True)
        model.load_state_dict(checkpoint["model_state"])
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        start_epoch = int(checkpoint["epoch"]) + 1
        best_f1 = float(checkpoint["best_dev_macro_f1"])
    history = []
    epochs = int(config["optimization"]["epochs"])
    for epoch in range(start_epoch, epochs):
        model.train()
        train_losses = []
        for batch in train_loader:
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
        metrics = evaluate_loader(
            model,
            dev_loader,
            weights=config["loss_weights"],
            device=device,
        )
        metrics["epoch"] = epoch
        metrics["train_loss"] = sum(train_losses) / len(train_losses)
        history.append(metrics)
        checkpoint = {
            "schema": "prta-cxr.checkpoint.v1",
            "epoch": epoch,
            "best_dev_macro_f1": max(best_f1, float(metrics["macro_f1"])),
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "config": dict(config),
            "input_hashes": dict(input_hashes),
        }
        _save_checkpoint(output_root / "last.pt", checkpoint)
        if metrics["macro_f1"] > best_f1:
            best_f1 = float(metrics["macro_f1"])
            _save_checkpoint(output_root / "best.pt", checkpoint)
    receipt = {
        "schema": "prta-cxr.training-receipt.v1",
        "status": "PASS_TRAINING_FINISHED",
        "formal_experiment": True,
        "seed": seed,
        "epochs": epochs,
        "best_dev_macro_f1": best_f1,
        "history": history,
        "config_sha256": canonical_sha256(config),
        "input_hashes": dict(input_hashes),
        "checkpoint_path": "best.pt",
        "internal_test_opened": False,
        "protected_outcomes_opened": False,
    }
    write_json_atomic(output_root / "training_receipt.json", receipt)
    return receipt
