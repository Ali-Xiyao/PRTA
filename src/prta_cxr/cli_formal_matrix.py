from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.formal_matrix import (
    prepare_dev_baseline_queue,
    prepare_formal_matrix,
    write_development_gate,
)


def formal_matrix_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare frozen formal experiment stages"
    )
    parser.add_argument(
        "--action",
        choices=("preflight", "dev-baselines", "dev-gate", "formal-matrix"),
        default="preflight",
    )
    parser.add_argument("--run-registry", type=Path)
    parser.add_argument("--confirm-selection", type=Path)
    parser.add_argument("--gate-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_FORMAL_MATRIX_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not all((args.run_registry, args.confirm_selection, args.output)):
        parser.error("formal matrix action requires registry/selection/output")
    if args.action == "dev-baselines":
        result = prepare_dev_baseline_queue(
            registry_path=args.run_registry,
            confirm_selection=args.confirm_selection,
            output=args.output,
        )
    elif args.action == "dev-gate":
        result = write_development_gate(
            registry_path=args.run_registry,
            confirm_selection=args.confirm_selection,
            output=args.output,
        )
    else:
        if args.gate_receipt is None:
            parser.error("formal-matrix action requires --gate-receipt")
        result = prepare_formal_matrix(
            registry_path=args.run_registry,
            confirm_selection=args.confirm_selection,
            gate_receipt=args.gate_receipt,
            output=args.output,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
