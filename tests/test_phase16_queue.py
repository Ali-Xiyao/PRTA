import pytest

from prta_cxr.phase16_queue import allocate_lanes, validate_registry


def _registry():
    return {
        "schema": "prta-cxr.phase16-job-registry.v1",
        "jobs": [
            {
                "job_id": "a",
                "group": "modality_stress",
                "estimated_seconds": 10,
                "command": ["python", "a.py"],
                "dependencies": [],
            },
            {
                "job_id": "b",
                "group": "state_pruning",
                "estimated_seconds": 9,
                "command": ["python", "b.py"],
                "dependencies": ["a"],
            },
            {
                "job_id": "c",
                "group": "label_noise",
                "estimated_seconds": 8,
                "command": ["python", "c.py"],
                "dependencies": [],
            },
        ],
    }


def test_phase16_registry_and_lpt_balance():
    jobs = validate_registry(_registry())
    lanes = allocate_lanes(jobs)
    assert {job["job_id"] for queue in lanes.values() for job in queue} == {
        "a",
        "b",
        "c",
    }
    loads = [sum(job["estimated_seconds"] for job in queue) for queue in lanes.values()]
    assert max(loads) - min(loads) <= 9
    positions = {
        job["job_id"]: (lane, index)
        for lane, queue in lanes.items()
        for index, job in enumerate(queue)
    }
    if positions["a"][0] == positions["b"][0]:
        assert positions["a"][1] < positions["b"][1]


def test_phase16_assignment_balances_before_dependency_ordering():
    registry = {
        "schema": "prta-cxr.phase16-job-registry.v1",
        "jobs": [
            {
                "job_id": f"long-{index}",
                "group": "source_held_out",
                "estimated_seconds": 100,
                "command": ["python", "train.py"],
                "dependencies": [],
            }
            for index in range(3)
        ]
        + [
            {
                "job_id": f"short-{index}",
                "group": "state_pruning",
                "estimated_seconds": 40,
                "command": ["python", "evaluate.py"],
                "dependencies": ["long-0"],
            }
            for index in range(5)
        ],
    }
    lanes = allocate_lanes(validate_registry(registry))
    loads = [sum(job["estimated_seconds"] for job in lane) for lane in lanes.values()]
    assert max(loads) - min(loads) <= 40
    for lane in lanes.values():
        positions = {job["job_id"]: index for index, job in enumerate(lane)}
        for job in lane:
            for dependency in job.get("dependencies", []):
                if dependency in positions:
                    assert positions[dependency] < positions[job["job_id"]]


def test_phase16_rejects_cycle():
    registry = _registry()
    registry["jobs"][0]["dependencies"] = ["b"]
    with pytest.raises(ValueError, match="cycle"):
        validate_registry(registry)
