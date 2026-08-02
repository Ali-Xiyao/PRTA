from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.development_selection import _completed_runs, _write_queue


def _best_metrics(receipt: dict[str, Any]) -> dict[str, Any]:
    epoch = int(receipt["best_epoch"])
    return next(value for value in receipt["history"] if int(value["epoch"]) == epoch)


def prepare_dev_baseline_queue(
    *,
    registry_path: Path,
    confirm_selection: Path,
    output: Path,
) -> dict[str, Any]:
    receipts, configs = _completed_runs(registry_path)
    selection = json.loads(confirm_selection.read_text(encoding="utf-8"))
    if selection.get("stage") != "confirm":
        raise ValueError("Dev baselines require the confirm selection receipt")
    base_id = str(selection["reuse_experiment_id"])
    if base_id not in receipts:
        raise ValueError("final seed-17 PRTA run is incomplete")
    generated = []
    for experiment_id, family in (
        ("M305-B401-S17", "current_only"),
        ("M305-B402-S17", "siamese_diff"),
        ("M305-B403-S17", "tila"),
    ):
        config = deepcopy(configs[base_id])
        config["experiment_id"] = experiment_id
        config["development_axis"] = "strong_baseline_gate"
        config["model"]["family"] = family
        config["loss_weights"] = {
            "classification": 1.0,
            "alignment": 0.0,
            "state": 0.0,
            "inversion": 0.0,
            "cmcp": 0.0,
        }
        generated.append(config)
    queue = _write_queue(output, generated, stage="dev_baseline_gate")
    result = {
        "schema": "prta-cxr.dev-baseline-queue.v1",
        "status": "PASS_DEV_BASELINE_QUEUE_PREPARED",
        "final_prta_seed17_experiment_id": base_id,
        "generated_experiment_ids": [row["experiment_id"] for row in queue],
        "queue_sha256": canonical_sha256(queue),
        "internal_test_opened": False,
        "gold_opened": False,
    }
    write_json_atomic(output / "preparation_receipt.json", result)
    return result


