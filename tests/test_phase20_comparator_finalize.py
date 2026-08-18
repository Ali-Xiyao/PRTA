import json
from pathlib import Path

import pytest

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.phase20_comparator_finalize import (
    _method_summary,
    merge_phase20_comparator_shards,
)
from prta_cxr.phase20_comparator_program import COMPARATOR_SPECS, COMPARATOR_STATUS


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_comparator_summary_includes_three_seed_classes_params_and_time():
    rows = []
    for seed, score in ((17, 0.5), (28, 0.6), (43, 0.7)):
        rows.append(
            {
                "seed": seed,
                "experiment_id": f"P20-REBUILD-B401-S{seed}",
                "hardware_class": "A800-80GB",
                "best_epoch": 2,
                "completed_epochs": 4,
                "duration_seconds": 100 + seed,
                "checkpoint_sha256": str(seed) * 32,
                "training_receipt_sha256": str(seed) * 32,
                "metrics": {
                    "macro_f1": score,
                    "balanced_accuracy": score,
                    "min_class_recall": score,
                    "opposite_direction_error_rate": 0.01,
                },
                "ordinary": {
                    "per_class_recall": {label: score for label in PROGRESSION_LABELS},
                    "per_class_f1": {label: score for label in PROGRESSION_LABELS},
                },
                "parameter_audit": {
                    "total_parameters": 100,
                    "trainable_parameters": 50,
                },
            }
        )
    summary = _method_summary(rows)
    assert summary["scalar_metrics"]["macro_f1"]["mean"] == 0.6
    assert set(summary["per_class_recall"]) == set(PROGRESSION_LABELS)
    assert summary["parameter_count"]["trainable_parameters"] == 50
    assert summary["training_time_seconds"]["n"] == 3


def test_comparator_host_shards_merge_exact_24_cell_roster(tmp_path):
    program = tmp_path / "program"
    rows = []
    for method in COMPARATOR_SPECS:
        for seed in (17, 28, 43):
            rows.append(
                {
                    "job_id": f"train-P20-REBUILD-{method}-S{seed}",
                    "method": method,
                    "seed": seed,
                    "experiment_id": f"P20-REBUILD-{method}-S{seed}",
                    "hardware_class": "A800-80GB",
                    "best_epoch": 1,
                    "completed_epochs": 2,
                    "duration_seconds": 100,
                    "checkpoint_sha256": "a" * 64,
                    "training_receipt_sha256": "b" * 64,
                    "metrics": {"macro_f1": 0.5},
                    "ordinary": {
                        "per_class_recall": {
                            label: 0.5 for label in PROGRESSION_LABELS
                        },
                        "per_class_f1": {label: 0.5 for label in PROGRESSION_LABELS},
                    },
                    "parameter_audit": {
                        "total_parameters": 10,
                        "trainable_parameters": 5,
                    },
                }
            )
    _write(
        program / "job_registry.json",
        {"jobs": [{"job_id": row["job_id"]} for row in rows]},
    )
    _write(
        program / "preparation_receipt.json",
        {
            "status": COMPARATOR_STATUS,
            "source_commit": "a" * 40,
            "registry_sha256": sha256_file(program / "job_registry.json"),
        },
    )
    paths = []
    for host, selected in (("server", rows[:12]), ("local", rows[12:])):
        shard = {
            "status": "PASS_PHASE20_COMPARATOR_HOST_SHARD_VALIDATED",
            "host": host,
            "program_preparation_sha256": sha256_file(
                program / "preparation_receipt.json"
            ),
            "source_commit": "a" * 40,
            "unique_pass_count": len(selected),
            "job_ids": [row["job_id"] for row in selected],
            "cells": selected,
            "external_evaluation_included": False,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        }
        path = tmp_path / f"{host}.json"
        _write(path, shard)
        paths.append(path)
    result = merge_phase20_comparator_shards(program, paths)
    assert result["unique_pass_count"] == 24
    assert set(result["methods"]) == set(COMPARATOR_SPECS)
    broken = json.loads(paths[1].read_text(encoding="utf-8"))
    broken["cells"] = broken["cells"][1:]
    _write(tmp_path / "broken.json", broken)
    with pytest.raises(ValueError, match="payload/job drift"):
        merge_phase20_comparator_shards(program, [paths[0], tmp_path / "broken.json"])
