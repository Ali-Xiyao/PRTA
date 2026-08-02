from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import torch

from .authorization import require_formal_authorization
from .contracts import sha256_file
from .preflight import run_preflight
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
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--text-cache", type=Path)
    parser.add_argument("--weights", type=Path)
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
                            args.cache_root,
                            args.text_cache,
                            args.weights,
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
            "cache_root": args.cache_root,
            "text_cache": args.text_cache,
            "weights": args.weights,
            "output": args.output,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            parser.error("formal mode arguments missing: " + ", ".join(missing))
        from torch.utils.data import DataLoader

        from prta_cxr.data.token_cache import Block8CacheIndex
        from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
        from prta_cxr.training.engine import (
            PRTATrainModel,
            load_training_config,
            train_model,
        )
        from prta_cxr.vision.biomedclip import (
            load_biomedclip_visual,
            tail_modules,
        )

        config = load_training_config(args.config)
        rows = read_jsonl(args.split_manifest)
        cache = Block8CacheIndex(args.cache_root)
        train_dataset = PRTAFeatureDataset(
            rows, cache=cache, text_cache_path=args.text_cache, split="train"
        )
        dev_dataset = PRTAFeatureDataset(
            rows, cache=cache, text_cache_path=args.text_cache, split="dev"
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
        visual, _ = load_biomedclip_visual(args.weights)
        blocks, final_norm = tail_modules(visual)
        model = PRTATrainModel(blocks, final_norm, config)
        receipt = train_model(
            model,
            train_loader,
            dev_loader,
            config=config,
            output_root=args.output,
            device=torch.device(args.device),
            input_hashes={
                "split_manifest": sha256_file(args.split_manifest),
                "text_cache": sha256_file(args.text_cache),
                "weights": sha256_file(args.weights),
                "cache_manifest": sha256_file(
                    args.cache_root / "cache_manifest.json"
                ),
            },
            resume_path=args.resume,
        )
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
