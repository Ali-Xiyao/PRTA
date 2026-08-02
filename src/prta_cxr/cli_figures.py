from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.protocol_freeze import validate_protocol_freeze
from prta_cxr.visualization.paper_figures import (
    build_figure_manifest,
    make_calibration_figure,
    make_case_figure,
    make_confusion_figure,
    make_data_figure,
    make_forest_figure,
    make_heatmap_figure,
    make_pipeline_figure,
    make_scaling_figure,
    read_json,
    select_case_buckets,
)


def _prediction_file(root: Path, name: str) -> Path:
    path = root / "internal_test" / name
    if not path.is_file():
        raise FileNotFoundError(f"formal prediction missing: {path}")
    return path


def _scaling_rows(root: Path) -> list[dict[str, object]]:
    fractions = {
        "D201": 0.10,
        "D202": 0.25,
        "D203": 0.50,
        "D204": 0.75,
        "D205": 1.00,
    }
    output = []
    for experiment_id, fraction in fractions.items():
        matches = list(root.rglob(f"{experiment_id}/training_receipt.json"))
        if len(matches) != 1:
            matches = [
                path
                for path in root.rglob("training_receipt.json")
                if path.parent.name == experiment_id
            ]
        if len(matches) != 1:
            raise ValueError(f"expected one scaling receipt for {experiment_id}")
        receipt = read_json(matches[0])
        if receipt.get("status") != "PASS_TRAINING_FINISHED":
            raise ValueError(f"scaling run incomplete: {experiment_id}")
        output.append(
            {
                "experiment_id": experiment_id,
                "fraction": fraction,
                "macro_f1": float(receipt["best_dev_macro_f1"]),
            }
        )
    return output


def figures_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate frozen PRTA-CXR figures")
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--protocol-freeze", type=Path)
    parser.add_argument("--outcome-session", type=Path)
    parser.add_argument("--predictions-root", type=Path)
    parser.add_argument("--trust-audit", type=Path)
    parser.add_argument("--development-root", type=Path)
    parser.add_argument("--quality-audit", type=Path)
    parser.add_argument("--case-selection", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_FIGURE_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    required = (
        args.protocol_freeze,
        args.outcome_session,
        args.predictions_root,
        args.trust_audit,
        args.development_root,
        args.quality_audit,
        args.case_selection,
        args.output,
    )
    if not all(required):
        parser.error("formal figures require every frozen input and output")
    freeze_raw = read_json(args.protocol_freeze)
    freeze = validate_protocol_freeze(freeze_raw, receipt_path=args.protocol_freeze)
    outcome = read_json(args.outcome_session)
    if outcome.get("status") != "PASS_FORMAL_OUTCOME_PREDICTIONS_FINISHED":
        raise ValueError("formal outcome session is incomplete")
    if outcome.get("protocol_freeze_sha256") != freeze["receipt_file_sha256"]:
        raise ValueError("outcome session does not match protocol freeze")
    trust = read_json(args.trust_audit)
    if trust.get("status") != "PASS_TRUST_AUDITS_FINISHED":
        raise ValueError("trust audit is incomplete")
    if trust.get("protocol_freeze_sha256") != freeze["receipt_file_sha256"]:
        raise ValueError("trust audit does not match protocol freeze")
    case_config = read_json(args.case_selection)
    if case_config.get("manual_cherry_pick") is not False:
        raise ValueError("case-selection contract must forbid manual cherry-picking")
    args.output.mkdir(parents=True, exist_ok=False)
    train_dev = read_jsonl(Path(freeze["input_paths"]["train_dev_manifest"]))
    internal = read_jsonl(
        Path(freeze["input_paths"]["sealed_internal_test_manifest"])
    )
    data_rows = [*train_dev, *internal]
    true_files = [
        _prediction_file(
            args.predictions_root,
            f"B404-S{seed}.true.predictions.jsonl",
        )
        for seed in (17, 29, 43)
    ]
    prta_rows = [row for path in true_files for row in read_jsonl(path)]
    true_seed17 = read_jsonl(true_files[0])
    matched_seed17 = read_jsonl(
        _prediction_file(
            args.predictions_root,
            "B404-S17.matched_wrong_prior.predictions.jsonl",
        )
    )
    query_seed17 = read_jsonl(
        _prediction_file(
            args.predictions_root,
            "B404-S17.wrong_finding_query.predictions.jsonl",
        )
    )
    selected = select_case_buckets(
        true_seed17,
        matched_seed17,
        query_seed17,
        seed=int(case_config["rng_seed"]),
        cases_per_bucket=int(case_config["cases_per_bucket"]),
    )
    case_manifest = args.output / "V708_case_selection.json"
    write_json_atomic(
        case_manifest,
        {
            "schema": "prta-cxr.frozen-case-selection.v1",
            "config": case_config,
            "selected": selected,
        },
    )
    paths = []
    paths.extend(make_pipeline_figure(args.output))
    paths.extend(
        make_data_figure(data_rows, read_json(args.quality_audit), args.output)
    )
    paths.extend(make_scaling_figure(_scaling_rows(args.development_root), args.output))
    paths.extend(make_forest_figure(trust, args.output))
    paths.extend(make_confusion_figure(prta_rows, args.output))
    paths.extend(make_heatmap_figure(prta_rows, args.output))
    paths.extend(make_calibration_figure(prta_rows, args.output))
    paths.extend(make_case_figure(selected, args.output))
    paths.append(case_manifest)
    manifest = build_figure_manifest(
        paths,
        inputs={
            "protocol_freeze": args.protocol_freeze,
            "outcome_session": args.outcome_session,
            "trust_audit": args.trust_audit,
            "quality_audit": args.quality_audit,
            "case_selection": args.case_selection,
            **{
                f"prta_true_seed_{seed}": path
                for seed, path in zip((17, 29, 43), true_files, strict=True)
            },
        },
        case_counts={name: len(rows) for name, rows in selected.items()},
    )
    manifest_path = args.output / "figure_manifest.json"
    write_json_atomic(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0
