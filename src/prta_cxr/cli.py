from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import torch

from .authorization import require_formal_authorization
from .contracts import sha256_file
from .preflight import run_preflight
from .provenance import resolve_source_commit
from .training.smoke import run_synthetic_smoke


def preflight_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate clean-project contracts")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_preflight()
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


def train_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PRTA-CXR training entry point")
    parser.add_argument(
        "--mode", choices=("preflight", "smoke", "formal"), default="preflight"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--cleaned-split-freeze", type=Path)
    parser.add_argument("--cleaned-split-platform-root", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--text-cache", type=Path)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--label-quality-audit", type=Path)
    parser.add_argument("--run-registry", type=Path)
    parser.add_argument("--owner", default="Codex formal program")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("--formal cannot be combined with --mode preflight")
        print(
            json.dumps(
                {
                    "status": "PASS_TRAINING_PREFLIGHT",
                    "formal_experiment_started": False,
                    "real_data_opened": False,
                    "formal_arguments_present": all(
                        value is not None
                        for value in (
                            args.config,
                            args.split_manifest,
                            args.cleaned_split_freeze,
                            args.cache_root,
                            args.text_cache,
                            args.weights,
                            args.label_quality_audit,
                            args.run_registry,
                            args.output,
                        )
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.mode == "formal":
        require_formal_authorization(formal_flag=args.formal)
        required = {
            "config": args.config,
            "split_manifest": args.split_manifest,
            "cleaned_split_freeze": args.cleaned_split_freeze,
            "cache_root": args.cache_root,
            "text_cache": args.text_cache,
            "weights": args.weights,
            "label_quality_audit": args.label_quality_audit,
            "run_registry": args.run_registry,
            "output": args.output,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            parser.error("formal mode arguments missing: " + ", ".join(missing))
        from torch.utils.data import DataLoader

        from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
        from prta_cxr.data.token_cache import Block8CacheIndex
        from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
        from prta_cxr.experiments import (
            materialize_classification_counts,
            nested_train_fraction,
        )
        from prta_cxr.quality_gate import load_completed_human_silver_audit
        from prta_cxr.run_registry import upsert_run_registry
        from prta_cxr.training.engine import (
            build_train_model,
            load_training_config,
            train_model,
        )
        from prta_cxr.vision.biomedclip import (
            load_biomedclip_visual,
            tail_modules,
        )

        config = load_training_config(args.config)
        load_completed_human_silver_audit(args.label_quality_audit)
        require_cleaned_manifest(
            args.split_manifest,
            receipt_path=args.cleaned_split_freeze,
            role="train_dev",
            portable_root=args.cleaned_split_platform_root,
        )
        rows = read_jsonl(args.split_manifest)
        data_config = dict(config.get("data", {}))
        rows, fraction_audit = nested_train_fraction(
            rows,
            fraction=float(data_config.get("train_fraction", 1.0)),
            salt=str(
                data_config.get(
                    "fraction_salt", "prta-cxr-luna-primary-scaling-v1"
                )
            ),
        )
        config = materialize_classification_counts(config, rows)
        experiment_id = str(config.get("experiment_id", ""))
        if not experiment_id:
            raise ValueError("formal training config requires experiment_id")
        cache = Block8CacheIndex(args.cache_root)
        train_dataset = PRTAFeatureDataset(
            rows, cache=cache, text_cache_path=args.text_cache, split="train"
        )
        dev_dataset = PRTAFeatureDataset(
            rows, cache=cache, text_cache_path=args.text_cache, split="dev"
        )
        wrong_prior_dev_dataset = PRTAFeatureDataset(
            rows,
            cache=cache,
            text_cache_path=args.text_cache,
            split="dev",
            prior_intervention="matched_wrong",
        )
        batch_size = int(config["optimization"]["batch_size"])
        workers = int(config["optimization"].get("num_workers", 0))
        generator = torch.Generator().manual_seed(int(config["seed"]))
        train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
            num_workers=workers,
            generator=generator,
        )
        dev_loader = DataLoader(
            dev_dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=workers,
        )
        wrong_prior_dev_loader = DataLoader(
            wrong_prior_dev_dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=workers,
        )
        visual, _ = load_biomedclip_visual(args.weights)
        blocks, final_norm = tail_modules(visual)
        model = build_train_model(blocks, final_norm, config)
        input_hashes = {
            "split_manifest": sha256_file(args.split_manifest),
            "text_cache": sha256_file(args.text_cache),
            "weights": sha256_file(args.weights),
            "cache_manifest": sha256_file(args.cache_root / "cache_manifest.json"),
            "label_quality_audit": sha256_file(args.label_quality_audit),
            "cleaned_split_freeze": sha256_file(args.cleaned_split_freeze),
        }
        started = datetime.now(UTC).isoformat()
        git_commit = resolve_source_commit(Path(__file__).resolve().parents[2])
        registry_row = {
            "experiment_id": experiment_id,
            "date": started[:10],
            "owner": str(args.owner),
            "git_commit": git_commit,
            "config_path": str(args.config.resolve()),
            "config_hash": sha256_file(args.config),
            "split_manifest_hash": input_hashes["split_manifest"],
            "label_manifest_hash": input_hashes["split_manifest"],
            "seed": int(config["seed"]),
            "gpu": str(args.device),
            "start_time": started,
            "end_time": "",
            "status": "RUNNING",
            "checkpoint_path": "",
            "prediction_path": "",
            "metrics_path": "",
            "log_path": str((args.output / "training_progress.json").resolve()),
            "notes": "Train/Dev only; Internal-test and Gold sealed",
        }
        upsert_run_registry(args.run_registry, registry_row)
        try:
            receipt = train_model(
                model,
                train_loader,
                dev_loader,
                config=config,
                output_root=args.output,
                device=torch.device(args.device),
                input_hashes=input_hashes,
                resume_path=args.resume,
                fraction_audit=fraction_audit,
                wrong_prior_dev_loader=wrong_prior_dev_loader,
            )
        except Exception:
            registry_row["end_time"] = datetime.now(UTC).isoformat()
            registry_row["status"] = "FAILED"
            upsert_run_registry(args.run_registry, registry_row)
            raise
        registry_row["end_time"] = datetime.now(UTC).isoformat()
        registry_row["status"] = str(receipt["status"])
        registry_row["checkpoint_path"] = str((args.output / "best.pt").resolve())
        registry_row["metrics_path"] = str(
            (args.output / "training_receipt.json").resolve()
        )
        upsert_run_registry(args.run_registry, registry_row)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.formal:
        parser.error("--formal cannot be combined with --mode smoke")
    if args.output is None:
        parser.error("--output is required in smoke mode")
    result = run_synthetic_smoke(args.output, seed=args.seed, steps=args.steps)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def gated_step_main(step: str, argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"PRTA-CXR {step}; dry-run is the only authorized default"
    )
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.formal:
        require_formal_authorization(formal_flag=True)
        raise NotImplementedError(f"{step} formal implementation is not yet unlocked")
    print(
        json.dumps(
            {
                "status": "PASS_DRY_RUN",
                "step": step,
                "formal_experiment_started": False,
                "real_data_opened": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0
