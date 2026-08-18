import json

import pytest

from prta_cxr.authorization import FORMAL_ENV_NAME, FORMAL_ENV_VALUE
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.experiments import materialize_classification_counts
from prta_cxr.slim_matrix import SEEDS, SLIM_ARMS
from prta_cxr.slim_offload_reconcile import (
    _resolve_within,
    reconcile_slim_offload_main,
)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _config(arm, seed):
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": f"{arm}-S{seed}",
        "seed": seed,
        "model": {"family": "prta", "components": {}},
        "optimization": {"epochs": 1},
        "loss_weights": {"classification": 1.0},
    }


def _rows():
    return [
        {
            "sample_id": f"{split}-{index}",
            "patient_id_hash": f"{split}-patient-{index}",
            "source": "test",
            "split": split,
            "progression_label": label,
        }
        for split in ("train", "dev")
        for index, label in enumerate(PROGRESSION_LABELS)
    ]


def _receipt(config, rows, manifest_sha256, input_sha256):
    effective = materialize_classification_counts(config, rows)
    return {
        "schema": "prta-cxr.training-receipt.v1",
        "status": "PASS_TRAINING_FINISHED",
        "best_epoch": 0,
        "history": [
            {
                "epoch": 0,
                "macro_f1": 0.55,
                "opposite_direction_error_rate": 0.005,
                "min_class_recall": 0.47,
                "ordinary": {
                    "per_class_recall": {
                        label: 0.47 for label in PROGRESSION_LABELS
                    }
                },
            }
        ],
        "config_sha256": canonical_sha256(effective),
        "input_hashes": {"split_manifest": manifest_sha256, **input_sha256},
        "protected_outcomes_opened": False,
        "protected_outcome_read_count": 0,
    }


def test_import_paths_cannot_escape_staging_root(tmp_path):
    with pytest.raises(ValueError, match="escapes the import root"):
        _resolve_within(tmp_path, "../outside.json", label="receipt")
    with pytest.raises(ValueError, match="must be relative"):
        _resolve_within(tmp_path, str(tmp_path / "absolute.json"), label="receipt")


