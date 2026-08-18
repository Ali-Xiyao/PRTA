from __future__ import annotations

import json
from pathlib import Path

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_continuation_watcher import (
    SPEC_STATUS,
    gate_decision,
    validate_continuation_spec,
)


def _spec(tmp_path: Path) -> dict:
    next_queue = tmp_path / "next" / "queue" / "a800_3066.json"
    return {
        "schema": "prta-cxr.phase20-continuation-spec.v1",
        "status": SPEC_STATUS,
        "lane": "a800_3066",
        "source": str(tmp_path / "source"),
        "source_commit": "a" * 40,
        "gate_completion": str(tmp_path / "gate" / "completion.json"),
        "gate_queue": str(tmp_path / "gate" / "a800_3066.json"),
        "gate_queue_sha256": "b" * 64,
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
    queue_path = Path(spec["gate_queue"])
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text("[]\n", encoding="utf-8")
    spec["gate_queue_sha256"] = sha256_file(queue_path)
    completion_path = Path(spec["gate_completion"])
    completion_path.write_text(
        json.dumps(
            {
                "schema": "prta-cxr.phase20-lane-completion.v1",
                "status": "PASS",
                "lane": "a800_3066",
                "queue_sha256": spec["gate_queue_sha256"],
            }
        ),
        encoding="utf-8",
    )
    assert gate_decision(spec) == "RUN"
    value = json.loads(completion_path.read_text(encoding="utf-8"))
    value["status"] = "COMPLETE_WITH_FAILURES"
    completion_path.write_text(json.dumps(value), encoding="utf-8")
    assert gate_decision(spec) == "BLOCK"
