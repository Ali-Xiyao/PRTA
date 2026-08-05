from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import torch

from prta_cxr.artifacts import replace_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.program_keeper import run_formal_program


def program_keeper_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the gated PRTA-CXR program")
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--formal", action="store_true")
    for name in (
        "output",
        "initial-queue",
        "split-manifest",
        "cleaned-split-freeze",
        "sealed-internal-test",
        "gold-manifest",
        "cache-root",
        "gold-cache-root",
        "weights",
        "quality-audit",
        "run-registry",
        "development-runs-root",
        "formal-runs-root",
        "protocol-config",
        "trust-config",
        "case-selection-config",
        "vlm-config",
        "vlm-model-config",
        "vlm-model-index",
    ):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--devices", default="cuda:0,cuda:1")
    parser.add_argument("--outcome-device", default="cuda:0")
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_PROGRAM_KEEPER_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    paths = {
        key: value
        for key, value in vars(args).items()
        if key not in {"mode", "formal", "devices", "outcome_device", "poll_seconds"}
    }
    missing = [key for key, value in paths.items() if value is None]
    if missing:
        parser.error("formal program paths missing: " + ", ".join(missing))
    try:
        result = run_formal_program(
            **paths,
            devices=tuple(
                value.strip() for value in args.devices.split(",") if value.strip()
            ),
            outcome_device=torch.device(args.outcome_device),
            poll_seconds=args.poll_seconds,
        )
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        replace_json_atomic(
            args.output / "program_state.json",
            {
                "schema": "prta-cxr.formal-program-keeper.v1",
                "status": "HOLD_PROGRAM_ERROR",
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
