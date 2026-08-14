from __future__ import annotations

import os

from prta_cxr.contracts import canonical_sha256
from prta_cxr.queue_runner import process_alive
from prta_cxr.wave046_amendment import (
    ORIGINAL_QUEUE_SHA256,
    frozen_queue_identity,
)


def test_pid_alive_accepts_current_process() -> None:
    assert process_alive(os.getpid())


def test_frozen_queue_identity_removes_only_execution_fields() -> None:
    rows = [
        {
            "experiment_id": "A",
            "status": "RUNNING",
            "config_path": "config.json",
            "config_sha256": "abc",
            "effective_config_sha256": "def",
            "seed": 17,
            "stage": "stage",
            "train_fraction": 1.0,
            "internal_test_opened": False,
            "gold_opened": False,
            "pid": 123,
            "device": "cuda:0",
            "started_at": "now",
            "output_path": "out",
            "stdout_path": "stdout",
            "stderr_path": "stderr",
        }
    ]
    frozen = frozen_queue_identity(rows)
    assert frozen == [
        {
            "experiment_id": "A",
            "status": "PLANNED",
            "config_path": "config.json",
            "config_sha256": "abc",
            "effective_config_sha256": "def",
            "seed": 17,
            "stage": "stage",
            "train_fraction": 1.0,
            "internal_test_opened": False,
            "gold_opened": False,
        }
    ]
    assert canonical_sha256(frozen) != ORIGINAL_QUEUE_SHA256
