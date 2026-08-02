from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.data.cache_writer import build_block8_training_store


def build_training_store_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the contiguous Block-8 training access store"
    )
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_TRAINING_STORE_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if args.cache_root is None:
        parser.error("formal training-store build requires --cache-root")
    receipt = build_block8_training_store(args.cache_root)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
