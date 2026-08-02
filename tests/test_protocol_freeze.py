import json

import pytest

from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.protocol_freeze import queue_plan_projection, validate_protocol_freeze


def test_validate_protocol_freeze_detects_changed_input(tmp_path):
    input_path = tmp_path / "input.json"
    input_path.write_text("{}\n", encoding="utf-8")
    receipt_path = tmp_path / "freeze.json"
    receipt = {
        "status": "PASS_PROTOCOL_FROZEN__FORMAL_OUTCOMES_CLOSED",
        "input_paths": {"data": str(input_path)},
        "input_hashes": {"data": sha256_file(input_path)},
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    validate_protocol_freeze(receipt, receipt_path=receipt_path)
    input_path.write_text("{\"changed\": true}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="input changed"):
        validate_protocol_freeze(receipt, receipt_path=receipt_path)


def test_queue_plan_projection_ignores_runtime_scheduler_fields():
    planned = {
        "experiment_id": "B401-S17",
        "status": "PLANNED",
        "stage": "formal",
        "config_path": "config.json",
        "config_sha256": "a",
        "effective_config_sha256": "b",
        "train_fraction": 1.0,
        "seed": 17,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    completed = {
        **planned,
        "status": "PASS_TRAINING_FINISHED",
        "pid": 123,
        "device": "cuda:0",
        "stdout_path": "run.stdout.log",
    }
    assert canonical_sha256([planned]) == canonical_sha256(
        queue_plan_projection([completed])
    )