def development_gate_decision(
    *,
    prta_seed_ids: list[str],
    baseline_ids: list[str],
    receipts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    missing = set(prta_seed_ids + baseline_ids) - set(receipts)
    if missing:
        raise ValueError(f"development gate runs incomplete: {sorted(missing)}")
    prta_metrics = [_best_metrics(receipts[value]) for value in prta_seed_ids]
    seed_f1 = [float(value["macro_f1"]) for value in prta_metrics]
    seed_min_recall = [float(value["min_class_recall"]) for value in prta_metrics]
    seed_prior_gap = [
        float(receipts[value]["dev_prior_audit"]["true_minus_wrong_prior_gap"])
        for value in prta_seed_ids
    ]
    baseline_metrics = {
        value: _best_metrics(receipts[value]) for value in baseline_ids
    }
    temporal_ids = [
        value for value in baseline_ids if "B402" in value or "B403" in value
    ]
    strongest_id = max(
        temporal_ids, key=lambda value: float(baseline_metrics[value]["macro_f1"])
    )
    seed17_gain = seed_f1[0] - float(baseline_metrics[strongest_id]["macro_f1"])
    mean_f1 = sum(seed_f1) / len(seed_f1)
    mean_min_recall = sum(seed_min_recall) / len(seed_min_recall)
    mean_oder = sum(
        float(value["opposite_direction_error_rate"]) for value in prta_metrics
    ) / len(prta_metrics)
    strongest_oder = float(
        baseline_metrics[strongest_id]["opposite_direction_error_rate"]
    )
    checks = {
        "mean_macro_f1_ge_0_52": mean_f1 >= 0.52,
        "seed17_gain_ge_0_03": seed17_gain >= 0.03,
        "mean_min_class_recall_ge_0_20": mean_min_recall >= 0.20,
        "mean_oder_not_above_strongest_temporal": mean_oder <= strongest_oder,
        "all_true_minus_wrong_prior_gaps_positive": min(seed_prior_gap) > 0,
        "no_seed_macro_f1_below_0_48": min(seed_f1) >= 0.48,
        "seed_range_le_0_10": max(seed_f1) - min(seed_f1) <= 0.10,
    }
    if all(checks.values()):
        decision = "GO"
    elif mean_f1 >= 0.48:
        decision = "HOLD"
    else:
        decision = "STOP"
    return {
        "schema": "prta-cxr.development-gate.v1",
        "status": f"{decision}_DEVELOPMENT_GATE",
        "decision": decision,
        "prta_seed_experiment_ids": prta_seed_ids,
        "baseline_experiment_ids": baseline_ids,
        "strongest_temporal_baseline_id": strongest_id,
        "seed_macro_f1": seed_f1,
        "mean_macro_f1": mean_f1,
        "seed17_gain_vs_strongest_temporal": seed17_gain,
        "seed_min_class_recall": seed_min_recall,
        "mean_min_class_recall": mean_min_recall,
        "seed_prior_gaps": seed_prior_gap,
        "mean_oder": mean_oder,
        "strongest_temporal_oder": strongest_oder,
        "checks": checks,
        "internal_test_opened": False,
        "gold_opened": False,
    }


def write_development_gate(
    *,
    registry_path: Path,
    confirm_selection: Path,
    output: Path,
) -> dict[str, Any]:
    receipts, _ = _completed_runs(registry_path)
    selection = json.loads(confirm_selection.read_text(encoding="utf-8"))
    seed17 = str(selection["reuse_experiment_id"])
    result = development_gate_decision(
        prta_seed_ids=[seed17, "M304-S29", "M304-S43"],
        baseline_ids=[
            "M305-B401-S17",
            "M305-B402-S17",
            "M305-B403-S17",
        ],
        receipts=receipts,
    )
    result["registry_sha256"] = sha256_file(registry_path)
    result["confirm_selection_sha256"] = sha256_file(confirm_selection)
    write_json_atomic(output, result)
    return result


def _formal_config(
    base: dict[str, Any], experiment_id: str, seed: int
) -> dict[str, Any]:
    config = deepcopy(base)
    config["experiment_id"] = experiment_id
    config["seed"] = seed
    config["development_axis"] = "formal_frozen"
    return config


def prepare_formal_matrix(
    *,
    registry_path: Path,
    confirm_selection: Path,
    gate_receipt: Path,
    output: Path,
) -> dict[str, Any]:
    gate = json.loads(gate_receipt.read_text(encoding="utf-8"))
    if gate.get("decision") != "GO":
        raise ValueError("formal matrix requires a GO development gate")
    receipts, configs = _completed_runs(registry_path)
    selection = json.loads(confirm_selection.read_text(encoding="utf-8"))
    base_id = str(selection["reuse_experiment_id"])
    if base_id not in receipts:
        raise ValueError("frozen PRTA config run is incomplete")
    base = configs[base_id]
    generated = []
    for method_id, family in (
        ("B401", "current_only"),
        ("B402", "siamese_diff"),
        ("B403", "tila"),
    ):
        for seed in (17, 29, 43):
            config = _formal_config(base, f"{method_id}-S{seed}", seed)
            config["model"]["family"] = family
            config["loss_weights"] = {
                "classification": 1.0,
                "alignment": 0.0,
                "state": 0.0,
                "inversion": 0.0,
                "cmcp": 0.0,
            }
            generated.append(config)
    for ablation_id in ("A501", "A502", "A503", "A504", "A505", "A506"):
        for seed in (17, 29, 43):
            config = _formal_config(base, f"{ablation_id}-S{seed}", seed)
            if ablation_id == "A501":
                config["model"]["components"]["finding_conditioning"] = False
            elif ablation_id == "A502":
                config["model"]["components"]["cross_time_alignment"] = False
            elif ablation_id == "A503":
                config["model"]["components"]["dual_branch"] = False
            elif ablation_id == "A504":
                config["loss_weights"]["cmcp"] = 0.0
            elif ablation_id == "A505":
                config["loss_weights"]["inversion"] = 0.0
            elif ablation_id == "A506":
                config["loss_weights"]["state"] = 0.0
            generated.append(config)
    queue = _write_queue(output, generated, stage="formal_baselines_and_ablations")
    result = {
        "schema": "prta-cxr.formal-matrix.v1",
        "status": "PASS_FORMAL_MATRIX_PREPARED",
        "frozen_prta_seed17_experiment_id": base_id,
        "prta_aliases": {
            "B404-S17": base_id,
            "B404-S29": "M304-S29",
            "B404-S43": "M304-S43",
            "A500-S17": base_id,
            "A500-S29": "M304-S29",
            "A500-S43": "M304-S43",
        },
        "n_a": {
            "B405": "N/A_NO_STABLE_NATIVE_IMPLEMENTATION_AT_FREEZE",
            "A507": "N/A_POLICY_RETIRED_RULE_LABELS",
        },
        "generated_runs": len(queue),
        "queue_sha256": canonical_sha256(queue),
        "development_gate_sha256": sha256_file(gate_receipt),
        "internal_test_opened": False,
        "gold_opened": False,
    }
    write_json_atomic(output / "formal_matrix_receipt.json", result)
    return result
