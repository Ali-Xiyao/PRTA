from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from prta_cxr.artifacts import (
    replace_json_atomic,
    write_json_atomic,
    write_jsonl_atomic,
)
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.formal_outcome_session import _load_model
from prta_cxr.run_registry import read_run_registry
from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules
from prta_cxr.vlm.fixed64 import pack_prta_fixed64
from prta_cxr.vlm.frozen_qwen import (
    FrozenQwenProgressionScorer,
    build_prompt_ids,
)
from prta_cxr.vlm.projector import Fixed64Projector


def select_vlm_training_rows(
    rows: list[dict[str, Any]], *, count: int, seed: int
) -> list[dict[str, Any]]:
    train = [row for row in rows if row.get("split") == "train"]
    ordered = sorted(
        train,
        key=lambda row: hashlib.sha256(
            f"prta-vlm-train-v1|{seed}|{row['patient_id_hash']}|"
            f"{row['sample_id']}".encode()
        ).hexdigest(),
    )
    selected = ordered[:count]
    if len(selected) != count:
        raise ValueError("VLM training subset has fewer rows than frozen count")
    if set(PROGRESSION_LABELS) != {
        str(row["progression_label"]) for row in selected
    }:
        raise ValueError("VLM training subset does not support all five labels")
    return selected


def _training_weights(rows: list[dict[str, Any]]) -> list[float]:
    labels = Counter(str(row["progression_label"]) for row in rows)
    patients = Counter(str(row["patient_id_hash"]) for row in rows)
    raw = [
        1.0
        / (
            labels[str(row["progression_label"])]
            * patients[str(row["patient_id_hash"])]
        )
        for row in rows
    ]
    mean = sum(raw) / len(raw)
    return [value / mean for value in raw]


def _atomic_torch_save(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    torch.save(value, temporary)
    os.replace(temporary, path)


def _sentence(finding: str, prediction: str) -> str:
    templates = {
        "Stable": "No interval change in {finding}.",
        "Improved": "The {finding} has improved compared with the prior study.",
        "Worse": "The {finding} has worsened compared with the prior study.",
        "New": "New {finding} is present on the current study.",
        "Resolved": "The previously seen {finding} has resolved.",
    }
    return templates[prediction].format(finding=finding)


def _load_qwen(config: dict[str, Any], device: torch.device):
    from transformers import AutoTokenizer, Qwen3VLForConditionalGeneration

    model_config = config["model"]
    tokenizer = AutoTokenizer.from_pretrained(
        model_config["path"],
        local_files_only=True,
        trust_remote_code=False,
    )
    placeholder = int(
        tokenizer.convert_tokens_to_ids(config["interface"]["sentinel_token"])
    )
    if placeholder != int(config["interface"]["placeholder_token_id"]):
        raise ValueError("VLM placeholder token differs from frozen protocol")
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_config["path"],
        dtype=torch.bfloat16,
        attn_implementation=model_config["attention_implementation"],
        local_files_only=True,
        trust_remote_code=False,
        low_cpu_mem_usage=True,
    ).to(device)
    model.config.use_cache = False
    return tokenizer, model, placeholder


