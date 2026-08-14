from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import replace_json_atomic, write_json_atomic
from prta_cxr.audit.tracin import AuditContractError, audit_path
from prta_cxr.contracts import canonical_sha256, sha256_file

SOURCE_COMMIT = "62235ff46fb26e4ccf05e3c9073188a84ca39119"
PREPARATION_SHA256 = "a417b03e22b54da612e673600cac91b5233cfffcb7e533c8611adfda9d7f2aaa"
ORIGINAL_QUEUE_SHA256 = (
    "01bfda09a57ddac97504d5e76fc6440d4a82169e62c72054f76a259f5e997828"
)
TARGET_ID = "W046-B401-S43"
EXPECTED_STATUS = {
    "W046-B401-S17": "RUNNING",
    "W046-B401-S28": "RUNNING",
    TARGET_ID: "PLANNED",
    "W046-B402-S28": "PLANNED",
    "W046-B402-S43": "PLANNED",
}
RUNTIME_FIELDS = {
    "device",
    "failure_reason",
    "output_path",
    "pid",
    "started_at",
    "stderr_path",
    "stdout_path",
}
SERVER_BASE = Path(
    "/ipfs/inspurfileset/home/dqxy/dqxy11/projects/xiyaowang/050_VisualVIT"
)
SERVER_LIVE = SERVER_BASE / "PRTA-CXR"
SERVER_RUNTIME = SERVER_LIVE / "data/runtime"
SERVER_SEARCH = SERVER_RUNTIME / "server_runs/continuous_lightweight_dev_search_v1"
SERVER_ROOT = SERVER_SEARCH / "wave046_native_baseline_3066_amendment_v1"
SERVER_SOURCE = SERVER_BASE / "PRTA-CXR-source-snapshots" / SOURCE_COMMIT


def _now() -> str:
    return datetime.now(UTC).isoformat()


