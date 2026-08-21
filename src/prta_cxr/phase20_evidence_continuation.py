from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import replace_json_atomic, write_json_atomic
from prta_cxr.authorization import (
    FORMAL_ENV_NAME,
    FORMAL_ENV_VALUE,
    require_formal_authorization,
)
from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_evidence_runner import validate_evidence_platform_inputs
from prta_cxr.provenance import resolve_source_commit

SPEC_SCHEMA = "prta-cxr.phase20-evidence-continuation-spec.v1"
SPEC_STATUS = "PASS_PHASE20_EVIDENCE_CONTINUATION_SPEC_FROZEN"
RECEIPT_SCHEMA = "prta-cxr.phase20-evidence-continuation-receipt.v1"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_closed(value: Mapping[str, Any], *, label: str) -> None:
    for key in (
        "external_opened",
        "external_included",
        "external_evaluation_included",
        "internal_test_opened",
        "gold_opened",
    ):
        if key in value and value[key] is not False:
            raise ValueError(f"{label} violates protected boundary through {key}")
    if int(value.get("protected_outcome_read_count", 0)) != 0:
        raise ValueError(f"{label} violates protected read boundary")


def validate_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    spec = dict(raw)
    if spec.get("schema") != SPEC_SCHEMA or spec.get("status") != SPEC_STATUS:
        raise ValueError("unsupported or non-frozen evidence continuation spec")
    required = (
        "lane",
        "source",
        "source_commit",
        "comparator_queue",
        "comparator_queue_sha256",
        "comparator_source_commit",
        "comparator_completion",
        "comparator_state_root",
        "expected_comparator_job_ids",
        "evidence_program",
        "evidence_queue",
        "evidence_queue_sha256",
        "evidence_inputs",
        "evidence_output",
        "evidence_shared_state",
        "runner_command",
    )
    if any(not spec.get(name) for name in required):
        raise ValueError("incomplete evidence continuation spec")
    jobs = list(map(str, spec["expected_comparator_job_ids"]))
    if not jobs or len(jobs) != len(set(jobs)):
        raise ValueError("comparator job IDs must be a non-empty unique list")
    command = spec["runner_command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(value, str) and value for value in command)
    ):
        raise ValueError("evidence runner command must be argv")
    expected_flags = {
        "--lane": str(spec["lane"]),
        "--source": str(spec["source"]),
        "--runtime-root": str(spec["evidence_program"]),
        "--queue": str(spec["evidence_queue"]),
        "--inputs": str(spec["evidence_inputs"]),
        "--output-root": str(spec["evidence_output"]),
        "--shared-state": str(spec["evidence_shared_state"]),
    }
    for flag, expected in expected_flags.items():
        if flag not in command or command[command.index(flag) + 1] != expected:
            raise ValueError(f"evidence runner command drift: {flag}")
    if "--formal" not in command:
        raise ValueError("evidence runner command is not formal")
    _require_closed(spec, label="evidence continuation spec")
    return spec


def validate_static_inputs(spec: Mapping[str, Any]) -> None:
    comparator_queue = Path(str(spec["comparator_queue"])).resolve()
    if sha256_file(comparator_queue) != spec["comparator_queue_sha256"]:
        raise ValueError("comparator queue hash drift")
    queue = _read_json(comparator_queue)
    if not isinstance(queue, list):
        raise ValueError("comparator queue is not a list")
    expected_jobs = list(map(str, spec["expected_comparator_job_ids"]))
    if [str(job.get("job_id")) for job in queue] != expected_jobs:
        raise ValueError("comparator queue job identity/order drift")
    if any(str(job.get("lane")) != spec["lane"] for job in queue):
        raise ValueError("comparator queue lane drift")

    source = Path(str(spec["source"])).resolve()
    if resolve_source_commit(source) != spec["source_commit"]:
        raise ValueError("evidence source commit drift")
    program = Path(str(spec["evidence_program"])).resolve()
    preparation = dict(_read_json(program / "preparation_receipt.json"))
    if (
        preparation.get("status")
        != "PASS_PHASE20_SLIM_S1_EVIDENCE_PROGRAM_FROZEN"
        or preparation.get("source_commit") != spec["source_commit"]
        or preparation.get("lane") != spec["lane"]
        or int(preparation.get("job_count", -1)) != 6
    ):
        raise ValueError("evidence program identity drift")
    evidence_queue = Path(str(spec["evidence_queue"])).resolve()
    if (
        sha256_file(evidence_queue) != spec["evidence_queue_sha256"]
        or preparation.get("queue_sha256") != spec["evidence_queue_sha256"]
    ):
        raise ValueError("evidence queue hash drift")
    validate_evidence_platform_inputs(
        dict(_read_json(Path(str(spec["evidence_inputs"])))),
        dict(_read_json(program / "input_manifest.json")),
    )


