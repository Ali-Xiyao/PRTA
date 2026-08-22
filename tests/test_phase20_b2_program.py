from collections import Counter

import pytest

from prta_cxr.phase20_b2_program import (
    B2_DEFAULT_LANES,
    artifact_hash_inventory_from_finalizers,
    build_phase20_b2_jobs,
)


def test_phase20_b2_program_has_27_exports_then_guarded_statistics():
    jobs = build_phase20_b2_jobs()
    by_id = {job["job_id"]: job for job in jobs}
    assert len(jobs) == 28
    exports = [job for job in jobs if job["group"] == "phase20_b2_probability_export"]
    assert len(exports) == 27
    assert all(job["lane"] == "rtx3090_0" for job in jobs)
    command = by_id["b2-export-S0-S17"]["command"]
    assert command[command.index("--diagnostic-scope") + 1] == "phase20_b2"
    assert "--true-only" in command
    statistics = by_id["b2-post-comparator-statistics"]
    assert len(statistics["dependencies"]) == 27
    assert "10000" in statistics["command"]
    assert "20260818" in statistics["command"]


def test_phase20_b2_program_balances_four_lanes_and_places_statistics_on_a800():
    jobs = build_phase20_b2_jobs(
        lanes=B2_DEFAULT_LANES,
        statistics_lane="a800_3066",
    )
    exports = [job for job in jobs if job["group"] == "phase20_b2_probability_export"]
    assert Counter(job["lane"] for job in exports) == {
        "a800_3066": 7,
        "a800_9929": 8,
        "rtx3090_0": 6,
        "rtx3090_1": 6,
    }
    statistics = jobs[-1]
    assert statistics["lane"] == "a800_3066"
    assert statistics["host"] == "server"
    assert len(statistics["dependencies"]) == 27


def test_phase20_b2_program_rejects_partial_or_inactive_lane_assignment():
    with pytest.raises(ValueError, match="exact 9x3"):
        build_phase20_b2_jobs(
            lanes=B2_DEFAULT_LANES,
            statistics_lane="a800_3066",
            artifact_lanes={("V2", 17): "a800_3066"},
        )


def test_artifact_hash_inventory_can_be_frozen_without_cross_host_mounts():
    systems = (
        "V2",
        "S0",
        "B401",
        "B402",
        "TILA8",
        "BioViLT",
        "CheXRelNet",
        "TILAPaper",
    )
    comparator = {
        "cells": [
            {
                "method": system,
                "seed": seed,
                "checkpoint_sha256": "a" * 64,
                "training_receipt_sha256": "b" * 64,
            }
            for system in systems
            for seed in (17, 28, 43)
        ]
    }
    phase20_a = {
        "training": [
            {
                "experiment_id": f"P20-F02-DMW0-S{seed}",
                "checkpoint_sha256": "c" * 64,
                "training_receipt_sha256": "d" * 64,
            }
            for seed in (17, 28, 43)
        ]
    }
    inventory = artifact_hash_inventory_from_finalizers(
        phase20_a_final=phase20_a, comparator_final=comparator
    )
    assert len(inventory) == 27
    assert inventory[("V2", 17)] == ("a" * 64, "b" * 64)
    assert inventory[("F02-DMW0", 43)] == ("c" * 64, "d" * 64)
