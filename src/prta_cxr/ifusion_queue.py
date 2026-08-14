from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import replace_json_atomic, write_json_atomic
from prta_cxr.authorization import (
    FORMAL_ENV_NAME,
    FORMAL_ENV_VALUE,
    require_formal_authorization,
)
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.provenance import resolve_source_commit

LANE_NAMES = ("server3066", "server9929", "local_gpu0", "local_gpu1")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _device_snapshot(device_index: int) -> dict[str, int]:
    command = [
        "nvidia-smi",
        "-i",
        str(device_index),
        "--query-gpu=memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    output = subprocess.run(
        command, check=True, capture_output=True, text=True
    ).stdout.strip()
    memory, utilization = [int(value.strip()) for value in output.split(",")]
    return {"memory_used_mib": memory, "utilization_percent": utilization}


def wait_for_device_idle(
    device_index: int,
    *,
    memory_threshold_mib: int,
    utilization_threshold_percent: int,
    poll_seconds: int,
) -> dict[str, Any]:
    started = _now()
    while True:
        snapshot = _device_snapshot(device_index)
        if (
            snapshot["memory_used_mib"] <= memory_threshold_mib
            and snapshot["utilization_percent"] <= utilization_threshold_percent
        ):
            return {"wait_started_at": started, "ready_at": _now(), **snapshot}
        time.sleep(poll_seconds)


def _validate_inputs(args: argparse.Namespace, preparation: dict[str, Any]) -> None:
    expected = dict(preparation["input_sha256"])
    observed = {
        "split_manifest": sha256_file(args.split_manifest),
        "cleaned_split_freeze": sha256_file(args.cleaned_split_freeze),
        "cache_manifest": sha256_file(args.cache_root / "cache_manifest.json"),
        "text_cache": sha256_file(args.text_cache),
        "matched_hard_prior_map": sha256_file(args.matched_hard_prior_map),
        "weights": sha256_file(args.weights),
        "label_quality_audit": sha256_file(args.label_quality_audit),
    }
    if observed != expected:
        changed = sorted(
            role
            for role in set(observed) | set(expected)
            if observed.get(role) != expected.get(role)
        )
        raise ValueError(f"Information Fusion input hash drift: {changed}")
    if (
        sha256_file(args.random_counterfactual_prior_map)
        != preparation["random_counterfactual_prior_map_sha256"]
    ):
        raise ValueError("Information Fusion random CMCP map hash drift")


def _training_command(
    args: argparse.Namespace,
    *,
    config_path: Path,
    output: Path,
    map_role: str | None,
) -> list[str]:
    command = [
        sys.executable,
        str(args.source / "scripts/07_train.py"),
        "--mode",
        "formal",
        "--formal",
        "--config",
        str(config_path),
        "--split-manifest",
        str(args.split_manifest),
        "--cleaned-split-freeze",
        str(args.cleaned_split_freeze),
        "--cache-root",
        str(args.cache_root),
        "--text-cache",
        str(args.text_cache),
        "--weights",
        str(args.weights),
        "--label-quality-audit",
        str(args.label_quality_audit),
        "--run-registry",
        str(args.root / f"run_registry_{args.lane}.jsonl"),
        "--owner",
        "PRTA-CXR Information Fusion final evidence",
        "--device",
        "cuda:0",
        "--output",
        str(output),
    ]
    if args.cleaned_split_platform_root is not None:
        command.extend(
            [
                "--cleaned-split-platform-root",
                str(args.cleaned_split_platform_root),
            ]
        )
    if map_role == "matched_hard_prior_map":
        command.extend(["--counterfactual-prior-map", str(args.matched_hard_prior_map)])
    elif map_role == "random_counterfactual_prior_map":
        command.extend(
            [
                "--counterfactual-prior-map",
                str(args.random_counterfactual_prior_map),
            ]
        )
    elif map_role is not None:
        raise ValueError(f"unsupported counterfactual map role: {map_role}")
    return command


