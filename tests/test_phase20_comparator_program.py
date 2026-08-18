from __future__ import annotations

from copy import deepcopy

import pytest

from prta_cxr.phase20_comparator_program import (
    COMPARATOR_PROTOCOL,
    COMPARATOR_SPECS,
    allocate_phase20_comparator_jobs,
    build_phase20_comparator_configs,
    validate_phase20_comparator_configs,
)
from prta_cxr.phase20_program import PHASE20_PROTOCOL, SEEDS


def _final_s1(seed: int) -> dict:
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": f"P20-FINAL-S1-S{seed}",
        "seed": seed,
        "prta_v2_variant": "Slim-S1",
        "development_axis": PHASE20_PROTOCOL,
        "phase20_protocol": PHASE20_PROTOCOL,
        "phase20_axis": "final_mainline_confirmation",
        "model": {
            "family": "prta",
            "adapter_scope": "tail8",
            "adapter_rank": 32,
            "heads": 8,
            "state_tokens": 4,
            "transition_tokens": 4,
            "native_head": "H0",
            "components": {
                "finding_conditioning": True,
                "cross_time_alignment": True,
                "matched_hard_cmcp": True,
            },
        },
        "optimization": {"epochs": 20},
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.0,
            "branch_decorrelation": 0.0,
            "direction_margin": 0.0,
            "opposite_direction_cost": 0.05,
            "state": 0.025,
            "inversion": 0.0,
            "cmcp": 0.01,
            "prototype_alignment": 0.0,
        },
        "cmcp": {"matching": "offline_hard_v1", "margin": 0.2},
        "data": {"train_fraction": 1.0},
    }


def _configs() -> dict[str, dict]:
    return build_phase20_comparator_configs(
        {seed: _final_s1(seed) for seed in SEEDS}
    )


def test_phase20_comparator_rebuild_freezes_exact_8_by_3_matrix():
    configs = _configs()
    assert len(configs) == 24
    assert {
        (config["phase20_role"], config["seed"]) for config in configs.values()
    } == {(system, seed) for system in COMPARATOR_SPECS for seed in SEEDS}
    assert {config["phase20_protocol"] for config in configs.values()} == {
        COMPARATOR_PROTOCOL
    }
    assert all(
        config["final_mainline_reference"] == "Slim-S1"
        for config in configs.values()
    )


def test_phase20_comparator_rebuild_materializes_audited_loss_contracts():
    configs = _configs()
    v2 = configs["P20-REBUILD-V2-S17"]
    s0 = configs["P20-REBUILD-S0-S17"]
    assert v2["model"]["family"] == "prta"
    assert v2["loss_weights"]["prototype_alignment"] == 0.01
    assert v2["loss_weights"]["direction_margin"] == 0.01
    assert s0["loss_weights"]["prototype_alignment"] == 0.01
    assert s0["loss_weights"]["direction_margin"] == 0.0
    for system in ("B401", "B402", "TILA8", "BioViLT", "CheXRelNet"):
        config = configs[f"P20-REBUILD-{system}-S17"]
        assert config["loss_weights"]["classification"] == 1.0
        assert all(
            value == 0.0
            for name, value in config["loss_weights"].items()
            if name != "classification"
        )
    paper = configs["P20-REBUILD-TILAPaper-S17"]
    assert paper["loss_weights"]["inversion"] == 0.10
    assert paper["official_implementation"] is False
    assert paper["method_provenance"] == "independent_paper_based_reimplementation"


def test_phase20_comparator_validation_rejects_contract_drift():
    configs = _configs()
    broken = deepcopy(configs)
    broken["P20-REBUILD-S0-S17"]["loss_weights"]["direction_margin"] = 0.01
    with pytest.raises(ValueError, match="DMW drift"):
        validate_phase20_comparator_configs(broken)


def test_phase20_comparator_jobs_use_only_three_allowed_balanced_lanes():
    active = ("a800_3066", "a800_9929", "rtx3090_0")
    queues = allocate_phase20_comparator_jobs(_configs(), active_lanes=active)
    assert tuple(queues) == active
    assert "rtx3090_1" not in queues
    jobs = [job for queue in queues.values() for job in queue]
    assert len(jobs) == 24
    assert len({job["job_id"] for job in jobs}) == 24
    assert {job["lane"] for job in jobs} <= set(active)
    assert sum("--counterfactual-prior-map" in job["command"] for job in jobs) == 6
    loads = [
        sum(job["estimated_seconds"] for job in queue) for queue in queues.values()
    ]
    assert max(loads) - min(loads) < 20_000


def test_phase20_comparator_rejects_reserved_or_duplicate_lane_requests():
    configs = _configs()
    with pytest.raises(ValueError, match="unique"):
        allocate_phase20_comparator_jobs(
            configs, active_lanes=("a800_3066", "a800_3066")
        )
    with pytest.raises(ValueError, match="unknown"):
        allocate_phase20_comparator_jobs(configs, active_lanes=("unknown",))
