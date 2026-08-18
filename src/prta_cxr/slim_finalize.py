from __future__ import annotations

import argparse
import json
import os
import statistics
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.experiments import (
    filter_train_dev_sources,
    inject_train_label_noise,
    materialize_classification_counts,
    nested_train_fraction,
)
from prta_cxr.phase16_queue import LANES
from prta_cxr.slim_matrix import SEEDS, SLIM_ARMS

METRICS = (
    "macro_f1",
    "opposite_direction_error_rate",
    "min_class_recall",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object at {path}:{line_number}")
        rows.append(value)
    if not rows:
        raise ValueError(f"Slim selection manifest is empty: {path}")
    return rows


def _effective_training_config_sha256(
    config: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> str:
    """Replay the deterministic config transform used by formal training."""
    data_config = dict(config.get("data", {}))
    selected, _ = filter_train_dev_sources(
        rows,
        train_sources=data_config.get("train_sources"),
        dev_sources=data_config.get("dev_sources"),
    )
    selected, _ = nested_train_fraction(
        selected,
        fraction=float(data_config.get("train_fraction", 1.0)),
        salt=str(
            data_config.get("fraction_salt", "prta-cxr-luna-primary-scaling-v1")
        ),
    )
    noise_config = dict(data_config.get("label_noise", {}))
    noise_rate = float(noise_config.get("rate", 0.0))
    if noise_rate:
        selected, _ = inject_train_label_noise(
            selected,
            rate=noise_rate,
            family=str(noise_config.get("family", "symmetric")),
            salt=str(noise_config.get("salt", "prta-cxr-label-noise-v1")),
        )
    effective = materialize_classification_counts(config, selected)
    return canonical_sha256(effective)


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _closed(value: Mapping[str, Any], *, label: str) -> None:
    for key in (
        "internal_test_opened",
        "gold_opened",
        "external_opened",
    ):
        if key in value and value.get(key) is not False:
            raise ValueError(f"{label} reports forbidden access: {key}")
    protected = value.get(
        "protected_outcome_read_count",
        0 if value.get("protected_outcomes_opened") is False else -1,
    )
    if int(protected) != 0:
        raise ValueError(f"{label} reports protected reads")


def _best_epoch_metrics(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if receipt.get("schema") != "prta-cxr.training-receipt.v1":
        raise ValueError("unsupported Slim training receipt schema")
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError("Slim training receipt is not PASS")
    _closed(receipt, label="Slim training receipt")
    best_epoch = int(receipt.get("best_epoch", -1))
    matches = [
        dict(row)
        for row in receipt.get("history", [])
        if int(row.get("epoch", -2)) == best_epoch
    ]
    if len(matches) != 1:
        raise ValueError("Slim receipt lacks one best-epoch metric row")
    metrics = matches[0]
    ordinary = dict(metrics.get("ordinary", {}))
    recalls = dict(ordinary.get("per_class_recall", {}))
    if set(recalls) != set(PROGRESSION_LABELS):
        raise ValueError("Slim best epoch lacks per-class recalls")
    result = {name: float(metrics[name]) for name in METRICS}
    result["per_class_recall"] = {
        label: float(recalls[label]) for label in PROGRESSION_LABELS
    }
    result["best_epoch"] = best_epoch
    return result


def _mean_sd(values: Sequence[float]) -> dict[str, float]:
    if len(values) != len(SEEDS):
        raise ValueError("Slim summary requires exactly three seeds")
    return {
        "mean": float(statistics.fmean(values)),
        "sd": float(statistics.stdev(values)),
    }


def summarize_and_select(
    cells: Mapping[str, Mapping[int, Mapping[str, Any]]],
    *,
    macro_f1_tolerance: float = 0.003,
    oder_tolerance: float = 0.0005,
    recall_tolerance: float = 0.01,
) -> dict[str, Any]:
    if set(cells) != set(SLIM_ARMS):
        raise ValueError("Slim finalizer requires all four arms")
    summaries: dict[str, Any] = {}
    for arm in SLIM_ARMS:
        if set(cells[arm]) != set(SEEDS):
            raise ValueError(f"Slim arm lacks three seeds: {arm}")
        seed_rows = {str(seed): dict(cells[arm][seed]) for seed in SEEDS}
        summaries[arm] = {
            "optional_module_count": sum(SLIM_ARMS[arm]),
            "factors": {
                "prototype_alignment": SLIM_ARMS[arm][0],
                "state_anchor": SLIM_ARMS[arm][1],
            },
            "seeds": seed_rows,
            "metrics": {
                name: _mean_sd([float(cells[arm][seed][name]) for seed in SEEDS])
                for name in METRICS
            },
            "per_class_recall": {
                label: _mean_sd(
                    [
                        float(cells[arm][seed]["per_class_recall"][label])
                        for seed in SEEDS
                    ]
                )
                for label in PROGRESSION_LABELS
            },
        }
    best_macro = max(
        value["metrics"]["macro_f1"]["mean"] for value in summaries.values()
    )
    best_oder = min(
        value["metrics"]["opposite_direction_error_rate"]["mean"]
        for value in summaries.values()
    )
    best_recalls = {
        label: max(
            value["per_class_recall"][label]["mean"] for value in summaries.values()
        )
        for label in PROGRESSION_LABELS
    }
    admissibility = {}
    admissible = []
    for arm, value in summaries.items():
        tests = {
            "macro_f1_within_tolerance": (
                value["metrics"]["macro_f1"]["mean"] >= best_macro - macro_f1_tolerance
            ),
            "oder_within_tolerance": (
                value["metrics"]["opposite_direction_error_rate"]["mean"]
                <= best_oder + oder_tolerance
            ),
            "all_class_recalls_within_tolerance": all(
                value["per_class_recall"][label]["mean"]
                >= best_recalls[label] - recall_tolerance
                for label in PROGRESSION_LABELS
            ),
        }
        tests["admissible"] = all(tests.values())
        admissibility[arm] = tests
        if tests["admissible"]:
            admissible.append(arm)
    if admissible:
        selected = min(
            admissible,
            key=lambda arm: (summaries[arm]["optional_module_count"], arm),
        )
        disposition = "SELECTED_SIMPLEST_WITHIN_FROZEN_TOLERANCES"
    else:
        selected = "Slim-S0"
        disposition = "NO_COMMON_ADMISSIBLE_ARM_RETAIN_NO_SIMPLIFICATION_REFERENCE"
    return {
        "arm_summaries": summaries,
        "reference_best": {
            "macro_f1": best_macro,
            "opposite_direction_error_rate": best_oder,
            "per_class_recall": best_recalls,
        },
        "admissibility": admissibility,
        "admissible_arms": sorted(admissible),
        "selected_arm": selected,
        "selection_disposition": disposition,
        "selection_rule": {
            "macro_f1_tolerance": macro_f1_tolerance,
            "oder_tolerance": oder_tolerance,
            "per_class_recall_tolerance": recall_tolerance,
            "tie_break": "fewest optional modules then lexical arm ID",
            "no_admissible_fallback": "Slim-S0 no-simplification reference",
        },
    }


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# PRTA-CXR-Slim Train-only 最小矩阵结果",
        "",
        f"状态：`{result['status']}`",
        "",
        (
            "该矩阵只使用原 Train 患者构建的新 patient-disjoint 选择面；"
            "未使用原 Dev、Internal-test、Gold 或外部结果。"
        ),
        "",
        "| Arm | Prototype CE | State anchor | Macro-F1 | ODER | Min recall | 判定 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for arm, value in result["arm_summaries"].items():
        metrics = value["metrics"]
        decision = (
            "admissible"
            if result["admissibility"][arm]["admissible"]
            else "not admissible"
        )
        lines.append(
            f"| {arm} | {'✓' if value['factors']['prototype_alignment'] else '—'} "
            f"| {'✓' if value['factors']['state_anchor'] else '—'} "
            f"| {metrics['macro_f1']['mean']:.6f} ± {metrics['macro_f1']['sd']:.6f} "
            f"| {metrics['opposite_direction_error_rate']['mean']:.6f} ± "
            f"{metrics['opposite_direction_error_rate']['sd']:.6f} "
            f"| {metrics['min_class_recall']['mean']:.6f} ± "
            f"{metrics['min_class_recall']['sd']:.6f} | {decision} |"
        )
    lines.extend(
        [
            "",
            f"冻结规则选择：`{result['selected_arm']}`（`{result['selection_disposition']}`）。",
            "",
            (
                "选择规则在运行前冻结：Macro-F1 距最佳不超过 0.003，"
                "ODER 距最低不超过 0.0005，每类 recall 距该类最佳不超过 "
                "0.01；满足时选择可选模块最少者。"
            ),
            "",
            "历史 V2 与完整消融结果全部保留；本表只决定后续 Slim 候选，不删除旧证据。",
            "",
        ]
    )
    return "\n".join(lines)


def finalize_slim_matrix_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize the frozen Slim matrix")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--offload-reconciliation", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    preparation_path = args.root / "preparation_receipt.json"
    preparation = _read_json(preparation_path)
    if preparation.get("schema") != "prta-cxr.slim-matrix-preparation.v1":
        raise ValueError("unsupported Slim preparation schema")
    if preparation.get("status") != "PASS_SLIM_MATRIX_FROZEN":
        raise ValueError("Slim matrix preparation is not PASS")
    _closed(preparation, label="Slim preparation")
    reconciliation_inventory = None
    if args.offload_reconciliation is not None:
        reconciliation = _read_json(args.offload_reconciliation)
        if reconciliation.get("schema") != "prta-cxr.slim-offload-reconciliation.v1":
            raise ValueError("unsupported Slim offload reconciliation")
        if reconciliation.get("status") != "PASS_SLIM_OFFLOAD_RECONCILED":
            raise ValueError("Slim offload reconciliation is not PASS")
        if reconciliation.get("server_preparation_sha256") != sha256_file(
            preparation_path
        ):
            raise ValueError("Slim offload reconciliation preparation drift")
        _closed(reconciliation, label="Slim offload reconciliation")
        reconciliation_inventory = {
            "path": str(args.offload_reconciliation),
            "sha256": sha256_file(args.offload_reconciliation),
            "imported_seed43": sorted(reconciliation.get("imported_seed43", {})),
        }
    lane_inventory = {}
    for lane in LANES:
        path = args.root / "results" / lane / "completion.json"
        completion = _read_json(path)
        if completion.get("schema") != "prta-cxr.phase16-lane-completion.v1":
            raise ValueError(f"unsupported Slim lane completion: {lane}")
        if completion.get("status") != "PASS" or completion.get("failures") != []:
            raise ValueError(f"Slim lane is not PASS: {lane}")
        if completion.get("lane") != lane:
            raise ValueError(f"Slim lane identity drift: {lane}")
        if (
            completion.get("queue_sha256")
            != preparation["queue_hashes"][f"{lane}.json"]
        ):
            raise ValueError(f"Slim lane queue hash drift: {lane}")
        _closed(completion, label=f"Slim lane {lane}")
        lane_inventory[lane] = {
            "completion_sha256": sha256_file(path),
            "completed_job_count": len(completion.get("completed", [])),
        }
    cells: dict[str, dict[int, dict[str, Any]]] = {arm: {} for arm in SLIM_ARMS}
    receipt_inventory = {}
    config_inventory = {}
    selection_manifest_path = (
        args.root / "selection" / "train_only_selection_v1.jsonl"
    )
    if sha256_file(selection_manifest_path) != preparation["derived_manifest_sha256"]:
        raise ValueError("Slim selection manifest hash drift")
    selection_rows = _read_jsonl(selection_manifest_path)
    for arm in SLIM_ARMS:
        for seed in SEEDS:
            experiment_id = f"{arm}-S{seed}"
            config_path = args.root / "configs" / f"{experiment_id}.json"
            if (
                sha256_file(config_path)
                != preparation["config_file_hashes"][config_path.name]
            ):
                raise ValueError(f"Slim config file drift: {experiment_id}")
            config = _read_json(config_path)
            source_config_sha256 = canonical_sha256(config)
            if (
                source_config_sha256
                != preparation["config_hashes"][config_path.name]
            ):
                raise ValueError(f"Slim config identity drift: {experiment_id}")
            effective_config_sha256 = _effective_training_config_sha256(
                config, selection_rows
            )
            path = (
                args.root / "results" / "runs" / experiment_id / "training_receipt.json"
            )
            receipt = _read_json(path)
            if receipt.get("config_sha256") != effective_config_sha256:
                raise ValueError(f"Slim receipt config drift: {experiment_id}")
            input_hashes = dict(receipt.get("input_hashes", {}))
            if (
                input_hashes.get("split_manifest")
                != preparation["derived_manifest_sha256"]
            ):
                raise ValueError(f"Slim selection manifest drift: {experiment_id}")
            cells[arm][seed] = _best_epoch_metrics(receipt)
            receipt_inventory[experiment_id] = sha256_file(path)
            config_inventory[experiment_id] = {
                "config_file_sha256": sha256_file(config_path),
                "source_config_sha256": source_config_sha256,
                "effective_config_sha256": effective_config_sha256,
            }
    selection = summarize_and_select(
        cells,
        macro_f1_tolerance=float(preparation["selection_rule"]["macro_f1_tolerance"]),
        oder_tolerance=float(preparation["selection_rule"]["oder_tolerance"]),
        recall_tolerance=float(
            preparation["selection_rule"]["per_class_recall_tolerance"]
        ),
    )
    result = {
        "schema": "prta-cxr.slim-matrix-final.v1",
        "status": "PASS_SLIM_MATRIX_SELECTED",
        "created_at": datetime.now(UTC).isoformat(),
        "preparation_sha256": sha256_file(preparation_path),
        "finalizer_module_sha256": sha256_file(Path(__file__)),
        "offload_reconciliation": reconciliation_inventory,
        "lane_completions": lane_inventory,
        "config_sha256": config_inventory,
        "training_receipt_sha256": receipt_inventory,
        **selection,
        "selection_performed": True,
        "winner_selected": True,
        "current_dev_used_for_selection": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new(args.output_json, json.dumps(result, indent=2, sort_keys=True) + "\n")
    _write_new(args.output_markdown, render_markdown(result))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
