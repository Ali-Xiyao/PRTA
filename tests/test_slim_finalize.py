import json

from prta_cxr.authorization import FORMAL_ENV_NAME, FORMAL_ENV_VALUE
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.experiments import materialize_classification_counts
from prta_cxr.phase16_queue import LANES
from prta_cxr.slim_finalize import finalize_slim_matrix_main
from prta_cxr.slim_matrix import SEEDS, SLIM_ARMS


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _config(arm, seed):
    prototype_on, state_on = SLIM_ARMS[arm]
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": f"{arm}-S{seed}",
        "seed": seed,
        "model": {"family": "prta", "components": {}},
        "optimization": {"epochs": 1},
        "loss_weights": {
            "classification": 1.0,
            "prototype_alignment": 0.01 if prototype_on else 0.0,
            "state": 0.025 if state_on else 0.0,
        },
    }


def _receipt(config, manifest_sha256):
    effective = materialize_classification_counts(
        config,
        [
            {"split": "train", "progression_label": label}
            for label in PROGRESSION_LABELS
        ],
    )
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
        "input_hashes": {"split_manifest": manifest_sha256},
        "protected_outcomes_opened": False,
        "protected_outcome_read_count": 0,
    }


def test_finalizer_replays_effective_config_materialization(tmp_path, monkeypatch):
    root = tmp_path / "slim"
    manifest = root / "selection" / "train_only_selection_v1.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "".join(
            json.dumps(
                {
                    "sample_id": f"{split}-sample-{index}",
                    "patient_id_hash": f"{split}-patient-{index}",
                    "source": "test",
                    "split": split,
                    "progression_label": label,
                }
            )
            + "\n"
            for split in ("train", "dev")
            for index, label in enumerate(PROGRESSION_LABELS)
        ),
        encoding="utf-8",
    )
    manifest_sha256 = sha256_file(manifest)
    config_hashes = {}
    config_file_hashes = {}
    for arm in SLIM_ARMS:
        for seed in SEEDS:
            experiment_id = f"{arm}-S{seed}"
            config = _config(arm, seed)
            config_path = root / "configs" / f"{experiment_id}.json"
            _write_json(config_path, config)
            config_hashes[config_path.name] = canonical_sha256(config)
            config_file_hashes[config_path.name] = sha256_file(config_path)
            receipt = _receipt(config, manifest_sha256)
            assert receipt["config_sha256"] != config_hashes[config_path.name]
            _write_json(
                root / "results" / "runs" / experiment_id / "training_receipt.json",
                receipt,
            )
    queue_hashes = {}
    for lane in LANES:
        queue_hashes[f"{lane}.json"] = f"queue-{lane}"
        _write_json(
            root / "results" / lane / "completion.json",
            {
                "schema": "prta-cxr.phase16-lane-completion.v1",
                "status": "PASS",
                "lane": lane,
                "queue_sha256": f"queue-{lane}",
                "failures": [],
                "completed": [],
                "protected_outcome_read_count": 0,
            },
        )
    _write_json(
        root / "preparation_receipt.json",
        {
            "schema": "prta-cxr.slim-matrix-preparation.v1",
            "status": "PASS_SLIM_MATRIX_FROZEN",
            "config_hashes": config_hashes,
            "config_file_hashes": config_file_hashes,
            "derived_manifest_sha256": manifest_sha256,
            "queue_hashes": queue_hashes,
            "selection_rule": {
                "macro_f1_tolerance": 0.003,
                "oder_tolerance": 0.0005,
                "per_class_recall_tolerance": 0.01,
            },
            "protected_outcome_read_count": 0,
        },
    )
    output_json = tmp_path / "slim-final.json"
    output_markdown = tmp_path / "slim-final.md"
    monkeypatch.setenv(FORMAL_ENV_NAME, FORMAL_ENV_VALUE)
    assert (
        finalize_slim_matrix_main(
            [
                "--root",
                str(root),
                "--output-json",
                str(output_json),
                "--output-markdown",
                str(output_markdown),
                "--formal",
            ]
        )
        == 0
    )
    result = json.loads(output_json.read_text(encoding="utf-8"))
    assert result["status"] == "PASS_SLIM_MATRIX_SELECTED"
    assert result["selected_arm"] == "Slim-S3"
    assert set(result["config_sha256"]) == {
        f"{arm}-S{seed}" for arm in SLIM_ARMS for seed in SEEDS
    }
