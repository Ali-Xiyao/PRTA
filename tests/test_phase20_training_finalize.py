import json
from pathlib import Path

import pytest
import torch

from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.phase20_training_finalize import (
    merge_phase20_training_shards,
    validate_phase20_training_job,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path):
    experiment = "P20-FINAL-S1-S17"
    config = {"experiment_id": experiment, "seed": 17}
    program = tmp_path / "program"
    config_path = program / "configs" / f"{experiment}.json"
    _write(config_path, config)
    frozen_inputs = {
        "split_manifest": "1" * 64,
        "cleaned_split_freeze": "2" * 64,
        "cache_manifest": "3" * 64,
        "text_cache": "4" * 64,
        "weights": "5" * 64,
        "label_quality_audit": "6" * 64,
        "matched_hard_prior_map": "7" * 64,
    }
    output = tmp_path / "output" / "runs" / experiment
    receipt_path = output / "training_receipt.json"
    checkpoint_path = output / "best.pt"
    history = [
        {
            "epoch": 1,
            "macro_f1": 0.7,
            "ordinary": {
                "macro_f1": 0.7,
                "per_class_recall": {},
                "per_class_f1": {},
            },
        }
    ]
    receipt = {
        "schema": "prta-cxr.training-receipt.v1",
        "status": "PASS_TRAINING_FINISHED",
        "formal_experiment": True,
        "seed": 17,
        "best_epoch": 1,
        "best_dev_macro_f1": 0.7,
        "completed_epochs": 2,
        "history": history,
        "config_sha256": canonical_sha256(config),
        "input_hashes": frozen_inputs,
        "parameter_audit": {"total_parameters": 10, "trainable_parameters": 5},
        "start_time": "2026-08-18T00:00:00+00:00",
        "end_time": "2026-08-18T00:01:00+00:00",
        "internal_test_opened": False,
        "protected_outcomes_opened": False,
    }
    _write(receipt_path, receipt)
    torch.save(
        {
            "schema": "prta-cxr.checkpoint.v1",
            "config": config,
            "input_hashes": frozen_inputs,
            "best_epoch": 1,
            "best_dev_macro_f1": 0.7,
            "parameter_audit": receipt["parameter_audit"],
        },
        checkpoint_path,
    )
    job = {
        "job_id": f"train-{experiment}",
        "group": "final_mainline_confirmation",
        "lane": "a800_3066",
        "hardware_class": "A800-80GB",
        "expected_outputs": [
            f"{{output_root}}/runs/{experiment}/training_receipt.json",
            f"{{output_root}}/runs/{experiment}/best.pt",
        ],
    }
    command = [
        "python",
        "train.py",
        "--config",
        str(config_path),
        "--counterfactual-prior-map",
        str(tmp_path / "map.json"),
    ]
    Path(command[-1]).write_text("map", encoding="utf-8")
    frozen_inputs["matched_hard_prior_map"] = sha256_file(Path(command[-1]))
    receipt["input_hashes"] = frozen_inputs
    _write(receipt_path, receipt)
    checkpoint = torch.load(checkpoint_path, weights_only=True)
    checkpoint["input_hashes"] = frozen_inputs
    torch.save(checkpoint, checkpoint_path)
    state = {
        "schema": "prta-cxr.phase20-job-state.v1",
        "status": "PASS",
        "job_id": job["job_id"],
        "group": job["group"],
        "lane": job["lane"],
        "return_code": 0,
        "source_commit": "a" * 40,
        "queue_sha256": "b" * 64,
        "command": command,
        "output_checks": [
            {
                "path": str(receipt_path),
                "exists": True,
                "sha256": sha256_file(receipt_path),
            },
            {
                "path": str(checkpoint_path),
                "exists": True,
                "sha256": sha256_file(checkpoint_path),
            },
        ],
    }
    return job, state, program, frozen_inputs


