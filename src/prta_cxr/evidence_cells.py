from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.provenance import resolve_source_commit
from prta_cxr.v2_calibration_evidence import (
    EXPECTED_SEEDS,
    _opposite_error,
    _softmax,
    _validated_arrays,
)

CALIBRATION_MODES = ("uncalibrated", "cross_fitted_calibrated")


def _summary(values: Sequence[float | None]) -> dict[str, Any]:
    retained = [float(value) for value in values if value is not None]
    if not retained:
        return {"mean": None, "sd": None, "values": list(values)}
    return {
        "mean": float(np.mean(retained)),
        "sd": (
            float(np.std(retained, ddof=1)) if len(retained) > 1 else None
        ),
        "values": list(values),
    }


def _same_float(values: Sequence[object], *, name: str) -> float:
    converted = [float(value) for value in values]
    if not np.allclose(converted, converted[0], atol=1e-12, rtol=0.0):
        raise ValueError(f"calibration {name} drift across seeds")
    return converted[0]


def _validate_calibration_report(report: Mapping[str, Any]) -> None:
    if report.get("schema") != "prta-cxr.phase20-s1-dev-calibration-evidence.v1":
        raise ValueError("unsupported Slim-S1 calibration evidence schema")
    if report.get("status") != "PASS_PHASE20_S1_DEV_CALIBRATION_COMPLETE":
        raise ValueError("Slim-S1 calibration evidence is not terminal PASS")
    if str(report.get("system")) != "Slim-S1":
        raise ValueError("calibration evidence is not the frozen Slim-S1 system")
    if tuple(int(value) for value in report.get("seeds", ())) != EXPECTED_SEEDS:
        raise ValueError("calibration evidence does not contain the frozen seeds")
    if int(report.get("protected_outcome_read_count", -1)) != 0:
        raise ValueError("calibration evidence opened protected outcomes")
    if bool(report.get("internal_test_opened", True)):
        raise ValueError("calibration evidence opened Internal-test")
    if bool(report.get("selection_performed", True)):
        raise ValueError("calibration evidence performed model selection")
    seed_reports = list(report.get("seed_reports", ()))
    seeds = tuple(int(item.get("seed", -1)) for item in seed_reports)
    if seeds != EXPECTED_SEEDS:
        raise ValueError("calibration seed reports are missing or reordered")


