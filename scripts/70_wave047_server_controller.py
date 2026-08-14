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
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


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


def verify_manifest(root: Path, expected_sha: str, allocation: int) -> dict[str, Any]:
    path = root / f"server_manifest_{allocation}.json"
    if sha256_file(path) != expected_sha:
        raise RuntimeError("Wave047 server manifest hash drift")
    manifest = read_json(path)
    if manifest.get("status") != "PASS_WAVE047_SERVER_QUEUE_FROZEN":
        raise RuntimeError("Wave047 server manifest status drift")
    if int(manifest.get("allocation", -1)) != allocation:
        raise RuntimeError("Wave047 allocation drift")
    if manifest.get("protected_outcome_read_count") != 0:
        raise RuntimeError("Wave047 manifest protected-read drift")
    if manifest.get("internal_test_opened") is not False:
        raise RuntimeError("Wave047 manifest opened Internal-test")
    if manifest.get("gold_opened") is not False:
        raise RuntimeError("Wave047 manifest opened Gold")
    return manifest


def verify_inputs(manifest: dict[str, Any]) -> dict[str, str]:
    paths = {key: Path(value) for key, value in manifest["global_input_paths"].items()}
    expected = dict(manifest["global_input_sha256"])
    observed = {}
    for role in (
        "split_manifest",
        "cleaned_split_freeze",
        "cache_manifest",
        "text_cache",
        "weights",
        "label_quality_audit",
        "matched_hard_prior_map",
    ):
        observed[role] = sha256_file(paths[role])
        if observed[role] != expected[role]:
            raise RuntimeError(f"Wave047 global input hash drift: {role}")
    source = Path(manifest["source_path"])
    for relative, expected_sha in manifest["source_files"].items():
        if sha256_file(source / relative) != expected_sha:
            raise RuntimeError(f"Wave047 source file hash drift: {relative}")
    for job in manifest["jobs"]:
        if job["kind"] == "candidate_prior_diagnostic":
            checkpoint = Path(job["checkpoint_path"])
            receipt = Path(job["training_receipt_path"])
            if sha256_file(checkpoint) != job["checkpoint_sha256"]:
                raise RuntimeError(f"Wave047 checkpoint hash drift: {job['run_id']}")
            if sha256_file(receipt) != job["training_receipt_sha256"]:
                raise RuntimeError(
                    f"Wave047 training receipt hash drift: {job['run_id']}"
                )
            value = read_json(receipt)
            if value.get("status") != "PASS_TRAINING_FINISHED":
                raise RuntimeError(f"Wave047 source run nonterminal: {job['run_id']}")
            if value.get("config_sha256") != job["effective_config_sha256"]:
                raise RuntimeError(f"Wave047 source config drift: {job['run_id']}")
            if value.get("internal_test_opened") is not False:
                raise RuntimeError(
                    f"Wave047 source opened Internal-test: {job['run_id']}"
                )
            if value.get("protected_outcomes_opened") is not False:
                raise RuntimeError(
                    f"Wave047 source opened protected data: {job['run_id']}"
                )
        elif job["kind"] == "tail8_tila_training":
            config = Path(job["config_path"])
            if sha256_file(config) != job["config_file_sha256"]:
                raise RuntimeError(f"Wave047 TILA config hash drift: {job['run_id']}")
            if canonical_sha256(read_json(config)) != job["effective_config_sha256"]:
                raise RuntimeError(
                    f"Wave047 TILA effective config drift: {job['run_id']}"
                )
        else:
            raise RuntimeError(f"unknown Wave047 job kind: {job['kind']}")
    return observed


