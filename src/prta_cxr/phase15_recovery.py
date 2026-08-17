from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.phase15_queue import LANES


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def derive_recovery_suffix(
    queue: Sequence[Mapping[str, Any]], failure: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if failure.get("schema") != "prta-cxr.phase15-lane-progress.v1":
        raise ValueError("unsupported Phase 15 failure schema")
    if failure.get("status") != "FAILED":
        raise ValueError("recovery requires a terminal FAILED lane receipt")
    lane = str(failure.get("lane", ""))
    if lane not in LANES or any(str(job.get("lane")) != lane for job in queue):
        raise ValueError("recovery lane identity drift")
    identifiers = [str(job.get("job_id", "")) for job in queue]
    failed = str(failure.get("failed_job_id", ""))
    if failed not in identifiers:
        raise ValueError("failed job is absent from the original queue")
    failed_index = identifiers.index(failed)
    completed = list(failure.get("completed", []))
    completed_ids = [str(value.get("job_id", "")) for value in completed]
    if completed_ids != identifiers[:failed_index]:
        raise ValueError("completed jobs are not an exact original-queue prefix")
    for value in completed:
        receipt_hash = str(value.get("receipt_sha256", ""))
        if len(receipt_hash) != 64:
            raise ValueError("completed recovery evidence lacks a SHA-256 receipt")
    if int(failure.get("remaining", -1)) != len(queue) - failed_index:
        raise ValueError("failure remaining count does not match queue suffix")
    return [dict(job) for job in queue[failed_index:]]


def prepare_phase15_recovery_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive an immutable Phase 15 failed-lane suffix queue"
    )
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--failure", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    failure = json.loads(args.failure.read_text(encoding="utf-8"))
    suffix = derive_recovery_suffix(queue, failure)
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    _write_new_json(staging / "queue.json", suffix)
    receipt = {
        "schema": "prta-cxr.phase15-recovery-queue.v1",
        "status": "PASS_PHASE15_RECOVERY_SUFFIX_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "lane": failure["lane"],
        "original_queue_sha256": sha256_file(args.queue),
        "failure_receipt_sha256": sha256_file(args.failure),
        "completed_prefix_job_ids": [value["job_id"] for value in failure["completed"]],
        "recovery_job_ids": [value["job_id"] for value in suffix],
        "recovery_matrix_sha256": canonical_sha256(
            [(value["job_id"], value["checkpoint_sha256"]) for value in suffix]
        ),
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "recovery_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
