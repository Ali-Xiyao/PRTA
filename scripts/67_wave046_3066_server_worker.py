from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")


def replace_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    os.replace(temporary, path)


def verify_manifest(root: Path, expected_sha: str) -> dict[str, Any]:
    manifest_path = root / "server_manifest.json"
    if sha256_file(manifest_path) != expected_sha:
        raise RuntimeError("server manifest file hash drift")
    manifest = read_json(manifest_path)
    if manifest.get("status") != "PASS_WAVE046_3066_SERVER_MANIFEST_FROZEN":
        raise RuntimeError("server manifest status drift")
    if int(manifest.get("allocation", -1)) != 3066:
        raise RuntimeError("server allocation drift")
    if manifest.get("run_id") != "W046-B401-S17":
        raise RuntimeError("server run identity drift")
    if manifest.get("source_commit") != ("62235ff46fb26e4ccf05e3c9073188a84ca39119"):
        raise RuntimeError("server source commit drift")
    if manifest.get("protected_outcome_read_count") != 0:
        raise RuntimeError("protected read count is not zero")
    if manifest.get("internal_test_opened") is not False:
        raise RuntimeError("Internal-test is not closed")
    if manifest.get("gold_opened") is not False:
        raise RuntimeError("Gold is not closed")
    return manifest


def verify_inputs(root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    paths = {key: Path(value) for key, value in manifest["input_paths"].items()}
    expected = dict(manifest["input_sha256"])
    observed: dict[str, str] = {}
    for role in (
        "split_manifest",
        "cleaned_split_freeze",
        "cache_manifest",
        "text_cache",
        "weights",
        "label_quality_audit",
    ):
        observed[role] = sha256_file(paths[role])
        if observed[role] != expected[role]:
            raise RuntimeError(f"server input hash drift: {role}")
    cache_manifest = read_json(paths["cache_manifest"])
    store = paths["training_store"]
    if not store.is_file():
        raise FileNotFoundError(f"training store missing: {store}")
    observed["training_store"] = str(
        cache_manifest.get("training_store", {}).get("file_sha256")
    )
    if observed["training_store"] != expected["training_store"]:
        raise RuntimeError("server training-store identity drift")
    encoded = str(cache_manifest.get("encoder", {}).get("weights_sha256"))
    if encoded != expected["weights"]:
        raise RuntimeError("server cache weights identity drift")

    source = Path(manifest["source_path"])
    for relative in (
        "scripts/07_train.py",
        "scripts/sues_hpc_run_dev_search_arm.sh",
        "src/prta_cxr/training/engine.py",
    ):
        if not (source / relative).is_file():
            raise FileNotFoundError(f"source snapshot file missing: {relative}")
    config = Path(manifest["config_path"])
    if sha256_file(config) != manifest["config_file_sha256"]:
        raise RuntimeError("server config file hash drift")
    if canonical_sha256(read_json(config)) != manifest["effective_config_sha256"]:
        raise RuntimeError("server effective config hash drift")
    return observed


def prepare(root: Path, expected_manifest_sha: str) -> None:
    manifest = verify_manifest(root, expected_manifest_sha)
    preparation_path = root / "preparation_receipt.json"
    if preparation_path.exists():
        raise FileExistsError("server preparation receipt already exists")
    observed = verify_inputs(root, manifest)
    receipt = {
        "schema": "prta-cxr.wave046-3066-server-preparation.v1",
        "status": "PASS_WAVE046_3066_SERVER_PREPARED",
        "created_at": now(),
        "run_id": manifest["run_id"],
        "allocation": 3066,
        "hardware_class": manifest["hardware_class"],
        "source_commit": manifest["source_commit"],
        "server_manifest_sha256": expected_manifest_sha,
        "config_file_sha256": manifest["config_file_sha256"],
        "effective_config_sha256": manifest["effective_config_sha256"],
        "observed_input_sha256": observed,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "training_started": False,
    }
    write_new_json(preparation_path, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))


