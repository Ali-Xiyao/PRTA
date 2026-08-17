from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
from prta_cxr.phase15_queue import LANES, SYSTEMS
from prta_cxr.provenance import resolve_source_commit


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_path(runtime_root: Path, value: str, *, role: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = runtime_root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError as error:
        raise ValueError(f"{role} escapes runtime root") from error
    if role == "cache_root":
        if not resolved.is_dir():
            raise FileNotFoundError(f"missing {role}: {resolved}")
    elif not resolved.is_file():
        raise FileNotFoundError(f"missing {role}: {resolved}")
    return resolved


def _resolved_job(runtime_root: Path, job: Mapping[str, Any]) -> dict[str, Any]:
    resolved = dict(job)
    resolved["checkpoint"] = _runtime_path(
        runtime_root, str(job["checkpoint"]), role="checkpoint"
    )
    resolved["training_receipt"] = _runtime_path(
        runtime_root, str(job["training_receipt"]), role="training_receipt"
    )
    inputs = {
        role: _runtime_path(runtime_root, str(value), role=role)
        for role, value in dict(job["inputs"]).items()
    }
    resolved["inputs"] = inputs
    if sha256_file(resolved["checkpoint"]) != str(job["checkpoint_sha256"]):
        raise ValueError(f"checkpoint hash drift: {job['job_id']}")
    if sha256_file(resolved["training_receipt"]) != str(job["training_receipt_sha256"]):
        raise ValueError(f"training receipt hash drift: {job['job_id']}")
    return resolved


def _job_command(
    *, source: Path, job: Mapping[str, Any], output: Path, device: str
) -> list[str]:
    system = str(job["system"])
    inputs = dict(job["inputs"])
    common = [
        "--checkpoint",
        str(job["checkpoint"]),
        "--training-receipt",
        str(job["training_receipt"]),
        "--split-manifest",
        str(inputs["split_manifest"]),
        "--cleaned-split-freeze",
        str(inputs["cleaned_split_freeze"]),
        "--cleaned-split-platform-root",
        str(Path(inputs["cleaned_split_freeze"]).parent),
        "--cache-root",
        str(inputs["cache_root"]),
        "--text-cache",
        str(inputs["text_cache"]),
        "--matched-hard-prior-map",
        str(inputs["matched_hard_prior_map"]),
        "--weights",
        str(inputs["weights"]),
        "--label-quality-audit",
        str(inputs["label_quality_audit"]),
        "--output",
        str(output),
        "--device",
        device,
        "--formal",
    ]
    if job["task"] == "probability":
        scope = "ifusion_final" if system.startswith("IF-") else "formal_baseline"
        return [
            sys.executable,
            str(source / "scripts/45_evaluate_prta_v2_mechanisms.py"),
            *common,
            "--batch-size",
            "16",
            "--diagnostic-scope",
            scope,
            "--retain-logits",
            "--true-only",
        ]
    return [
        sys.executable,
        str(source / "scripts/91_profile_comparator_efficiency.py"),
        *common,
        "--system",
        system,
        "--warmup",
        "20",
        "--repeats",
        "100",
    ]


def validate_job_output(job: Mapping[str, Any], output: Path) -> dict[str, Any]:
    system = str(job["system"])
    checkpoint = Path(job["checkpoint"])
    if job["task"] == "probability":
        receipt_path = output / "candidate_probability_diagnostic_receipt.json"
        receipt = _read_json(receipt_path)
        if receipt.get("schema") != "prta-cxr.comparator-dev-probability-diagnostic.v1":
            raise ValueError("unsupported comparator probability schema")
        if receipt.get("status") != "PASS_COMPARATOR_DEV_PROBABILITY_EXPORT":
            raise ValueError("comparator probability export is not terminal PASS")
        if receipt.get("variant") != system or receipt.get("seed") != job["seed"]:
            raise ValueError("comparator probability identity drift")
        if receipt.get("evaluation_interventions") != ["true"]:
            raise ValueError("comparator probability intervention drift")
        blocks = receipt.get("prediction_blocks", {})
        if set(blocks) != {"true"}:
            raise ValueError("comparator probability block drift")
        block = blocks["true"]
        path = output / str(block["path"])
        if sha256_file(path) != block["sha256"]:
            raise ValueError("comparator probability block hash drift")
        return {
            "receipt_sha256": sha256_file(receipt_path),
            "rows": int(block["rows"]),
            "true_block_sha256": str(block["sha256"]),
        }
    report = _read_json(output)
    if report.get("schema") != "prta-cxr.comparator-efficiency-evidence.v1":
        raise ValueError("unsupported comparator efficiency schema")
    if report.get("status") != "PASS_COMPARATOR_FIXED_HARDWARE_EFFICIENCY":
        raise ValueError("comparator efficiency evidence is not terminal PASS")
    if report.get("system") != system or report.get("seed") != job["seed"]:
        raise ValueError("comparator efficiency identity drift")
    if report.get("checkpoint_sha256") != sha256_file(checkpoint):
        raise ValueError("comparator efficiency checkpoint hash drift")
    return {"receipt_sha256": sha256_file(output)}


def run_phase15_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one immutable comparator-evidence lane on an A800"
    )
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--lane", choices=LANES, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    runtime_root = args.runtime_root.resolve()
    source = args.source.resolve()
    queue = _read_json(args.queue)
    if not isinstance(queue, list) or not queue:
        raise ValueError("Phase 15 lane queue is empty")
    if any(job.get("lane") != args.lane for job in queue):
        raise ValueError("Phase 15 lane queue identity drift")
    if any(job.get("system") not in SYSTEMS for job in queue):
        raise ValueError("Phase 15 queue contains an unsupported system")
    lane_root = args.output_root.resolve() / args.lane
    if lane_root.exists():
        raise FileExistsError(f"Phase 15 lane output exists: {lane_root}")
    (lane_root / "logs").mkdir(parents=True)
    progress_path = lane_root / "progress.json"
    progress: dict[str, Any] = {
        "schema": "prta-cxr.phase15-lane-progress.v1",
        "status": "RUNNING",
        "created_at": _now(),
        "updated_at": _now(),
        "lane": args.lane,
        "source_commit": resolve_source_commit(source),
        "queue_sha256": sha256_file(args.queue),
        "current_job_id": None,
        "completed": [],
        "remaining": len(queue),
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(progress_path, progress)
    environment = os.environ.copy()
    environment[FORMAL_ENV_NAME] = FORMAL_ENV_VALUE
    for raw_job in queue:
        job = _resolved_job(runtime_root, raw_job)
        job_id = str(job["job_id"])
        output = (
            lane_root / job_id
            if job["task"] == "probability"
            else lane_root / f"{job_id}.json"
        )
        progress["current_job_id"] = job_id
        progress["updated_at"] = _now()
        replace_json_atomic(progress_path, progress)
        command = _job_command(
            source=source, job=job, output=output, device=args.device
        )
        stdout_path = lane_root / "logs" / f"{job_id}.stdout.log"
        stderr_path = lane_root / "logs" / f"{job_id}.stderr.log"
        with (
            stdout_path.open("w", encoding="utf-8") as stdout,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            completed = subprocess.run(
                command,
                cwd=source,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        if completed.returncode != 0:
            failure = {
                **progress,
                "status": "FAILED",
                "failed_job_id": job_id,
                "return_code": completed.returncode,
                "command": command,
            }
            write_json_atomic(lane_root / "failure.json", failure)
            raise RuntimeError(f"Phase 15 job failed: {job_id}")
        validation = validate_job_output(job, output)
        progress["completed"].append({"job_id": job_id, **validation})
        progress["remaining"] -= 1
        progress["updated_at"] = _now()
        replace_json_atomic(progress_path, progress)
    completion = {
        **progress,
        "status": "PASS_PHASE15_LANE_COMPLETE",
        "completed_at": _now(),
        "current_job_id": None,
    }
    write_json_atomic(lane_root / "completion.json", completion)
    replace_json_atomic(progress_path, completion)
    print(json.dumps(completion, indent=2, sort_keys=True))
    return 0
