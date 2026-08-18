from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.evaluation.calibration import (
    binary_detection_metrics,
    calibration_metrics,
    fit_temperature,
    referral_metrics,
    risk_coverage_metrics,
)
from prta_cxr.evaluation.progression import (
    deterministic_patient_folds,
    metrics_from_confusion,
)
from prta_cxr.provenance import resolve_source_commit

INTERVENTIONS = ("true", "matched_hard", "null", "reversed")
EXPECTED_SEEDS = (17, 28, 43)
COVERAGES = (1.0, 0.95, 0.9, 0.8, 0.7)
REFERRAL_FRACTIONS = (0.05, 0.1, 0.2)


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    values = np.exp(shifted)
    return values / values.sum(axis=1, keepdims=True)


def _label_indices(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    label_index = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
    return np.asarray([label_index[str(row["target"])] for row in rows], dtype=int)


def _validated_arrays(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    logits = np.asarray([row["logits"] for row in rows], dtype=np.float64)
    targets = _label_indices(rows)
    if logits.shape != (len(rows), len(PROGRESSION_LABELS)):
        raise ValueError("probability export logits have the wrong shape")
    if not np.isfinite(logits).all():
        raise ValueError("probability export logits must be finite")
    probabilities = _softmax(logits)
    for index, row in enumerate(rows):
        retained = np.asarray(row["probabilities"], dtype=np.float64)
        if not np.allclose(retained, probabilities[index], atol=1e-6):
            raise ValueError("retained probabilities do not match raw logits")
        prediction = PROGRESSION_LABELS[int(probabilities[index].argmax())]
        if prediction != str(row["prediction"]):
            raise ValueError("retained prediction does not match raw logits")
    return logits, targets


def cross_fitted_temperature_probabilities(
    rows_by_intervention: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    fold_count: int = 5,
) -> dict[str, Any]:
    if "true" not in rows_by_intervention:
        raise ValueError("probability evidence requires a true PRIOR block")
    interventions = tuple(rows_by_intervention)
    true_rows = list(rows_by_intervention["true"])
    records = [
        {
            "patient_id_hash": str(row["patient_id"]),
            "progression_label": str(row["target"]),
        }
        for row in true_rows
    ]
    assignment = deterministic_patient_folds(
        records,
        labels=PROGRESSION_LABELS,
        fold_count=fold_count,
        salt="prta-cxr-v2-calibration-v1",
    )
    fold_by_row = np.asarray(
        [assignment[str(row["patient_id"])] for row in true_rows], dtype=int
    )
    true_logits, targets = _validated_arrays(true_rows)
    all_logits = {}
    true_ids = [str(row["observation_id"]) for row in true_rows]
    for intervention in interventions:
        rows = list(rows_by_intervention[intervention])
        if [str(row["observation_id"]) for row in rows] != true_ids:
            raise ValueError("intervention probability rows are not aligned")
        logits, intervention_targets = _validated_arrays(rows)
        if not np.array_equal(intervention_targets, targets):
            raise ValueError("intervention targets are not aligned")
        all_logits[intervention] = logits

    calibrated = {
        intervention: np.zeros_like(all_logits[intervention])
        for intervention in interventions
    }
    temperatures = []
    fold_audit = []
    for fold in range(fold_count):
        held_out = fold_by_row == fold
        training = ~held_out
        temperature = fit_temperature(
            torch.as_tensor(true_logits[training], dtype=torch.float64),
            torch.as_tensor(targets[training], dtype=torch.long),
        )
        temperatures.append(temperature)
        for intervention in interventions:
            calibrated[intervention][held_out] = _softmax(
                all_logits[intervention][held_out] / temperature
            )
        held_patients = {
            str(row["patient_id"])
            for row, selected in zip(true_rows, held_out, strict=True)
            if selected
        }
        fold_audit.append(
            {
                "fold": fold,
                "temperature": temperature,
                "held_out_rows": int(held_out.sum()),
                "held_out_patients": len(held_patients),
            }
        )
    return {
        "probabilities": calibrated,
        "targets": targets,
        "fold_by_row": fold_by_row,
        "temperatures": temperatures,
        "fold_audit": fold_audit,
        "fold_assignment_sha256": canonical_sha256(dict(sorted(assignment.items()))),
    }


def _selective_classification(
    probabilities: np.ndarray,
    targets: np.ndarray,
    uncertainty: np.ndarray,
) -> dict[str, Any]:
    order = np.argsort(uncertainty, kind="stable")
    predictions = probabilities.argmax(axis=1)
    total_support = np.bincount(targets, minlength=len(PROGRESSION_LABELS))
    output = {}
    for coverage in COVERAGES:
        retained_count = min(len(targets), max(1, math.ceil(coverage * len(targets))))
        retained = order[:retained_count]
        confusion = np.zeros(
            (len(PROGRESSION_LABELS), len(PROGRESSION_LABELS)), dtype=float
        )
        for target, prediction in zip(
            targets[retained], predictions[retained], strict=True
        ):
            confusion[target, prediction] += 1
        metrics = metrics_from_confusion(
            confusion, labels=PROGRESSION_LABELS, require_all_labels=False
        )
        retained_support = np.bincount(
            targets[retained], minlength=len(PROGRESSION_LABELS)
        )
        output[str(coverage)] = {
            "requested_coverage": coverage,
            "rows": retained_count,
            "realized_coverage": retained_count / len(targets),
            "metrics": metrics,
            "class_coverage": {
                label: (
                    None
                    if total_support[index] == 0
                    else float(retained_support[index] / total_support[index])
                )
                for index, label in enumerate(PROGRESSION_LABELS)
            },
        }
    return output


def _opposite_error(targets: np.ndarray, predictions: np.ndarray) -> np.ndarray:
    index = {label: offset for offset, label in enumerate(PROGRESSION_LABELS)}
    pairs = {
        (index["Improved"], index["Worse"]),
        (index["Worse"], index["Improved"]),
        (index["New"], index["Resolved"]),
        (index["Resolved"], index["New"]),
    }
    return np.asarray(
        [
            (int(target), int(prediction)) in pairs
            for target, prediction in zip(targets, predictions, strict=True)
        ],
        dtype=bool,
    )


def _uncertainty_summary(
    probabilities: Mapping[str, np.ndarray], targets: np.ndarray
) -> dict[str, Any]:
    true = probabilities["true"]
    true_prediction = true.argmax(axis=1)
    wrong = true_prediction != targets
    msp = 1.0 - true.max(axis=1)
    entropy = -np.sum(true * np.log(np.clip(true, 1e-12, 1.0)), axis=1) / math.log(
        true.shape[1]
    )
    events = {
        "final_prediction_error": wrong,
        "opposite_direction_error": _opposite_error(targets, true_prediction),
    }
    scores = {
        "msp_uncertainty": msp,
        "normalized_entropy": entropy,
    }
    definitions = {
        "msp_uncertainty": "1 - maximum calibrated class probability",
        "normalized_entropy": "predictive entropy divided by log(K)",
    }
    has_prior_stress = all(name in probabilities for name in INTERVENTIONS)
    if has_prior_stress:
        prior_sensitivity = np.maximum.reduce(
            [
                0.5 * np.abs(true - probabilities[name]).sum(axis=1)
                for name in ("matched_hard", "null", "reversed")
            ]
        )
        reversal_inconsistency = 0.5 * np.abs(true - probabilities["reversed"]).sum(
            axis=1
        )
        true_correct = ~wrong
        wrong_prior_sensitive = np.zeros(len(targets), dtype=bool)
        for name in ("matched_hard", "null", "reversed"):
            wrong_prior_sensitive |= true_correct & (
                probabilities[name].argmax(axis=1) != targets
            )
        events["wrong_prior_sensitivity"] = wrong_prior_sensitive
        scores["prior_sensitivity_max_tv"] = prior_sensitivity
        scores["reversal_inconsistency_tv"] = reversal_inconsistency
        definitions.update(
            {
                "prior_sensitivity_max_tv": (
                    "maximum total-variation distance from true PRIOR over "
                    "matched-hard/null/reversed"
                ),
                "reversal_inconsistency_tv": (
                    "total-variation distance between true and reversed "
                    "PRIOR predictions"
                ),
            }
        )
    output = {
        "score_definitions": definitions,
        "prior_stress_scores_evaluated": has_prior_stress,
        "error_detection": {
            score_name: {
                event_name: binary_detection_metrics(score, event)
                for event_name, event in events.items()
            }
            for score_name, score in scores.items()
        },
        "referral": {
            score_name: referral_metrics(
                score, wrong, referral_fractions=REFERRAL_FRACTIONS
            )
            for score_name, score in scores.items()
        },
        "selective_prediction": {
            score_name: _selective_classification(true, targets, score)
            for score_name, score in scores.items()
        },
        "combined_uncertainty": {
            "evaluated": False,
            "reason": "no combined score was preregistered before outcome analysis",
        },
    }
    if has_prior_stress:
        reversed_prediction = probabilities["reversed"].argmax(axis=1)
        output["reversed_prediction_flip_rate"] = float(
            np.mean(reversed_prediction != true_prediction)
        )
    else:
        output["prior_stress_unavailable_reason"] = (
            "receipt contains true PRIOR only; no PRIOR score was reconstructed"
        )
    return output


def _three_seed_disagreement(
    probabilities_by_seed: Sequence[np.ndarray], targets: np.ndarray
) -> dict[str, Any]:
    if len(probabilities_by_seed) != len(EXPECTED_SEEDS):
        raise ValueError("seed disagreement requires exactly three seeds")
    stack = np.stack(probabilities_by_seed)
    if stack.ndim != 3 or stack.shape[1:] != (
        len(targets),
        len(PROGRESSION_LABELS),
    ):
        raise ValueError("seed probability arrays do not align")
    pairwise_tv = [
        0.5 * np.abs(stack[left] - stack[right]).sum(axis=1)
        for left, right in combinations(range(len(probabilities_by_seed)), 2)
    ]
    mean_pairwise_tv = np.mean(pairwise_tv, axis=0)
    votes = stack.argmax(axis=2)
    vote_disagreement = np.asarray(
        [
            1.0
            - np.bincount(votes[:, index], minlength=len(PROGRESSION_LABELS)).max()
            / len(probabilities_by_seed)
            for index in range(len(targets))
        ]
    )
    ensemble = stack.mean(axis=0)
    ensemble_prediction = ensemble.argmax(axis=1)
    events = {
        "ensemble_prediction_error": ensemble_prediction != targets,
        "ensemble_opposite_direction_error": _opposite_error(
            targets, ensemble_prediction
        ),
    }
    scores = {
        "mean_pairwise_total_variation": mean_pairwise_tv,
        "vote_disagreement": vote_disagreement,
    }
    return {
        "evaluated": True,
        "seed_count": len(probabilities_by_seed),
        "definitions": {
            "mean_pairwise_total_variation": (
                "mean pairwise total-variation distance across the three "
                "cross-fitted calibrated seed predictions"
            ),
            "vote_disagreement": "1 - largest seed vote fraction",
        },
        "score_summary": {
            name: {
                "mean": float(values.mean()),
                "sd": float(values.std(ddof=1)),
                "p50": float(np.quantile(values, 0.5)),
                "p95": float(np.quantile(values, 0.95)),
            }
            for name, values in scores.items()
        },
        "error_detection": {
            score_name: {
                event_name: binary_detection_metrics(score, event)
                for event_name, event in events.items()
            }
            for score_name, score in scores.items()
        },
        "referral": {
            score_name: referral_metrics(
                score,
                events["ensemble_prediction_error"],
                referral_fractions=REFERRAL_FRACTIONS,
            )
            for score_name, score in scores.items()
        },
        "selective_prediction": {
            score_name: _selective_classification(ensemble, targets, score)
            for score_name, score in scores.items()
        },
    }


def _load_probability_receipt(
    receipt_path: Path,
    *,
    expected_system: str = "V2",
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected_schema, expected_status = {
        "V2": (
            "prta-cxr.wave047-candidate-probability-diagnostic.v1",
            "PASS_WAVE047_V2_DEV_PROBABILITY_EXPORT",
        ),
        "Slim-S1": (
            "prta-cxr.phase20-s1-dev-probability-diagnostic.v1",
            "PASS_PHASE20_S1_DEV_PROBABILITY_EXPORT",
        ),
    }.get(
        expected_system,
        (
            "prta-cxr.comparator-dev-probability-diagnostic.v1",
            "PASS_COMPARATOR_DEV_PROBABILITY_EXPORT",
        ),
    )
    if receipt.get("schema") != expected_schema:
        raise ValueError("unsupported probability diagnostic schema")
    if receipt.get("status") != expected_status:
        raise ValueError("probability diagnostic is not terminal PASS")
    if (
        receipt.get("variant") != expected_system
        or receipt.get("probability_export") is not True
    ):
        raise ValueError("probability diagnostic system identity mismatch")
    if receipt.get("internal_test_opened") is not False:
        raise ValueError("probability diagnostic reports Internal-test access")
    if receipt.get("protected_outcome_read_count") != 0:
        raise ValueError("probability diagnostic reports protected-outcome access")
    blocks = {}
    interventions = tuple(receipt.get("evaluation_interventions", INTERVENTIONS))
    if "true" not in interventions:
        raise ValueError("probability diagnostic does not contain true PRIOR")
    for intervention in interventions:
        inventory = receipt["prediction_blocks"][intervention]
        path = receipt_path.parent / str(inventory["path"])
        if sha256_file(path) != str(inventory["sha256"]):
            raise ValueError("probability prediction block hash mismatch")
        rows = _read_jsonl(path)
        if len(rows) != int(inventory["rows"]):
            raise ValueError("probability prediction block row mismatch")
        blocks[intervention] = rows
    return receipt, blocks


def _seed_report(
    receipt: Mapping[str, Any],
    blocks: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    cross_fitted = cross_fitted_temperature_probabilities(blocks)
    true_logits, targets = _validated_arrays(blocks["true"])
    uncalibrated = _softmax(true_logits)
    calibrated = cross_fitted["probabilities"]["true"]
    report = {
        "seed": int(receipt["seed"]),
        "rows": len(targets),
        "patients": len({str(row["patient_id"]) for row in blocks["true"]}),
        "checkpoint_sha256": str(receipt["checkpoint_sha256"]),
        "fold_assignment_sha256": cross_fitted["fold_assignment_sha256"],
        "fold_audit": cross_fitted["fold_audit"],
        "temperature_mean": float(np.mean(cross_fitted["temperatures"])),
        "temperature_sd": float(np.std(cross_fitted["temperatures"], ddof=1)),
        "uncalibrated": {
            "calibration": calibration_metrics(uncalibrated, targets, bins=15),
            "risk_coverage": risk_coverage_metrics(
                uncalibrated, targets, requested_coverages=COVERAGES
            ),
        },
        "cross_fitted_calibrated": {
            "calibration": calibration_metrics(calibrated, targets, bins=15),
            "risk_coverage": risk_coverage_metrics(
                calibrated, targets, requested_coverages=COVERAGES
            ),
        },
        "uncertainty": _uncertainty_summary(cross_fitted["probabilities"], targets),
    }
    return report, calibrated, targets


def _scalar_aggregate(seed_reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output = {}
    for state in ("uncalibrated", "cross_fitted_calibrated"):
        output[state] = {}
        for metric in ("nll", "brier", "ece", "adaptive_ece", "classwise_ece"):
            values = [
                float(report[state]["calibration"][metric]) for report in seed_reports
            ]
            output[state][metric] = {
                "mean": float(np.mean(values)),
                "sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
                "values": values,
            }
        for metric in ("aurc", "e_aurc"):
            values = [
                float(report[state]["risk_coverage"][metric]) for report in seed_reports
            ]
            output[state][metric] = {
                "mean": float(np.mean(values)),
                "sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
                "values": values,
            }
    return output


def _markdown(report: Mapping[str, Any]) -> str:
    system = str(report.get("system", "V2"))
    lines = [
        f"# Frozen {system} Dev calibration and selective-prediction evidence",
        "",
        f"Status: `{report['status']}`  ",
        f"Seeds: `{report['seeds']}`  ",
        f"Rows per seed: `{report['rows_per_seed']}`  ",
        "Cohort: frozen Dev only; Internal-test/protected outcomes were not opened.",
        "",
        "## Calibration summary",
        "",
        (
            "| State | NLL | Brier | ECE-15 | Adaptive ECE | "
            "Classwise ECE | AURC | E-AURC |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for state, label in (
        ("uncalibrated", "Uncalibrated"),
        ("cross_fitted_calibrated", "5-fold cross-fitted temperature"),
    ):
        summary = report["aggregate"][state]

        def cell(metric: str, values: Mapping[str, Any] = summary) -> str:
            value = values[metric]
            if value["sd"] is None:
                return f"{value['mean']:.6f}"
            return f"{value['mean']:.6f} ± {value['sd']:.6f}"

        lines.append(
            f"| {label} | {cell('nll')} | {cell('brier')} | {cell('ece')} | "
            f"{cell('adaptive_ece')} | {cell('classwise_ece')} | {cell('aurc')} | "
            f"{cell('e_aurc')} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            (
                "- Temperature is fitted out-of-fold at patient level (five "
                "folds); each patient is scored only by a temperature fitted "
                "without that patient."
            ),
            (
                "- MSP and normalized entropy are reported for every system. "
                "PRIOR-derived scores are reported only when the receipt "
                "contains the complete frozen intervention set."
            ),
            (
                "- A combined uncertainty score is intentionally absent because "
                "no combination was preregistered before inspecting outcomes."
            ),
            (
                "- These are frozen Dev characterization results, not an "
                "Internal-test claim."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def calibration_evidence_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate frozen Dev calibration and selective prediction"
    )
    parser.add_argument(
        "--diagnostic-receipt", type=Path, action="append", required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--system",
        choices=("Slim-S1", "V2", "B401", "TILA8", "IF-F01", "IF-F02"),
        default="V2",
    )
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
    if len(set(seeds)) != len(seeds):
        parser.error("probability diagnostic seeds must be unique")
    if args.smoke:
        if len(seeds) != 1:
            parser.error("--smoke requires exactly one seed")
    elif seeds != EXPECTED_SEEDS:
        parser.error(f"formal evidence requires seeds {EXPECTED_SEEDS}")
    input_hashes = [dict(receipt["input_hashes"]) for receipt, _ in loaded]
    if any(value != input_hashes[0] for value in input_hashes[1:]):
        raise ValueError("probability diagnostics do not share frozen inputs")
    evaluated_seeds = [
        _seed_report(receipt, blocks)
        for receipt, blocks in sorted(loaded, key=lambda value: int(value[0]["seed"]))
    ]
    seed_reports = [item[0] for item in evaluated_seeds]
    rows_per_seed = [int(report["rows"]) for report in seed_reports]
    if len(set(rows_per_seed)) != 1:
        raise ValueError("probability diagnostics have different Dev row counts")
    fold_hashes = {str(report["fold_assignment_sha256"]) for report in seed_reports}
    if len(fold_hashes) != 1:
        raise ValueError("probability diagnostics produced different patient folds")
    target_arrays = [item[2] for item in evaluated_seeds]
    if any(
        not np.array_equal(target_arrays[0], candidate)
        for candidate in target_arrays[1:]
    ):
        raise ValueError("probability diagnostics have different Dev targets")
    if args.system == "Slim-S1":
        evidence_schema = "prta-cxr.phase20-s1-dev-calibration-evidence.v1"
        evidence_status = (
            "PASS_PHASE20_S1_DEV_CALIBRATION_SMOKE"
            if args.smoke
            else "PASS_PHASE20_S1_DEV_CALIBRATION_COMPLETE"
        )
        manifest_schema = "prta-cxr.phase20-s1-dev-calibration-manifest.v1"
        result_stem = "phase20_s1_dev_calibration_evidence"
    elif args.system == "V2":
        evidence_schema = "prta-cxr.v2-dev-calibration-evidence.v1"
        evidence_status = (
            "PASS_V2_DEV_CALIBRATION_SMOKE"
            if args.smoke
            else "PASS_V2_DEV_CALIBRATION_COMPLETE"
        )
        manifest_schema = "prta-cxr.v2-dev-calibration-manifest.v1"
        result_stem = "v2_dev_calibration_evidence"
    else:
        evidence_schema = "prta-cxr.comparator-dev-calibration-evidence.v1"
        evidence_status = (
            "PASS_COMPARATOR_DEV_CALIBRATION_SMOKE"
            if args.smoke
            else "PASS_COMPARATOR_DEV_CALIBRATION_COMPLETE"
        )
        manifest_schema = "prta-cxr.comparator-dev-calibration-manifest.v1"
        result_stem = "comparator_dev_calibration_evidence"
    report = {
        "schema": evidence_schema,
        "status": evidence_status,
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "system": args.system,
        "seeds": list(seeds),
        "rows_per_seed": rows_per_seed[0],
        "input_hashes": input_hashes[0],
        "diagnostic_receipts": [
            {"path": str(path), "sha256": sha256_file(path)}
            for path in args.diagnostic_receipt
        ],
        "patient_fold_assignment_sha256": next(iter(fold_hashes)),
        "seed_reports": seed_reports,
        "aggregate": _scalar_aggregate(seed_reports),
        "three_seed_disagreement": (
            {"evaluated": False, "reason": "smoke mode contains only one seed"}
            if args.smoke
            else _three_seed_disagreement(
                [item[1] for item in evaluated_seeds], target_arrays[0]
            )
        ),
        "selection_performed": False,
        "internal_test_opened": False,
        "protected_outcome_read_count": 0,
    }
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    if staging.exists():
        raise FileExistsError(f"calibration evidence staging exists: {staging}")
    staging.mkdir(parents=True, exist_ok=False)
    _write_new_json(staging / f"{result_stem}.json", report)
    markdown = _markdown(report)
    (staging / f"{result_stem}.md").write_text(markdown, encoding="utf-8")
    manifest = {
        "schema": manifest_schema,
        "status": report["status"],
        "files": {
            path.name: sha256_file(path)
            for path in sorted(staging.iterdir())
            if path.is_file()
        },
        "internal_test_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "manifest.json", manifest)
    staging.replace(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0
