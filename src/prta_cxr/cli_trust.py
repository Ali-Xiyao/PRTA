from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.evaluation.progression import hierarchical_patient_bootstrap
from prta_cxr.evaluation.reporting import (
    benjamini_hochberg,
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
    protocol = json.loads(
        Path(freeze["input_paths"]["protocol_config"]).read_text(encoding="utf-8")
    )
    bootstrap_config = protocol["bootstrap"]

    def bootstrap_rows(system_rows):
        output = []
        for system, seed, rows in system_rows:
            patient_sizes = defaultdict(int)
            for row in rows:
                patient_sizes[str(row["patient_id"])] += 1
            for row in rows:
                output.append(
                    {
                        "system": system,
                        "training_seed": seed,
                        "derangement_id": 0,
                        "patient_id": str(row["patient_id"]),
                        "observation_id": str(row["observation_id"]),
                        "target": str(row["target"]),
                        "prediction": str(row["prediction"]),
                        "weight": 1.0 / patient_sizes[str(row["patient_id"])],
                    }
                )
        return output

    main_systems = ("B401", "B402", "B403", "B404")
    seeds = (17, 29, 43)
    main_blocks = []
    for system in main_systems:
        for seed in seeds:
            rows = grouped.get((system, seed, "internal_test"), {}).get("true")
            if rows is None:
                raise ValueError(f"main bootstrap block missing: {system}/{seed}")
            main_blocks.append((system, seed, rows))
    main_bootstrap = hierarchical_patient_bootstrap(
        bootstrap_rows(main_blocks),
        labels=tuple(PROGRESSION_LABELS),
        systems=main_systems,
        seeds=seeds,
        derangements=(0,),
        contrasts={
            "B404_minus_B401": ("B404", "B401"),
            "B404_minus_B402": ("B404", "B402"),
            "B404_minus_B403": ("B404", "B403"),
        },
        replicates=int(bootstrap_config["replicates"]),
        rng_seed=int(bootstrap_config["rng_seed"]),
        minimum_valid_fraction=float(bootstrap_config["minimum_valid_fraction"]),
    )
    intervention_names = (
        "true",
        "current_only",
        "null",
        "random",
        "matched_wrong",
        "reversed",
        "wrong_finding_query",
    )
    intervention_blocks = []
    for condition in intervention_names:
        for seed in seeds:
            rows = grouped.get(("B404", seed, "internal_test"), {}).get(condition)
            if rows is None:
                raise ValueError(
                    f"intervention bootstrap block missing: {condition}/{seed}"
                )
            intervention_blocks.append((condition, seed, rows))
    intervention_bootstrap = hierarchical_patient_bootstrap(
        bootstrap_rows(intervention_blocks),
        labels=tuple(PROGRESSION_LABELS),
        systems=intervention_names,
        seeds=seeds,
        derangements=(0,),
        contrasts={
            f"true_minus_{condition}": ("true", condition)
            for condition in intervention_names
            if condition != "true"
        },
        replicates=int(bootstrap_config["replicates"]),
        rng_seed=int(bootstrap_config["rng_seed"]) + 1,
        minimum_valid_fraction=float(bootstrap_config["minimum_valid_fraction"]),
    )
    p_values = {
        f"main:{name}": value["empirical_two_sided_p"]
        for name, value in main_bootstrap["contrasts"].items()
    }
    p_values.update(
        {
            f"intervention:{name}": value["empirical_two_sided_p"]
            for name, value in intervention_bootstrap["contrasts"].items()
        }
    )
    adjusted = benjamini_hochberg(
        {key: value for key, value in p_values.items() if value is not None}
    )
    result = {
        "schema": "prta-cxr.trust-audit.v1",
        "status": "PASS_TRUST_AUDITS_FINISHED",
        "prediction_files": len(files),
        "summaries": summaries,
        "interventions": interventions,
        "subgroups": subgroups,
        "bootstrap": {
            "main_methods": main_bootstrap,
            "interventions": intervention_bootstrap,
        },
        "multiple_comparison": {
            "method": "benjamini_hochberg",
            "raw_p": p_values,
            "adjusted_p": adjusted,
        },
        "protocol_freeze_sha256": validate_protocol_freeze(
            freeze, receipt_path=args.protocol_freeze
        )["receipt_file_sha256"],
    }
    write_json_atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
