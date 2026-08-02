from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.development_selection import prepare_next_development_stage


def prepare_next_development_stage_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select and prepare the next Dev stage"
    )
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--stage", choices=("loss", "adapter", "confirm"))
    parser.add_argument("--run-registry", type=Path)
    parser.add_argument("--previous-selection", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_DEV_SELECTION_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not all((args.stage, args.run_registry, args.output)):
        parser.error("formal selection requires stage, registry, and output")
    result = prepare_next_development_stage(
        stage=args.stage,
        registry_path=args.run_registry,
        previous_selection=args.previous_selection,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
