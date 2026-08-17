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
from prta_cxr.provenance import resolve_source_commit

SYSTEMS = ("B401", "TILA8", "IF-F01", "IF-F02")
SEEDS = (17, 28, 43)
TASKS = ("probability", "efficiency")
LANES = ("a800_3066", "a800_9929")


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def validate_job_registry(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    if registry.get("schema") != "prta-cxr.phase15-job-registry.v1":
        raise ValueError("unsupported Phase 15 job registry schema")
    jobs = [dict(job) for job in registry.get("jobs", [])]
    expected_probability = {
        f"probability-{system}-S{seed}" for system in SYSTEMS for seed in SEEDS
    }
    expected_efficiency = {f"efficiency-{system}-S43" for system in SYSTEMS}
    expected = expected_probability | expected_efficiency
    identifiers = [str(job.get("job_id", "")) for job in jobs]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Phase 15 job registry contains duplicate job IDs")
    if set(identifiers) != expected:
        missing = sorted(expected - set(identifiers))
        extra = sorted(set(identifiers) - expected)
        raise ValueError(f"Phase 15 matrix mismatch: missing={missing}, extra={extra}")
    for job in jobs:
        system = str(job.get("system", ""))
        task = str(job.get("task", ""))
        seed = int(job.get("seed", -1))
        if system not in SYSTEMS or task not in TASKS:
            raise ValueError("Phase 15 job has an unsupported system or task")
        if task == "probability" and seed not in SEEDS:
            raise ValueError("probability job seed is outside the frozen roster")
        if task == "efficiency" and seed != 43:
            raise ValueError(
                "efficiency jobs must use the fixed representative Seed 43"
            )
        if int(job.get("estimated_seconds", 0)) <= 0:
            raise ValueError("Phase 15 job estimate must be positive")
        for field in (
            "checkpoint",
            "checkpoint_sha256",
            "training_receipt",
            "training_receipt_sha256",
        ):
            if not str(job.get(field, "")):
                raise ValueError(f"Phase 15 job is missing {field}")
        inputs = dict(job.get("inputs", {}))
        required_inputs = {
            "split_manifest",
            "cleaned_split_freeze",
            "cache_root",
            "text_cache",
            "matched_hard_prior_map",
            "weights",
            "label_quality_audit",
        }
        if set(inputs) != required_inputs:
            raise ValueError("Phase 15 job input surface is incomplete or expanded")
    return jobs


def allocate_two_a800_lanes(
    jobs: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    assignments: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
    loads = {lane: 0 for lane in LANES}
    ordered = sorted(
        (dict(job) for job in jobs),
        key=lambda job: (-int(job["estimated_seconds"]), str(job["job_id"])),
    )
    for job in ordered:
        lane = min(LANES, key=lambda name: (loads[name], name))
        job["lane"] = lane
        job["queue_index"] = len(assignments[lane])
        assignments[lane].append(job)
        loads[lane] += int(job["estimated_seconds"])
    return assignments


def prepare_phase15_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an immutable duration-balanced two-A800 Phase 15 queue"
    )
    parser.add_argument("--job-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    registry = json.loads(args.job_registry.read_text(encoding="utf-8"))
    jobs = validate_job_registry(registry)
    assignments = allocate_two_a800_lanes(jobs)
    loads = {
        lane: sum(int(job["estimated_seconds"]) for job in queue)
        for lane, queue in assignments.items()
    }
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    if staging.exists():
        raise FileExistsError(f"Phase 15 queue staging exists: {staging}")
    staging.mkdir(parents=True, exist_ok=False)
    queue_files = {}
    for lane, queue in assignments.items():
        path = staging / f"{lane}.json"
        _write_new_json(path, queue)
        queue_files[path.name] = sha256_file(path)
    receipt = {
        "schema": "prta-cxr.phase15-two-a800-queue.v1",
        "status": "PASS_PHASE15_TWO_A800_QUEUE_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "job_registry_sha256": sha256_file(args.job_registry),
        "job_matrix_sha256": canonical_sha256(
            sorted(
                (
                    str(job["job_id"]),
                    str(job["checkpoint_sha256"]),
                    int(job["estimated_seconds"]),
                )
                for job in jobs
            )
        ),
        "lanes": list(LANES),
        "job_count": len(jobs),
        "lane_load_estimated_seconds": loads,
        "estimated_imbalance_seconds": max(loads.values()) - min(loads.values()),
        "queue_files": queue_files,
        "scheduling_method": "longest-processing-time-first greedy assignment",
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "preparation_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
