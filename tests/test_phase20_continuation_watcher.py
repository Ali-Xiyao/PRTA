from __future__ import annotations

import json
from pathlib import Path

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_continuation_watcher import (
    SPEC_STATUS,
    gate_decision,
    validate_continuation_spec,
    validate_next_completion,
)


def _spec(tmp_path: Path) -> dict:
    next_queue = tmp_path / "next" / "queue" / "a800_3066.json"
    return {
        "schema": "prta-cxr.phase20-continuation-spec.v2",
        "status": SPEC_STATUS,
        "lane": "a800_3066",
        "source": str(tmp_path / "source"),
        "source_commit": "a" * 40,
        "gate_finalizer": str(tmp_path / "gate" / "finalizer.json"),
        "gate_program_preparation": str(
            tmp_path / "phase20-a" / "preparation_receipt.json"
        ),
        "gate_program_preparation_sha256": "b" * 64,
        "gate_source_commit": "c" * 40,
        "next_program": str(tmp_path / "next"),
        "next_queue": str(next_queue),
        "next_completion": str(tmp_path / "result" / "completion.json"),
        "runner_command": [
            "python",
            str(tmp_path / "source" / "scripts" / "117_run_phase20_queue.py"),
            "--queue",
            str(next_queue),
            "--lane",
            "a800_3066",
        ],
        "external_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def test_continuation_spec_is_argv_bound_and_protected_read_closed(tmp_path):
    spec = _spec(tmp_path)
    assert validate_continuation_spec(spec)["lane"] == "a800_3066"
    broken = dict(spec)
    broken["runner_command"] = "python runner.py"
    with pytest.raises(ValueError, match="argv"):
        validate_continuation_spec(broken)
    broken = dict(spec)
    broken["gold_opened"] = True
    with pytest.raises(ValueError, match="protected-read"):
        validate_continuation_spec(broken)


def test_continuation_gate_waits_then_requires_exact_pass(tmp_path):
    spec = _spec(tmp_path)
    assert gate_decision(spec) == "WAIT"
    finalizer_path = Path(spec["gate_finalizer"])
    finalizer_path.parent.mkdir(parents=True)
    finalizer_path.write_text(
        json.dumps(
            {
                "schema": "prta-cxr.phase20-a-final-no-selection-aggregate.v1",
                "status": "PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE",
                "source_commit": spec["gate_source_commit"],
                "program_preparation_sha256": spec["gate_program_preparation_sha256"],
                "expected_job_count": 88,
                "unique_pass_count": 88,
                "training_cell_count": 63,
                "transformed_map_count": 19,
                "source_held_evaluation_count": 6,
                "selection_performed": False,
                "winner_selected": False,
                "external_evaluation_included": False,
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            }
        ),
        encoding="utf-8",
    )
    assert gate_decision(spec) == "RUN"
    value = json.loads(finalizer_path.read_text(encoding="utf-8"))
    value["status"] = "COMPLETE_WITH_FAILURES"
    finalizer_path.write_text(json.dumps(value), encoding="utf-8")
    assert gate_decision(spec) == "BLOCK"


def test_continuation_requires_hash_source_and_closed_next_completion(tmp_path):
    spec = _spec(tmp_path)
    next_program = Path(spec["next_program"])
    next_queue = Path(spec["next_queue"])
    next_queue.parent.mkdir(parents=True)
    next_queue.write_text("[]\n", encoding="utf-8")
    (next_program / "preparation_receipt.json").write_text(
        json.dumps({"queue_hashes": {next_queue.name: sha256_file(next_queue)}}),
        encoding="utf-8",
    )
    completion = {
        "schema": "prta-cxr.phase20-lane-completion.v1",
        "status": "PASS",
        "lane": spec["lane"],
        "queue_sha256": sha256_file(next_queue),
        "source_commit": spec["source_commit"],
        "external_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    validate_next_completion(spec, completion)
    broken = dict(completion)
    broken["queue_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="identity drift"):
        validate_next_completion(spec, broken)
    broken = dict(completion)
    broken["external_opened"] = True
    with pytest.raises(ValueError, match="protected-read"):
        validate_next_completion(spec, broken)
