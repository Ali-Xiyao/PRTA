import copy

import pytest

from prta_cxr.wave047_confirmation import (
    _server_job_queues,
    build_tail8_tila_config,
)


def _tila_parent():
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "B403-S17",
        "seed": 17,
        "development_axis": "old",
        "classification_loss": {"name": "class_balanced_focal"},
        "data": {"train_fraction": 1.0},
        "loss_weights": {
            "alignment": 0.0,
            "classification": 1.0,
            "cmcp": 0.0,
            "inversion": 0.0,
            "state": 0.0,
        },
        "model": {
            "adapter_rank": 32,
            "adapter_scope": "tail4",
            "family": "tila",
            "native_head": "H0",
        },
        "optimization": {"epochs": 20},
    }


def test_tail8_tila_changes_only_preregistered_identity_scope_and_seed():
    parent = _tila_parent()
    before = copy.deepcopy(parent)
    result = build_tail8_tila_config(parent, seed=28)
    assert parent == before
    assert result["experiment_id"] == "W047-TILA8-S28"
    assert result["seed"] == 28
    assert result["model"]["adapter_scope"] == "tail8"
    assert result["model"]["family"] == "tila"
    assert result["loss_weights"] == parent["loss_weights"]
    assert result["optimization"] == parent["optimization"]


def test_tail8_tila_rejects_non_native_or_auxiliary_parent():
    parent = _tila_parent()
    parent["model"]["family"] = "prta"
    with pytest.raises(ValueError, match="not TILA"):
        build_tail8_tila_config(parent, seed=17)
    parent = _tila_parent()
    parent["loss_weights"]["alignment"] = 0.1
    with pytest.raises(ValueError, match="auxiliary loss"):
        build_tail8_tila_config(parent, seed=17)


def test_server_queues_cover_exact_confirmation_matrix_without_duplicates():
    queues = _server_job_queues()
    jobs = queues[3066] + queues[9929]
    assert len(jobs) == 12
    assert len(set(jobs)) == 12
    assert {job for job in jobs if job.startswith("W047D-")} == {
        f"W047D-V{variant}-S{seed}" for variant in range(3) for seed in (17, 28, 43)
    }
    assert {job for job in jobs if job.startswith("W047-TILA8-")} == {
        "W047-TILA8-S17",
        "W047-TILA8-S28",
        "W047-TILA8-S43",
    }