def test_phase20_training_finalizer_validates_checkpoint_receipt_and_best_epoch(
    tmp_path,
):
    job, state, program, frozen_inputs = _fixture(tmp_path)
    row = validate_phase20_training_job(
        job,
        state,
        program_root=program,
        program_source_commit="a" * 40,
        queue_sha256="b" * 64,
        frozen_inputs=frozen_inputs,
    )
    assert row["experiment_id"] == "P20-FINAL-S1-S17"
    assert row["best_epoch"] == 1
    assert row["duration_seconds"] == 60


def test_phase20_training_finalizer_rejects_source_or_protected_drift(tmp_path):
    job, state, program, frozen_inputs = _fixture(tmp_path)
    broken = dict(state)
    broken["source_commit"] = "c" * 40
    with pytest.raises(ValueError, match="source commit drift"):
        validate_phase20_training_job(
            job,
            broken,
            program_root=program,
            program_source_commit="a" * 40,
            queue_sha256="b" * 64,
            frozen_inputs=frozen_inputs,
        )
    broken = dict(state)
    broken["protected_outcome_read_count"] = 1
    with pytest.raises(ValueError, match="protected reads"):
        validate_phase20_training_job(
            job,
            broken,
            program_root=program,
            program_source_commit="a" * 40,
            queue_sha256="b" * 64,
            frozen_inputs=frozen_inputs,
        )


def test_phase20_training_shards_merge_exact_global_roster(tmp_path):
    program = tmp_path / "program"
    jobs = []
    training = []
    maps = []
    evaluations = []
    for index in range(63):
        seed = (17, 28, 43)[index % 3]
        job_id = f"train-P20-X{index // 3:02d}-S{seed}"
        jobs.append({"job_id": job_id})
        training.append(
            {
                "job_id": job_id,
                "experiment_id": job_id.removeprefix("train-"),
                "seed": seed,
                "metrics": {"macro_f1": 0.5},
            }
        )
    for index in range(19):
        job_id = f"map-{index:02d}"
        jobs.append({"job_id": job_id})
        maps.append({"job_id": job_id})
    for index in range(6):
        job_id = f"evaluate-{index:02d}"
        jobs.append({"job_id": job_id})
        evaluations.append({"job_id": job_id})
    _write(program / "job_registry.json", {"jobs": jobs})
    _write(
        program / "preparation_receipt.json",
        {
            "status": "PASS_PHASE20_SLIM_S1_PROGRAM_FROZEN",
            "source_commit": "a" * 40,
            "registry_sha256": sha256_file(program / "job_registry.json"),
        },
    )
    rows = training + maps + evaluations
    paths = []
    for host, selected in (
        ("server", rows[:44]),
        ("local", rows[44:]),
    ):
        selected_ids = [row["job_id"] for row in selected]
        shard = {
            "status": "PASS_PHASE20_A_HOST_SHARD_VALIDATED",
            "host": host,
            "program_preparation_sha256": sha256_file(
                program / "preparation_receipt.json"
            ),
            "source_commit": "a" * 40,
            "unique_pass_count": len(selected),
            "job_ids": selected_ids,
            "training": [row for row in training if row["job_id"] in selected_ids],
            "transformed_maps": [row for row in maps if row["job_id"] in selected_ids],
            "source_held_evaluations": [
                row for row in evaluations if row["job_id"] in selected_ids
            ],
            "external_evaluation_included": False,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        }
        path = tmp_path / f"{host}.json"
        _write(path, shard)
        paths.append(path)
    result = merge_phase20_training_shards(program, paths)
    assert result["status"] == "PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE"
    assert result["unique_pass_count"] == 88
    broken = json.loads(paths[1].read_text(encoding="utf-8"))
    broken["training"] = broken["training"][1:]
    _write(tmp_path / "broken.json", broken)
    with pytest.raises(ValueError, match="payload/job drift"):
        merge_phase20_training_shards(program, [paths[0], tmp_path / "broken.json"])
