from __future__ import annotations

from copy import deepcopy

import pytest

from prta_cxr.ifusion_finalize import METRICS, SEEDS, VARIANTS, reconcile_inventories


def _preparation() -> dict:
    matrix = []
    for variant in VARIANTS:
        for seed in SEEDS:
            matrix.append(
                {
                    "experiment_id": f"{variant}-S{seed}",
                    "config_sha256": f"config-{variant}-{seed}",
                }
            )
    return {
        "status": "PASS_IFUSION_CORE_MATRIX_FROZEN",
        "experiment_matrix_sha256": "matrix-hash",
        "training_cell_count": len(matrix),
        "matrix": matrix,
        "internal_test_opened": False,
        "protected_outcome_read_count": 0,
    }


def _inventory(source: str, rows: list[tuple[str, int]]) -> dict:
    receipts = []
    for variant, seed in rows:
        value = float(seed) / 1000.0
        receipts.append(
            {
                "run_id": f"{variant}-S{seed}",
                "variant": variant,
                "seed": seed,
                "status": "PASS_TRAINING_FINISHED",
                "config_sha256": f"config-{variant}-{seed}",
                "receipt_sha256": f"receipt-{variant}-{seed}",
                "metrics": {metric: value for metric in METRICS},
                "internal_test_opened": False,
                "protected_outcome_read_count": 0,
            }
        )
    return {
        "status": "PASS_IFUSION_RECEIPT_INVENTORY",
        "source_label": source,
        "experiment_matrix_sha256": "matrix-hash",
        "receipt_count": len(receipts),
        "receipts": receipts,
        "internal_test_opened": False,
        "protected_outcome_read_count": 0,
    }


def test_reconcile_inventories_requires_and_aggregates_all_33_cells() -> None:
    rows = [(variant, seed) for variant in VARIANTS for seed in SEEDS]
    result = reconcile_inventories(
        _preparation(),
        [_inventory("left", rows[:17]), _inventory("right", rows[17:])],
    )

    assert result["status"] == "PASS_IFUSION_FINAL_33_CELL_AGGREGATE"
    assert result["training_cell_count"] == 33
    assert result["variant_aggregates"]["IF-A01"]["metrics"]["macro_f1"][
        "mean"
    ] == pytest.approx((0.017 + 0.028 + 0.043) / 3)
    assert result["protected_outcome_read_count"] == 0


def test_reconcile_inventories_rejects_duplicate_run() -> None:
    rows = [(variant, seed) for variant in VARIANTS for seed in SEEDS]
    duplicate = _inventory("duplicate", [rows[0]])

    with pytest.raises(ValueError, match="duplicate reconciled run"):
        reconcile_inventories(
            _preparation(),
            [_inventory("all", rows), duplicate],
        )


def test_reconcile_inventories_rejects_protected_read() -> None:
    rows = [(variant, seed) for variant in VARIANTS for seed in SEEDS]
    inventory = _inventory("all", rows)
    changed = deepcopy(inventory)
    changed["receipts"][0]["protected_outcome_read_count"] = 1

    with pytest.raises(ValueError, match="protected read"):
        reconcile_inventories(_preparation(), [changed])
