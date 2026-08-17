import json
from pathlib import Path

import pytest
import torch

from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.phase16_finalize import reconcile_phase16_states


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path):
    experiment_id = "P16-NOISE-05-S17"
    config = {"experiment_id": experiment_id, "seed": 17}
    input_hashes = {"split_manifest": "a" * 64}
    output = tmp_path / "output" / "runs" / experiment_id
    receipt_path = output / "training_receipt.json"
    checkpoint_path = output / "best.pt"
    config_path = tmp_path / "program" / "config.json"
    _write_json(config_path, config)
    _write_json(
        receipt_path,
        {
            "schema": "prta-cxr.training-receipt.v1",
            "status": "PASS_TRAINING_FINISHED",
            "seed": 17,
            "best_epoch": 1,
            "best_dev_macro_f1": 0.75,
            "history": [{"epoch": 1, "macro_f1": 0.75}],
            "config_sha256": canonical_sha256(config),
            "input_hashes": input_hashes,
            "internal_test_opened": False,
            "protected_outcomes_opened": False,
        },
    )
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "schema": "prta-cxr.checkpoint.v1",
            "config": config,
            "input_hashes": input_hashes,
        },
        checkpoint_path,
    )
    job_id = f"train-{experiment_id}"
    registry = {
        "schema": "prta-cxr.phase16-job-registry.v1",
        "jobs": [
            {
                "job_id": job_id,
                "group": "label_noise",
                "estimated_seconds": 1,
                "dependencies": [],
                "command": ["python"],
                "expected_outputs": [
                    f"{{output_root}}/runs/{experiment_id}/training_receipt.json",
                    f"{{output_root}}/runs/{experiment_id}/best.pt",
                ],
            }
        ],
    }
    state_root = tmp_path / "states"
    state = {
        "schema": "prta-cxr.phase16-job-state.v1",
        "status": "PASS",
        "job_id": job_id,
        "group": "label_noise",
        "return_code": 0,
        "source_commit": "a" * 40,
        "command": ["python", "train.py", "--config", str(config_path)],
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
    _write_json(state_root / f"{job_id}.json", state)
    return registry, state_root, state


def test_reconcile_phase16_states_validates_training_provenance(tmp_path: Path):
    registry, state_root, _ = _fixture(tmp_path)
    result = reconcile_phase16_states(registry, {"main": state_root})
    assert result["status"] == "PASS_PHASE16_FINAL_NO_SELECTION_AGGREGATE"
    assert result["selected_pass_count"] == 1
    selected = result["selected_jobs"][0]
    assert selected["training"]["experiment_id"] == "P16-NOISE-05-S17"
    assert selected["training"]["checkpoint_sha256"]
    assert result["selection_performed"] is False


def test_reconcile_phase16_states_rejects_duplicate_pass(tmp_path: Path):
    registry, state_root, state = _fixture(tmp_path)
    second = tmp_path / "second"
    _write_json(second / f"{state['job_id']}.json", state)
    with pytest.raises(ValueError, match="exactly one PASS"):
        reconcile_phase16_states(registry, {"main": state_root, "retry": second})


def test_reconcile_phase16_states_rejects_protected_access(tmp_path: Path):
    registry, state_root, state = _fixture(tmp_path)
    state["protected_outcome_read_count"] = 1
    _write_json(state_root / f"{state['job_id']}.json", state)
    with pytest.raises(ValueError, match="protected reads"):
        reconcile_phase16_states(registry, {"main": state_root})
