import json
from pathlib import PurePosixPath

import pytest

from prta_cxr.contracts import ContractError
from prta_cxr.server_dev_search import (
    build_direction_margin_wave,
    prepare_direction_margin_wave,
)


def _parent():
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "TUNE-FG1-S17",
        "seed": 17,
        "development_axis": "exploratory_loss_screen_v1",
        "classification_loss": {
            "name": "class_balanced_focal",
            "beta": 0.9999,
            "gamma": 1.0,
            "class_counts": [10, 9, 8, 7, 6],
        },
        "model": {"family": "prta", "native_head": "H0"},
        "optimization": {"learning_rate": 0.0001},
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.0,
            "cmcp": 0.0,
            "inversion": 0.0,
            "state": 0.0,
        },
    }


def test_direction_margin_wave_changes_only_small_loss_constraint():
    parent = _parent()
    configs = build_direction_margin_wave(parent, weights=(0.02, 0.05))
    assert [value["experiment_id"] for value in configs] == [
        "SVR-FG1-DMW020-S17",
        "SVR-FG1-DMW050-S17",
    ]
    for value, weight in zip(configs, (0.02, 0.05), strict=True):
        assert value["model"] == parent["model"]
        assert value["optimization"] == parent["optimization"]
        assert value["classification_loss"] == parent["classification_loss"]
        assert value["loss_weights"]["direction_margin"] == weight
        assert value["direction_margin"] == {"margin": 0.2}


def test_direction_margin_wave_rejects_broad_or_duplicate_values():
    with pytest.raises(ContractError, match="two distinct"):
        build_direction_margin_wave(_parent(), weights=(0.02, 0.02))
    with pytest.raises(ContractError, match=r"in \(0, 0.5\]"):
        build_direction_margin_wave(_parent(), weights=(0.02, 0.8))


def test_prepare_wave_binds_readiness_and_remote_allocations(tmp_path):
    parent = tmp_path / "parent.json"
    readiness = tmp_path / "readiness.json"
    parent.write_text(json.dumps(_parent()), encoding="utf-8")
    readiness.write_text(
        json.dumps(
            {
                "status": "PASS_SUES_HPC_ENGINEERING_READINESS",
                "internal_test_opened": False,
                "gold_opened": False,
            }
        ),
        encoding="utf-8",
    )
    receipt = prepare_direction_margin_wave(
        parent_config=parent,
        readiness_receipt=readiness,
        output_root=tmp_path / "wave001",
        remote_output_root=PurePosixPath("/remote/wave001"),
        weights=(0.02, 0.05),
    )
    assert receipt["status"] == "PASS_SERVER_DEV_SEARCH_WAVE_PREPARED"
    assert receipt["allocations"] == [4161, 3066]
    queue = json.loads((tmp_path / "wave001" / "run_queue.json").read_text())
    assert [row["allocation_id"] for row in queue] == [4161, 3066]
    assert all("/remote/wave001/configs/" in row["remote_config_path"] for row in queue)
    assert receipt["protected_outcome_read_count"] == 0
