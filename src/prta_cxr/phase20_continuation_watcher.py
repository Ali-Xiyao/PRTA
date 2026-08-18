from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_queue_runner import replace_json_atomic, write_json_atomic
from prta_cxr.provenance import resolve_source_commit

SPEC_STATUS = "PASS_PHASE20_CONTINUATION_SPEC_FROZEN"
NEXT_PROGRAM_STATUSES = {"PASS_PHASE20_COMPARATOR_REBUILD_PROGRAM_FROZEN"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_continuation_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    spec = dict(raw)
    if spec.get("schema") != "prta-cxr.phase20-continuation-spec.v1":
        raise ValueError("unsupported Phase20 continuation spec schema")
    if spec.get("status") != SPEC_STATUS:
        raise ValueError("Phase20 continuation spec is not frozen PASS")
    lane = str(spec.get("lane", ""))
    required_paths = (
        "source",
        "gate_completion",
        "gate_queue",
        "next_program",
        "next_queue",
        "next_completion",
    )
    for name in required_paths:
        if not str(spec.get(name, "")):
            raise ValueError(f"Phase20 continuation spec missing {name}")
    command = spec.get("runner_command")
    if not isinstance(command, list) or not command or not all(
        isinstance(value, str) and value for value in command
    ):
        raise ValueError("Phase20 continuation runner command must be argv")
    if not any(value.endswith("117_run_phase20_queue.py") for value in command):
        raise ValueError("Phase20 continuation must use the frozen queue runner")
    lane_index = command.index("--lane") if "--lane" in command else -1
    if (
        lane_index < 0
        or lane_index + 1 >= len(command)
        or command[lane_index + 1] != lane
    ):
        raise ValueError("Phase20 continuation runner lane drift")
    queue_index = command.index("--queue") if "--queue" in command else -1
    if (
        queue_index < 0
        or queue_index + 1 >= len(command)
        or Path(command[queue_index + 1]).resolve()
        != Path(str(spec["next_queue"])).resolve()
    ):
        raise ValueError("Phase20 continuation runner queue drift")
    if any(
        bool(spec.get(name, False))
        for name in ("external_opened", "internal_test_opened", "gold_opened")
    ) or int(spec.get("protected_outcome_read_count", -1)) != 0:
        raise ValueError("Phase20 continuation protected-read boundary drift")
    return spec


def validate_continuation_inputs(spec: Mapping[str, Any]) -> None:
    source = Path(str(spec["source"])).resolve()
    if resolve_source_commit(source) != spec.get("source_commit"):
        raise ValueError("Phase20 continuation source commit drift")
    gate_queue = Path(str(spec["gate_queue"])).resolve()
    if sha256_file(gate_queue) != spec.get("gate_queue_sha256"):
        raise ValueError("Phase20 continuation gate queue hash drift")
    next_program = Path(str(spec["next_program"])).resolve()
    preparation = dict(_read_json(next_program / "preparation_receipt.json"))
    if preparation.get("status") not in NEXT_PROGRAM_STATUSES:
        raise ValueError("Phase20 continuation next program is not frozen PASS")
    if preparation.get("source_commit") != spec.get("source_commit"):
        raise ValueError("Phase20 continuation program/source drift")
    next_queue = Path(str(spec["next_queue"])).resolve()
    expected = dict(preparation.get("queue_hashes", {})).get(next_queue.name)
    if not expected or sha256_file(next_queue) != expected:
        raise ValueError("Phase20 continuation next queue hash drift")


def gate_decision(spec: Mapping[str, Any]) -> str:
    completion_path = Path(str(spec["gate_completion"])).resolve()
    if not completion_path.is_file():
        return "WAIT"
    completion = dict(_read_json(completion_path))
    if (
        completion.get("schema") != "prta-cxr.phase20-lane-completion.v1"
        or completion.get("lane") != spec.get("lane")
        or completion.get("queue_sha256") != spec.get("gate_queue_sha256")
    ):
        raise ValueError("Phase20 continuation gate completion identity drift")
    return "RUN" if completion.get("status") == "PASS" else "BLOCK"


def watch_phase20_continuation_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Wait for a frozen Phase20 lane boundary and launch its continuation"
        )
    )
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    if args.receipt.exists():
        parser.error("--receipt must be a new immutable continuation receipt")
    spec = validate_continuation_spec(dict(_read_json(args.spec)))
    validate_continuation_inputs(spec)
    base = {
        "schema": "prta-cxr.phase20-continuation-receipt.v1",
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
                args.receipt,
                {**base, "status": "BLOCKED_GATE_NONPASS", "completed_at": _now()},
            )
            return 2
        time.sleep(args.poll_seconds)
    replace_json_atomic(
        args.receipt, {**base, "status": "RUNNING_CONTINUATION", "started_at": _now()}
    )
    result = subprocess.run(list(spec["runner_command"]), check=False)
    completion_path = Path(str(spec["next_completion"])).resolve()
    completion = (
        dict(_read_json(completion_path)) if completion_path.is_file() else {}
    )
    passed = (
        result.returncode == 0
        and completion.get("status") == "PASS"
        and completion.get("lane") == spec.get("lane")
    )
    replace_json_atomic(
        args.receipt,
        {
            **base,
            "status": "PASS_CONTINUATION_COMPLETE" if passed else "FAILED_CONTINUATION",
            "completed_at": _now(),
            "return_code": result.returncode,
            "next_completion_sha256": (
                sha256_file(completion_path) if completion_path.is_file() else None
            ),
        },
    )
    return 0 if passed else 2
