from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from prta_cxr.artifacts import write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.experiments import filter_train_dev_sources
from prta_cxr.provenance import resolve_source_commit
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import (
    adapter_scope_cache_entry_block,
    load_biomedclip_visual,
    tail_modules,
)


def target_source_rows(
    rows: Sequence[Mapping[str, Any]], *, target_source: str
) -> list[dict[str, Any]]:
    selected = [
        dict(row)
        for row in rows
        if row.get("split") == "dev" and str(row.get("source")) == target_source
    ]
    if not selected:
        raise ValueError(f"target source has no Dev rows: {target_source}")
    if {str(row["source"]) for row in selected} != {target_source}:
        raise ValueError("target-source filter drift")
    return selected


def validate_source_holdout_sources(
    config: Mapping[str, Any], *, target_source: str
) -> tuple[list[str], list[str]]:
    data_config = dict(config.get("data", {}))
    train_sources = list(map(str, data_config.get("train_sources", ())))
    dev_sources = list(map(str, data_config.get("dev_sources", ())))
    if not train_sources or not dev_sources:
        raise ValueError("source-held-out config source rosters are missing")
    if target_source in train_sources:
        raise ValueError("target source leaked into source-held-out Train")
    if target_source in dev_sources:
        raise ValueError("target source leaked into selection Dev")
    if set(train_sources) != set(dev_sources) or len(set(train_sources)) != 1:
        raise ValueError("source-held-out Train/selection-Dev source drift")
    return train_sources, dev_sources


def validate_source_filter_receipt(
    receipt: Mapping[str, Any],
    checkpoint_hashes: Mapping[str, Any],
    *,
    expected_source_audit: Mapping[str, Any],
) -> None:
    recorded_source_audit = dict(
        dict(receipt.get("fraction_audit", {})).get("source_filter", {})
    )
    if recorded_source_audit != dict(expected_source_audit):
        raise ValueError("training receipt source-filter audit drift")
    if checkpoint_hashes.get("source_filter_audit") != canonical_sha256(
        expected_source_audit
    ):
        raise ValueError("checkpoint source-filter audit hash drift")


@torch.no_grad()
def _predict(
    model, loader: DataLoader, *, device: torch.device
) -> list[dict[str, Any]]:
    model.eval()
    rows = []
    for batch in loader:
        _, logits, _ = model(
            batch["prior"].to(device),
            batch["current"].to(device),
            batch["finding_text"].to(device),
        )
        probabilities = logits.detach().float().cpu().softmax(dim=-1)
        predictions = probabilities.argmax(dim=-1)
        for index, sample_id in enumerate(batch["sample_id"]):
            target = int(batch["target"][index])
            prediction = int(predictions[index])
            rows.append(
                {
                    "patient_id": str(batch["patient_id_hash"][index]),
                    "observation_id": str(sample_id),
                    "target": PROGRESSION_LABELS[target],
                    "prediction": PROGRESSION_LABELS[prediction],
                    "logits": logits[index].detach().float().cpu().tolist(),
                    "probabilities": probabilities[index].tolist(),
                    "source": str(batch["source"][index]),
                    "finding": str(batch["finding"][index]),
                }
            )
    return rows


def source_held_out_evaluation_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate source-held-out target Dev")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--target-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    cleaned = require_cleaned_manifest(
        args.split_manifest,
        receipt_path=args.cleaned_split_freeze,
        role="train_dev",
        portable_root=args.cleaned_split_platform_root,
    )
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported checkpoint schema")
    config = dict(checkpoint["config"])
    if config.get("phase16_axis") != "source_held_out":
        raise ValueError("checkpoint is not a Phase16 source-held-out run")
    if str(config.get("source_held_out_target")) != args.target_source:
        raise ValueError("target-source identity drift")
    train_sources, dev_sources = validate_source_holdout_sources(
        config, target_source=args.target_source
    )
    receipt = json.loads(args.training_receipt.read_text(encoding="utf-8"))
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError("training receipt is not terminal PASS")
    if receipt.get("config_sha256") != canonical_sha256(config):
        raise ValueError("checkpoint/training config identity drift")
    if dict(receipt.get("input_hashes", {})) != dict(
        checkpoint.get("input_hashes", {})
    ):
        raise ValueError("checkpoint/training input identity drift")
    expected_base = {
        "split_manifest": sha256_file(args.split_manifest),
        "cache_manifest": sha256_file(args.cache_root / "cache_manifest.json"),
        "text_cache": sha256_file(args.text_cache),
        "weights": sha256_file(args.weights),
        "cleaned_split_freeze": sha256_file(args.cleaned_split_freeze),
    }
    checkpoint_hashes = dict(checkpoint.get("input_hashes", {}))
    for name, value in expected_base.items():
        if checkpoint_hashes.get(name) != value:
            raise ValueError(f"source-held-out input hash mismatch: {name}")
    all_rows = read_jsonl(args.split_manifest)
    _, expected_source_audit = filter_train_dev_sources(
        all_rows, train_sources=train_sources, dev_sources=dev_sources
    )
    validate_source_filter_receipt(
        receipt,
        checkpoint_hashes,
        expected_source_audit=expected_source_audit,
    )
    rows = target_source_rows(all_rows, target_source=args.target_source)
    cache = Block8CacheIndex(args.cache_root)
    dataset = PRTAFeatureDataset(
        rows,
        cache=cache,
        text_cache_path=args.text_cache,
        split="dev",
    )
    loader = DataLoader(
        dataset, batch_size=args.batch_size, shuffle=False, num_workers=0
    )
    entry_block = adapter_scope_cache_entry_block(config["model"]["adapter_scope"])
    visual, _ = load_biomedclip_visual(args.weights)
    blocks, final_norm = tail_modules(visual, start_block=entry_block)
    model = build_train_model(blocks, final_norm, config)
    model.load_state_dict(checkpoint["model_state"])
    device = torch.device(args.device)
    model.to(device)
    predictions = _predict(model, loader, device=device)
    metrics = classification_metrics(predictions, labels=PROGRESSION_LABELS)
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    prediction_path = staging / "target_source_predictions.jsonl"
    write_jsonl_atomic(prediction_path, predictions)
    payload = {
        "schema": "prta-cxr.source-held-out-dev-evaluation.v1",
        "status": "PASS_SOURCE_HELD_OUT_TARGET_DEV_EVALUATION",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "experiment_id": config["experiment_id"],
        "seed": int(config["seed"]),
        "training_sources": train_sources,
        "selection_dev_sources": dev_sources,
        "target_source": args.target_source,
        "source_held_out_protocol": str(
            config.get("source_held_out_protocol", "legacy_unspecified")
        ),
        "source_filter_audit": expected_source_audit,
        "source_filter_audit_sha256": canonical_sha256(expected_source_audit),
        "target_source_used_for_selection": False,
        "rows": len(predictions),
        "metrics": metrics,
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "training_receipt_sha256": sha256_file(args.training_receipt),
        "prediction_block": {
            "path": prediction_path.name,
            "sha256": sha256_file(prediction_path),
            "rows": len(predictions),
        },
        "cleaned_split_freeze_sha256": cleaned["receipt_sha256"],
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    receipt_path = staging / "source_held_out_evaluation_receipt.json"
    receipt_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    staging.replace(args.output)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
