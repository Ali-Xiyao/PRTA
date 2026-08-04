from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import torch

from prta_cxr.audit.runner import (
    assemble_outputs,
    bind_work_contract,
    code_safety_scan,
    prepare_contract,
    run_dev_predictions,
    run_seed_scores,
    select_and_save_probes,
)
from prta_cxr.audit.tracin import SEEDS, AuditContractError, audit_path


def tracin_audit_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Train/Dev approximate TracIn audit"
    )
    parser.add_argument(
        "--phase",
        choices=("preflight", "dev", "probes", "seed", "assemble", "all"),
        default="preflight",
    )
    parser.add_argument("--readonly-audit", action="store_true")
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--text-cache", type=Path)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--probe-batch-size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if not args.readonly_audit:
        parser.error("every phase requires --readonly-audit")
    required = {
        "split_manifest": args.split_manifest,
        "cache_root": args.cache_root,
        "text_cache": args.text_cache,
        "weights": args.weights,
        "runs_root": args.runs_root,
        "output": args.output,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("audit paths missing: " + ", ".join(missing))
    if args.phase == "seed" and args.seed is None:
        parser.error("--phase seed requires --seed")
    if args.batch_size <= 0 or args.probe_batch_size <= 0 or args.workers < 0:
        parser.error("batch sizes must be positive and workers non-negative")
    repo_root = Path(args.repo_root).resolve()
    code_safety_scan(repo_root)
    try:
        rows, snapshot, _ = prepare_contract(
            split_manifest=args.split_manifest,
            cache_root=args.cache_root,
            text_cache=args.text_cache,
            weights=args.weights,
            runs_root=args.runs_root,
            output=args.output,
            repo_root=repo_root,
        )
    except AuditContractError as error:
        parser.error(str(error))
    output = audit_path(args.output, role="private output")
    device = torch.device(args.device)
    common = {
        "rows": rows,
        "weights": audit_path(args.weights, role="weights"),
        "runs_root": audit_path(args.runs_root, role="runs root"),
        "cache_root": audit_path(args.cache_root, role="cache root"),
        "text_cache": audit_path(args.text_cache, role="text cache"),
        "output": output,
        "device": device,
        "batch_size": args.batch_size,
        "workers": args.workers,
        "resume": args.resume,
    }
    if args.phase == "preflight":
        print(
            json.dumps(
                {
                    "status": "PASS_READONLY_TRACIN_PREFLIGHT",
                    "train_rows": 91_065,
                    "dev_rows": 16_666,
                    "protected_outcome_read_count": 0,
                    "training_started": False,
                    "input_hashes": snapshot,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    output.mkdir(parents=True, exist_ok=True)
    bind_work_contract(output, snapshot)
    if args.phase in {"dev", "all"}:
        run_dev_predictions(**common)
    if args.phase in {"probes", "all"}:
        select_and_save_probes(rows, output=output)
    if args.phase == "seed":
        run_seed_scores(
            args.seed,
            **common,
            probe_batch_size=args.probe_batch_size,
        )
    elif args.phase == "all":
        for seed in SEEDS:
            run_seed_scores(
                seed,
                **common,
                probe_batch_size=args.probe_batch_size,
            )
    if args.phase in {"assemble", "all"}:
        receipt = assemble_outputs(
            rows,
            output=output,
            snapshot_before=snapshot,
            split_manifest=audit_path(args.split_manifest, role="Train/Dev manifest"),
            cache_root=audit_path(args.cache_root, role="cache root"),
            text_cache=audit_path(args.text_cache, role="text cache"),
            weights=audit_path(args.weights, role="weights"),
            runs_root=audit_path(args.runs_root, role="runs root"),
            repo_root=repo_root,
        )
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
