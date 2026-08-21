from __future__ import annotations

import json
from pathlib import Path

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_evidence_continuation import gate_decision, validate_spec


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _spec(tmp_path: Path) -> dict[str, object]:
    queue = tmp_path / "comparator.json"
    _write(queue, [{"job_id": "C1", "lane": "a800_3066"}])
    return {
        "schema": "prta-cxr.phase20-evidence-continuation-spec.v1",
        "status": "PASS_PHASE20_EVIDENCE_CONTINUATION_SPEC_FROZEN",
        "lane": "a800_3066",
        "source": str(tmp_path / "source"),
        "source_commit": "b" * 40,
        "comparator_queue": str(queue),
        "comparator_queue_sha256": sha256_file(queue),
        "comparator_source_commit": "a" * 40,
        "comparator_completion": str(tmp_path / "completion.json"),
        "comparator_state_root": str(tmp_path / "states"),
        "expected_comparator_job_ids": ["C1"],
        "evidence_program": str(tmp_path / "program"),
        "evidence_queue": str(tmp_path / "program" / "queue.json"),
        "evidence_queue_sha256": "c" * 64,
        "evidence_inputs": str(tmp_path / "inputs.json"),
        "evidence_output": str(tmp_path / "output"),
        "evidence_shared_state": str(tmp_path / "evidence_states"),
        "runner_command": [
            "srun",
            "--lane",
            "a800_3066",
            "--source",
            str(tmp_path / "source"),
            "--runtime-root",
            str(tmp_path / "program"),
            "--queue",
            str(tmp_path / "program" / "queue.json"),
            "--inputs",
            str(tmp_path / "inputs.json"),
            "--output-root",
            str(tmp_path / "output"),
            "--shared-state",
            str(tmp_path / "evidence_states"),
            "--formal",
        ],
        "external_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def test_gate_waits_then_accepts_exact_comparator_pass(tmp_path: Path) -> None:
    spec = validate_spec(_spec(tmp_path))
    assert gate_decision(spec) == "WAIT"
    _write(
        Path(str(spec["comparator_completion"])),
        {
            "schema": "prta-cxr.phase20-lane-completion.v1",
            "status": "PASS",
            "lane": "a800_3066",
            "queue_sha256": spec["comparator_queue_sha256"],
            "source_commit": spec["comparator_source_commit"],
            "completed": [{"job_id": "C1", "status": "PASS"}],
            "failures": [],
            "skipped": [],
            "external_opened": False,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
    )
    _write(
        Path(str(spec["comparator_state_root"])) / "C1.json",
        {
            "schema": "prta-cxr.phase20-job-state.v1",
            "status": "PASS",
            "job_id": "C1",
            "lane": "a800_3066",
            "source_commit": spec["comparator_source_commit"],
            "queue_sha256": spec["comparator_queue_sha256"],
            "return_code": 0,
            "external_opened": False,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
    )
    assert gate_decision(spec) == "RUN"


def test_gate_blocks_nonpass_comparator_completion(tmp_path: Path) -> None:
    spec = validate_spec(_spec(tmp_path))
    _write(
        Path(str(spec["comparator_completion"])),
        {
            "schema": "prta-cxr.phase20-lane-completion.v1",
            "status": "COMPLETE_WITH_FAILURES",
            "lane": "a800_3066",
            "queue_sha256": spec["comparator_queue_sha256"],
            "source_commit": spec["comparator_source_commit"],
            "completed": [{"job_id": "C1", "status": "FAILED"}],
            "failures": ["C1"],
            "skipped": [],
        },
    )
    assert gate_decision(spec) == "BLOCK"


def test_spec_rejects_nonformal_runner(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    spec["runner_command"] = list(spec["runner_command"])[0:-1]
    with pytest.raises(ValueError, match="not formal"):
        validate_spec(spec)