def verify_terminal(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    run_id = str(manifest["run_id"])
    receipt_path = root / "runs" / run_id / "training_receipt.json"
    receipt = read_json(receipt_path)
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise RuntimeError("server training receipt is not terminal PASS")
    if receipt.get("internal_test_opened") is not False:
        raise RuntimeError("server training opened Internal-test")
    if receipt.get("protected_outcomes_opened") is not False:
        raise RuntimeError("server training opened a protected outcome")
    if receipt.get("config_sha256") != manifest["effective_config_sha256"]:
        raise RuntimeError("server terminal config identity drift")
    expected_hashes = {
        "split_manifest": manifest["input_sha256"]["split_manifest"],
        "text_cache": manifest["input_sha256"]["text_cache"],
        "weights": manifest["input_sha256"]["weights"],
        "cache_manifest": manifest["input_sha256"]["cache_manifest"],
        "label_quality_audit": manifest["input_sha256"]["label_quality_audit"],
        "cleaned_split_freeze": manifest["input_sha256"]["cleaned_split_freeze"],
    }
    if receipt.get("input_hashes") != expected_hashes:
        raise RuntimeError("server terminal input identity drift")
    return {
        "run_id": run_id,
        "training_receipt_sha256": sha256_file(receipt_path),
        "config_file_sha256": manifest["config_file_sha256"],
        "effective_config_sha256": manifest["effective_config_sha256"],
        "zero_protected_reads": True,
    }


def run(root: Path, expected_manifest_sha: str) -> None:
    manifest = verify_manifest(root, expected_manifest_sha)
    preparation_path = root / "preparation_receipt.json"
    preparation = read_json(preparation_path)
    if preparation.get("status") != "PASS_WAVE046_3066_SERVER_PREPARED":
        raise RuntimeError("server preparation status drift")
    for path in (
        root / "completion_receipt.json",
        root / "failure_receipt.json",
        root / "worker_progress.json",
        root / "runs" / str(manifest["run_id"]),
    ):
        if path.exists():
            raise FileExistsError(f"server amendment namespace already started: {path}")
    verify_inputs(root, manifest)
    progress = {
        "schema": "prta-cxr.wave046-3066-worker-progress.v1",
        "status": "RUNNING_FROZEN_SERVER_CELL",
        "updated_at": now(),
        "run_id": manifest["run_id"],
        "allocation": 3066,
        "hardware_class": manifest["hardware_class"],
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    write_new_json(root / "worker_progress.json", progress)
    source = Path(manifest["source_path"])
    config = Path(manifest["config_path"])
    output = root / "runs" / str(manifest["run_id"])
    registry = root / "run_registry.jsonl"
    log = root / "launcher.log"
    command = [
        "srun",
        "--jobid=3066",
        "--overlap",
        "--ntasks=1",
        f"--chdir={source}",
        "env",
        f"PRTA_CXR_SOURCE_COMMIT={manifest['source_commit']}",
        f"PRTA_CXR_PROJECT_ROOT={source}",
        f"PRTA_CXR_RUNTIME_ROOT={Path(manifest['input_paths']['split_manifest']).parents[2]}",
        f"PRTA_CXR_CACHE_ROOT={manifest['input_paths']['cache_root']}",
        "bash",
        str(source / "scripts/sues_hpc_run_dev_search_arm.sh"),
        str(config),
        str(manifest["config_file_sha256"]),
        str(output),
        str(registry),
        "3066",
    ]
    with log.open("xb") as stream:
        returncode = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode
    if returncode:
        failure = {
            "schema": "prta-cxr.wave046-3066-worker-failure.v1",
            "status": "WAVE046_3066_WORKER_FAILED_HOLD",
            "created_at": now(),
            "run_id": manifest["run_id"],
            "returncode": returncode,
            "protected_outcome_read_count": 0,
            "internal_test_opened": False,
            "gold_opened": False,
        }
        write_new_json(root / "failure_receipt.json", failure)
        replace_json(root / "worker_progress.json", failure)
        raise RuntimeError("Wave046 3066 worker failed")
    terminal = verify_terminal(root, manifest)
    completion = {
        "schema": "prta-cxr.wave046-3066-worker-completion.v1",
        "status": "PASS_WAVE046_3066_WORKER_COMPLETE",
        "created_at": now(),
        "allocation": 3066,
        "hardware_class": manifest["hardware_class"],
        "completed": [terminal],
        "source_commit": manifest["source_commit"],
        "server_manifest_sha256": expected_manifest_sha,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    write_new_json(root / "completion_receipt.json", completion)
    replace_json(
        root / "worker_progress.json",
        {
            **completion,
            "updated_at": now(),
            "current_run_id": None,
        },
    )


def status(root: Path, expected_manifest_sha: str) -> None:
    verify_manifest(root, expected_manifest_sha)
    progress_path = root / "worker_progress.json"
    print(
        json.dumps(
            {
                "progress": read_json(progress_path)
                if progress_path.exists()
                else None,
                "completion_exists": (root / "completion_receipt.json").exists(),
                "failure_exists": (root / "failure_receipt.json").exists(),
            },
            indent=2,
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run", "status"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == "prepare":
        prepare(root, args.manifest_sha256)
    elif args.mode == "run":
        run(root, args.manifest_sha256)
    else:
        status(root, args.manifest_sha256)


if __name__ == "__main__":
    main()
