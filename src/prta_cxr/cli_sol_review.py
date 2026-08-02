from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cli_independent_silver import synthetic_ai_rows
from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.independent_silver import load_independent_ai_output
from prta_cxr.sol_review import compare_rule_luna_sol


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def compare_sol_review_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare rule, Luna, and blind Sol labels"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--luna-output-dir", type=Path)
    parser.add_argument("--sol-output-dir", type=Path)
    parser.add_argument("--comparison-output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        samples = synthetic_samples()
        luna_rows = synthetic_ai_rows(samples)
        sol_rows = synthetic_ai_rows(samples)
        comparisons, audit = compare_rule_luna_sol(
            samples, luna_rows, sol_rows
        )
        _print(
            {
                "status": "PASS_SOL_REVIEW_COMPARISON_PREFLIGHT",
                "rows": len(comparisons),
                "audit": audit,
                "real_labels_opened": False,
            }
        )
        return 0

    require_formal_authorization(formal_flag=args.formal)
    required = (
        args.candidates,
        args.luna_output_dir,
        args.sol_output_dir,
        args.comparison_output,
        args.audit_output,
    )
    if not all(required):
        parser.error("formal mode requires all input and output paths")
    samples = read_jsonl(args.candidates)
    luna_rows = []
    sol_rows = []
    for path in sorted(args.luna_output_dir.glob("batch_*.json")):
        luna_rows.extend(load_independent_ai_output(path))
    for path in sorted(args.sol_output_dir.glob("batch_*.json")):
        sol_rows.extend(load_independent_ai_output(path))
    if not luna_rows or not sol_rows:
        raise RuntimeError("Luna and Sol output directories must be non-empty")
    comparisons, audit = compare_rule_luna_sol(samples, luna_rows, sol_rows)
    write_jsonl_atomic(args.comparison_output, comparisons)
    write_json_atomic(args.audit_output, audit)
    _print(audit)
    return 0