def _load_true_probability_receipt(
    receipt_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != (
        "prta-cxr.phase20-s1-dev-probability-diagnostic.v1"
    ):
        raise ValueError("unsupported Slim-S1 probability diagnostic schema")
    if receipt.get("status") != "PASS_PHASE20_S1_DEV_PROBABILITY_EXPORT":
        raise ValueError("Slim-S1 probability diagnostic is not terminal PASS")
    if (
        receipt.get("variant") != "Slim-S1"
        or receipt.get("probability_export") is not True
    ):
        raise ValueError("probability diagnostic system identity mismatch")
    if receipt.get("internal_test_opened") is not False:
        raise ValueError("probability diagnostic reports Internal-test access")
    if receipt.get("gold_opened") is not False:
        raise ValueError("probability diagnostic reports Gold access")
    if receipt.get("selection_performed") is not False:
        raise ValueError("probability diagnostic reports model selection")
    if receipt.get("protected_outcome_read_count") != 0:
        raise ValueError("probability diagnostic reports protected-outcome access")
    if "true" not in tuple(receipt.get("evaluation_interventions", ())):
        raise ValueError("probability diagnostic does not contain true PRIOR")
    inventory = receipt.get("prediction_blocks", {}).get("true")
    if not isinstance(inventory, Mapping):
        raise ValueError("probability diagnostic true block is missing")
    relative = str(inventory.get("path", ""))
    if relative != Path(relative).name or relative != "true.predictions.jsonl":
        raise ValueError("unsafe or unexpected true prediction path")
    path = receipt_path.parent / relative
    if sha256_file(path) != str(inventory.get("sha256")):
        raise ValueError("true probability prediction block hash mismatch")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != int(inventory.get("rows", -1)):
        raise ValueError("true probability prediction block row mismatch")
    return receipt, rows


def _aggregate_fixed_bins(
    seed_reports: Sequence[Mapping[str, Any]], mode: str
) -> list[dict[str, Any]]:
    blocks = [report[mode]["calibration"]["reliability"] for report in seed_reports]
    if not blocks or any(len(block) != len(blocks[0]) for block in blocks[1:]):
        raise ValueError(f"{mode} fixed-bin count drift")
    rows_per_seed = [int(report["rows"]) for report in seed_reports]
    output = []
    for index, seed_bins in enumerate(zip(*blocks, strict=True)):
        lower = _same_float([item["lower"] for item in seed_bins], name="lower")
        upper = _same_float([item["upper"] for item in seed_bins], name="upper")
        counts = [int(item["count"]) for item in seed_bins]
        accuracy = [item["accuracy"] for item in seed_bins]
        confidence = [item["confidence"] for item in seed_bins]
        contributions = [
            (
                None
                if acc is None or conf is None
                else count / total * abs(float(acc) - float(conf))
            )
            for count, total, acc, conf in zip(
                counts, rows_per_seed, accuracy, confidence, strict=True
            )
        ]
        output.append(
            {
                "bin_index": index,
                "lower": lower,
                "upper": upper,
                "count_per_seed": counts,
                "count_mean": float(np.mean(counts)),
                "accuracy": _summary(accuracy),
                "confidence": _summary(confidence),
                "ece_contribution": _summary(contributions),
            }
        )
    return output


def _aggregate_adaptive_bins(
    seed_reports: Sequence[Mapping[str, Any]], mode: str
) -> list[dict[str, Any]]:
    blocks = [
        report[mode]["calibration"]["adaptive_reliability"]
        for report in seed_reports
    ]
    if not blocks or any(len(block) != len(blocks[0]) for block in blocks[1:]):
        raise ValueError(f"{mode} adaptive-bin count drift")
    output = []
    for index, seed_bins in enumerate(zip(*blocks, strict=True)):
        counts = [int(item["count"]) for item in seed_bins]
        output.append(
            {
                "bin_index": index,
                "count_per_seed": counts,
                "count_mean": float(np.mean(counts)),
                "minimum_confidence": _summary(
                    [item["minimum_confidence"] for item in seed_bins]
                ),
                "maximum_confidence": _summary(
                    [item["maximum_confidence"] for item in seed_bins]
                ),
                "accuracy": _summary([item["accuracy"] for item in seed_bins]),
                "confidence": _summary(
                    [item["confidence"] for item in seed_bins]
                ),
            }
        )
    return output


def _aggregate_classwise_bins(
    seed_reports: Sequence[Mapping[str, Any]], mode: str
) -> list[dict[str, Any]]:
    blocks = [
        report[mode]["calibration"]["classwise_reliability"]
        for report in seed_reports
    ]
    if any(len(block) != len(PROGRESSION_LABELS) for block in blocks):
        raise ValueError(f"{mode} classwise calibration has the wrong labels")
    output = []
    for class_index, label in enumerate(PROGRESSION_LABELS):
        class_blocks = [block[class_index] for block in blocks]
        if any(int(item["class_index"]) != class_index for item in class_blocks):
            raise ValueError(f"{mode} class index drift")
        seed_bins = [item["bins"] for item in class_blocks]
        if any(len(block) != len(seed_bins[0]) for block in seed_bins[1:]):
            raise ValueError(f"{mode} classwise-bin count drift")
        bins = []
        for bin_index, entries in enumerate(zip(*seed_bins, strict=True)):
            lower = _same_float(
                [entry["lower"] for entry in entries], name="class lower"
            )
            upper = _same_float(
                [entry["upper"] for entry in entries], name="class upper"
            )
            counts = [int(entry["count"]) for entry in entries]
            bins.append(
                {
                    "bin_index": bin_index,
                    "lower": lower,
                    "upper": upper,
                    "count_per_seed": counts,
                    "count_mean": float(np.mean(counts)),
                    "frequency": _summary(
                        [entry["frequency"] for entry in entries]
                    ),
                    "probability": _summary(
                        [entry["probability"] for entry in entries]
                    ),
                }
            )
        output.append(
            {
                "class_index": class_index,
                "label": label,
                "ece": _summary([item["ece"] for item in class_blocks]),
                "bins": bins,
            }
        )
    return output


def aggregate_calibration_bins(report: Mapping[str, Any]) -> dict[str, Any]:
    _validate_calibration_report(report)
    seed_reports = list(report["seed_reports"])
    output = {}
    for mode in CALIBRATION_MODES:
        output[mode] = {
            "fixed_width": _aggregate_fixed_bins(seed_reports, mode),
            "adaptive_equal_count": _aggregate_adaptive_bins(seed_reports, mode),
            "classwise_fixed_width": _aggregate_classwise_bins(
                seed_reports, mode
            ),
        }
    return output


def _aligned_seed_rows(
    seed_blocks: Sequence[tuple[int, Sequence[Mapping[str, Any]]]],
) -> list[tuple[int, list[Mapping[str, Any]]]]:
    ordered = sorted((int(seed), list(rows)) for seed, rows in seed_blocks)
    if tuple(seed for seed, _ in ordered) != EXPECTED_SEEDS:
        raise ValueError("joint cells require the frozen S17/S28/S43 exports")
    reference = [
        (
            str(row["observation_id"]),
            str(row["patient_id"]),
            str(row["finding"]),
            str(row["target"]),
        )
        for row in ordered[0][1]
    ]
    for _, rows in ordered[1:]:
        identity = [
            (
                str(row["observation_id"]),
                str(row["patient_id"]),
                str(row["finding"]),
                str(row["target"]),
            )
            for row in rows
        ]
        if identity != reference:
            raise ValueError("joint-cell cohort identity drift across seeds")
    return ordered


def aggregate_finding_progression_cells(
    seed_blocks: Sequence[tuple[int, Sequence[Mapping[str, Any]]]],
    *,
    minimum_rows: int = 30,
    minimum_patients: int = 20,
) -> dict[str, Any]:
    if minimum_rows < 1 or minimum_patients < 1:
        raise ValueError("joint-cell publication thresholds must be positive")
    ordered = _aligned_seed_rows(seed_blocks)
    findings = sorted({str(row["finding"]) for row in ordered[0][1]})
    seed_values = {}
    for seed, rows in ordered:
        logits, targets = _validated_arrays(rows)
        probabilities = _softmax(logits)
        predictions = probabilities.argmax(axis=1)
        opposite = _opposite_error(targets, predictions)
        seed_values[seed] = (rows, probabilities, predictions, opposite)

    cells = []
    for finding in findings:
        for label_index, label in enumerate(PROGRESSION_LABELS):
            metrics = []
            row_count = None
            patient_count = None
            for seed, _ in ordered:
                rows, probabilities, predictions, opposite = seed_values[seed]
                selected = np.asarray(
                    [
                        str(row["finding"]) == finding
                        and str(row["target"]) == label
                        for row in rows
                    ],
                    dtype=bool,
                )
                current_rows = int(selected.sum())
                current_patients = len(
                    {
                        str(row["patient_id"])
                        for row, keep in zip(rows, selected, strict=True)
                        if keep
                    }
                )
                if row_count is None:
                    row_count = current_rows
                    patient_count = current_patients
                elif (row_count, patient_count) != (
                    current_rows,
                    current_patients,
                ):
                    raise ValueError("joint-cell membership drift across seeds")
                if current_rows:
                    metrics.append(
                        {
                            "seed": seed,
                            "recall": float(
                                (predictions[selected] == label_index).mean()
                            ),
                            "mean_confidence": float(
                                probabilities[selected].max(axis=1).mean()
                            ),
                            "opposite_direction_error_rate": float(
                                opposite[selected].mean()
                            ),
                        }
                    )
                else:
                    metrics.append(
                        {
                            "seed": seed,
                            "recall": None,
                            "mean_confidence": None,
                            "opposite_direction_error_rate": None,
                        }
                    )
            assert row_count is not None and patient_count is not None
            suppressed = (
                row_count < minimum_rows or patient_count < minimum_patients
            )
            cells.append(
                {
                    "finding": finding,
                    "progression_label": label,
                    "rows": row_count,
                    "patients": patient_count,
                    "suppressed": suppressed,
                    "suppression_reason": (
                        "rows_or_patients_below_publication_threshold"
                        if suppressed
                        else None
                    ),
                    "recall": (
                        None
                        if suppressed
                        else _summary([item["recall"] for item in metrics])
                    ),
                    "mean_confidence": (
                        None
                        if suppressed
                        else _summary(
                            [item["mean_confidence"] for item in metrics]
                        )
                    ),
                    "opposite_direction_error_rate": (
                        None
                        if suppressed
                        else _summary(
                            [
                                item["opposite_direction_error_rate"]
                                for item in metrics
                            ]
                        )
                    ),
                }
            )
    return {
        "findings": findings,
        "progression_labels": list(PROGRESSION_LABELS),
        "expected_cells": len(findings) * len(PROGRESSION_LABELS),
        "observed_cells": len(cells),
        "minimum_rows": minimum_rows,
        "minimum_patients": minimum_patients,
        "suppressed_cells": sum(bool(cell["suppressed"]) for cell in cells),
        "cells": cells,
    }


def _format_metric(metric: Mapping[str, Any] | None) -> str:
    if metric is None or metric.get("mean") is None:
        return "suppressed"
    if metric.get("sd") is None:
        return f"{float(metric['mean']):.6f}"
    return f"{float(metric['mean']):.6f} ± {float(metric['sd']):.6f}"


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# PRTA-CXR calibration bins and finding × progression cells",
        "",
        f"Status: `{report['status']}`  ",
        f"Seeds: `{report['seeds']}`  ",
        "Cohort: frozen selection-Dev only; aggregate-only descriptive evidence.",
        "",
    ]
    for mode in CALIBRATION_MODES:
        lines.extend(
            [
                f"## Reliability: {mode}",
                "",
                "| Bin | Range | Count/seed | Accuracy | Confidence |",
                "|---:|---|---|---:|---:|",
            ]
        )
        for cell in report["calibration_bins"][mode]["fixed_width"]:
            lines.append(
                f"| {cell['bin_index']} | ({cell['lower']:.4f}, "
                f"{cell['upper']:.4f}] | {cell['count_per_seed']} | "
                f"{_format_metric(cell['accuracy'])} | "
                f"{_format_metric(cell['confidence'])} |"
            )
        lines.append("")
    joint = report["finding_progression"]
    lines.extend(
        [
            "## Finding × progression",
            "",
            (
                f"Publication threshold: rows ≥ {joint['minimum_rows']} and "
                f"patients ≥ {joint['minimum_patients']}."
            ),
            "",
            "| Finding | Progression | Rows | Patients | Recall | ODER |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for cell in joint["cells"]:
        lines.append(
            f"| {cell['finding']} | {cell['progression_label']} | "
            f"{cell['rows']} | {cell['patients']} | "
            f"{_format_metric(cell['recall'])} | "
            f"{_format_metric(cell['opposite_direction_error_rate'])} |"
        )
    lines.extend(
        [
            "",
            "Counts describe the same frozen cohort for each seed and are not summed.",
            "Suppressed cells must remain blank in public heatmaps.",
            (
                "No patient-level rows, identifiers, images, reports, or "
                "predictions are included."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def evidence_cells_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build aggregate-only calibration and joint subgroup cells"
    )
    parser.add_argument("--calibration-evidence", type=Path, required=True)
    parser.add_argument(
        "--diagnostic-receipt", type=Path, action="append", required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-cell-rows", type=int, default=30)
    parser.add_argument("--minimum-cell-patients", type=int, default=20)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    calibration_report = json.loads(
        args.calibration_evidence.read_text(encoding="utf-8")
    )
    calibration_bins = aggregate_calibration_bins(calibration_report)
    loaded = [
        (path, *_load_true_probability_receipt(path))
        for path in args.diagnostic_receipt
    ]
    ordered = sorted(loaded, key=lambda value: int(value[1]["seed"]))
    joint = aggregate_finding_progression_cells(
        [(int(receipt["seed"]), rows) for _, receipt, rows in ordered],
        minimum_rows=args.minimum_cell_rows,
        minimum_patients=args.minimum_cell_patients,
    )
    report = {
        "schema": "prta-cxr.calibration-joint-cells.v1",
        "status": "PASS_CALIBRATION_JOINT_CELLS_COMPLETE",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "paper_method": "PRTA-CXR",
        "system_identity": "Slim-S1",
        "seeds": list(EXPECTED_SEEDS),
        "rows_per_seed": [len(rows) for _, _, rows in ordered],
        "calibration_evidence_sha256": sha256_file(args.calibration_evidence),
        "diagnostic_receipts": [
            {
                "seed": int(receipt["seed"]),
                "sha256": sha256_file(path),
                "checkpoint_sha256": str(receipt["checkpoint_sha256"]),
            }
            for path, receipt, _ in ordered
        ],
        "calibration_bins": calibration_bins,
        "finding_progression": joint,
        "privacy": {
            "aggregate_only": True,
            "patient_identifiers_published": False,
            "patient_level_predictions_published": False,
            "minimum_cell_rows": args.minimum_cell_rows,
            "minimum_cell_patients": args.minimum_cell_patients,
        },
        "descriptive_only": True,
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    if staging.exists():
        raise FileExistsError(f"evidence staging exists: {staging}")
    staging.mkdir(parents=True, exist_ok=False)
    json_path = staging / "calibration_joint_cells.json"
    markdown_path = staging / "calibration_joint_cells.md"
    _write_new(
        json_path,
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    _write_new(markdown_path, _markdown(report))
    manifest = {
        "schema": "prta-cxr.calibration-joint-cells-manifest.v1",
        "status": report["status"],
        "files": {
            json_path.name: sha256_file(json_path),
            markdown_path.name: sha256_file(markdown_path),
        },
        "patient_level_predictions_published": False,
        "protected_outcome_read_count": 0,
    }
    _write_new(
        staging / "manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    staging.replace(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0