def run_vlm_additional(
    *,
    freeze: dict[str, Any],
    config: dict[str, Any],
    outcome_receipt: dict[str, Any],
    output: Path,
    device: torch.device,
    resume: bool,
) -> dict[str, Any]:
    if outcome_receipt.get("status") != "PASS_FORMAL_OUTCOME_PREDICTIONS_FINISHED":
        raise ValueError("VLM deployment requires the completed outcome session")
    if outcome_receipt.get("protocol_freeze_sha256") != freeze["receipt_file_sha256"]:
        raise ValueError("VLM outcome receipt does not match protocol freeze")
    if config.get("schema") != "prta-cxr.vlm-additional-protocol.v1":
        raise ValueError("unsupported VLM additional protocol")
    if output.exists() and not resume:
        raise FileExistsError(f"VLM additional output already exists: {output}")
    if resume and not output.exists():
        raise FileNotFoundError("cannot resume a missing VLM additional output")
    completed_path = output / "result.json"
    if resume and completed_path.is_file():
        completed = json.loads(completed_path.read_text(encoding="utf-8"))
        if completed.get("status") != "PASS_VLM_ADDITIONAL_FINISHED":
            raise ValueError("existing VLM result is not complete")
        return completed
    output.mkdir(parents=True, exist_ok=resume)
    registry = {
        str(row["experiment_id"]): row
        for row in read_run_registry(Path(freeze["run_registry_path"]))
    }
    source_id = str(config["source_method"])
    source_experiment = str(freeze["prta_aliases"][source_id])
    spec = {
        "evaluation_id": source_id,
        "source_experiment_id": source_experiment,
        "method": "B404",
        "seed": 17,
    }
    visual, _ = load_biomedclip_visual(Path(freeze["input_paths"]["weights"]))
    blocks, final_norm = tail_modules(visual)
    prta = _load_model(spec, registry, blocks, final_norm, device, freeze)
    prta.eval().requires_grad_(False)
    tokenizer, qwen, placeholder = _load_qwen(config, device)
    scorer = FrozenQwenProgressionScorer(
        qwen, tokenizer, placeholder_token_id=placeholder
    ).to(device)
    projector = Fixed64Projector(
        input_width=int(config["interface"]["input_width"]),
        hidden_size=int(config["model"]["hidden_size"]),
    ).to(device)
    optimizer = torch.optim.AdamW(
        projector.parameters(),
        lr=float(config["training"]["learning_rate"]),
        weight_decay=float(config["training"]["weight_decay"]),
    )
    train_rows_all = read_jsonl(Path(freeze["input_paths"]["train_dev_manifest"]))
    train_rows = select_vlm_training_rows(
        train_rows_all,
        count=int(config["training"]["rows"]),
        seed=int(config["training"]["seed"]),
    )
    train_cache = Block8CacheIndex(
        Path(freeze["input_paths"]["main_cache_manifest"]).parent
    )
    train_dataset = PRTAFeatureDataset(
        train_rows,
        cache=train_cache,
        text_cache_path=Path(freeze["input_paths"]["main_text_cache"]),
        split="train",
    )
    train_loader = DataLoader(train_dataset, batch_size=1, shuffle=False, num_workers=0)
    weights = _training_weights(train_rows)
    progress_path = output / "training_progress.json"
    resume_path = output / "projector_resume.pt"
    start_step = 0
    if resume:
        state = torch.load(resume_path, map_location="cpu", weights_only=False)
        if state["config_sha256"] != canonical_sha256(config):
            raise ValueError("VLM resume config differs")
        projector.load_state_dict(state["projector"])
        optimizer.load_state_dict(state["optimizer"])
        for optimizer_state in optimizer.state.values():
            for key, value in optimizer_state.items():
                if isinstance(value, torch.Tensor):
                    optimizer_state[key] = value.to(device)
        start_step = int(state["step"])
    accumulation = int(config["training"]["gradient_accumulation"])
    started = time.perf_counter()
    optimizer.zero_grad(set_to_none=True)
    running_loss = 0.0
    for step, (batch, weight) in enumerate(zip(train_loader, weights, strict=True), 1):
        if step <= start_step:
            continue
        with torch.no_grad():
            output_tokens, _, query = prta(
                batch["prior"].to(device),
                batch["current"].to(device),
                batch["finding_text"].to(device),
            )
            fixed = pack_prta_fixed64(output_tokens, query)
        projected = projector(fixed)
        prompt = build_prompt_ids(
            tokenizer,
            finding=str(batch["finding"][0]),
            placeholder_token_id=placeholder,
        ).to(device)
        scores = scorer.score(prompt, projected)
        target = batch["target"].to(device)
        loss = F.cross_entropy(scores.unsqueeze(0), target) * float(weight)
        (loss / accumulation).backward()
        running_loss += float(loss.detach())
        if step % accumulation == 0 or step == len(train_dataset):
            torch.nn.utils.clip_grad_norm_(projector.parameters(), 1.0)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
        if step % 100 == 0 or step == len(train_dataset):
            _atomic_torch_save(
                resume_path,
                {
                    "schema": "prta-cxr.vlm-projector-resume.v1",
                    "step": step,
                    "config_sha256": canonical_sha256(config),
                    "projector": projector.state_dict(),
                    "optimizer": optimizer.state_dict(),
                },
            )
            replace_json_atomic(
                progress_path,
                {
                    "status": "RUNNING_VLM_PROJECTOR_TRAINING",
                    "step": step,
                    "total": len(train_dataset),
                    "mean_loss": running_loss / max(1, step - start_step),
                },
            )
    checkpoint = output / "projector.pt"
    _atomic_torch_save(
        checkpoint,
        {
            "schema": "prta-cxr.vlm-projector.v1",
            "config_sha256": canonical_sha256(config),
            "source_checkpoint_sha256": sha256_file(
                Path(registry[source_experiment]["checkpoint_path"])
            ),
            "projector": projector.state_dict(),
        },
    )
    gold_rows = read_jsonl(Path(freeze["input_paths"]["gold_manifest"]))
    gold_rows = [
        {**row, "split": "gold", "human_label": str(row["human_label"])}
        for row in gold_rows
    ]
    if len(gold_rows) != int(config["evaluation"]["rows"]):
        raise ValueError("VLM Gold row count differs from frozen protocol")
    gold_dataset = PRTAFeatureDataset(
        gold_rows,
        cache=Block8CacheIndex(
            Path(freeze["input_paths"]["gold_cache_manifest"]).parent
        ),
        text_cache_path=Path(freeze["input_paths"]["gold_text_cache"]),
        split="gold",
        label_key="human_label",
    )
    predictions = []
    projector.eval()
    for batch in DataLoader(gold_dataset, batch_size=1, shuffle=False, num_workers=0):
        with torch.no_grad():
            output_tokens, _, query = prta(
                batch["prior"].to(device),
                batch["current"].to(device),
                batch["finding_text"].to(device),
            )
            scores = scorer.score(
                build_prompt_ids(
                    tokenizer,
                    finding=str(batch["finding"][0]),
                    placeholder_token_id=placeholder,
                ).to(device),
                projector(pack_prta_fixed64(output_tokens, query)),
            )
            probabilities = scores.softmax(dim=-1).cpu()
        prediction = PROGRESSION_LABELS[int(probabilities.argmax())]
        target = PROGRESSION_LABELS[int(batch["target"].item())]
        finding = str(batch["finding"][0])
        predictions.append(
            {
                "patient_id": str(batch["patient_id_hash"][0]),
                "observation_id": str(batch["sample_id"][0]),
                "finding": finding,
                "target": target,
                "prediction": prediction,
                "probabilities": probabilities.tolist(),
                "schema_valid": True,
                "finding_consistent": True,
                "sentence": _sentence(finding, prediction),
            }
        )
    prediction_path = output / "gold_predictions.jsonl"
    write_jsonl_atomic(prediction_path, predictions)
    metrics = classification_metrics(predictions, labels=PROGRESSION_LABELS)
    ordinary = metrics["ordinary"]
    macro_f1 = float(ordinary["macro_f1"])
    temporal_contradiction = float(ordinary["opposite_direction_error_rate"])
    gate = config["inclusion_gate"]
    included = (
        macro_f1 >= float(gate["minimum_macro_f1"])
        and 1.0 >= float(gate["minimum_schema_validity"])
        and 1.0 >= float(gate["minimum_finding_consistency"])
        and temporal_contradiction <= float(gate["maximum_temporal_contradiction"])
    )
    result = {
        "schema": "prta-cxr.vlm-additional-result.v1",
        "status": "PASS_VLM_ADDITIONAL_FINISHED",
        "paper_inclusion": "GO_ADDITIONAL" if included else "HOLD_OMIT_ADDITIONAL",
        "source_method": source_id,
        "training_rows": len(train_dataset),
        "evaluation_rows": len(predictions),
        "macro_f1": macro_f1,
        "schema_validity": 1.0,
        "finding_consistency": 1.0,
        "temporal_contradiction": temporal_contradiction,
        "classification": metrics,
        "trainable_projector_parameters": sum(
            parameter.numel() for parameter in projector.parameters()
        ),
        "vlm_freeze_audit": scorer.freeze_audit(),
        "token_budget": 64,
        "pixel_inputs_used": False,
        "free_text_generated_by_vlm": False,
        "sentence_is_deterministic_qualitative_rendering": True,
        "prta_changed_after_vlm": False,
        "baseline_matrix_run": False,
        "checkpoint_path": str(checkpoint.resolve()),
        "prediction_path": str(prediction_path.resolve()),
        "elapsed_seconds": time.perf_counter() - started,
    }
    write_json_atomic(output / "result.json", result)
    replace_json_atomic(progress_path, result)
    return result
