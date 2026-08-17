from pathlib import Path

from prta_cxr.phase16_repair import build_repair_registry


def _job(job_id, group, dependencies=()):
    return {
        "job_id": job_id,
        "group": group,
        "estimated_seconds": 10,
        "dependencies": list(dependencies),
        "command": ["python", "script.py", "--formal"],
        "expected_outputs": [],
    }


def test_repair_registry_selects_known_groups_and_injects_raw_root():
    registry = {
        "schema": "prta-cxr.phase16-job-registry.v1",
        "jobs": [
            _job("modality-current-cache-blur", "modality_stress"),
            _job(
                "modality-stress-S17",
                "modality_stress",
                ("modality-current-cache-blur",),
            ),
            _job("train-source", "source_held_out"),
            _job("state-export", "state_pruning"),
            _job("train-noise", "label_noise"),
        ],
    }
    repaired = build_repair_registry(registry, raw_image_root=Path("/raw/images"))
    jobs = repaired["jobs"]
    assert {job["job_id"] for job in jobs} == {
        "modality-current-cache-blur",
        "modality-stress-S17",
        "train-source",
        "state-export",
    }
    cache = next(job for job in jobs if job["job_id"].startswith("modality-current"))
    assert cache["command"][-3:] == [
        "--raw-image-root",
        str(Path("/raw/images")),
        "--formal",
    ]
