from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.data.sealing import seal_split_surfaces


def seal_split_surfaces_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seal labeled Train/Dev and Internal-test from outcome-free cache input"
        )
    )
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--train-dev-output", type=Path)
    parser.add_argument("--internal-test-output", type=Path)
    parser.add_argument("--cache-input-output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(
            json.dumps(
                {
                    "status": "PASS_SPLIT_SURFACE_SEAL_PREFLIGHT",
                    "real_data_opened": False,
                    "internal_test_outcomes_opened": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    require_formal_authorization(formal_flag=args.formal)
    required = (
        args.input,
        args.train_dev_output,
        args.internal_test_output,
        args.cache_input_output,
        args.audit_output,
    )
    if not all(required):
        parser.error("formal sealing requires every input/output path")
    rows = read_jsonl(args.input)
    train_dev, internal_test, cache_input, audit = seal_split_surfaces(rows)
    audit["source_manifest_file_sha256"] = sha256_file(args.input)
    write_jsonl_atomic(args.train_dev_output, train_dev)
    write_jsonl_atomic(args.internal_test_output, internal_test)
    write_jsonl_atomic(args.cache_input_output, cache_input)
    write_json_atomic(args.audit_output, audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0