def frozen_queue_identity(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    frozen: list[dict[str, Any]] = []
    for row in rows:
        value = {key: item for key, item in row.items() if key not in RUNTIME_FIELDS}
        value["status"] = "PLANNED"
        frozen.append(value)
    return frozen


def _git_blob_sha(repo_root: Path, commit: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    import hashlib

    return hashlib.sha256(result.stdout).hexdigest()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _validate_live_queue(rows: Sequence[Mapping[str, Any]]) -> None:
    by_id = {str(row["experiment_id"]): row for row in rows}
    if set(by_id) != set(EXPECTED_STATUS):
        raise AuditContractError("Wave046 live queue identity drift")
    for run_id, status in EXPECTED_STATUS.items():
        if by_id[run_id].get("status") != status:
            raise AuditContractError(f"Wave046 status drift for {run_id}")
    for run_id in ("W046-B401-S17", "W046-B401-S28"):
        pid = int(by_id[run_id].get("pid", -1))
        if pid <= 0 or not _pid_alive(pid):
            raise AuditContractError(f"Wave046 active PID missing for {run_id}")
    if any(row.get("status") in {"FAILED", "PASS_TRAINING_FINISHED"} for row in rows):
        raise AuditContractError("Wave046 terminal outcome exists before amendment")


def _server_manifest(*, config: Mapping[str, Any], config_path: Path) -> dict[str, Any]:
    cache = SERVER_RUNTIME / "formal_program_v1/cache/full_repartition_v1"
    quality = SERVER_SEARCH / "inputs/human_silver_accuracy_audit.json"
    weights = SERVER_BASE.parent / "model/biomedclip/open_clip_pytorch_model.bin"
    split = (
        SERVER_RUNTIME
        / "formal_cleaned_split_v1_1/manifests/train_dev_cleaned_v1.jsonl"
    )
    freeze = (
        SERVER_RUNTIME / "formal_cleaned_split_v1_1/cleaned_split_freeze_receipt.json"
    )
    return {
        "schema": "prta-cxr.wave046-3066-server-manifest.v1",
        "status": "PASS_WAVE046_3066_SERVER_MANIFEST_FROZEN",
        "created_at": _now(),
        "allocation": 3066,
        "hardware_class": "A800-80GB",
        "run_id": TARGET_ID,
        "source_commit": SOURCE_COMMIT,
        "source_path": str(SERVER_SOURCE),
        "runtime_root": str(SERVER_ROOT),
        "config_path": str(SERVER_ROOT / "configs" / config_path.name),
        "config_file_sha256": sha256_file(config_path),
        "effective_config_sha256": canonical_sha256(config),
        "input_paths": {
            "split_manifest": str(split),
            "cleaned_split_freeze": str(freeze),
            "cache_root": str(cache),
            "cache_manifest": str(cache / "cache_manifest.json"),
            "text_cache": str(cache / "text_cache.pt"),
            "training_store": str(cache / "block8_features.f16.bin"),
            "weights": str(weights),
            "label_quality_audit": str(quality),
        },
        "input_sha256": {
            "split_manifest": (
                "45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89"
            ),
            "cleaned_split_freeze": (
                "aa761c13ae74f29f7c30bc0fecb23db20eab02d79a52778dbbeddec9563cd069"
            ),
            "cache_manifest": (
                "7bec0eb448206ad01c13248f69c611a49e8669ff69a7e7fed1adbf8aaa57d7d5"
            ),
            "text_cache": (
                "1846e3d9d7c12cdb71b37d8e12023d376a5b5b70438cfdecc3f141595c81a3fd"
            ),
            "training_store": (
                "050a4837dbff14f39cab75e9438c3bf7b86776583a06d12b68b1308fca44e540"
            ),
            "weights": (
                "52cc993c5c5ff962bd0c60931874bc001e7e9b41666a385530f4a036294576be"
            ),
            "label_quality_audit": (
                "b6c7d4cc1784deef5e45640d0c0151b68504a51f7f70b5b922ef67eba034b2c9"
            ),
        },
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "no_outcome_selection": True,
    }


def prepare_wave046_3066_amendment_main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the pre-outcome Wave046 B401-S43 handoff to allocation 3066"
    )
    parser.add_argument("--wave-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)

    wave_root = audit_path(args.wave_root, role="wave046_root")
    output_root = args.output_root.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    if output_root.exists():
        raise FileExistsError(f"refusing existing amendment root: {output_root}")
    try:
        output_root.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise AuditContractError("Wave046 amendment runtime must stay outside Git")

    preparation_path = wave_root / "preparation_receipt.json"
    queue_path = wave_root / "run_queue.json"
    config_path = wave_root / "configs" / f"{TARGET_ID}.json"
    if sha256_file(preparation_path) != PREPARATION_SHA256:
        raise AuditContractError("Wave046 preparation receipt drift")
    rows = json.loads(queue_path.read_text(encoding="utf-8"))
    if canonical_sha256(frozen_queue_identity(rows)) != ORIGINAL_QUEUE_SHA256:
        raise AuditContractError("Wave046 frozen queue identity drift")
    _validate_live_queue(rows)
    by_id = {str(row["experiment_id"]): row for row in rows}
    target = by_id[TARGET_ID]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if target.get("config_sha256") != sha256_file(config_path):
        raise AuditContractError("Wave046 target config file hash drift")
    if target.get("effective_config_sha256") != canonical_sha256(config):
        raise AuditContractError("Wave046 target effective config hash drift")

    amended = [dict(row) for row in rows if row["experiment_id"] != TARGET_ID]
    temporary = output_root.with_name(output_root.name + ".preparing")
    if temporary.exists():
        raise FileExistsError(f"refusing stale amendment temp: {temporary}")
    (temporary / "server_package" / "configs").mkdir(parents=True)
    shutil.copy2(
        config_path, temporary / "server_package" / "configs" / config_path.name
    )
    controller_source = repo_root / "scripts/67_wave046_3066_server_worker.py"
    controller_target = temporary / "server_package" / controller_source.name
    shutil.copy2(controller_source, controller_target)
    write_json_atomic(temporary / "original_queue_at_amendment.json", rows)
    write_json_atomic(temporary / "amended_local_queue.json", amended)
    manifest = _server_manifest(config=config, config_path=config_path)
    server_manifest_path = temporary / "server_package" / "server_manifest.json"
    write_json_atomic(server_manifest_path, manifest)
    preparation = {
        "schema": "prta-cxr.wave046-3066-execution-amendment.v1",
        "status": "PASS_WAVE046_3066_AMENDMENT_PREPARED",
        "created_at": _now(),
        "source_commit": SOURCE_COMMIT,
        "original_preparation_receipt_sha256": sha256_file(preparation_path),
        "original_frozen_queue_sha256": ORIGINAL_QUEUE_SHA256,
        "live_queue_file_sha256_before": sha256_file(queue_path),
        "claimed_run_id": TARGET_ID,
        "claimed_config_file_sha256": sha256_file(config_path),
        "claimed_effective_config_sha256": canonical_sha256(config),
        "local_continuation_ids": [str(row["experiment_id"]) for row in amended],
        "active_local_pids": {
            run_id: int(by_id[run_id]["pid"])
            for run_id in ("W046-B401-S17", "W046-B401-S28")
        },
        "server_manifest_file_sha256": sha256_file(server_manifest_path),
        "server_manifest_canonical_sha256": canonical_sha256(manifest),
        "server_controller_sha256": sha256_file(controller_target),
        "source_file_sha256": {
            path: _git_blob_sha(repo_root, SOURCE_COMMIT, path)
            for path in (
                "scripts/07_train.py",
                "scripts/sues_hpc_run_dev_search_arm.sh",
                "src/prta_cxr/training.py",
            )
        },
        "no_outcome_selection": True,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "activation_required": True,
    }
    write_json_atomic(temporary / "preparation_receipt.json", preparation)
    temporary.replace(output_root)

    if sha256_file(queue_path) != preparation["live_queue_file_sha256_before"]:
        raise AuditContractError(
            "Wave046 live queue changed during amendment preparation"
        )
    replace_json_atomic(queue_path, amended)
    activated = json.loads(queue_path.read_text(encoding="utf-8"))
    if [row["experiment_id"] for row in activated] != [
        row["experiment_id"] for row in amended
    ]:
        raise AuditContractError("Wave046 amended queue activation mismatch")
    activation = {
        "schema": "prta-cxr.wave046-3066-amendment-activation.v1",
        "status": "PASS_WAVE046_3066_AMENDMENT_ACTIVATED",
        "created_at": _now(),
        "claimed_run_id": TARGET_ID,
        "local_queue_total": len(activated),
        "local_queue_file_sha256": sha256_file(queue_path),
        "local_queue_canonical_sha256": canonical_sha256(activated),
        "preparation_receipt_sha256": sha256_file(
            output_root / "preparation_receipt.json"
        ),
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    write_json_atomic(output_root / "activation_receipt.json", activation)
    print(json.dumps({"preparation": preparation, "activation": activation}, indent=2))
    return 0
