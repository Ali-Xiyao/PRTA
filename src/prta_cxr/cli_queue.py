from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.queue_runner import run_training_queue


def run_development_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen Train/Dev queue")
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--quality-audit", type=Path)
    parser.add_argument("--run-registry", type=Path)
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--devices", default="cuda:0,cuda:1")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_DEVELOPMENT_RUNNER_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    required = {
        "queue": args.queue,
        "split_manifest": args.split_manifest,
        "cache_root": args.cache_root,
        "weights": args.weights,
        "quality_audit": args.quality_audit,
        "run_registry": args.run_registry,
        "runs_root": args.runs_root,
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        parser.error("formal queue arguments missing: " + ", ".join(missing))
    result = run_training_queue(
        queue_path=args.queue,
        split_manifest=args.split_manifest,
        cache_root=args.cache_root,
        weights=args.weights,
        quality_audit=args.quality_audit,
        run_registry=args.run_registry,
        runs_root=args.runs_root,
        devices=tuple(
            value.strip() for value in args.devices.split(",") if value.strip()
        ),
        poll_seconds=args.poll_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"].startswith("PASS_") else 1
