from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.formal_outcome_session import run_formal_outcome_session


def formal_outcome_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the one-time formal outcome session"
    )
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--protocol-freeze", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--open-formal-outcomes", action="store_true")
    parser.add_argument("--resume-session", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal or args.open_formal_outcomes:
            parser.error("preflight cannot open formal outcomes")
        print(json.dumps({"status": "PASS_FORMAL_OUTCOME_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not args.open_formal_outcomes:
        parser.error("formal session requires --open-formal-outcomes")
    if args.protocol_freeze is None or args.output is None:
        parser.error("formal session requires protocol freeze and output")
    result = run_formal_outcome_session(
        protocol_path=args.protocol_freeze,
        output_root=args.output,
        device=torch.device(args.device),
        batch_size=args.batch_size,
        workers=args.workers,
        resume=args.resume_session,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
