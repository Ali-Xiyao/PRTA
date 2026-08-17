import pytest

from prta_cxr.phase15_queue import (
    LANES,
    SEEDS,
    SYSTEMS,
    allocate_two_a800_lanes,
    validate_job_registry,
)


def _job(job_id, system, seed, task, estimate):
    inputs = {
        "split_manifest": "/runtime/split.jsonl",
        "cleaned_split_freeze": "/runtime/freeze.json",
        "cache_root": "/runtime/cache",
        "text_cache": "/runtime/text.pt",
        "matched_hard_prior_map": "/runtime/map.json",
        "weights": "/runtime/weights.pt",
        "label_quality_audit": "/runtime/audit.json",
    }
    return {
        "job_id": job_id,
        "system": system,
        "seed": seed,
        "task": task,
        "estimated_seconds": estimate,
        "checkpoint": f"/runtime/{job_id}/best.pt",
        "checkpoint_sha256": "a" * 64,
        "training_receipt": f"/runtime/{job_id}/training_receipt.json",
        "training_receipt_sha256": "b" * 64,
        "inputs": inputs,
    }


def _registry():
    jobs = [
        _job(f"probability-{system}-S{seed}", system, seed, "probability", 60)
        for system in SYSTEMS
        for seed in SEEDS
    ]
    jobs.extend(
        _job(f"efficiency-{system}-S43", system, 43, "efficiency", 90)
        for system in SYSTEMS
    )
    return {"schema": "prta-cxr.phase15-job-registry.v1", "jobs": jobs}


def test_phase15_registry_is_complete_and_two_lane_balance_is_tight():
    jobs = validate_job_registry(_registry())
    assignments = allocate_two_a800_lanes(jobs)
    assert set(assignments) == set(LANES)
    assert sum(map(len, assignments.values())) == 16
    loads = [
        sum(job["estimated_seconds"] for job in assignments[lane]) for lane in LANES
    ]
    assert abs(loads[0] - loads[1]) <= max(job["estimated_seconds"] for job in jobs)


def test_phase15_registry_rejects_missing_cells_and_tail_seed_drift():
    registry = _registry()
    registry["jobs"].pop()
    with pytest.raises(ValueError, match="matrix mismatch"):
        validate_job_registry(registry)

    registry = _registry()
    efficiency = next(job for job in registry["jobs"] if job["task"] == "efficiency")
    efficiency["seed"] = 17
    with pytest.raises(ValueError, match="Seed 43"):
        validate_job_registry(registry)
