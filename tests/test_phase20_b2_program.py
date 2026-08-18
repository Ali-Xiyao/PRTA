from prta_cxr.phase20_b2_program import build_phase20_b2_jobs


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
