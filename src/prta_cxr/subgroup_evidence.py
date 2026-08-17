from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.data.training_dataset import read_jsonl
from prta_cxr.evaluation.calibration import calibration_metrics
from prta_cxr.provenance import resolve_source_commit
from prta_cxr.v2_calibration_evidence import (
    EXPECTED_SEEDS,
    _load_probability_receipt,
    _opposite_error,
    _softmax,
    _validated_arrays,
)

SYSTEMS = ("V2", "B401", "TILA8", "IF-F01", "IF-F02")
AXES = (
    "progression_label",
    "finding",
    "source",
    "current_view",
    "view_relation",
    "interval_bin",
    "class_rarity",
)


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _interval_bin(row: Mapping[str, Any]) -> str:
    if not bool(row.get("calendar_interval_available", False)):
        return "ordinal_or_unknown"
    value = float(row.get("interval_days", -1.0))
    for bound in (7, 30, 90, 365):
        if value <= bound:
            return f"le_{bound}_days"
    return "gt_365_days"


def class_rarity_map(split_rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    labels = [
        str(row["progression_label"])
        for row in split_rows
        if row.get("split") == "train"
    ]
    counts = Counter(labels)
    if not labels or set(counts) != set(PROGRESSION_LABELS):
        raise ValueError("Train split does not cover all progression labels")
    total = len(labels)
    return {
        label: "rare_lt_5pct" if counts[label] / total < 0.05 else "common_ge_5pct"
        for label in PROGRESSION_LABELS
    }


def _group_value(row: Mapping[str, Any], axis: str, rarity: Mapping[str, str]) -> str:
    if axis == "progression_label":
        return str(row["target"])
    if axis in {"finding", "source", "current_view"}:
        return str(row.get(axis, "unknown"))
    if axis == "view_relation":
        return (
            "matched"
            if str(row.get("prior_view", "unknown"))
            == str(row.get("current_view", "unknown"))
            else "mismatched"
        )
    if axis == "interval_bin":
        return _interval_bin(row)
    if axis == "class_rarity":
        return rarity[str(row["target"])]
    raise ValueError(f"unsupported subgroup axis: {axis}")


def subgroup_metrics(
    rows: Sequence[Mapping[str, Any]], probabilities: np.ndarray
) -> dict[str, Any]:
    _, targets = _validated_arrays(rows)
    if probabilities.shape != (len(rows), len(PROGRESSION_LABELS)):
        raise ValueError("subgroup probabilities have the wrong shape")
    predictions = probabilities.argmax(axis=1)
    correct = predictions == targets
    supported = np.unique(targets)
    f1_values = []
    for label in supported:
        true_positive = np.sum((targets == label) & (predictions == label))
        false_positive = np.sum((targets != label) & (predictions == label))
        false_negative = np.sum((targets == label) & (predictions != label))
        denominator = 2 * true_positive + false_positive + false_negative
        f1_values.append(0.0 if denominator == 0 else 2 * true_positive / denominator)
    calibration = calibration_metrics(probabilities, targets, bins=15)
    return {
        "rows": len(rows),
        "patients": len({str(row["patient_id"]) for row in rows}),
        "accuracy": float(correct.mean()),
        "error_rate": float(1.0 - correct.mean()),
        "supported_class_macro_f1": float(np.mean(f1_values)),
        "supported_classes": [PROGRESSION_LABELS[int(index)] for index in supported],
        "mean_confidence": float(probabilities.max(axis=1).mean()),
        "nll": float(calibration["nll"]),
        "brier": float(calibration["brier"]),
        "ece": float(calibration["ece"]),
        "opposite_direction_error_rate": float(
            _opposite_error(targets, predictions).mean()
        ),
    }


def evaluate_seed_subgroups(
    rows: Sequence[Mapping[str, Any]], rarity: Mapping[str, str]
) -> dict[str, Any]:
    logits, _ = _validated_arrays(rows)
    probabilities = _softmax(logits)
    output: dict[str, Any] = {}
    for axis in AXES:
        grouped: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            grouped[_group_value(row, axis, rarity)].append(index)
        output[axis] = {
            name: subgroup_metrics(
                [rows[index] for index in indices], probabilities[indices]
            )
            for name, indices in sorted(grouped.items())
        }
    return output


def aggregate_subgroups(seed_reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    metrics = (
        "accuracy",
        "error_rate",
        "supported_class_macro_f1",
        "mean_confidence",
        "nll",
        "brier",
        "ece",
        "opposite_direction_error_rate",
    )
    for axis in AXES:
        names = set(seed_reports[0][axis])
        if any(set(report[axis]) != names for report in seed_reports[1:]):
            raise ValueError(f"subgroup membership drift across seeds: {axis}")
        output[axis] = {}
        for name in sorted(names):
            entry = {
                "rows": int(seed_reports[0][axis][name]["rows"]),
                "patients": int(seed_reports[0][axis][name]["patients"]),
                "metrics": {},
            }
            for metric in metrics:
                values = [float(report[axis][name][metric]) for report in seed_reports]
                entry["metrics"][metric] = {
                    "mean": float(np.mean(values)),
                    "sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
                    "values": values,
                }
            output[axis][name] = entry
    return output


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# Frozen {report['system']} Dev subgroup and long-tail evidence",
        "",
        f"Status: `{report['status']}`  ",
        f"Seeds: `{report['seeds']}`  ",
        "Cohort: frozen Dev only; descriptive analysis; no subgroup model selection.",
        "",
    ]
    for axis in AXES:
        lines.extend(
            [
                f"## {axis}",
                "",
                (
                    "| Group | Rows | Patients | Accuracy | Error | Macro-F1* | "
                    "NLL | ECE | ODER |"
                ),
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for name, entry in report["aggregate"][axis].items():
            metric = entry["metrics"]

            def cell(key: str, values: Mapping[str, Any] = metric) -> str:
                value = values[key]
                if value["sd"] is None:
                    return f"{value['mean']:.6f}"
                return f"{value['mean']:.6f} ± {value['sd']:.6f}"

            lines.append(
                f"| {name} | {entry['rows']} | {entry['patients']} | "
                f"{cell('accuracy')} | {cell('error_rate')} | "
                f"{cell('supported_class_macro_f1')} | {cell('nll')} | "
                f"{cell('ece')} | {cell('opposite_direction_error_rate')} |"
            )
        lines.append("")
    lines.extend(
        [
            (
                "*Macro-F1 is averaged over target classes supported inside that "
                "subgroup; it is"
            ),
            "not directly interchangeable with the full-cohort five-class Macro-F1.",
            "",
            (
                "No p-values are reported because subgroup analyses are descriptive "
                "and are not"
            ),
            "used to modify the frozen model.",
            "",
        ]
    )
    return "\n".join(lines)


def subgroup_evidence_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate frozen Dev subgroup and long-tail evidence"
    )
    parser.add_argument(
        "--diagnostic-receipt", type=Path, action="append", required=True
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--system", choices=SYSTEMS, default="V2")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    loaded = [
        _load_probability_receipt(path, expected_system=args.system)
        for path in args.diagnostic_receipt
    ]
    seeds = tuple(sorted(int(receipt["seed"]) for receipt, _ in loaded))
    if args.smoke:
        if len(seeds) != 1:
            parser.error("--smoke requires exactly one seed")
    elif seeds != EXPECTED_SEEDS:
        parser.error(f"formal evidence requires seeds {EXPECTED_SEEDS}")
    split_rows = read_jsonl(args.split_manifest)
    if {str(row.get("split")) for row in split_rows} - {"train", "dev"}:
        raise ValueError("subgroup split manifest contains a protected split")
    rarity = class_rarity_map(split_rows)
    seed_reports = []
    for receipt, blocks in sorted(loaded, key=lambda value: int(value[0]["seed"])):
        true_rows = blocks["true"]
        seed_reports.append(
            {
                "seed": int(receipt["seed"]),
                "checkpoint_sha256": str(receipt["checkpoint_sha256"]),
                "subgroups": evaluate_seed_subgroups(true_rows, rarity),
            }
        )
    aggregate = aggregate_subgroups([report["subgroups"] for report in seed_reports])
    status = (
        "PASS_DEV_SUBGROUP_EVIDENCE_SMOKE"
        if args.smoke
        else "PASS_DEV_SUBGROUP_EVIDENCE_COMPLETE"
    )
    report = {
        "schema": "prta-cxr.dev-subgroup-evidence.v1",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "system": args.system,
        "seeds": list(seeds),
        "axes": list(AXES),
        "class_rarity_threshold": "Train prevalence < 5%",
        "class_rarity_map": rarity,
        "split_manifest_sha256": sha256_file(args.split_manifest),
        "diagnostic_receipts": [
            {"path": str(path), "sha256": sha256_file(path)}
            for path in args.diagnostic_receipt
        ],
        "seed_reports": seed_reports,
        "aggregate": aggregate,
        "descriptive_only": True,
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    if staging.exists():
        raise FileExistsError(f"subgroup evidence staging exists: {staging}")
    staging.mkdir(parents=True, exist_ok=False)
    json_path = staging / "dev_subgroup_evidence.json"
    _write_new_json(json_path, report)
    markdown_path = staging / "dev_subgroup_evidence.md"
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    manifest = {
        "schema": "prta-cxr.dev-subgroup-manifest.v1",
        "status": status,
        "files": {
            json_path.name: sha256_file(json_path),
            markdown_path.name: sha256_file(markdown_path),
        },
        "internal_test_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "manifest.json", manifest)
    staging.replace(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0
