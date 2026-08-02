from __future__ import annotations

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
from prta_cxr.data.cache_writer import build_block8_training_store


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def dependencies_satisfied(
    row: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> bool:
    dependencies = tuple(str(value) for value in row.get("depends_on", ()))
    if not dependencies and str(row["experiment_id"]).startswith("M301-"):
        dependencies = ("D205",)
    statuses = {str(value["experiment_id"]): str(value["status"]) for value in rows}
    return all(
        statuses.get(value) == "PASS_TRAINING_FINISHED" for value in dependencies
    )


def _cache_ready(cache_root: Path) -> bool:
    manifest_path = cache_root / "cache_manifest.json"
    text_path = cache_root / "text_cache.pt"
    if not manifest_path.is_file() or not text_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS_PRTA_CXR_BLOCK8_CACHE":
        return False
    if "training_store" not in manifest:
        build_block8_training_store(cache_root)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest.get("training_store", {}).get("status") == (
        "PASS_BLOCK8_TRAINING_STORE"
    )


def _close_finished_rows(rows: list[dict[str, Any]]) -> bool:
    changed = False
    for row in rows:
        if row.get("status") != "RUNNING":
            continue
        pid = int(row["pid"])
        if process_alive(pid):
            continue
        output = Path(str(row["output_path"]))
        receipt_path = output / "training_receipt.json"
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            row["status"] = str(receipt["status"])
            row["best_dev_macro_f1"] = float(receipt["best_dev_macro_f1"])
            row["completed_at"] = datetime.now(UTC).isoformat()
        else:
            row["status"] = "FAILED"
            row["completed_at"] = datetime.now(UTC).isoformat()
            row["failure_reason"] = "process exited without training receipt"
        changed = True
    return changed


def run_training_queue(
    *,
    queue_path: Path,
    split_manifest: Path,
    cache_root: Path,
    weights: Path,
    quality_audit: Path,
    run_registry: Path,
    runs_root: Path,
    devices: Sequence[str],
    poll_seconds: int,
) -> dict[str, Any]:
    if not devices or poll_seconds < 5:
        raise ValueError("queue requires devices and poll_seconds >= 5")
    queue_path = Path(queue_path)
    runs_root = Path(runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)
    log_root = runs_root / "logs"
    log_root.mkdir(exist_ok=True)
    repo_root = Path(__file__).resolve().parents[2]
    state_path = queue_path.with_name("scheduler_state.json")
    while True:
        rows = json.loads(queue_path.read_text(encoding="utf-8"))
        changed = _close_finished_rows(rows)
        failed = [row for row in rows if row.get("status") == "FAILED"]
        complete = [
            row for row in rows if row.get("status") == "PASS_TRAINING_FINISHED"
        ]
        if failed:
            if changed:
                replace_json_atomic(queue_path, rows)
            state = {
                "status": "HOLD_QUEUE_FAILED",
                "failed": [row["experiment_id"] for row in failed],
                "completed": len(complete),
                "total": len(rows),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            replace_json_atomic(state_path, state)
            return state
        if len(complete) == len(rows):
            if changed:
                replace_json_atomic(queue_path, rows)
            stage = str(rows[0].get("stage", "initial_development"))
            result = {
                "schema": "prta-cxr.training-queue-receipt.v1",
                "status": "PASS_TRAINING_QUEUE_FINISHED",
                "stage": stage,
                "completed": len(complete),
                "total": len(rows),
                "internal_test_opened": False,
                "gold_opened": False,
                "completed_at": datetime.now(UTC).isoformat(),
            }
            replace_json_atomic(state_path, result)
            receipt_path = queue_path.with_name("scheduler_receipt.json")
            if not receipt_path.exists():
                write_json_atomic(receipt_path, result)
            return result
        if not _cache_ready(cache_root):
            state = {
                "status": "WAITING_FOR_COMPLETE_CACHE_AND_TRAINING_STORE",
                "completed": len(complete),
                "total": len(rows),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            replace_json_atomic(state_path, state)
            if changed:
                replace_json_atomic(queue_path, rows)
            time.sleep(poll_seconds)
            continue
        running = [row for row in rows if row.get("status") == "RUNNING"]
        used_devices = {str(row["device"]) for row in running}
        free_devices = [value for value in devices if value not in used_devices]
        for device in free_devices:
            planned = next(
                (
                    row
                    for row in rows
                    if row.get("status") == "PLANNED"
                    and dependencies_satisfied(row, rows)
                ),
                None,
            )
            if planned is None:
                break
            experiment_id = str(planned["experiment_id"])
            output = runs_root / experiment_id
            if output.exists():
                planned["status"] = "FAILED"
                planned["failure_reason"] = "unexpected existing output directory"
                changed = True
                break
            stdout_path = log_root / f"{experiment_id}.stdout.log"
            stderr_path = log_root / f"{experiment_id}.stderr.log"
            command = [
                sys.executable,
                str(repo_root / "scripts" / "07_train.py"),
                "--mode",
                "formal",
                "--formal",
                "--config",
                str(planned["config_path"]),
                "--split-manifest",
                str(split_manifest),
                "--cache-root",
                str(cache_root),
                "--text-cache",
                str(cache_root / "text_cache.pt"),
                "--weights",
                str(weights),
                "--label-quality-audit",
                str(quality_audit),
                "--run-registry",
                str(run_registry),
                "--device",
                device,
                "--output",
                str(output),
            ]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            with stdout_path.open("w", encoding="utf-8") as stdout_handle:
                with stderr_path.open("w", encoding="utf-8") as stderr_handle:
                    process = subprocess.Popen(
                        command,
                        cwd=repo_root,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        creationflags=creationflags,
                    )
            planned.update(
                {
                    "status": "RUNNING",
                    "pid": process.pid,
                    "device": device,
                    "output_path": str(output.resolve()),
                    "stdout_path": str(stdout_path.resolve()),
                    "stderr_path": str(stderr_path.resolve()),
                    "started_at": datetime.now(UTC).isoformat(),
                }
            )
            changed = True
        if changed:
            replace_json_atomic(queue_path, rows)
        state = {
            "status": "RUNNING" if any(
                row.get("status") == "RUNNING" for row in rows
            ) else "WAITING_DEPENDENCIES",
            "completed": len(
                [row for row in rows if row.get("status") == "PASS_TRAINING_FINISHED"]
            ),
            "running": [
                row["experiment_id"]
                for row in rows
                if row.get("status") == "RUNNING"
            ],
            "total": len(rows),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        replace_json_atomic(state_path, state)
        time.sleep(poll_seconds)
