from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .authorization import require_formal_authorization
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
    parser.add_argument("--mode", choices=("smoke", "formal"), default="smoke")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "formal":
        require_formal_authorization(formal_flag=args.formal)
        raise NotImplementedError(
            "formal training remains behind the Phase 0 parity/data-freeze gate"
        )
    if args.formal:
        parser.error("--formal cannot be combined with --mode smoke")
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
