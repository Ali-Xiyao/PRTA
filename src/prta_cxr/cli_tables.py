from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.protocol_freeze import validate_protocol_freeze
from prta_cxr.reporting.paper_tables import (
    data_table,
    intervention_result,
    method_result,
    render_markdown,
    wilson_interval,
)
from prta_cxr.run_registry import read_run_registry


def _scaling(registry_path: Path) -> list[dict[str, object]]:
    fractions = {"D201": 0.10, "D202": 0.25, "D203": 0.50, "D204": 0.75, "D205": 1.0}
    registry = {
        str(row["experiment_id"]): row
        for row in read_run_registry(registry_path)
    }
    output = []
    for experiment_id, fraction in fractions.items():
        row = registry.get(experiment_id)
        if row is None or row["status"] != "PASS_TRAINING_FINISHED":
            raise ValueError(f"scaling run is incomplete: {experiment_id}")
        receipt = json.loads(Path(row["metrics_path"]).read_text(encoding="utf-8"))
        audit = receipt["fraction_audit"]
        patients = audit.get("selected_patients", audit.get("patients"))
        rows = audit.get("selected_rows", audit.get("rows"))
        if patients is None or rows is None:
            raise ValueError(f"scaling receipt counts missing: {experiment_id}")
        output.append(
            {
                "experiment_id": experiment_id,
                "fraction": fraction,
                "patients": int(patients),
                "rows": int(rows),
                "macro_f1": float(receipt["best_dev_macro_f1"]),
            }
        )
    return output


def paper_tables_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build frozen PRTA-CXR paper tables")
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--protocol-freeze", type=Path)
    parser.add_argument("--outcome-session", type=Path)
    parser.add_argument("--trust-audit", type=Path)
    parser.add_argument("--figure-manifest", type=Path)
    parser.add_argument("--vlm-result", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_PAPER_TABLES_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    required = (
        args.protocol_freeze,
        args.outcome_session,
        args.trust_audit,
        args.figure_manifest,
        args.vlm_result,
        args.output,
    )
    if not all(required):
        parser.error("formal tables require every frozen upstream artifact")
    freeze_raw = json.loads(args.protocol_freeze.read_text(encoding="utf-8"))
    freeze = validate_protocol_freeze(freeze_raw, receipt_path=args.protocol_freeze)
    outcome = json.loads(args.outcome_session.read_text(encoding="utf-8"))
    trust = json.loads(args.trust_audit.read_text(encoding="utf-8"))
    figures = json.loads(args.figure_manifest.read_text(encoding="utf-8"))
    vlm = json.loads(args.vlm_result.read_text(encoding="utf-8"))
    expected = freeze["receipt_file_sha256"]
    if outcome.get("protocol_freeze_sha256") != expected:
        raise ValueError("outcome session does not match protocol freeze")
    if trust.get("protocol_freeze_sha256") != expected:
        raise ValueError("trust audit does not match protocol freeze")
    if figures.get("status") != "PASS_PAPER_FIGURES_FINISHED":
        raise ValueError("paper figures are incomplete")
    if vlm.get("status") != "PASS_VLM_ADDITIONAL_FINISHED":
        raise ValueError("VLM additional deployment is incomplete")
    if vlm.get("protocol_freeze_sha256") != expected:
        raise ValueError("VLM result does not match protocol freeze")
    quality = json.loads(
        Path(freeze["input_paths"]["quality_audit"]).read_text(encoding="utf-8")
    )
    successes = round(float(quality["silver_accuracy"]) * int(quality["reviewed_rows"]))
    lower, upper = wilson_interval(successes, int(quality["reviewed_rows"]))
    train_dev = read_jsonl(Path(freeze["input_paths"]["train_dev_manifest"]))
    internal = read_jsonl(Path(freeze["input_paths"]["sealed_internal_test_manifest"]))
    main = [method_result(trust, system) for system in ("B401", "B402", "B403", "B404")]
    strongest = max(main[:-1], key=lambda row: row["macro_f1"])
    bundle = {
        "schema": "prta-cxr.paper-tables.v1",
        "status": "PASS_PAPER_TABLES_FINISHED",
        "table1_data": data_table([*train_dev, *internal]),
        "table2_quality": {**quality, "ci_lower": lower, "ci_upper": upper},
        "table3_main": main,
        "table4_scaling": _scaling(Path(freeze["run_registry_path"])),
        "table5_ablations": [
            method_result(trust, system)
            for system in ("B404", "A501", "A502", "A503", "A504", "A505", "A506")
        ],
        "table6_interventions": [
            intervention_result(trust, condition)
            for condition in (
                "true",
                "current_only",
                "null",
                "random",
                "matched_wrong",
                "reversed",
                "wrong_finding_query",
            )
        ],
        "table7_calibration": [strongest, main[-1]],
        "table8_vlm": vlm,
        "gold_main": [
            method_result(trust, system, cohort="gold")
            for system in ("B401", "B402", "B403", "B404")
        ],
        "strongest_baseline": strongest["system"],
        "test_or_gold_used_for_model_selection": False,
    }
    args.output.mkdir(parents=True, exist_ok=False)
    bundle_path = args.output / "paper_tables.json"
    write_json_atomic(bundle_path, bundle)
    markdown_path = args.output / "PRTA_CXR_论文正式结果表_CN.md"
    markdown_path.write_text(render_markdown(bundle), encoding="utf-8")
    receipt = {
        "schema": "prta-cxr.paper-finalization.v1",
        "status": "PASS_PAPER_RESULT_PACKAGE_FINISHED",
        "protocol_freeze_sha256": expected,
        "paper_tables_sha256": sha256_file(bundle_path),
        "markdown_sha256": sha256_file(markdown_path),
        "figure_manifest_sha256": sha256_file(args.figure_manifest),
        "vlm_result_sha256": sha256_file(args.vlm_result),
        "test_or_gold_used_for_model_selection": False,
        "rule_labels_used_for_training": False,
    }
    write_json_atomic(args.output / "finalization_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
