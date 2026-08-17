import pytest

from prta_cxr.phase15_recovery import derive_recovery_suffix


def _queue():
    return [{"job_id": f"job-{index}", "lane": "a800_3066"} for index in range(4)]


def _failure():
    return {
        "schema": "prta-cxr.phase15-lane-progress.v1",
        "status": "FAILED",
        "lane": "a800_3066",
        "failed_job_id": "job-2",
        "completed": [
            {"job_id": "job-0", "receipt_sha256": "a" * 64},
            {"job_id": "job-1", "receipt_sha256": "b" * 64},
        ],
        "remaining": 2,
    }


def test_recovery_derives_only_failed_job_and_original_suffix():
    assert [job["job_id"] for job in derive_recovery_suffix(_queue(), _failure())] == [
        "job-2",
        "job-3",
    ]


def test_recovery_rejects_nonprefix_completion_history():
    failure = _failure()
    failure["completed"][1]["job_id"] = "job-3"
    with pytest.raises(ValueError, match="exact original-queue prefix"):
        derive_recovery_suffix(_queue(), failure)