def gate_decision(spec: Mapping[str, Any]) -> str:
    completion_path = Path(str(spec["comparator_completion"])).resolve()
    if not completion_path.is_file():
        return "WAIT"
    completion = dict(_read_json(completion_path))
    _require_closed(completion, label="comparator lane completion")
    expected_jobs = list(map(str, spec["expected_comparator_job_ids"]))
    completed = completion.get("completed")
    if (
        completion.get("schema") != "prta-cxr.phase20-lane-completion.v1"
        or completion.get("status") != "PASS"
        or completion.get("lane") != spec["lane"]
        or completion.get("queue_sha256") != spec["comparator_queue_sha256"]
        or completion.get("source_commit") != spec["comparator_source_commit"]
        or completion.get("failures") != []
        or completion.get("skipped") != []
        or not isinstance(completed, list)
        or [str(item.get("job_id")) for item in completed] != expected_jobs
        or any(item.get("status") != "PASS" for item in completed)
    ):
        return "BLOCK"
    state_root = Path(str(spec["comparator_state_root"])).resolve()
    for job_id in expected_jobs:
        path = state_root / f"{job_id}.json"
        if not path.is_file():
            return "BLOCK"
        state = dict(_read_json(path))
        _require_closed(state, label=f"comparator state {job_id}")
        if (
            state.get("schema") != "prta-cxr.phase20-job-state.v1"
            or state.get("status") != "PASS"
            or state.get("job_id") != job_id
            or state.get("lane") != spec["lane"]
            or state.get("source_commit") != spec["comparator_source_commit"]
            or state.get("queue_sha256") != spec["comparator_queue_sha256"]
            or int(state.get("return_code", -1)) != 0
        ):
            return "BLOCK"
    return "RUN"


def validate_evidence_completion(spec: Mapping[str, Any]) -> None:
    path = Path(str(spec["evidence_output"])) / "completion.json"
    completion = dict(_read_json(path))
    _require_closed(completion, label="evidence completion")
    expected_jobs = list(_read_json(Path(str(spec["evidence_queue"]))))
    if (
        completion.get("schema") != "prta-cxr.phase20-evidence-completion.v1"
        or completion.get("status") != "PASS"
        or completion.get("lane") != spec["lane"]
        or completion.get("source_commit") != spec["source_commit"]
        or completion.get("queue_sha256") != spec["evidence_queue_sha256"]
        or completion.get("failures") != []
        or completion.get("skipped") != []
        or [item.get("job_id") for item in completion.get("completed", [])]
        != [job.get("job_id") for job in expected_jobs]
        or any(item.get("status") != "PASS" for item in completion["completed"])
    ):
        raise ValueError("evidence completion identity drift")


def watch_phase20_evidence_continuation_main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen Phase20-B1 after one comparator lane passes"
    )
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    if args.receipt.exists():
        parser.error("receipt must be a new immutable owner path")
    spec = validate_spec(dict(_read_json(args.spec)))
    validate_static_inputs(spec)
    if args.validate_only:
        print("PASS_PHASE20_EVIDENCE_CONTINUATION_VALIDATION")
        return 0
    evidence_output = Path(str(spec["evidence_output"])).resolve()
    shared_state = Path(str(spec["evidence_shared_state"])).resolve()
    if (evidence_output / "completion.json").exists():
        raise FileExistsError("evidence completion already exists")
    if shared_state.exists() and any(shared_state.iterdir()):
        raise RuntimeError("evidence shared state is not empty")
    base = {
        "schema": RECEIPT_SCHEMA,
        "lane": spec["lane"],
        "spec_sha256": sha256_file(args.spec),
        "source_commit": spec["source_commit"],
        "created_at": _now(),
        "external_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(args.receipt, {**base, "status": "WATCHING"})
    while True:
        decision = gate_decision(spec)
        if decision == "RUN":
            break
        if decision == "BLOCK":
            replace_json_atomic(
                args.receipt, {**base, "status": "BLOCKED_COMPARATOR_NONPASS"}
            )
            return 2
        time.sleep(args.poll_seconds)
    replace_json_atomic(args.receipt, {**base, "status": "RUNNING_EVIDENCE"})
    environment = os.environ.copy()
    environment[FORMAL_ENV_NAME] = FORMAL_ENV_VALUE
    result = subprocess.run(
        list(spec["runner_command"]), check=False, env=environment
    )
    passed = result.returncode == 0
    if passed:
        try:
            validate_evidence_completion(spec)
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            passed = False
    completion_path = evidence_output / "completion.json"
    replace_json_atomic(
        args.receipt,
        {
            **base,
            "status": (
                "PASS_EVIDENCE_CONTINUATION_COMPLETE"
                if passed
                else "FAILED_EVIDENCE_CONTINUATION"
            ),
            "completed_at": _now(),
            "return_code": result.returncode,
            "completion_sha256": (
                sha256_file(completion_path) if completion_path.is_file() else None
            ),
        },
    )
    return 0 if passed else 2

