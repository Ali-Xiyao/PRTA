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

LANES = ("a800_3066", "a800_9929")
GROUPS = (
    "modality_stress",
    "state_pruning",
    "source_held_out",
    "source_held_out_exploratory",
    "source_held_out_confirmatory",
    "data_scaling",
    "label_noise",
    "official_baseline",
    "internal_longitudinal_comparator",
    "slim_matrix",
)
TERMINAL = {"PASS", "FAILED", "SKIPPED"}


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def validate_registry(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    if registry.get("schema") != "prta-cxr.phase16-job-registry.v1":
        raise ValueError("unsupported Phase16 job registry schema")
    jobs = [dict(item) for item in registry.get("jobs", [])]
    if not jobs:
        raise ValueError("Phase16 registry is empty")
    identifiers = [str(job.get("job_id", "")) for job in jobs]
    if any(not value for value in identifiers) or len(identifiers) != len(
        set(identifiers)
    ):
        raise ValueError("Phase16 job IDs must be non-empty and unique")
    known = set(identifiers)
    graph: dict[str, tuple[str, ...]] = {}
    for job in jobs:
        job_id = str(job["job_id"])
        group = str(job.get("group", ""))
        if group not in GROUPS:
            raise ValueError(f"unsupported Phase16 group: {group}")
        if int(job.get("estimated_seconds", 0)) <= 0:
            raise ValueError(f"non-positive estimate: {job_id}")
        command = job.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(value, str) and value for value in command)
        ):
            raise ValueError(f"invalid command: {job_id}")
        dependencies = tuple(str(value) for value in job.get("dependencies", []))
        if job_id in dependencies or set(dependencies) - known:
            raise ValueError(f"invalid dependencies: {job_id}")
        graph[job_id] = dependencies
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("Phase16 dependency graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for identifier in identifiers:
        visit(identifier)
    return jobs


def allocate_lanes(
    jobs: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    assignments: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
    loads = {lane: 0 for lane in LANES}
    by_id = {str(job["job_id"]): dict(job) for job in jobs}
    ranks: dict[str, int] = {}

    def rank(job_id: str) -> int:
        if job_id not in ranks:
            dependencies = [
                str(value) for value in by_id[job_id].get("dependencies", [])
            ]
            ranks[job_id] = 0 if not dependencies else 1 + max(map(rank, dependencies))
        return ranks[job_id]

    assignment_order = sorted(
        by_id.values(),
        key=lambda item: (
            -int(item["estimated_seconds"]),
            rank(str(item["job_id"])),
            int(item.get("queue_priority", 100)),
            str(item["job_id"]),
        ),
    )
    for job in assignment_order:
        lane = min(LANES, key=lambda value: (loads[value], value))
        job["lane"] = lane
        assignments[lane].append(job)
        loads[lane] += int(job["estimated_seconds"])
    for lane_jobs in assignments.values():
        lane_jobs.sort(
            key=lambda item: (
                rank(str(item["job_id"])),
                int(item.get("queue_priority", 100)),
                -int(item["estimated_seconds"]),
                str(item["job_id"]),
            )
        )
        for index, job in enumerate(lane_jobs):
            job["queue_index"] = index
    return assignments


def prepare_phase16_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze balanced Phase16 two-A800 queues"
    )
    parser.add_argument("--job-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be new")
    registry = json.loads(args.job_registry.read_text(encoding="utf-8"))
    jobs = validate_registry(registry)
    assignments = allocate_lanes(jobs)
    loads = {
        lane: sum(int(job["estimated_seconds"]) for job in queue)
        for lane, queue in assignments.items()
    }
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    queue_hashes = {}
    for lane, queue in assignments.items():
        path = staging / f"{lane}.json"
        _write_new_json(path, queue)
        queue_hashes[path.name] = sha256_file(path)
    receipt = {
        "schema": "prta-cxr.phase16-two-a800-queue.v1",
        "status": "PASS_PHASE16_TWO_A800_QUEUE_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "registry_sha256": sha256_file(args.job_registry),
        "matrix_sha256": canonical_sha256(jobs),
        "job_count": len(jobs),
        "lanes": list(LANES),
        "lane_load_estimated_seconds": loads,
        "estimated_imbalance_seconds": max(loads.values()) - min(loads.values()),
        "queue_files": queue_hashes,
        "scheduling_method": "LPT with dependency-aware shared terminal states",
        "external_evaluation_included": False,
        "clinician_manual_work_included": False,
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "preparation_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
