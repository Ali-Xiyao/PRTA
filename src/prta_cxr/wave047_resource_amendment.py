from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import replace_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.development_selection import _write_queue

EXPECTED_SOURCE = "384ecc19645edaf799da62594ee4294a693754f6"
EXPECTED_PREPARATION = (
    "b0b6e81676b701c35b5a36bf159ff6c22f8463a54501529263c7bb0edd67218b"
)
EXPECTED_MANIFESTS = {
    "3066": "cebed907b74e9fbbd92b1f15a1ffb7ed6f00fca32fd27fc7da75b1a90ecdc13c",
    "9929": "9a38ba216164bff91b8c865cbb21d7474876aae6f2822a7b23f24dee816ad871",
}


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _config_by_seed(preparation: dict[str, object], seed: int) -> dict[str, object]:
    rows = list(preparation["tail8_tila_configs"])
    matches = [row for row in rows if int(row["seed"]) == seed]
    if len(matches) != 1:
        raise ValueError(f"Tail8-TILA seed identity drift: {seed}")
    return dict(matches[0])


def _relocate_queue_rows(
    rows: list[dict[str, Any]], destination: Path
) -> list[dict[str, Any]]:
    relocated = []
    for row in rows:
        value = dict(row)
        config_name = Path(str(value["config_path"])).name
        value["config_path"] = str((destination / "configs" / config_name).resolve())
        relocated.append(value)
    return relocated


