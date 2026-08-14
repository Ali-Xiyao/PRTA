from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.contracts import canonical_sha256, sha256_file


class Wave045FinalizationError(RuntimeError):
    """Raised when a frozen Wave045 finalization contract is violated."""


VARIANTS = tuple(f"V{index}" for index in range(6))
DIAGNOSTIC_VARIANTS = ("V3", "V4", "V5")
SEEDS = (17, 28, 43)
INTERVENTIONS = ("true", "matched_hard", "null", "reversed")
CLASS_NAMES = ("Stable", "Improved", "Worse", "New", "Resolved")
SCALAR_METRICS = (
    "accuracy",
    "balanced_accuracy",
    "macro_f1",
    "min_class_recall",
    "opposite_direction_error_rate",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing existing finalization artifact: {path}")
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Wave045FinalizationError(message)


def _mean_sd(values: Iterable[float]) -> dict[str, Any]:
    numbers = [float(value) for value in values]
    _require(bool(numbers), "cannot summarize an empty value set")
    return {
        "values": numbers,
        "mean": statistics.fmean(numbers),
        "sample_sd": statistics.stdev(numbers) if len(numbers) > 1 else 0.0,
        "count": len(numbers),
    }


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _best_history_metrics(receipt: Mapping[str, Any]) -> dict[str, Any]:
    best_epoch = int(receipt["best_epoch"])
    matches = [
        row for row in receipt["history"] if int(row.get("epoch", -1)) == best_epoch
    ]
    _require(len(matches) == 1, "training receipt has ambiguous best epoch")
    row = matches[0]
    ordinary = row["ordinary"]
    patient_balanced = row["patient_balanced"]
    _require(
        math.isclose(
            float(receipt["best_dev_macro_f1"]),
            float(ordinary["macro_f1"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "best Dev macro-F1 does not match the frozen best epoch",
    )
    return {
        "best_epoch": best_epoch,
        "ordinary": {metric: ordinary[metric] for metric in SCALAR_METRICS}
        | {
            "per_class_f1": ordinary["per_class_f1"],
            "per_class_recall": ordinary["per_class_recall"],
            "support": ordinary["support"],
        },
        "patient_balanced": {
            metric: patient_balanced[metric] for metric in SCALAR_METRICS
        }
        | {
            "per_class_f1": patient_balanced["per_class_f1"],
            "per_class_recall": patient_balanced["per_class_recall"],
            "support": patient_balanced["support"],
        },
        "train_loss": row.get("train_loss"),
    }


def _verify_worker_receipts(
    *,
    preparation: Mapping[str, Any],
    preparation_sha256: str,
    local_root: Path,
    server_root: Path,
    receipt_hash_key: str,
    expected_status: str,
) -> dict[str, str]:
    completed_hashes: dict[str, str] = {}
    expected_run_ids: set[str] = set()
    for worker, spec in preparation["workers"].items():
        root = local_root if spec["site"] == "local" else server_root
        path = root / "workers" / f"{worker}_completion_receipt.json"
        receipt = _read_json(path)
        _require(receipt.get("status") == expected_status, f"{worker} not PASS")
        _require(receipt.get("worker") == worker, f"{worker} identity drift")
        _require(
            receipt.get("preparation_receipt_sha256") == preparation_sha256,
            f"{worker} preparation hash drift",
        )
        _require(
            receipt.get("source_commit") == preparation["source_commit"],
            f"{worker} source drift",
        )
        _require(
            receipt.get("hardware_class") == spec["hardware"],
            f"{worker} hardware drift",
        )
        _require(receipt.get("internal_test_opened") is False, "Internal-test read")
        _require(receipt.get("gold_opened") is False, "Gold read")
        _require(
            receipt.get("protected_outcome_read_count") == 0,
            "worker protected-read count is nonzero",
        )
        queue = list(spec["queue"])
        _require(receipt.get("queue") == queue, f"{worker} queue drift")
        completed = receipt.get("completed", [])
        _require(len(completed) == len(queue), f"{worker} completion count drift")
        for row in completed:
            run_id = row["run_id"]
            _require(run_id in queue, f"unexpected completed ID: {run_id}")
            _require(row.get("zero_protected_reads") is True, "protected read")
            _require(run_id not in completed_hashes, f"duplicate run: {run_id}")
            completed_hashes[run_id] = row[receipt_hash_key]
        expected_run_ids.update(queue)
    _require(
        set(completed_hashes) == expected_run_ids,
        "worker completion roster mismatch",
    )
    return completed_hashes


def _verify_input_hashes(
    receipt: Mapping[str, Any],
    preparation: Mapping[str, Any],
    *,
    uses_matched_hard_map: bool,
) -> None:
    expected = {
        "split_manifest": preparation["train_dev_manifest_sha256"],
        "cleaned_split_freeze": preparation["cleaned_split_freeze_sha256"],
        "cache_manifest": preparation["cache_manifest_sha256"],
        "text_cache": preparation["text_cache_sha256"],
        "weights": preparation["weights_sha256"],
        "label_quality_audit": preparation["quality_audit_sha256"],
    }
    if uses_matched_hard_map:
        expected["matched_hard_prior_map"] = preparation[
            "matched_hard_prior_map_sha256"
        ]
    _require(receipt.get("input_hashes") == expected, "scientific input hash drift")


def _summarize_class_metrics(
    rows: Sequence[Mapping[str, Any]], metric_name: str
) -> dict[str, Any]:
    return {
        class_name: _mean_sd(row[metric_name][class_name] for row in rows)
        for class_name in CLASS_NAMES
    }


def _summarize_metric_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "scalars": {
            metric: _mean_sd(row[metric] for row in rows) for metric in SCALAR_METRICS
        },
        "per_class_f1": _summarize_class_metrics(rows, "per_class_f1"),
        "per_class_recall": _summarize_class_metrics(rows, "per_class_recall"),
    }


def _summarize_distribution(
    conditions: Sequence[Mapping[str, Any]], field: str
) -> dict[str, Any]:
    distributions = [condition.get(field) for condition in conditions]
    if all(distribution is None for distribution in distributions):
        return {
            "available": False,
            "reason": "NOT_APPLICABLE_FOR_FROZEN_VARIANT",
        }
    _require(
        all(distribution is not None for distribution in distributions),
        f"partial diagnostic distribution availability: {field}",
    )
    return {
        "available": True,
        "summary": {
            key: _mean_sd(distribution[key] for distribution in distributions)
            for key in ("mean", "std", "p10", "p50", "p90")
        },
    }


def _build_progressive_aggregate(
    *,
    preparation: Mapping[str, Any],
    preparation_sha256: str,
    local_root: Path,
    server_root: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    receipt_hashes = _verify_worker_receipts(
        preparation=preparation,
        preparation_sha256=preparation_sha256,
        local_root=local_root,
        server_root=server_root,
        receipt_hash_key="training_receipt_sha256",
        expected_status="PASS_WAVE045_WORKER_COMPLETE",
    )
    _require(
        preparation["matrix"]
        == {
            "cells": 18,
            "seeds": list(SEEDS),
            "selection": "none",
            "variants": list(VARIANTS),
        },
        "progressive matrix drift",
    )
    cells: list[dict[str, Any]] = []
    by_variant_seed: dict[tuple[str, int], dict[str, Any]] = {}
    for arm in preparation["arms"]:
        run_id = arm["run_id"]
        root = local_root if arm["site"] == "local" else server_root
        receipt_path = root / "runs" / run_id / "training_receipt.json"
        _require(
            sha256_file(receipt_path) == receipt_hashes[run_id],
            f"training receipt hash drift: {run_id}",
        )
        config_path = local_root / "configs" / f"{run_id}.json"
        _require(
            sha256_file(config_path) == arm["config_sha256"],
            f"config file hash drift: {run_id}",
        )
        config = _read_json(config_path)
        _require(
            canonical_sha256(config) == arm["effective_config_sha256"],
            f"effective config hash drift: {run_id}",
        )
        receipt = _read_json(receipt_path)
        _require(receipt.get("status") == "PASS_TRAINING_FINISHED", run_id)
        _require(receipt.get("seed") == arm["seed"], f"seed drift: {run_id}")
        _require(
            receipt.get("config_sha256") == arm["effective_config_sha256"],
            f"receipt config drift: {run_id}",
        )
        _require(receipt.get("internal_test_opened") is False, "Internal-test read")
        _require(
            receipt.get("protected_outcomes_opened") is False,
            "protected outcome read",
        )
        _verify_input_hashes(
            receipt,
            preparation,
            uses_matched_hard_map=arm["uses_matched_hard_map"],
        )
        metrics = _best_history_metrics(receipt)
        duration = (
            _parse_timestamp(receipt["end_time"])
            - _parse_timestamp(receipt["start_time"])
        ).total_seconds()
        cell = {
            "run_id": run_id,
            "variant": arm["variant"],
            "seed": arm["seed"],
            "worker": arm["worker"],
            "site": arm["site"],
            "hardware_class": arm["hardware_class"],
            "allocation_id": arm["allocation_id"],
            "local_gpu_index": arm["local_gpu_index"],
            "config_file_sha256": arm["config_sha256"],
            "effective_config_sha256": arm["effective_config_sha256"],
            "training_receipt_sha256": receipt_hashes[run_id],
            "completed_epochs": receipt["completed_epochs"],
            "duration_seconds": duration,
            "peak_gpu_memory_mib": None,
            "peak_gpu_memory_status": "NOT_RECORDED_BY_FROZEN_RUNNER",
            "metrics": metrics,
        }
        cells.append(cell)
        by_variant_seed[(arm["variant"], arm["seed"])] = cell
    _require(len(cells) == 18, "progressive cell count mismatch")

    summaries: dict[str, Any] = {}
    for variant in VARIANTS:
        variant_cells = [by_variant_seed[(variant, seed)] for seed in SEEDS]
        summaries[variant] = {
            "ordinary": _summarize_metric_rows(
                [cell["metrics"]["ordinary"] for cell in variant_cells]
            ),
            "patient_balanced": _summarize_metric_rows(
                [cell["metrics"]["patient_balanced"] for cell in variant_cells]
            ),
            "resource": {
                "duration_seconds": _mean_sd(
                    cell["duration_seconds"] for cell in variant_cells
                ),
                "completed_epochs": _mean_sd(
                    cell["completed_epochs"] for cell in variant_cells
                ),
            },
        }

    paired_deltas: dict[str, Any] = {}
    for previous, current in zip(VARIANTS[:-1], VARIANTS[1:], strict=True):
        comparison = f"{current}_minus_{previous}"
        seed_rows = []
        for seed in SEEDS:
            before = by_variant_seed[(previous, seed)]["metrics"]["ordinary"]
            after = by_variant_seed[(current, seed)]["metrics"]["ordinary"]
            seed_rows.append(
                {
                    "seed": seed,
                    **{
                        f"{metric}_delta": after[metric] - before[metric]
                        for metric in SCALAR_METRICS
                    },
                }
            )
        paired_deltas[comparison] = {
            "by_seed": seed_rows,
            "summary": {
                f"{metric}_delta": _mean_sd(row[f"{metric}_delta"] for row in seed_rows)
                for metric in SCALAR_METRICS
            },
        }

    resource_by_hardware: dict[str, Any] = {}
    hardware_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        hardware_groups[cell["hardware_class"]].append(cell)
    for hardware, hardware_cells in sorted(hardware_groups.items()):
        resource_by_hardware[hardware] = {
            "cells": len(hardware_cells),
            "total_duration_seconds": sum(
                cell["duration_seconds"] for cell in hardware_cells
            ),
            "duration_seconds": _mean_sd(
                cell["duration_seconds"] for cell in hardware_cells
            ),
            "peak_gpu_memory_status": "NOT_RECORDED_BY_FROZEN_RUNNER",
        }

    aggregate = {
        "schema": "prta-cxr.wave045-progressive-build-aggregate.v1",
        "status": "PASS_WAVE045_PROGRESSIVE_BUILD_AGGREGATED_NO_SELECTION",
        "created_at": datetime.now(UTC).isoformat(),
        "preparation_receipt_sha256": preparation_sha256,
        "source_commit": preparation["source_commit"],
        "scientific_input_hashes": {
            key: preparation[key]
            for key in (
                "train_dev_manifest_sha256",
                "cleaned_split_freeze_sha256",
                "cache_manifest_sha256",
                "text_cache_sha256",
                "weights_sha256",
                "quality_audit_sha256",
                "matched_hard_prior_map_sha256",
            )
        },
        "matrix": preparation["matrix"],
        "cells": cells,
        "variant_summary": summaries,
        "cumulative_paired_seed_deltas": paired_deltas,
        "resource_by_hardware": resource_by_hardware,
        "selection_performed": False,
        "winner_selected": False,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "checks": {
            "all_18_receipts_pass": True,
            "all_receipt_hashes_match_workers": True,
            "all_config_and_input_hashes_match_preparation": True,
            "all_three_seeds_present_per_variant": True,
            "resources_stratified_by_hardware": True,
        },
    }
    return aggregate, receipt_hashes


def _build_diagnostic_aggregate(
    *,
    preparation: Mapping[str, Any],
    preparation_sha256: str,
    original_preparation: Mapping[str, Any],
    local_root: Path,
    server_root: Path,
    training_receipt_hashes: Mapping[str, str],
) -> dict[str, Any]:
    receipt_hashes = _verify_worker_receipts(
        preparation=preparation,
        preparation_sha256=preparation_sha256,
        local_root=local_root,
        server_root=server_root,
        receipt_hash_key="diagnostic_receipt_sha256",
        expected_status="PASS_WAVE045_POSTREVIEW_WORKER_COMPLETE",
    )
    _require(
        preparation["matrix"]
        == {
            "checkpoint_only": True,
            "jobs": 9,
            "seeds": list(SEEDS),
            "selection": "none",
            "training": False,
            "variants": list(DIAGNOSTIC_VARIANTS),
        },
        "diagnostic matrix drift",
    )
    cells: list[dict[str, Any]] = []
    receipts: dict[tuple[str, int], dict[str, Any]] = {}
    for arm in preparation["arms"]:
        run_id = arm["run_id"]
        root = local_root if arm["site"] == "local" else server_root
        receipt_path = root / "runs" / run_id / "mechanism_diagnostic_receipt.json"
        _require(
            sha256_file(receipt_path) == receipt_hashes[run_id],
            f"diagnostic receipt hash drift: {run_id}",
        )
        receipt = _read_json(receipt_path)
        _require(
            receipt.get("status") == "PASS_WAVE045_TRAIN_DEV_MECHANISM_DIAGNOSTIC",
            f"diagnostic is not PASS: {run_id}",
        )
        _require(
            receipt.get("experiment_id") == arm["source_run_id"],
            f"source experiment ID drift: {run_id}",
        )
        _require(receipt.get("variant") == arm["variant"], f"variant drift: {run_id}")
        _require(receipt.get("seed") == arm["seed"], f"seed drift: {run_id}")
        _require(receipt.get("selection_performed") is False, "selection performed")
        _require(receipt.get("internal_test_opened") is False, "Internal-test read")
        _require(receipt.get("gold_opened") is False, "Gold read")
        _require(
            receipt.get("protected_outcome_read_count") == 0,
            "diagnostic protected-read count is nonzero",
        )
        _require(
            receipt.get("training_receipt_sha256")
            == training_receipt_hashes[arm["source_run_id"]],
            f"source training receipt drift: {run_id}",
        )
        _verify_input_hashes(
            receipt,
            original_preparation,
            uses_matched_hard_map=True,
        )
        _require(
            arm["interventions"] == list(INTERVENTIONS),
            f"frozen intervention order drift: {run_id}",
        )
        _require(
            set(receipt["interventions"]) == set(INTERVENTIONS)
            and len(receipt["interventions"]) == len(INTERVENTIONS),
            f"intervention roster drift: {run_id}",
        )
        receipts[(arm["variant"], arm["seed"])] = receipt
        cells.append(
            {
                "run_id": run_id,
                "source_run_id": arm["source_run_id"],
                "variant": arm["variant"],
                "seed": arm["seed"],
                "worker": arm["worker"],
                "site": arm["site"],
                "hardware_class": arm["hardware_class"],
                "allocation_id": arm["allocation_id"],
                "local_gpu_index": arm["local_gpu_index"],
                "diagnostic_receipt_sha256": receipt_hashes[run_id],
                "training_receipt_sha256": receipt["training_receipt_sha256"],
                "checkpoint_sha256": receipt["checkpoint_sha256"],
                "mechanism": receipt["mechanism"],
                "interventions": receipt["interventions"],
            }
        )
    _require(len(cells) == 9, "diagnostic cell count mismatch")

    summaries: dict[str, Any] = {}
    for variant in DIAGNOSTIC_VARIANTS:
        variant_receipts = [receipts[(variant, seed)] for seed in SEEDS]
        intervention_summary: dict[str, Any] = {}
        for intervention in INTERVENTIONS:
            conditions = [
                receipt["interventions"][intervention] for receipt in variant_receipts
            ]
            intervention_summary[intervention] = {
                "ordinary": _summarize_metric_rows(
                    [condition["metrics"]["ordinary"] for condition in conditions]
                ),
                "patient_balanced": _summarize_metric_rows(
                    [
                        condition["metrics"]["patient_balanced"]
                        for condition in conditions
                    ]
                ),
                "comparison_to_true": {
                    key: _mean_sd(
                        condition["comparison_to_true"][key] for condition in conditions
                    )
                    for key in (
                        "macro_f1_delta",
                        "opposite_direction_error_rate_delta",
                        "prediction_flip_rate",
                        "true_minus_intervention_macro_f1",
                    )
                }
                | {
                    "prediction_flip_count": _mean_sd(
                        condition["comparison_to_true"]["prediction_flip_count"]
                        for condition in conditions
                    )
                },
                "prior_reliability": _summarize_distribution(
                    conditions, "prior_reliability"
                ),
                "selective_state_weight": _summarize_distribution(
                    conditions, "selective_state_weight"
                ),
                "change_energy": _summarize_distribution(conditions, "change_energy"),
            }
        summaries[variant] = {
            "interventions": intervention_summary,
            "residual_coefficients": {
                key: _mean_sd(receipt["mechanism"][key] for receipt in variant_receipts)
                for key in (
                    "training_checkpoint_relation_residual_scale",
                    "evaluation_checkpoint_relation_residual_scale",
                )
            },
        }

    return {
        "schema": "prta-cxr.wave045-mechanism-diagnostic-aggregate.v1",
        "status": "PASS_WAVE045_MECHANISM_DIAGNOSTICS_AGGREGATED_NO_SELECTION",
        "created_at": datetime.now(UTC).isoformat(),
        "preparation_receipt_sha256": preparation_sha256,
        "original_preparation_receipt_sha256": preparation[
            "original_preparation_sha256"
        ],
        "source_commit": preparation["source_commit"],
        "original_source_commit": preparation["original_source_commit"],
        "matrix": preparation["matrix"],
        "cells": cells,
        "variant_summary": summaries,
        "selection_performed": False,
        "winner_selected": False,
        "training_started_by_finalizer": False,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "checks": {
            "all_9_receipts_pass": True,
            "all_receipt_hashes_match_workers": True,
            "all_source_training_receipt_hashes_match": True,
            "all_four_interventions_present": True,
            "all_three_seeds_present_per_variant": True,
        },
    }


def _render_markdown(
    progressive: Mapping[str, Any], diagnostic: Mapping[str, Any]
) -> str:
    lines = [
        "# Wave045 Train/Dev no-selection summary",
        "",
        "Wave045 is terminal at 18/18 progressive cells and 9/9 "
        "checkpoint diagnostics.",
        "No winner was selected and no Internal-test or Gold outcome was opened.",
        "",
        "## Progressive build (three-seed Dev)",
        "",
        "| Variant | Macro-F1 mean ± SD | Balanced accuracy mean ± SD | "
        "ODER mean ± SD |",
        "|---|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        scalars = progressive["variant_summary"][variant]["ordinary"]["scalars"]
        lines.append(
            f"| {variant} | {scalars['macro_f1']['mean']:.6f} ± "
            f"{scalars['macro_f1']['sample_sd']:.6f} | "
            f"{scalars['balanced_accuracy']['mean']:.6f} ± "
            f"{scalars['balanced_accuracy']['sample_sd']:.6f} | "
            f"{scalars['opposite_direction_error_rate']['mean']:.6f} ± "
            f"{scalars['opposite_direction_error_rate']['sample_sd']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Cumulative paired Dev deltas",
            "",
            "| Step | Macro-F1 delta mean ± SD | ODER delta mean ± SD |",
            "|---|---:|---:|",
        ]
    )
    for comparison, payload in progressive["cumulative_paired_seed_deltas"].items():
        summary = payload["summary"]
        lines.append(
            f"| {comparison} | {summary['macro_f1_delta']['mean']:.6f} ± "
            f"{summary['macro_f1_delta']['sample_sd']:.6f} | "
            f"{summary['opposite_direction_error_rate_delta']['mean']:.6f} ± "
            f"{summary['opposite_direction_error_rate_delta']['sample_sd']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Checkpoint interventions",
            "",
            "Values are intervention-minus-true paired Dev deltas averaged "
            "across seeds.",
            "",
            "| Variant | Intervention | Macro-F1 delta mean ± SD | "
            "Prediction flip rate mean ± SD |",
            "|---|---|---:|---:|",
        ]
    )
    for variant in DIAGNOSTIC_VARIANTS:
        for intervention in INTERVENTIONS[1:]:
            comparison = diagnostic["variant_summary"][variant]["interventions"][
                intervention
            ]["comparison_to_true"]
            lines.append(
                f"| {variant} | {intervention} | "
                f"{comparison['macro_f1_delta']['mean']:.6f} ± "
                f"{comparison['macro_f1_delta']['sample_sd']:.6f} | "
                f"{comparison['prediction_flip_rate']['mean']:.6f} ± "
                f"{comparison['prediction_flip_rate']['sample_sd']:.6f} |"
            )
    lines.extend(
        [
            "",
            "Peak GPU memory was not retained by the frozen runner and is reported as",
            "`NOT_RECORDED_BY_FROZEN_RUNNER`; durations and hardware classes "
            "are retained",
            "in the immutable progressive aggregate.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_wave045(
    *,
    original_local_root: Path,
    original_server_root: Path,
    diagnostic_local_root: Path,
    diagnostic_server_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    roots = (
        original_local_root,
        original_server_root,
        diagnostic_local_root,
        diagnostic_server_root,
    )
    for root in roots:
        _require(root.is_dir(), f"missing finalization input root: {root}")
    original_local_preparation = original_local_root / "preparation_receipt.json"
    original_server_preparation = original_server_root / "preparation_receipt.json"
    diagnostic_local_preparation = diagnostic_local_root / "preparation_receipt.json"
    diagnostic_server_preparation = diagnostic_server_root / "preparation_receipt.json"
    original_preparation_sha256 = sha256_file(original_local_preparation)
    diagnostic_preparation_sha256 = sha256_file(diagnostic_local_preparation)
    _require(
        sha256_file(original_server_preparation) == original_preparation_sha256,
        "server original preparation hash drift",
    )
    _require(
        sha256_file(diagnostic_server_preparation) == diagnostic_preparation_sha256,
        "server diagnostic preparation hash drift",
    )
    original_preparation = _read_json(original_local_preparation)
    diagnostic_preparation = _read_json(diagnostic_local_preparation)
    _require(
        original_preparation.get("status") == "PASS_WAVE045_18_CELL_MATRIX_FROZEN",
        "original preparation is not PASS",
    )
    _require(
        diagnostic_preparation.get("status")
        == "PASS_WAVE045_POSTREVIEW_NINE_DIAGNOSTICS_FROZEN",
        "diagnostic preparation is not PASS",
    )
    _require(
        diagnostic_preparation["original_preparation_sha256"]
        == original_preparation_sha256,
        "diagnostic parent preparation hash drift",
    )
    for preparation in (original_preparation, diagnostic_preparation):
        _require(preparation.get("internal_test_opened") is False, "Internal-test")
        _require(preparation.get("gold_opened") is False, "Gold")
        _require(
            preparation.get("protected_outcome_read_count") == 0,
            "preparation protected-read count is nonzero",
        )

    progressive, training_hashes = _build_progressive_aggregate(
        preparation=original_preparation,
        preparation_sha256=original_preparation_sha256,
        local_root=original_local_root,
        server_root=original_server_root,
    )
    diagnostic = _build_diagnostic_aggregate(
        preparation=diagnostic_preparation,
        preparation_sha256=diagnostic_preparation_sha256,
        original_preparation=original_preparation,
        local_root=diagnostic_local_root,
        server_root=diagnostic_server_root,
        training_receipt_hashes=training_hashes,
    )
    return (
        progressive,
        diagnostic,
        original_preparation_sha256,
        diagnostic_preparation_sha256,
    )


def finalize_wave045(
    *,
    original_local_root: Path,
    original_server_root: Path,
    diagnostic_local_root: Path,
    diagnostic_server_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(f"refusing existing final output root: {output_root}")
    (
        progressive,
        diagnostic,
        original_preparation_sha256,
        diagnostic_preparation_sha256,
    ) = validate_wave045(
        original_local_root=original_local_root,
        original_server_root=original_server_root,
        diagnostic_local_root=diagnostic_local_root,
        diagnostic_server_root=diagnostic_server_root,
    )
    staging = output_root.parent / f".{output_root.name}.staging.{os.getpid()}"
    if staging.exists():
        raise FileExistsError(f"refusing existing staging root: {staging}")
    staging.mkdir(parents=False)
    progressive_path = staging / "progressive_build_aggregate.json"
    diagnostic_path = staging / "mechanism_diagnostic_aggregate.json"
    summary_path = staging / "SUMMARY.md"
    _write_new_json(progressive_path, progressive)
    _write_new_json(diagnostic_path, diagnostic)
    summary_path.write_text(_render_markdown(progressive, diagnostic), encoding="utf-8")
    finalization = {
        "schema": "prta-cxr.wave045-finalization-receipt.v1",
        "status": "PASS_WAVE045_FINALIZED_NO_SELECTION",
        "created_at": datetime.now(UTC).isoformat(),
        "original_preparation_receipt_sha256": original_preparation_sha256,
        "diagnostic_preparation_receipt_sha256": diagnostic_preparation_sha256,
        "outputs": {
            progressive_path.name: sha256_file(progressive_path),
            diagnostic_path.name: sha256_file(diagnostic_path),
            summary_path.name: sha256_file(summary_path),
        },
        "original_cells": 18,
        "diagnostic_jobs": 9,
        "selection_performed": False,
        "winner_selected": False,
        "training_started_by_finalizer": False,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    _write_new_json(staging / "finalization_receipt.json", finalization)
    staging.replace(output_root)
    return finalization


def wave045_finalization_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Finalize Wave045 Train/Dev-only no-selection aggregates"
    )
    parser.add_argument("--original-local-root", type=Path, required=True)
    parser.add_argument("--original-server-root", type=Path, required=True)
    parser.add_argument("--diagnostic-local-root", type=Path, required=True)
    parser.add_argument("--diagnostic-server-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    common = {
        "original_local_root": args.original_local_root.resolve(),
        "original_server_root": args.original_server_root.resolve(),
        "diagnostic_local_root": args.diagnostic_local_root.resolve(),
        "diagnostic_server_root": args.diagnostic_server_root.resolve(),
    }
    if args.validate_only:
        progressive, diagnostic, original_sha, diagnostic_sha = validate_wave045(
            **common
        )
        print(
            json.dumps(
                {
                    "status": "PASS_WAVE045_FINALIZATION_VALIDATED_NO_WRITE",
                    "original_cells": len(progressive["cells"]),
                    "diagnostic_jobs": len(diagnostic["cells"]),
                    "original_preparation_receipt_sha256": original_sha,
                    "diagnostic_preparation_receipt_sha256": diagnostic_sha,
                    "protected_outcome_read_count": 0,
                    "internal_test_opened": False,
                    "gold_opened": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    receipt = finalize_wave045(
        **common,
        output_root=args.output_root.resolve(),
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(wave045_finalization_main())