def test_reconcile_imports_seed43_and_closes_original_lanes(tmp_path, monkeypatch):
    root = tmp_path / "server"
    import_root = tmp_path / "import"
    rows = _rows()
    selection = root / "selection" / "train_only_selection_v1.jsonl"
    selection.parent.mkdir(parents=True)
    selection.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    selection_sha256 = sha256_file(selection)
    input_sha256 = {
        "cache_manifest": "cache",
        "cleaned_split_freeze": "cleaned",
        "label_quality_audit": "labels",
        "source_cleaned_manifest": "source",
        "text_cache": "text",
        "weights": "weights",
    }
    receipt_input_sha256 = {
        key: value
        for key, value in input_sha256.items()
        if key != "source_cleaned_manifest"
    }
    config_hashes = {}
    config_file_hashes = {}
    server_receipts = {}
    for arm in SLIM_ARMS:
        for seed in SEEDS:
            experiment_id = f"{arm}-S{seed}"
            config = _config(arm, seed)
            config_path = root / "configs" / f"{experiment_id}.json"
            _write(config_path, config)
            config_hashes[config_path.name] = canonical_sha256(config)
            config_file_hashes[config_path.name] = sha256_file(config_path)
            receipt = _receipt(
                config, rows, selection_sha256, receipt_input_sha256
            )
            receipt_path = (
                root / "results" / "runs" / experiment_id / "training_receipt.json"
            )
            _write(receipt_path, receipt)
            server_receipts[experiment_id] = receipt

    lane_jobs = {
        "a800_3066": ["map-slim-train-only"]
        + [
            f"train-{arm}-S{seed}"
            for arm in ("Slim-S0", "Slim-S2")
            for seed in SEEDS
        ],
        "a800_9929": [
            f"train-{arm}-S{seed}"
            for arm in ("Slim-S1", "Slim-S3")
            for seed in SEEDS
        ],
    }
    queue_hashes = {}
    for lane, job_ids in lane_jobs.items():
        queue_path = root / "queue" / f"{lane}.json"
        _write(queue_path, [{"job_id": job_id} for job_id in job_ids])
        queue_hashes[queue_path.name] = sha256_file(queue_path)
    preparation = {
        "schema": "prta-cxr.slim-matrix-preparation.v1",
        "status": "PASS_SLIM_MATRIX_FROZEN",
        "source_commit": "frozen-commit",
        "config_hashes": config_hashes,
        "config_file_hashes": config_file_hashes,
        "derived_manifest_sha256": selection_sha256,
        "input_sha256": input_sha256,
        "queue_hashes": queue_hashes,
        "protected_outcome_read_count": 0,
    }
    preparation_path = root / "preparation_receipt.json"
    _write(preparation_path, preparation)
    _write(
        root / "shared_state" / "map-slim-train-only.json",
        {"status": "PASS", "protected_outcome_read_count": 0},
    )
    for experiment_id in server_receipts:
        _write(
            root / "shared_state" / f"train-{experiment_id}.json",
            {
                "schema": "prta-cxr.phase16-job-state.v1",
                "status": "RUNNING" if experiment_id == "Slim-S0-S17" else "PASS",
                "job_id": f"train-{experiment_id}",
            },
        )

    local_preparation = dict(preparation)
    local_preparation_path = import_root / "local_preparation_receipt.json"
    _write(local_preparation_path, local_preparation)
    cells = {}
    local_lanes = {
        "a800_3066": ["train-Slim-S0-S43", "train-Slim-S2-S43"],
        "a800_9929": ["train-Slim-S1-S43", "train-Slim-S3-S43"],
    }
    for arm in SLIM_ARMS:
        experiment_id = f"{arm}-S43"
        receipt_path = import_root / "receipts" / f"{experiment_id}.json"
        _write(receipt_path, server_receipts[experiment_id])
        state_path = import_root / "states" / f"train-{experiment_id}.json"
        _write(
            state_path,
            {
                "status": "PASS",
                "job_id": f"train-{experiment_id}",
                "output_checks": [
                    {
                        "path": "training_receipt.json",
                        "sha256": sha256_file(receipt_path),
                    },
                    {"path": "best.pt", "sha256": f"checkpoint-{experiment_id}"},
                ],
            },
        )
        cells[experiment_id] = {
            "receipt_path": str(receipt_path.relative_to(import_root)),
            "receipt_sha256": sha256_file(receipt_path),
            "state_path": str(state_path.relative_to(import_root)),
            "effective_config_sha256": server_receipts[experiment_id][
                "config_sha256"
            ],
            "server_lane": (
                "a800_3066" if arm in ("Slim-S0", "Slim-S2") else "a800_9929"
            ),
        }
    lane_records = {}
    for lane, job_ids in local_lanes.items():
        path = import_root / "lanes" / f"{lane}.json"
        _write(
            path,
            {
                "status": "PASS",
                "failures": [],
                "completed": [
                    {"job_id": job_id, "status": "PASS"} for job_id in job_ids
                ],
            },
        )
        lane_records[lane] = {
            "path": str(path.relative_to(import_root)),
            "sha256": sha256_file(path),
            "expected_job_ids": job_ids,
        }
    manifest_path = import_root / "manifest.json"
    _write(
        manifest_path,
        {
            "schema": "prta-cxr.slim-seed43-import-manifest.v1",
            "status": "PASS_LOCAL_SEED43_EXPORT_FROZEN",
            "server_preparation_sha256": sha256_file(preparation_path),
            "local_preparation_path": str(
                local_preparation_path.relative_to(import_root)
            ),
            "local_preparation_sha256": sha256_file(local_preparation_path),
            "cells": cells,
            "local_lane_completions": lane_records,
            "protected_outcome_read_count": 0,
        },
    )
    retirement = tmp_path / "controller-retirement.json"
    _write(
        retirement,
        {
            "status": "PASS_SLIM_CONTROLLERS_RETIRED",
            "phase16_parents_remain_stopped": True,
            "protected_outcome_read_count": 0,
        },
    )
    output = root / "reconciliation" / "seed43.json"
    monkeypatch.setenv(FORMAL_ENV_NAME, FORMAL_ENV_VALUE)
    assert (
        reconcile_slim_offload_main(
            [
                "--root",
                str(root),
                "--import-root",
                str(import_root),
                "--import-manifest",
                str(manifest_path),
                "--controller-retirement-receipt",
                str(retirement),
                "--output",
                str(output),
                "--formal",
            ]
        )
        == 0
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "PASS_SLIM_OFFLOAD_RECONCILED"
    assert set(result["imported_seed43"]) == {f"{arm}-S43" for arm in SLIM_ARMS}
    for lane, job_ids in lane_jobs.items():
        completion = json.loads(
            (root / "results" / lane / "completion.json").read_text(
                encoding="utf-8"
            )
        )
        assert completion["status"] == "PASS"
        assert [row["job_id"] for row in completion["completed"]] == job_ids
    repaired = json.loads(
        (root / "shared_state" / "train-Slim-S0-S17.json").read_text(
            encoding="utf-8"
        )
    )
    assert repaired["status"] == "PASS"
    assert repaired["reconciliation_origin"] == "terminal_receipt_state_repair"