def prepare_wave047_resource_amendment_main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the outcome-blind Wave047 four-GPU resource amendment"
    )
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--progress-3066-sha256", required=True)
    parser.add_argument("--progress-9929-sha256", required=True)
    parser.add_argument("--paused-controller-pid", type=int, required=True)
    parser.add_argument("--active-child-pid", type=int, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)

    original_root = args.original_root.resolve()
    output_root = args.output_root.resolve()
    source_snapshot = args.source_snapshot.resolve()
    if output_root.exists():
        raise FileExistsError(f"resource amendment root exists: {output_root}")
    if not (source_snapshot / "scripts/07b_run_development_queue.py").is_file():
        raise FileNotFoundError("frozen scientific source snapshot is incomplete")

    preparation_path = original_root / "preparation_receipt.json"
    if sha256_file(preparation_path) != EXPECTED_PREPARATION:
        raise ValueError("Wave047 preparation hash drift")
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    if preparation.get("source_commit") != EXPECTED_SOURCE:
        raise ValueError("Wave047 scientific source drift")
    for allocation, expected in EXPECTED_MANIFESTS.items():
        path = original_root / f"server_manifest_{allocation}.json"
        if sha256_file(path) != expected:
            raise ValueError(f"Wave047 manifest drift: {allocation}")
    if preparation.get("internal_test_opened") is not False:
        raise ValueError("Wave047 preparation opened Internal-test")
    if int(preparation.get("protected_outcome_read_count", -1)) != 0:
        raise ValueError("Wave047 preparation reports protected reads")

    configs: dict[int, dict[str, object]] = {}
    config_rows: dict[int, dict[str, object]] = {}
    for seed in (17, 28):
        row = _config_by_seed(preparation, seed)
        path = Path(str(row["path"]))
        config = json.loads(path.read_text(encoding="utf-8"))
        if sha256_file(path) != row["file_sha256"]:
            raise ValueError(f"Tail8-TILA config-file drift: seed{seed}")
        if canonical_sha256(config) != row["effective_config_sha256"]:
            raise ValueError(f"Tail8-TILA effective-config drift: seed{seed}")
        configs[seed] = config
        config_rows[seed] = row

    staging = output_root.with_name(f".{output_root.name}.preparing.{os.getpid()}")
    if staging.exists():
        raise FileExistsError(f"resource amendment staging exists: {staging}")
    staging.mkdir(parents=True)
    queue_rows = {
        "local_gpu0": _write_queue(
            staging / "local_gpu0", [configs[17]], stage="wave047_four_gpu_v1"
        ),
        "local_gpu1": _write_queue(
            staging / "local_gpu1", [configs[28]], stage="wave047_four_gpu_v1"
        ),
    }
    for lane, rows in tuple(queue_rows.items()):
        relocated = _relocate_queue_rows(rows, output_root / lane)
        replace_json_atomic(staging / lane / "run_queue.json", relocated)
        queue_rows[lane] = relocated
    receipt = {
        "schema": "prta-cxr.wave047-four-gpu-resource-amendment.v1",
        "status": "PASS_WAVE047_FOUR_GPU_RESOURCE_AMENDMENT_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "scientific_source_commit": EXPECTED_SOURCE,
        "scientific_source_snapshot": str(source_snapshot),
        "original_preparation_sha256": EXPECTED_PREPARATION,
        "original_manifest_sha256": EXPECTED_MANIFESTS,
        "server_progress_sha256_at_freeze": {
            "3066": args.progress_3066_sha256,
            "9929": args.progress_9929_sha256,
        },
        "paused_server_lane": {
            "allocation": 3066,
            "controller_pid": args.paused_controller_pid,
            "active_child_pid": args.active_child_pid,
            "active_run_id": "W047D-V2-S28",
            "pause_semantics": "controller_only_child_continues_to_terminal",
        },
        "resource_assignment": {
            "local_gpu0": ["W047-TILA8-S17"],
            "local_gpu1": ["W047-TILA8-S28"],
            "server_9929": ["W047D-V1-S28", "W047-TILA8-S43"],
            "server_3066_terminal_only": ["W047D-V2-S28"],
        },
        "queue_rows": queue_rows,
        "config_identities": {
            str(seed): {
                "run_id": config_rows[seed]["run_id"],
                "file_sha256": config_rows[seed]["file_sha256"],
                "effective_config_sha256": config_rows[seed]["effective_config_sha256"],
            }
            for seed in (17, 28)
        },
        "reason": "newly idle local GPUs; no outcome or metric was inspected",
        "scientific_config_changed": False,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
        "training_started": False,
    }
    _write_new_json(staging / "resource_amendment_receipt.json", receipt)
    staging.replace(output_root)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def launch_wave047_local_lane_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Launch one frozen local Wave047 Tail8-TILA lane"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--lane", choices=("local_gpu0", "local_gpu1"), required=True)
    parser.add_argument("--device-index", type=int, choices=(0, 1), required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)

    root = args.root.resolve()
    runtime = args.runtime_root.resolve()
    receipt_path = root / "resource_amendment_receipt.json"
    amendment = json.loads(receipt_path.read_text(encoding="utf-8"))
    if amendment.get("status") != ("PASS_WAVE047_FOUR_GPU_RESOURCE_AMENDMENT_FROZEN"):
        raise ValueError("Wave047 resource amendment is not frozen")
    if amendment.get("scientific_source_commit") != EXPECTED_SOURCE:
        raise ValueError("Wave047 resource amendment source drift")
    expected_lane = f"local_gpu{args.device_index}"
    if args.lane != expected_lane:
        raise ValueError("Wave047 local lane/device mismatch")

    lane_root = root / args.lane
    queue_path = lane_root / "run_queue.json"
    rows = json.loads(queue_path.read_text(encoding="utf-8"))
    if len(rows) != 1 or rows[0].get("status") != "PLANNED":
        raise ValueError("Wave047 local lane is not one unstarted frozen row")
    row = dict(rows[0])
    config_path = Path(str(row["config_path"]))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if sha256_file(config_path) != row["config_sha256"]:
        raise ValueError("Wave047 local config-file hash drift")
    if canonical_sha256(config) != row["effective_config_sha256"]:
        raise ValueError("Wave047 local effective-config hash drift")

    source = Path(str(amendment["scientific_source_snapshot"]))
    split_root = runtime / "formal_cleaned_split_v1_1"
    cache = (
        runtime
        / "formal_program_v1/cache/full_repartition_v1_block4_tail8_local_wave031_v1"
    )
    paths = {
        "split_manifest": split_root / "manifests/train_dev_cleaned_v1.jsonl",
        "cleaned_split_freeze": split_root / "cleaned_split_freeze_receipt.json",
        "cache_manifest": cache / "cache_manifest.json",
        "text_cache": cache / "text_cache.pt",
        "weights": Path("H:/xiyao/model/biomedclip/open_clip_pytorch_model.bin"),
        "quality_audit": (
            runtime / "formal_program_v1/receipts/human_silver_accuracy_audit.json"
        ),
    }
    expected_hashes = {
        "split_manifest": (
            "45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89"
        ),
        "cleaned_split_freeze": (
            "aa761c13ae74f29f7c30bc0fecb23db20eab02d79a52778dbbeddec9563cd069"
        ),
        "cache_manifest": (
            "c541ec8c1eebdab45d6cb1d7dea2bfea388d12f78cc52f692aea3b04c6c1ac81"
        ),
        "text_cache": (
            "1846e3d9d7c12cdb71b37d8e12023d376a5b5b70438cfdecc3f141595c81a3fd"
        ),
        "weights": "52cc993c5c5ff962bd0c60931874bc001e7e9b41666a385530f4a036294576be",
        "quality_audit": (
            "b6c7d4cc1784deef5e45640d0c0151b68504a51f7f70b5b922ef67eba034b2c9"
        ),
    }
    for role, path in paths.items():
        if sha256_file(path) != expected_hashes[role]:
            raise ValueError(f"Wave047 local input hash drift: {role}")

    run_id = str(row["experiment_id"])
    output = lane_root / "runs" / run_id
    log_root = lane_root / "logs"
    stdout_path = log_root / f"{run_id}.stdout.log"
    stderr_path = log_root / f"{run_id}.stderr.log"
    launch_receipt_path = lane_root / "local_launch_receipt.json"
    if output.exists() or stdout_path.exists() or stderr_path.exists():
        raise FileExistsError("Wave047 local immutable output/log namespace exists")
    log_root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(source / "scripts/07_train.py"),
        "--mode",
        "formal",
        "--formal",
        "--config",
        str(config_path),
        "--split-manifest",
        str(paths["split_manifest"]),
        "--cleaned-split-freeze",
        str(paths["cleaned_split_freeze"]),
        "--cleaned-split-platform-root",
        str(split_root),
        "--cache-root",
        str(cache),
        "--text-cache",
        str(paths["text_cache"]),
        "--weights",
        str(paths["weights"]),
        "--label-quality-audit",
        str(paths["quality_audit"]),
        "--run-registry",
        str(lane_root / "run_registry.jsonl"),
        "--owner",
        "Codex Wave047 four-GPU resource amendment",
        "--device",
        f"cuda:{args.device_index}",
        "--output",
        str(output),
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "PRTA_CXR_ALLOW_FORMAL": "I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN",
            "PRTA_CXR_SOURCE_COMMIT": EXPECTED_SOURCE,
            "PYTHONUNBUFFERED": "1",
        }
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with stdout_path.open("xb") as stdout_handle:
        with stderr_path.open("xb") as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=source,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=creationflags,
            )
    row.update(
        {
            "status": "RUNNING",
            "pid": process.pid,
            "device": f"cuda:{args.device_index}",
            "output_path": str(output),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "started_at": datetime.now(UTC).isoformat(),
        }
    )
    replace_json_atomic(queue_path, [row])
    launch_receipt = {
        "schema": "prta-cxr.wave047-local-lane-launch.v1",
        "status": "PASS_WAVE047_LOCAL_LANE_LAUNCHED",
        "created_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "lane": args.lane,
        "device": f"cuda:{args.device_index}",
        "pid": process.pid,
        "scientific_source_commit": EXPECTED_SOURCE,
        "config_file_sha256": row["config_sha256"],
        "effective_config_sha256": row["effective_config_sha256"],
        "input_sha256": expected_hashes,
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(launch_receipt_path, launch_receipt)
    print(json.dumps(launch_receipt, indent=2, sort_keys=True))
    return 0