def run_ifusion_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one frozen Information Fusion GPU lane"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--lane", choices=LANE_NAMES, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--matched-hard-prior-map", type=Path, required=True)
    parser.add_argument("--random-counterfactual-prior-map", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--device-index", type=int, required=True)
    parser.add_argument("--allocation", type=int)
    parser.add_argument("--wait-for-idle", action="store_true")
    parser.add_argument("--idle-memory-mib", type=int, default=512)
    parser.add_argument("--idle-utilization-percent", type=int, default=5)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)

    args.root = args.root.resolve()
    args.source = args.source.resolve()
    preparation_path = args.root / "preparation_receipt.json"
    preparation = _read_json(preparation_path)
    if preparation.get("status") != "PASS_IFUSION_CORE_MATRIX_FROZEN":
        raise ValueError("Information Fusion preparation is not frozen")
    source_commit = resolve_source_commit(args.source)
    if source_commit != preparation.get("repository_commit"):
        raise ValueError("Information Fusion source commit drift")
    _validate_inputs(args, preparation)

    queue_path = args.root / "queue" / f"{args.lane}.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(queue, list) or not queue:
        raise ValueError("Information Fusion lane queue is empty")
    progress_path = args.root / "progress" / f"{args.lane}.json"
    completion_path = args.root / "completion" / f"{args.lane}.json"
    failure_path = args.root / "failures" / f"{args.lane}.json"
    for path in (progress_path, completion_path, failure_path):
        if path.exists():
            raise FileExistsError(f"Information Fusion lane already started: {path}")

    progress = {
        "schema": "prta-cxr.ifusion-lane-progress.v1",
        "status": "WAITING_FOR_DEVICE" if args.wait_for_idle else "RUNNING",
        "updated_at": _now(),
        "lane": args.lane,
        "allocation": args.allocation,
        "device_index": args.device_index,
        "source_commit": source_commit,
        "preparation_sha256": sha256_file(preparation_path),
        "current_run_id": None,
        "completed": [],
        "remaining": len(queue),
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(progress_path, progress)

    environment = os.environ.copy()
    environment.update(
        {
            FORMAL_ENV_NAME: FORMAL_ENV_VALUE,
            "PRTA_CXR_SOURCE_COMMIT": source_commit,
            "PYTHONUNBUFFERED": "1",
            "CUDA_VISIBLE_DEVICES": str(args.device_index),
        }
    )
    completed: list[dict[str, Any]] = []
    for index, row in enumerate(queue):
        run_id = str(row["experiment_id"])
        config_record = dict(row["config"])
        config_path = args.root / str(config_record["path"])
        config = _read_json(config_path)
        if sha256_file(config_path) != config_record["file_sha256"]:
            raise ValueError(f"Information Fusion config file drift: {run_id}")
        if canonical_sha256(config) != config_record["effective_config_sha256"]:
            raise ValueError(f"Information Fusion effective config drift: {run_id}")
        if config.get("experiment_id") != run_id:
            raise ValueError(f"Information Fusion config identity drift: {run_id}")

        idle_audit = None
        if args.wait_for_idle:
            idle_audit = wait_for_device_idle(
                args.device_index,
                memory_threshold_mib=args.idle_memory_mib,
                utilization_threshold_percent=args.idle_utilization_percent,
                poll_seconds=args.poll_seconds,
            )
        output = args.root / "runs" / run_id
        log = args.root / "logs" / args.lane / f"{run_id}.log"
        if output.exists() or log.exists():
            raise FileExistsError(f"immutable Information Fusion run exists: {run_id}")
        log.parent.mkdir(parents=True, exist_ok=True)
        progress.update(
            {
                "status": "RUNNING",
                "updated_at": _now(),
                "current_run_id": run_id,
                "current_queue_index": index,
                "completed": completed,
                "remaining": len(queue) - index,
                "device_idle_audit": idle_audit,
            }
        )
        replace_json_atomic(progress_path, progress)
        command = _training_command(
            args,
            config_path=config_path,
            output=output,
            map_role=row.get("counterfactual_map_role"),
        )
        with log.open("xb") as stream:
            returncode = subprocess.run(
                command,
                cwd=args.source,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
        if returncode:
            failure = {
                "schema": "prta-cxr.ifusion-lane-failure.v1",
                "status": "IFUSION_LANE_FAILED_HOLD",
                "created_at": _now(),
                "lane": args.lane,
                "allocation": args.allocation,
                "run_id": run_id,
                "returncode": returncode,
                "completed": completed,
                "log": str(log.relative_to(args.root)).replace("\\", "/"),
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            }
            write_json_atomic(failure_path, failure)
            replace_json_atomic(progress_path, failure)
            raise RuntimeError(f"Information Fusion lane failed: {run_id}")
        receipt_path = output / "training_receipt.json"
        receipt = _read_json(receipt_path)
        if receipt.get("status") != "PASS_TRAINING_FINISHED":
            raise RuntimeError(f"Information Fusion run is nonterminal: {run_id}")
        if receipt.get("config_sha256") != config_record["effective_config_sha256"]:
            raise RuntimeError(f"Information Fusion receipt config drift: {run_id}")
        if receipt.get("internal_test_opened") is not False:
            raise RuntimeError(f"Information Fusion opened Internal-test: {run_id}")
        protected = receipt.get(
            "protected_outcome_read_count",
            0 if receipt.get("protected_outcomes_opened") is False else -1,
        )
        if protected != 0:
            raise RuntimeError(f"Information Fusion protected-read drift: {run_id}")
        completed.append(
            {
                "run_id": run_id,
                "receipt_sha256": sha256_file(receipt_path),
                "config_sha256": config_record["effective_config_sha256"],
                "zero_protected_reads": True,
            }
        )

    completion = {
        "schema": "prta-cxr.ifusion-lane-completion.v1",
        "status": "PASS_IFUSION_LANE_COMPLETE",
        "created_at": _now(),
        "lane": args.lane,
        "allocation": args.allocation,
        "device_index": args.device_index,
        "source_commit": source_commit,
        "preparation_sha256": sha256_file(preparation_path),
        "completed": completed,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(completion_path, completion)
    replace_json_atomic(
        progress_path,
        {**completion, "updated_at": _now(), "current_run_id": None},
    )
    print(json.dumps(completion, indent=2, sort_keys=True))
    return 0
