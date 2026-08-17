import pytest

from prta_cxr.phase16_stop import build_terminal_stop_receipt


def _final():
    return {
        "schema": "prta-cxr.phase16-final-reconciliation.v1",
        "status": "PASS_PHASE16_FINAL_NO_SELECTION_AGGREGATE",
        "expected_job_count": 87,
        "selected_pass_count": 87,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def _lanes():
    return {
        lane: (
            {
                "schema": "prta-cxr.phase16-lane-completion.v1",
                "status": "PASS",
                "lane": lane,
                "completed": [{"job_id": f"job-{lane}", "status": "PASS"}],
                "failures": [],
                "skipped": [],
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            },
            f"sha-{lane}",
        )
        for lane in ("a800_3066", "a800_9929")
    }


def test_terminal_stop_requires_complete_pass_and_no_processes():
    result = build_terminal_stop_receipt(
        _final(),
        _lanes(),
        final_aggregate_sha256="final-sha",
        residual_processes=[],
        source_commit="commit",
    )
    assert result["status"] == "STOP_ALL_MODEL_AND_EXPERIMENT_SELECTION"
    assert result["automatic_downstream_experiments_enabled"] is False
    assert result["slurm_allocations_cancelled"] is False


def test_terminal_stop_rejects_incomplete_final_aggregate():
    final = _final()
    final["selected_pass_count"] = 86
    with pytest.raises(ValueError, match="incomplete PASS coverage"):
        build_terminal_stop_receipt(
            final,
            _lanes(),
            final_aggregate_sha256="final-sha",
            residual_processes=[],
            source_commit="commit",
        )


def test_terminal_stop_rejects_residual_experiment_process():
    with pytest.raises(ValueError, match="processes remain active"):
        build_terminal_stop_receipt(
            _final(),
            _lanes(),
            final_aggregate_sha256="final-sha",
            residual_processes=[{"pid": 123}],
            source_commit="commit",
        )
