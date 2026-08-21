from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
from prta_cxr.phase20_evidence_program import EVIDENCE_LANES
from prta_cxr.phase20_queue_runner import dependency_decision
from prta_cxr.provenance import resolve_source_commit

TERMINAL = {"PASS", "FAILED", "SKIPPED"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_evidence_platform_inputs(
    platform: Mapping[str, Any], input_manifest: Mapping[str, Any]
) -> dict[str, Path]:
    required = {
        "split_manifest",
        "cleaned_split_freeze",
        "cleaned_split_platform_root",
        "cache_root",
        "text_cache",
        "matched_hard_prior_map",
        "weights",
        "label_quality_audit",
        *(f"s1_checkpoint_{seed}" for seed in (17, 28, 43)),
        *(f"s1_training_receipt_{seed}" for seed in (17, 28, 43)),
    }
    if set(platform) != required:
        raise ValueError("Phase20 evidence platform input role set drift")
    paths = {role: Path(str(platform[role])).resolve() for role in required}
    expected = dict(input_manifest.get("input_sha256", {}))
    file_roles = {
        "split_manifest": paths["split_manifest"],
        "cleaned_split_freeze": paths["cleaned_split_freeze"],
        "cache_manifest": paths["cache_root"] / "cache_manifest.json",
        "text_cache": paths["text_cache"],
        "matched_hard_prior_map": paths["matched_hard_prior_map"],
        "weights": paths["weights"],
        "label_quality_audit": paths["label_quality_audit"],
        **{
            f"s1_checkpoint_{seed}": paths[f"s1_checkpoint_{seed}"]
            for seed in (17, 28, 43)
        },
        **{
            f"s1_training_receipt_{seed}": paths[f"s1_training_receipt_{seed}"]
            for seed in (17, 28, 43)
        },
    }
    if set(expected) != set(file_roles):
        raise ValueError("Phase20 evidence frozen input role set drift")
    for role, path in file_roles.items():
        if not path.is_file():
            raise FileNotFoundError(f"Phase20 evidence platform input missing: {role}")
        if sha256_file(path) != expected[role]:
            raise ValueError(f"Phase20 evidence platform input hash drift: {role}")
    for role in (
        "cleaned_split_platform_root",
        "cache_root",
    ):
        if not paths[role].is_dir():
            raise FileNotFoundError(f"Phase20 evidence directory missing: {role}")
    return paths


def render_evidence_command(
    command: Sequence[str],
    *,
    source: Path,
    runtime_root: Path,
    output_root: Path,
    device: str,
    inputs: Mapping[str, Path],
) -> list[str]:
    replacements = {
        "{python}": sys.executable,
        "{source}": str(source),
        "{runtime_root}": str(runtime_root),
        "{output_root}": str(output_root),
        "{device}": device,
        **{f"{{{name}}}": str(path) for name, path in inputs.items()},
    }
    rendered = []
    for raw in command:
        value = str(raw)
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        if "{" in value or "}" in value:
            raise ValueError(f"unresolved Phase20 evidence placeholder: {value}")
        rendered.append(value)
    return rendered


def _state_path(shared_state: Path, job_id: str) -> Path:
    if not job_id or any(value in job_id for value in ("/", "\\", "..")):
        raise ValueError("unsafe Phase20 evidence job ID")
    return shared_state / f"{job_id}.json"


def _wait_for_dependencies(
    shared_state: Path, dependencies: Sequence[str], *, poll_seconds: float
) -> tuple[str, list[dict[str, Any]]]:
    while True:
        states = []
        for dependency in dependencies:
            path = _state_path(shared_state, dependency)
            status = "PENDING"
            if path.is_file():
                status = str(dict(_read_json(path)).get("status", ""))
            states.append({"job_id": dependency, "status": status})
        decision = dependency_decision([value["status"] for value in states])
        if decision != "WAIT":
            return decision, states
        time.sleep(poll_seconds)


def run_phase20_evidence_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run frozen Phase20 Slim-S1 evidence")
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--lane", choices=EVIDENCE_LANES, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-state", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    source = args.source.resolve()
    runtime_root = args.runtime_root.resolve()
    output_root = args.output_root.resolve()
    shared_state = args.shared_state.resolve()
    preparation = dict(_read_json(runtime_root / "preparation_receipt.json"))
    if preparation.get("status") != "PASS_PHASE20_SLIM_S1_EVIDENCE_PROGRAM_FROZEN":
        raise ValueError("Phase20 evidence preparation is not frozen PASS")
    if preparation.get("source_commit") != resolve_source_commit(source):
        raise ValueError("Phase20 evidence source commit drift")
    if preparation.get("lane") != args.lane:
        raise ValueError("Phase20 evidence lane drift")
    if sha256_file(args.queue) != preparation.get("queue_sha256"):
        raise ValueError("Phase20 evidence queue hash drift")
    platform_inputs = validate_evidence_platform_inputs(
        dict(_read_json(args.inputs)),
        dict(_read_json(runtime_root / "input_manifest.json")),
    )
    queue = _read_json(args.queue)
    if not isinstance(queue, list) or not queue:
        raise ValueError("Phase20 evidence queue is empty")
    if any(str(job.get("lane")) != args.lane for job in queue):
        raise ValueError("Phase20 evidence queue lane identity drift")
    logs = output_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    shared_state.mkdir(parents=True, exist_ok=True)
    progress_path = output_root / "progress.json"
    completion_path = output_root / "completion.json"
    if completion_path.exists():
        raise FileExistsError("Phase20 evidence already has a completion receipt")
    completed: list[dict[str, Any]] = []
    failures: list[str] = []
    skipped: list[str] = []
    environment = os.environ.copy()
    environment[FORMAL_ENV_NAME] = FORMAL_ENV_VALUE
    for raw_job in queue:
        job = dict(raw_job)
        job_id = str(job["job_id"])
        state_path = _state_path(shared_state, job_id)
        if state_path.is_file():
            existing = dict(_read_json(state_path))
            if existing.get("status") in TERMINAL:
                completed.append({"job_id": job_id, "status": existing["status"]})
                if existing["status"] == "FAILED":
                    failures.append(job_id)
                if existing["status"] == "SKIPPED":
                    skipped.append(job_id)
                continue
            raise RuntimeError(f"non-terminal Phase20 evidence state exists: {job_id}")
        decision, dependency_states = _wait_for_dependencies(
            shared_state,
            [str(value) for value in job.get("dependencies", [])],
            poll_seconds=args.poll_seconds,
        )
        if decision == "SKIP":
            terminal = {
                "schema": "prta-cxr.phase20-evidence-job-state.v1",
                "status": "SKIPPED",
                "job_id": job_id,
                "lane": args.lane,
                "created_at": _now(),
                "reason": "dependency_not_pass",
                "dependencies": dependency_states,
            }
            write_json_atomic(state_path, terminal)
            skipped.append(job_id)
            completed.append({"job_id": job_id, "status": "SKIPPED"})
            continue
        command = render_evidence_command(
            job["command"],
            source=source,
            runtime_root=runtime_root,
            output_root=output_root,
            device=args.device,
            inputs=platform_inputs,
        )
        running = {
            "schema": "prta-cxr.phase20-evidence-job-state.v1",
            "status": "RUNNING",
            "job_id": job_id,
            "group": job["group"],
            "lane": args.lane,
            "started_at": _now(),
            "command": command,
            "dependencies": dependency_states,
            "source_commit": resolve_source_commit(source),
            "queue_sha256": sha256_file(args.queue),
        }
        write_json_atomic(state_path, running)
        stdout_path = logs / f"{job_id}.stdout.log"
        stderr_path = logs / f"{job_id}.stderr.log"
        started = time.monotonic()
        with (
            stdout_path.open("x", encoding="utf-8") as stdout,
            stderr_path.open("x", encoding="utf-8") as stderr,
        ):
            result = subprocess.run(
                command,
                cwd=source,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        output_checks = []
        outputs_ok = True
        for raw_path in job.get("expected_outputs", []):
            rendered = render_evidence_command(
                [str(raw_path)],
                source=source,
                runtime_root=runtime_root,
                output_root=output_root,
                device=args.device,
                inputs=platform_inputs,
            )[0]
            path = Path(rendered)
            exists = path.exists()
            outputs_ok = outputs_ok and exists
            output_checks.append(
                {
                    "path": rendered,
                    "exists": exists,
                    "sha256": sha256_file(path) if path.is_file() else None,
                }
            )
        status = "PASS" if result.returncode == 0 and outputs_ok else "FAILED"
        terminal = {
            **running,
            "status": status,
            "completed_at": _now(),
            "elapsed_seconds": time.monotonic() - started,
            "return_code": result.returncode,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "output_checks": output_checks,
        }
        replace_json_atomic(state_path, terminal)
        completed.append({"job_id": job_id, "status": status})
        if status == "FAILED":
            failures.append(job_id)
        progress = {
            "schema": "prta-cxr.phase20-evidence-progress.v1",
            "status": "RUNNING",
            "updated_at": _now(),
            "completed": completed,
            "failures": failures,
            "skipped": skipped,
            "remaining": len(queue) - len(completed),
        }
        if progress_path.exists():
            replace_json_atomic(progress_path, progress)
        else:
            write_json_atomic(progress_path, progress)
    final_status = "PASS" if not failures else "COMPLETE_WITH_FAILURES"
    completion = {
        "schema": "prta-cxr.phase20-evidence-completion.v1",
        "status": final_status,
        "lane": args.lane,
        "completed_at": _now(),
        "completed": completed,
        "failures": failures,
        "skipped": skipped,
        "queue_sha256": sha256_file(args.queue),
        "source_commit": resolve_source_commit(source),
        "selection_performed": False,
        "external_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(completion_path, completion)
    if progress_path.exists():
        replace_json_atomic(progress_path, completion)
    else:
        write_json_atomic(progress_path, completion)
    print(json.dumps(completion, indent=2, sort_keys=True))
    return 0 if not failures else 2
