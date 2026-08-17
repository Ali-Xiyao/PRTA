from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file

SEEDS = (17, 28, 43)
VARIANTS = (
    "IF-A01",
    "IF-A02",
    "IF-A03",
    "IF-A04",
    "IF-A05",
    "IF-A06",
    "IF-A08",
    "IF-A10",
    "IF-A11",
    "IF-F01",
    "IF-F02",
)
METRICS = (
    "macro_f1",
    "balanced_accuracy",
    "min_class_recall",
    "opposite_direction_error_rate",
    "nll",
    "brier",
    "true_minus_wrong_prior_gap",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _matrix(preparation: Mapping[str, Any]) -> dict[str, str]:
    if preparation.get("status") != "PASS_IFUSION_CORE_MATRIX_FROZEN":
        raise ValueError("Information Fusion preparation is not frozen PASS")
    if preparation.get("protected_outcome_read_count") != 0:
        raise ValueError("preparation reports protected reads")
    if preparation.get("internal_test_opened") is not False:
        raise ValueError("preparation reports Internal-test access")
    rows = preparation.get("matrix")
    if not isinstance(rows, list):
        raise ValueError("preparation matrix is missing")
    expected: dict[str, str] = {}
    for row in rows:
        run_id = str(row["experiment_id"])
        if run_id in expected:
            raise ValueError(f"duplicate preparation matrix row: {run_id}")
        expected[run_id] = str(row["config_sha256"])
    if len(expected) != int(preparation.get("training_cell_count", -1)):
        raise ValueError("preparation matrix cell count drift")
    return expected


def _best_metrics(receipt: Mapping[str, Any]) -> dict[str, float]:
    best_epoch = int(receipt["best_epoch"])
    history = receipt.get("history")
    if not isinstance(history, list):
        raise ValueError("training receipt history is missing")
    matches = [row for row in history if int(row.get("epoch", -1)) == best_epoch]
    if len(matches) != 1:
        raise ValueError(f"best epoch {best_epoch} is not unique in history")
    best = matches[0]
    metrics = {
        name: float(best[name])
        for name in METRICS
        if name != "true_minus_wrong_prior_gap"
    }
    metrics["true_minus_wrong_prior_gap"] = float(
        receipt["dev_prior_audit"]["true_minus_wrong_prior_gap"]
    )
    if abs(metrics["macro_f1"] - float(receipt["best_dev_macro_f1"])) > 1e-12:
        raise ValueError("best Dev Macro-F1 drift between receipt fields")
    return metrics


def receipt_inventory_row(
    run_id: str,
    receipt_path: Path,
    *,
    expected_config_sha256: str,
) -> dict[str, Any]:
    receipt = _read_json(receipt_path)
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError(f"non-PASS training receipt: {run_id}")
    if receipt.get("config_sha256") != expected_config_sha256:
        raise ValueError(f"training receipt config drift: {run_id}")
    if receipt.get("internal_test_opened") is not False:
        raise ValueError(f"Internal-test access reported: {run_id}")
    protected = receipt.get(
        "protected_outcome_read_count",
        0 if receipt.get("protected_outcomes_opened") is False else -1,
    )
    if protected != 0:
        raise ValueError(f"protected outcome access reported: {run_id}")
    seed = int(receipt["seed"])
    if run_id != f"{run_id.rsplit('-S', 1)[0]}-S{seed}":
        raise ValueError(f"training receipt seed drift: {run_id}")
    return {
        "run_id": run_id,
        "variant": run_id.rsplit("-S", 1)[0],
        "seed": seed,
        "status": str(receipt["status"]),
        "config_sha256": str(receipt["config_sha256"]),
        "receipt_sha256": sha256_file(receipt_path),
        "best_epoch": int(receipt["best_epoch"]),
        "completed_epochs": int(receipt["completed_epochs"]),
        "stopped_early": bool(receipt["stopped_early"]),
        "metrics": _best_metrics(receipt),
        "internal_test_opened": False,
        "protected_outcome_read_count": 0,
    }


def build_receipt_inventory(
    preparation: Mapping[str, Any],
    run_roots: Sequence[Path],
    *,
    source_label: str,
) -> dict[str, Any]:
    expected = _matrix(preparation)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in run_roots:
        for receipt_path in sorted(root.glob("IF-*/training_receipt.json")):
            run_id = receipt_path.parent.name
            if run_id not in expected:
                raise ValueError(f"receipt is not in frozen matrix: {run_id}")
            if run_id in seen:
                raise ValueError(f"duplicate receipt across roots: {run_id}")
            seen.add(run_id)
            rows.append(
                receipt_inventory_row(
                    run_id,
                    receipt_path,
                    expected_config_sha256=expected[run_id],
                )
            )
    if not rows:
        raise ValueError("no Information Fusion training receipts found")
    return {
        "schema": "prta-cxr.ifusion-receipt-inventory.v1",
        "status": "PASS_IFUSION_RECEIPT_INVENTORY",
        "created_at": datetime.now(UTC).isoformat(),
        "source_label": source_label,
        "experiment_matrix_sha256": str(preparation["experiment_matrix_sha256"]),
        "receipt_count": len(rows),
        "receipts": sorted(rows, key=lambda row: str(row["run_id"])),
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def _validate_inventory(
    inventory: Mapping[str, Any],
    *,
    expected_matrix_sha256: str,
) -> list[dict[str, Any]]:
    if inventory.get("status") != "PASS_IFUSION_RECEIPT_INVENTORY":
        raise ValueError("receipt inventory is not PASS")
    if inventory.get("experiment_matrix_sha256") != expected_matrix_sha256:
        raise ValueError("receipt inventory matrix hash drift")
    if inventory.get("protected_outcome_read_count") != 0:
        raise ValueError("receipt inventory reports protected reads")
    if inventory.get("internal_test_opened") is not False:
        raise ValueError("receipt inventory reports Internal-test access")
    rows = inventory.get("receipts")
    if not isinstance(rows, list) or len(rows) != int(inventory["receipt_count"]):
        raise ValueError("receipt inventory row count drift")
    return [dict(row) for row in rows]


def reconcile_inventories(
    preparation: Mapping[str, Any],
    inventories: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected = _matrix(preparation)
    rows: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    for inventory in inventories:
        source = str(inventory["source_label"])
        for row in _validate_inventory(
            inventory,
            expected_matrix_sha256=str(preparation["experiment_matrix_sha256"]),
        ):
            run_id = str(row["run_id"])
            if run_id in rows:
                raise ValueError(f"duplicate reconciled run: {run_id}")
            if expected.get(run_id) != row.get("config_sha256"):
                raise ValueError(f"reconciled config drift: {run_id}")
            if row.get("status") != "PASS_TRAINING_FINISHED":
                raise ValueError(f"reconciled receipt is not PASS: {run_id}")
            if row.get("protected_outcome_read_count") != 0:
                raise ValueError(f"reconciled protected read: {run_id}")
            if row.get("internal_test_opened") is not False:
                raise ValueError(f"reconciled Internal-test access: {run_id}")
            rows[run_id] = row
            sources[run_id] = source
    missing = sorted(set(expected) - set(rows))
    unexpected = sorted(set(rows) - set(expected))
    if missing or unexpected:
        raise ValueError(
            f"reconciled matrix mismatch: missing={missing}, unexpected={unexpected}"
        )

    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run_id, row in rows.items():
        by_variant[str(row["variant"])].append(row)
        if run_id != f"{row['variant']}-S{row['seed']}":
            raise ValueError(f"reconciled identity drift: {run_id}")
    if set(by_variant) != set(VARIANTS):
        raise ValueError("reconciled variant set drift")

    aggregates = {}
    for variant in VARIANTS:
        variant_rows = sorted(by_variant[variant], key=lambda row: int(row["seed"]))
        if [int(row["seed"]) for row in variant_rows] != list(SEEDS):
            raise ValueError(f"seed set drift for {variant}")
        metric_summary = {}
        for metric in METRICS:
            values = [float(row["metrics"][metric]) for row in variant_rows]
            metric_summary[metric] = {
                "mean": float(mean(values)),
                "sample_sd": float(stdev(values)),
                "by_seed": {
                    str(row["seed"]): float(row["metrics"][metric])
                    for row in variant_rows
                },
            }
        aggregates[variant] = {
            "seeds": list(SEEDS),
            "metrics": metric_summary,
        }

    return {
        "schema": "prta-cxr.ifusion-final-33-cell-aggregate.v1",
        "status": "PASS_IFUSION_FINAL_33_CELL_AGGREGATE",
        "created_at": datetime.now(UTC).isoformat(),
        "experiment_matrix_sha256": str(preparation["experiment_matrix_sha256"]),
        "training_cell_count": len(rows),
        "receipt_sources": dict(sorted(sources.items())),
        "receipt_inventory": [rows[key] for key in sorted(rows)],
        "variant_aggregates": aggregates,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def ifusion_finalize_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventory or reconcile frozen Information Fusion receipts"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--preparation", type=Path, required=True)
    inventory_parser.add_argument(
        "--runs-root", type=Path, action="append", required=True
    )
    inventory_parser.add_argument("--source-label", required=True)
    inventory_parser.add_argument("--output", type=Path, required=True)
    inventory_parser.add_argument("--formal", action="store_true")

    reconcile_parser = subparsers.add_parser("reconcile")
    reconcile_parser.add_argument("--preparation", type=Path, required=True)
    reconcile_parser.add_argument(
        "--inventory", type=Path, action="append", required=True
    )
    reconcile_parser.add_argument("--output", type=Path, required=True)
    reconcile_parser.add_argument("--formal", action="store_true")

    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    preparation = _read_json(args.preparation)

    if args.command == "inventory":
        result = build_receipt_inventory(
            preparation,
            args.runs_root,
            source_label=args.source_label,
        )
        _write_new_json(args.output, result)
        print(
            json.dumps(
                {"status": result["status"], "receipt_count": result["receipt_count"]},
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    inventories = [_read_json(path) for path in args.inventory]
    result = reconcile_inventories(preparation, inventories)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    args.output.mkdir(parents=True, exist_ok=False)
    aggregate_path = args.output / "final_33_cell_aggregate.json"
    _write_new_json(aggregate_path, result)
    receipt = {
        "schema": "prta-cxr.ifusion-finalization-receipt.v1",
        "status": "PASS_IFUSION_FINALIZATION_COMPLETE",
        "created_at": datetime.now(UTC).isoformat(),
        "aggregate_sha256": sha256_file(aggregate_path),
        "preparation_sha256": sha256_file(args.preparation),
        "inventory_sha256": {
            str(index): sha256_file(path) for index, path in enumerate(args.inventory)
        },
        "training_cell_count": result["training_cell_count"],
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(args.output / "completion_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
