from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.data.sealing import (
    outcome_free_roster_cache_rows,
    seal_split_surfaces,
)
from prta_cxr.quality_gate import derive_completed_human_silver_audit


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


def derive_silver_quality_gate_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive the frozen Silver quality gate from senior review"
    )
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--senior-audit", type=Path)
    parser.add_argument("--comparisons", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_SILVER_QUALITY_GATE_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not all((args.senior_audit, args.comparisons, args.output)):
        parser.error("formal quality gate requires audit/comparisons/output")
    senior_audit = json.loads(args.senior_audit.read_text(encoding="utf-8"))
    comparisons = read_jsonl(args.comparisons)
    result = derive_completed_human_silver_audit(senior_audit, comparisons)
    if not result["training_gate_passed"]:
        raise RuntimeError("senior panel confirmation failed the Silver gate")
    write_json_atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def prepare_gold_cache_input_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare outcome-free Gold-candidate image cache input"
    )
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--roster", type=Path)
    parser.add_argument("--silver", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_GOLD_CACHE_INPUT_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not all((args.roster, args.silver, args.output, args.audit_output)):
        parser.error("formal cache-input preparation requires every path")
    rows, audit = outcome_free_roster_cache_rows(
        read_jsonl(args.roster), read_jsonl(args.silver)
    )
    write_jsonl_atomic(args.output, rows)
    audit["roster_file_sha256"] = sha256_file(args.roster)
    audit["silver_file_sha256"] = sha256_file(args.silver)
    audit["output_file_sha256"] = sha256_file(args.output)
    write_json_atomic(args.audit_output, audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0
