from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from _bootstrap import _prepare

_prepare()

from prta_cxr.artifacts import replace_json_atomic  # noqa: E402
from prta_cxr.audit.tracin import SEEDS, AuditContractError, audit_path  # noqa: E402


def _gpu_memory() -> dict[int, int]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.used",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = {}
    for line in completed.stdout.splitlines():
        index, used = (value.strip() for value in line.split(",", 1))
        result[int(index)] = int(used)
    return result


def _state(path: Path, **values: object) -> None:
    replace_json_atomic(
        path,
        {
            "schema": "prta-cxr.approximate-tracin-keeper.v1",
            "updated_at": datetime.now(UTC).isoformat(),
            "training_started": False,
            "protected_outcome_read_count": 0,
            **values,
        },
    )


def _common_args(args: argparse.Namespace) -> list[str]:
    return [
        str(Path(__file__).with_name("14_run_tracin_audit.py")),
        "--readonly-audit",
        "--split-manifest",
        str(args.split_manifest),
        "--cache-root",
        str(args.cache_root),
        "--text-cache",
        str(args.text_cache),
        "--weights",
        str(args.weights),
        "--runs-root",
        str(args.runs_root),
        "--output",
        str(args.output),
        "--repo-root",
        str(args.repo_root),
        "--batch-size",
        str(args.batch_size),
        "--probe-batch-size",
        str(args.probe_batch_size),
        "--workers",
        str(args.workers),
        "--resume",
    ]


def _launch_seed(
    args: argparse.Namespace, seed: int, device: str
) -> tuple[subprocess.Popen[str], object, object]:
    stdout_path = args.output / f"seed{seed}.stdout.log"
    stderr_path = args.output / f"seed{seed}.stderr.log"
    stdout = stdout_path.open("a", encoding="utf-8", buffering=1)
    stderr = stderr_path.open("a", encoding="utf-8", buffering=1)
    command = [
        sys.executable,
        *_common_args(args),
        "--phase",
        "seed",
        "--seed",
        str(seed),
        "--device",
        device,
    ]
    process = subprocess.Popen(
        command,
        cwd=args.repo_root,
        stdout=stdout,
        stderr=stderr,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return process, stdout, stderr


def _wait_for_idle(args: argparse.Namespace, state_path: Path) -> None:
    while True:
        memory = _gpu_memory()
        ready = all(memory.get(index, 10**9) <= args.max_used_mb for index in (0, 1))
        _state(
            state_path,
            status="WAITING_FOR_SAFE_GPU_MEMORY" if not ready else "GPU_MEMORY_READY",
            gpu_memory_used_mb=memory,
            maximum_allowed_used_mb=args.max_used_mb,
        )
        if ready:
            return
        time.sleep(args.poll_seconds)


def _wait_children(
    children: dict[int, tuple[subprocess.Popen[str], object, object]],
    state_path: Path,
    poll_seconds: int,
) -> None:
    while True:
        statuses = {
            str(seed): process.poll() for seed, (process, _, _) in children.items()
        }
        _state(
            state_path,
            status="RUNNING_SEED_LANES",
            child_status=statuses,
            child_pids={
                str(seed): process.pid for seed, (process, _, _) in children.items()
            },
        )
        if all(value is not None for value in statuses.values()):
            break
        time.sleep(poll_seconds)
    for _, stdout, stderr in children.values():
        stdout.close()
        stderr.close()
    failures = {seed: status for seed, status in statuses.items() if status != 0}
    if failures:
        raise RuntimeError(f"seed audit lane failed without deletion: {failures}")


def _assemble(args: argparse.Namespace) -> None:
    stdout_path = args.output / "assemble.stdout.log"
    stderr_path = args.output / "assemble.stderr.log"
    with stdout_path.open("a", encoding="utf-8", buffering=1) as stdout:
        with stderr_path.open("a", encoding="utf-8", buffering=1) as stderr:
            completed = subprocess.run(
                [
                    sys.executable,
                    *_common_args(args),
                    "--phase",
                    "assemble",
                ],
                cwd=args.repo_root,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
    if completed.returncode:
        raise RuntimeError(
            "final audit assembly failed; private intermediates retained"
        )


def keeper_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait-safe keeper for TracIn audit")
    parser.add_argument("--readonly-audit", action="store_true")
    for name in (
        "split-manifest",
        "cache-root",
        "text-cache",
        "weights",
        "runs-root",
        "output",
        "repo-root",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--probe-batch-size", type=int, default=2)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--max-used-mb", type=int, default=4_000)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    if not args.readonly_audit:
        parser.error("keeper requires --readonly-audit")
    if args.poll_seconds < 10 or args.poll_seconds > 60:
        parser.error("poll seconds must be within 10..60")
    try:
        for role in (
            "split_manifest",
            "cache_root",
            "text_cache",
            "weights",
            "runs_root",
            "output",
            "repo_root",
        ):
            setattr(args, role, audit_path(getattr(args, role), role=role))
    except AuditContractError as error:
        parser.error(str(error))
    args.output.mkdir(parents=True, exist_ok=True)
    state_path = args.output / "keeper_state.json"
    try:
        _wait_for_idle(args, state_path)
        first = {
            17: _launch_seed(args, 17, "cuda:0"),
            29: _launch_seed(args, 29, "cuda:1"),
        }
        _wait_children(first, state_path, args.poll_seconds)
        _wait_for_idle(args, state_path)
        final = {43: _launch_seed(args, 43, "cuda:0")}
        _wait_children(final, state_path, args.poll_seconds)
        _state(state_path, status="ASSEMBLING_FULL_PRIVATE_AUDIT")
        _assemble(args)
        _state(
            state_path,
            status="COMPLETE_READONLY_APPROXIMATE_TRACIN_AUDIT",
            completed_seeds=list(SEEDS),
        )
    except Exception as error:
        _state(
            state_path,
            status="HOLD_TRACIN_AUDIT_ERROR",
            error_type=type(error).__name__,
            error=str(error),
        )
        raise
    print(json.dumps(json.loads(state_path.read_text(encoding="utf-8")), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(keeper_main())
