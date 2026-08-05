from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.evaluation.inference import predict_loader
from prta_cxr.evaluation.progression import classification_metrics


def _synthetic_rows() -> list[dict[str, str]]:
    rows = []
    for index, label in enumerate(PROGRESSION_LABELS):
        rows.append(
            {
                "patient_id": f"patient-{index}",
                "observation_id": f"sample-{index}",
                "target": label,
                "prediction": label,
            }
        )
    return rows


@torch.no_grad()
def _predict(model, loader: DataLoader, device: torch.device):
    return predict_loader(
        model,
        loader,
        device=device,
        system="single_checkpoint",
        seed=int(model.config["seed"]),
        cohort="internal_test",
    )


def evaluate_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate frozen PRTA checkpoints")
    parser.add_argument(
        "--mode", choices=("preflight", "synthetic", "formal"), default="preflight"
    )
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--cleaned-split-freeze", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--text-cache", type=Path)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--open-internal-test", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal or args.open_internal_test:
            parser.error("preflight cannot authorize formal test opening")
        print(
            json.dumps(
                {
                    "status": "PASS_EVALUATION_PREFLIGHT",
                    "formal_evaluation_started": False,
                    "internal_test_opened": False,
                    "protected_outcomes_opened": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.mode == "formal":
        require_formal_authorization(formal_flag=args.formal)
    if args.output is None:
        parser.error("--output is required outside preflight mode")
    if args.mode == "synthetic":
        if args.formal or args.open_internal_test:
            parser.error("synthetic mode cannot authorize formal test opening")
        rows = _synthetic_rows()
        metrics = classification_metrics(rows, labels=PROGRESSION_LABELS)
        args.output.mkdir(parents=True, exist_ok=False)
        write_jsonl_atomic(args.output / "predictions.jsonl", rows)
        receipt = {
            "schema": "prta-cxr.synthetic-evaluation.v1",
            "status": "PASS_SYNTHETIC_EVALUATION",
            "metrics": metrics,
            "formal_evaluation": False,
            "internal_test_opened": False,
            "protected_outcomes_opened": False,
        }
        write_json_atomic(args.output / "metrics.json", receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0

    if not args.open_internal_test:
        parser.error("formal evaluation requires --open-internal-test")
    required = {
        "checkpoint": args.checkpoint,
        "split_manifest": args.split_manifest,
        "cleaned_split_freeze": args.cleaned_split_freeze,
        "cache_root": args.cache_root,
        "text_cache": args.text_cache,
        "weights": args.weights,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("formal evaluation arguments missing: " + ", ".join(missing))
    from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
    from prta_cxr.data.token_cache import Block8CacheIndex
    from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
    from prta_cxr.training.engine import build_train_model
    from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules

    cleaned = require_cleaned_manifest(
        args.split_manifest,
        receipt_path=args.cleaned_split_freeze,
        role="internal_test",
    )
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported checkpoint schema")
    expected = checkpoint["input_hashes"]
    current = {
        "split_manifest": sha256_file(args.split_manifest),
        "text_cache": sha256_file(args.text_cache),
        "weights": sha256_file(args.weights),
        "cache_manifest": sha256_file(args.cache_root / "cache_manifest.json"),
    }
    expected_evaluation_inputs = {
        key: expected.get(key) for key in current
    }
    if expected_evaluation_inputs != current:
        raise ValueError("evaluation inputs do not match checkpoint input hashes")
    visual, _ = load_biomedclip_visual(args.weights)
    blocks, final_norm = tail_modules(visual)
    model = build_train_model(blocks, final_norm, checkpoint["config"])
    model.load_state_dict(checkpoint["model_state"])
    model.to(torch.device(args.device))
    dataset = PRTAFeatureDataset(
        read_jsonl(args.split_manifest),
        cache=Block8CacheIndex(args.cache_root),
        text_cache_path=args.text_cache,
        split="internal_test",
    )
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False)
    rows = _predict(model, loader, torch.device(args.device))
    metrics = classification_metrics(rows, labels=PROGRESSION_LABELS)
    args.output.mkdir(parents=True, exist_ok=False)
    write_jsonl_atomic(args.output / "predictions.jsonl", rows)
    receipt = {
        "schema": "prta-cxr.internal-evaluation.v1",
        "status": "PASS_INTERNAL_EVALUATION_FINISHED",
        "metrics": metrics,
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "input_hashes": current,
        "cleaned_split_freeze_sha256": cleaned["receipt_sha256"],
        "internal_test_opened": True,
        "protected_outcomes_opened": False,
    }
    write_json_atomic(args.output / "metrics.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