def prepare(root: Path, manifest_sha: str, allocation: int) -> None:
    manifest = verify_manifest(root, manifest_sha, allocation)
    observed = verify_inputs(manifest)
    receipt = {
        "schema": "prta-cxr.wave047-server-preparation.v1",
        "status": "PASS_WAVE047_SERVER_QUEUE_PREPARED",
        "created_at": now(),
        "allocation": allocation,
        "hardware_class": manifest["hardware_class"],
        "source_commit": manifest["source_commit"],
        "manifest_sha256": manifest_sha,
        "queue": [job["run_id"] for job in manifest["jobs"]],
        "observed_input_sha256": observed,
        "training_started": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_new_json(root / f"server_preparation_{allocation}.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))


def _diagnostic_command(
    manifest: dict[str, Any], root: Path, job: dict[str, Any], allocation: int
) -> list[str]:
    paths = manifest["global_input_paths"]
    source = Path(manifest["source_path"])
    python = Path.home() / "miniforge3/envs/prta-cxr311/bin/python"
    return [
        "srun",
        f"--jobid={allocation}",
        "--overlap",
        "--ntasks=1",
        f"--chdir={source}",
        "env",
        f"PRTA_CXR_SOURCE_COMMIT={manifest['source_commit']}",
        "PRTA_CXR_ALLOW_FORMAL=I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN",
        "PYTHONUNBUFFERED=1",
        str(python),
        str(source / "scripts/45_evaluate_prta_v2_mechanisms.py"),
        "--formal",
        "--diagnostic-scope",
        "candidate_v0_v2",
        "--checkpoint",
        job["checkpoint_path"],
        "--training-receipt",
        job["training_receipt_path"],
        "--split-manifest",
        paths["split_manifest"],
        "--cleaned-split-freeze",
        paths["cleaned_split_freeze"],
        "--cleaned-split-platform-root",
        paths["cleaned_split_platform_root"],
        "--cache-root",
        paths["cache_root"],
        "--text-cache",
        paths["text_cache"],
        "--matched-hard-prior-map",
        paths["matched_hard_prior_map"],
        "--weights",
        paths["weights"],
        "--label-quality-audit",
        paths["label_quality_audit"],
        "--device",
        "cuda:0",
        "--output",
        str(root / "runs" / job["run_id"]),
    ]


def _training_command(
    manifest: dict[str, Any], root: Path, job: dict[str, Any], allocation: int
) -> list[str]:
    paths = manifest["global_input_paths"]
    source = Path(manifest["source_path"])
    return [
        "srun",
        f"--jobid={allocation}",
        "--overlap",
        "--ntasks=1",
        f"--chdir={source}",
        "env",
        f"PRTA_CXR_SOURCE_COMMIT={manifest['source_commit']}",
        f"PRTA_CXR_PROJECT_ROOT={source}",
        f"PRTA_CXR_RUNTIME_ROOT={paths['runtime_root']}",
        f"PRTA_CXR_CACHE_ROOT={paths['cache_root']}",
        "bash",
        str(source / "scripts/sues_hpc_run_dev_search_arm.sh"),
        job["config_path"],
        job["config_file_sha256"],
        str(root / "runs" / job["run_id"]),
        str(root / f"run_registry_{allocation}.jsonl"),
        str(allocation),
    ]


def verify_terminal(root: Path, job: dict[str, Any]) -> dict[str, Any]:
    run = root / "runs" / job["run_id"]
    if job["kind"] == "candidate_prior_diagnostic":
        receipt_path = run / "candidate_prior_diagnostic_receipt.json"
        receipt = read_json(receipt_path)
        if receipt.get("status") != (
            "PASS_WAVE047_CANDIDATE_TRAIN_DEV_PRIOR_DIAGNOSTIC"
        ):
            raise RuntimeError(f"Wave047 diagnostic nonterminal: {job['run_id']}")
        if receipt.get("checkpoint_sha256") != job["checkpoint_sha256"]:
            raise RuntimeError(f"Wave047 diagnostic checkpoint drift: {job['run_id']}")
        for block in receipt.get("prediction_blocks", {}).values():
            path = run / str(block["path"])
            if sha256_file(path) != block["sha256"]:
                raise RuntimeError(f"Wave047 prediction hash drift: {job['run_id']}")
    else:
        receipt_path = run / "training_receipt.json"
        receipt = read_json(receipt_path)
        if receipt.get("status") != "PASS_TRAINING_FINISHED":
            raise RuntimeError(f"Wave047 TILA nonterminal: {job['run_id']}")
        if receipt.get("config_sha256") != job["effective_config_sha256"]:
            raise RuntimeError(f"Wave047 TILA config drift: {job['run_id']}")
    if receipt.get("internal_test_opened") is not False:
        raise RuntimeError(f"Wave047 job opened Internal-test: {job['run_id']}")
    protected = receipt.get(
        "protected_outcome_read_count",
        0 if receipt.get("protected_outcomes_opened") is False else -1,
    )
    if protected != 0:
        raise RuntimeError(f"Wave047 job protected-read drift: {job['run_id']}")
    return {
        "run_id": job["run_id"],
        "kind": job["kind"],
        "receipt_sha256": sha256_file(receipt_path),
        "zero_protected_reads": True,
    }


def run(root: Path, manifest_sha: str, allocation: int) -> None:
    manifest = verify_manifest(root, manifest_sha, allocation)
    preparation = read_json(root / f"server_preparation_{allocation}.json")
    if preparation.get("status") != "PASS_WAVE047_SERVER_QUEUE_PREPARED":
        raise RuntimeError("Wave047 server preparation status drift")
    for path in (
        root / f"server_completion_{allocation}.json",
        root / f"server_failure_{allocation}.json",
        root / f"server_progress_{allocation}.json",
    ):
        if path.exists():
            raise FileExistsError(f"Wave047 server lane already started: {path}")
    verify_inputs(manifest)
    completed = []
    progress_path = root / f"server_progress_{allocation}.json"
    for index, job in enumerate(manifest["jobs"]):
        progress = {
            "schema": "prta-cxr.wave047-server-progress.v1",
            "status": "RUNNING_FROZEN_WAVE047_QUEUE",
            "updated_at": now(),
            "allocation": allocation,
            "current_run_id": job["run_id"],
            "current_kind": job["kind"],
            "completed": completed,
            "remaining": len(manifest["jobs"]) - index,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        }
        if progress_path.exists():
            replace_json(progress_path, progress)
        else:
            write_new_json(progress_path, progress)
        output = root / "runs" / job["run_id"]
        log = root / "logs" / f"{job['run_id']}.launcher.log"
        if output.exists() or log.exists():
            raise FileExistsError(f"Wave047 job namespace exists: {job['run_id']}")
        command = (
            _diagnostic_command(manifest, root, job, allocation)
            if job["kind"] == "candidate_prior_diagnostic"
            else _training_command(manifest, root, job, allocation)
        )
        log.parent.mkdir(parents=True, exist_ok=True)
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
                "schema": "prta-cxr.wave047-server-failure.v1",
                "status": "WAVE047_SERVER_QUEUE_FAILED_HOLD",
                "created_at": now(),
                "allocation": allocation,
                "run_id": job["run_id"],
                "kind": job["kind"],
                "returncode": returncode,
                "completed": completed,
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            }
            write_new_json(root / f"server_failure_{allocation}.json", failure)
            replace_json(progress_path, failure)
            raise RuntimeError("Wave047 server queue failed")
        completed.append(verify_terminal(root, job))
    completion = {
        "schema": "prta-cxr.wave047-server-completion.v1",
        "status": "PASS_WAVE047_SERVER_QUEUE_COMPLETE",
        "created_at": now(),
        "allocation": allocation,
        "hardware_class": manifest["hardware_class"],
        "source_commit": manifest["source_commit"],
        "manifest_sha256": manifest_sha,
        "completed": completed,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_new_json(root / f"server_completion_{allocation}.json", completion)
    replace_json(
        progress_path,
        {**completion, "updated_at": now(), "current_run_id": None},
    )


def status(root: Path, manifest_sha: str, allocation: int) -> None:
    manifest = verify_manifest(root, manifest_sha, allocation)
    progress = root / f"server_progress_{allocation}.json"
    print(
        json.dumps(
            {
                "allocation": allocation,
                "queue": [job["run_id"] for job in manifest["jobs"]],
                "progress": read_json(progress) if progress.exists() else None,
                "completion_exists": (
                    root / f"server_completion_{allocation}.json"
                ).exists(),
                "failure_exists": (root / f"server_failure_{allocation}.json").exists(),
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
    parser.add_argument("--allocation", type=int, choices=(3066, 9929), required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == "prepare":
        prepare(root, args.manifest_sha256, args.allocation)
    elif args.mode == "run":
        run(root, args.manifest_sha256, args.allocation)
    else:
        status(root, args.manifest_sha256, args.allocation)


if __name__ == "__main__":
    main()
