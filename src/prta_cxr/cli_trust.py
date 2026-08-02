from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.evaluation.reporting import (
    intervention_comparison,
    prediction_summary,
    subgroup_summary,
)
from prta_cxr.protocol_freeze import validate_protocol_freeze


def trust_audits_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize frozen trust predictions")
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--predictions-root", type=Path)
    parser.add_argument("--protocol-freeze", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_TRUST_AUDIT_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not all((args.predictions_root, args.protocol_freeze, args.output)):
        parser.error("formal trust audit requires predictions/freeze/output")
    freeze = json.loads(args.protocol_freeze.read_text(encoding="utf-8"))
    validate_protocol_freeze(freeze, receipt_path=args.protocol_freeze)
    files = sorted(args.predictions_root.rglob("*.predictions.jsonl"))
    if not files:
        raise ValueError("no frozen prediction files found")
    grouped = defaultdict(dict)
    summaries = {}
    subgroups = {}
    for path in files:
        rows = read_jsonl(path)
        first = rows[0]
        condition = (
            "wrong_finding_query"
            if first["query_finding"] != first["finding"]
            else str(first["prior_intervention"])
        )
        key = (
            str(first["system"]),
            int(first["training_seed"]),
            str(first["cohort"]),
        )
        if condition in grouped[key]:
            raise ValueError("duplicate prediction condition")
        grouped[key][condition] = rows
        summary_key = "|".join(map(str, (*key, condition)))
        summaries[summary_key] = prediction_summary(rows)
        if condition == "true":
            subgroups[summary_key] = {
                name: subgroup_summary(rows, name)
                for name in ("source", "finding", "current_view", "interval_bin")
            }
    interventions = {}
    for key, conditions in grouped.items():
        if "true" not in conditions:
            continue
        for condition, rows in conditions.items():
            if condition == "true":
                continue
            comparison_key = "|".join(map(str, (*key, condition)))
            interventions[comparison_key] = intervention_comparison(
                conditions["true"], rows
            )
    result = {
        "schema": "prta-cxr.trust-audit.v1",
        "status": "PASS_TRUST_AUDITS_FINISHED",
        "prediction_files": len(files),
        "summaries": summaries,
        "interventions": interventions,
        "subgroups": subgroups,
        "protocol_freeze_sha256": validate_protocol_freeze(
            freeze, receipt_path=args.protocol_freeze
        )["receipt_file_sha256"],
    }
    write_json_atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
