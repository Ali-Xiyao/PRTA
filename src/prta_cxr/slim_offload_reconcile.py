from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.phase16_queue import LANES
from prta_cxr.slim_finalize import (
    _effective_training_config_sha256,
    _read_jsonl,
)
from prta_cxr.slim_matrix import SEEDS, SLIM_ARMS

SEED43_EXPERIMENTS = tuple(f"{arm}-S43" for arm in SLIM_ARMS)
REQUIRED_INPUT_HASHES = (
    "cache_manifest",
    "cleaned_split_freeze",
    "label_quality_audit",
    "text_cache",
    "weights",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _resolve_within(root: Path, relative: str, *, label: str) -> Path:
    value = Path(relative)
    if value.is_absolute():
        raise ValueError(f"{label} must be relative to the import root")
    base = root.resolve()
    result = (base / value).resolve()
    try:
        result.relative_to(base)
    except ValueError as error:
        raise ValueError(f"{label} escapes the import root") from error
    return result


def _closed(value: Mapping[str, Any], *, label: str) -> None:
    for key in ("internal_test_opened", "gold_opened", "external_opened"):
        if key in value and value.get(key) is not False:
            raise ValueError(f"{label} reports forbidden access: {key}")
    protected = value.get(
        "protected_outcome_read_count",
        0 if value.get("protected_outcomes_opened") is False else -1,
    )
    if int(protected) != 0:
        raise ValueError(f"{label} reports protected reads")


def _require_training_receipt(
    receipt: Mapping[str, Any],
    *,
    experiment_id: str,
    effective_config_sha256: str,
    preparation: Mapping[str, Any],
) -> None:
    if receipt.get("schema") != "prta-cxr.training-receipt.v1":
        raise ValueError(f"unsupported training receipt: {experiment_id}")
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError(f"training receipt is not PASS: {experiment_id}")
    if receipt.get("config_sha256") != effective_config_sha256:
        raise ValueError(f"training receipt config drift: {experiment_id}")
    inputs = dict(receipt.get("input_hashes", {}))
    if inputs.get("split_manifest") != preparation["derived_manifest_sha256"]:
        raise ValueError(f"training selection drift: {experiment_id}")
    for role in REQUIRED_INPUT_HASHES:
        if inputs.get(role) != preparation["input_sha256"][role]:
            raise ValueError(f"training input drift ({role}): {experiment_id}")
    _closed(receipt, label=f"training receipt {experiment_id}")


def _reconciled_state(
    *,
    experiment_id: str,
    lane: str,
    receipt_path: Path,
    source_commit: str,
    origin: str,
    checkpoint_sha256: str | None = None,
) -> dict[str, Any]:
    checks = [
        {
            "path": str(receipt_path),
            "exists": True,
            "sha256": sha256_file(receipt_path),
        }
    ]
    if checkpoint_sha256 is not None:
        checks.append(
            {
                "path": "LOCAL_EVIDENCE_ARCHIVE",
                "exists": True,
                "sha256": checkpoint_sha256,
            }
        )
    return {
        "schema": "prta-cxr.phase16-job-state.v1",
        "status": "PASS",
        "job_id": f"train-{experiment_id}",
        "group": "slim_matrix",
        "lane": lane,
        "completed_at": datetime.now(UTC).isoformat(),
        "source_commit": source_commit,
        "reconciled": True,
        "reconciliation_origin": origin,
        "output_checks": checks,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }


def reconcile_slim_offload_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile preregistered local Slim offload receipts"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--import-root", type=Path, required=True)
    parser.add_argument("--import-manifest", type=Path, required=True)
    parser.add_argument("--controller-retirement-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite reconciliation: {args.output}")

    preparation_path = args.root / "preparation_receipt.json"
    preparation = _read_json(preparation_path)
    manifest = _read_json(args.import_manifest)
    retirement = _read_json(args.controller_retirement_receipt)
    if manifest.get("schema") != "prta-cxr.slim-seed43-import-manifest.v1":
        raise ValueError("unsupported Seed43 import manifest")
    if manifest.get("status") != "PASS_LOCAL_SEED43_EXPORT_FROZEN":
        raise ValueError("Seed43 import manifest is not PASS")
    if retirement.get("status") != "PASS_SLIM_CONTROLLERS_RETIRED":
        raise ValueError("Slim controller retirement is not PASS")
    if retirement.get("phase16_parents_remain_stopped") is not True:
        raise ValueError("Phase16 parents are not confirmed stopped")
    if sha256_file(preparation_path) != manifest["server_preparation_sha256"]:
        raise ValueError("server Slim preparation drift")
    _closed(preparation, label="server Slim preparation")
    _closed(manifest, label="Seed43 import manifest")
    _closed(retirement, label="Slim controller retirement")

    local_preparation_path = _resolve_within(
        args.import_root,
        str(manifest["local_preparation_path"]),
        label="local preparation path",
    )
    if sha256_file(local_preparation_path) != manifest["local_preparation_sha256"]:
        raise ValueError("local Slim preparation receipt drift")
    local_preparation = _read_json(local_preparation_path)
    for key in ("config_hashes", "derived_manifest_sha256", "input_sha256"):
        if local_preparation.get(key) != preparation.get(key):
            raise ValueError(f"local/server Slim preparation mismatch: {key}")
    source_commit = str(preparation["source_commit"])
    if local_preparation.get("source_commit") != source_commit:
        raise ValueError("local/server source commit mismatch")

    selection_path = args.root / "selection" / "train_only_selection_v1.jsonl"
    if sha256_file(selection_path) != preparation["derived_manifest_sha256"]:
        raise ValueError("server Slim selection manifest drift")
    selection_rows = _read_jsonl(selection_path)
    imported_receipts: dict[str, tuple[Path, dict[str, Any], str | None]] = {}
    cells = dict(manifest.get("cells", {}))
    if set(cells) != set(SEED43_EXPERIMENTS):
        raise ValueError("Seed43 import manifest must contain exactly four cells")
    for experiment_id, record_value in sorted(cells.items()):
        record = dict(record_value)
        receipt_path = _resolve_within(
            args.import_root,
            str(record["receipt_path"]),
            label=f"local receipt path {experiment_id}",
        )
        if sha256_file(receipt_path) != record["receipt_sha256"]:
            raise ValueError(f"local receipt bytes drift: {experiment_id}")
        state_path = _resolve_within(
            args.import_root,
            str(record["state_path"]),
            label=f"local state path {experiment_id}",
        )
        local_state = _read_json(state_path)
        if local_state.get("status") != "PASS":
            raise ValueError(f"local offload state is not PASS: {experiment_id}")
        if local_state.get("job_id") != f"train-{experiment_id}":
            raise ValueError(f"local offload state identity drift: {experiment_id}")
        config_path = args.root / "configs" / f"{experiment_id}.json"
        config = _read_json(config_path)
        if canonical_sha256(config) != preparation["config_hashes"][config_path.name]:
            raise ValueError(f"server source config drift: {experiment_id}")
        effective_sha256 = _effective_training_config_sha256(config, selection_rows)
        if record.get("effective_config_sha256") != effective_sha256:
            raise ValueError(f"import manifest config drift: {experiment_id}")
        receipt = _read_json(receipt_path)
        _require_training_receipt(
            receipt,
            experiment_id=experiment_id,
            effective_config_sha256=effective_sha256,
            preparation=preparation,
        )
        receipt_checks = [
            row
            for row in local_state.get("output_checks", [])
            if str(row.get("path", "")).endswith("training_receipt.json")
        ]
        if len(receipt_checks) != 1 or receipt_checks[0].get(
            "sha256"
        ) != sha256_file(receipt_path):
            raise ValueError(f"local state/receipt drift: {experiment_id}")
        checkpoint_checks = [
            row
            for row in local_state.get("output_checks", [])
            if str(row.get("path", "")).endswith("best.pt")
        ]
        checkpoint_sha256 = (
            str(checkpoint_checks[0]["sha256"])
            if len(checkpoint_checks) == 1
            else None
        )
        imported_receipts[experiment_id] = (
            receipt_path,
            receipt,
            checkpoint_sha256,
        )

    local_lanes = dict(manifest.get("local_lane_completions", {}))
    if set(local_lanes) != set(LANES):
        raise ValueError("local offload must contain both lane completions")
    local_completed_jobs = set()
    for lane, record_value in sorted(local_lanes.items()):
        record = dict(record_value)
        path = _resolve_within(
            args.import_root,
            str(record["path"]),
            label=f"local lane completion path {lane}",
        )
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"local lane completion drift: {lane}")
        completion = _read_json(path)
        completed = {row["job_id"] for row in completion.get("completed", [])}
        if completion.get("status") != "PASS" or completion.get("failures") != []:
            raise ValueError(f"local lane is not PASS: {lane}")
        if completed != set(record["expected_job_ids"]):
            raise ValueError(f"local lane membership drift: {lane}")
        if local_completed_jobs.intersection(completed):
            raise ValueError("local offload job appears in both lanes")
        local_completed_jobs.update(completed)
    if local_completed_jobs != {
        f"train-{experiment_id}" for experiment_id in SEED43_EXPERIMENTS
    }:
        raise ValueError("local offload lane coverage is not the four Seed43 cells")

    validated_queues = {}
    queued_train_jobs = set()
    map_count = 0
    for lane in LANES:
        queue_path = args.root / "queue" / f"{lane}.json"
        if sha256_file(queue_path) != preparation["queue_hashes"][queue_path.name]:
            raise ValueError(f"server queue drift: {lane}")
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        if not isinstance(queue, list) or not queue:
            raise ValueError(f"server queue is empty or malformed: {lane}")
        if (args.root / "results" / lane / "completion.json").exists():
            raise FileExistsError(f"server lane completion already exists: {lane}")
        for job in queue:
            job_id = str(job["job_id"])
            if job_id == "map-slim-train-only":
                map_count += 1
                state = _read_json(args.root / "shared_state" / f"{job_id}.json")
                if state.get("status") != "PASS":
                    raise ValueError("Slim map state is not PASS")
                continue
            if not job_id.startswith("train-") or job_id in queued_train_jobs:
                raise ValueError(f"server queue job identity drift: {job_id}")
            queued_train_jobs.add(job_id)
            experiment_id = job_id.removeprefix("train-")
            config_path = args.root / "configs" / f"{experiment_id}.json"
            if (
                sha256_file(config_path)
                != preparation["config_file_hashes"][config_path.name]
            ):
                raise ValueError(f"server config file drift: {experiment_id}")
            config = _read_json(config_path)
            if canonical_sha256(config) != preparation["config_hashes"][
                config_path.name
            ]:
                raise ValueError(f"server source config drift: {experiment_id}")
            if experiment_id in imported_receipts:
                receipt = imported_receipts[experiment_id][1]
                if cells[experiment_id]["server_lane"] != lane:
                    raise ValueError(f"Seed43 server lane drift: {experiment_id}")
            else:
                receipt = _read_json(
                    args.root
                    / "results"
                    / "runs"
                    / experiment_id
                    / "training_receipt.json"
                )
            _require_training_receipt(
                receipt,
                experiment_id=experiment_id,
                effective_config_sha256=_effective_training_config_sha256(
                    config, selection_rows
                ),
                preparation=preparation,
            )
        validated_queues[lane] = (queue_path, queue)
    expected_train_jobs = {
        f"train-{arm}-S{seed}" for arm in SLIM_ARMS for seed in SEEDS
    }
    if map_count != 1 or queued_train_jobs != expected_train_jobs:
        raise ValueError("server queues do not cover the exact frozen Slim matrix")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    quarantine = args.root / "quarantine" / f"seed43_import_{timestamp}"
    receipt_records = {}
    for experiment_id, (source_receipt, _, checkpoint_sha256) in sorted(
        imported_receipts.items()
    ):
        target_dir = args.root / "results" / "runs" / experiment_id
        if target_dir.exists():
            destination = quarantine / "runs" / experiment_id
            destination.parent.mkdir(parents=True, exist_ok=True)
            target_dir.replace(destination)
        target_dir.mkdir(parents=True)
        target_receipt = target_dir / "training_receipt.json"
        shutil.copy2(source_receipt, target_receipt)
        lane = str(cells[experiment_id]["server_lane"])
        state_path = args.root / "shared_state" / f"train-{experiment_id}.json"
        if state_path.exists():
            destination = quarantine / "shared_state" / state_path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            state_path.replace(destination)
        write_json_atomic(
            state_path,
            _reconciled_state(
                experiment_id=experiment_id,
                lane=lane,
                receipt_path=target_receipt,
                source_commit=source_commit,
                origin="preregistered_local_seed43_offload",
                checkpoint_sha256=checkpoint_sha256,
            ),
        )
        receipt_records[experiment_id] = {
            "training_receipt_sha256": sha256_file(target_receipt),
            "effective_config_sha256": cells[experiment_id][
                "effective_config_sha256"
            ],
            "local_best_checkpoint_sha256": checkpoint_sha256,
            "server_lane": lane,
        }

    lane_records = {}
    for lane in LANES:
        queue_path, queue = validated_queues[lane]
        completed = []
        for job in queue:
            job_id = str(job["job_id"])
            state_path = args.root / "shared_state" / f"{job_id}.json"
            if job_id == "map-slim-train-only":
                pass
            else:
                experiment_id = job_id.removeprefix("train-")
                receipt_path = (
                    args.root
                    / "results"
                    / "runs"
                    / experiment_id
                    / "training_receipt.json"
                )
                state = _read_json(state_path) if state_path.exists() else {}
                if state.get("status") != "PASS":
                    if state_path.exists():
                        destination = quarantine / "shared_state" / state_path.name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        state_path.replace(destination)
                    write_json_atomic(
                        state_path,
                        _reconciled_state(
                            experiment_id=experiment_id,
                            lane=lane,
                            receipt_path=receipt_path,
                            source_commit=source_commit,
                            origin="terminal_receipt_state_repair",
                        ),
                    )
            completed.append({"job_id": job_id, "status": "PASS"})
        completion_path = args.root / "results" / lane / "completion.json"
        write_json_atomic(
            completion_path,
            {
                "schema": "prta-cxr.phase16-lane-completion.v1",
                "status": "PASS",
                "lane": lane,
                "completed_at": datetime.now(UTC).isoformat(),
                "completed": completed,
                "failures": [],
                "skipped": [],
                "queue_sha256": sha256_file(queue_path),
                "completion_origin": "audited_offload_reconciliation",
                "import_manifest_sha256": sha256_file(args.import_manifest),
                "internal_test_opened": False,
                "gold_opened": False,
                "external_opened": False,
                "protected_outcome_read_count": 0,
            },
        )
        lane_records[lane] = {
            "completion_sha256": sha256_file(completion_path),
            "completed_job_count": len(completed),
            "queue_sha256": sha256_file(queue_path),
        }

    result = {
        "schema": "prta-cxr.slim-offload-reconciliation.v1",
        "status": "PASS_SLIM_OFFLOAD_RECONCILED",
        "created_at": datetime.now(UTC).isoformat(),
        "server_preparation_sha256": sha256_file(preparation_path),
        "local_preparation_sha256": sha256_file(local_preparation_path),
        "import_manifest_sha256": sha256_file(args.import_manifest),
        "controller_retirement_sha256": sha256_file(
            args.controller_retirement_receipt
        ),
        "source_commit": source_commit,
        "imported_seed43": receipt_records,
        "server_lane_completions": lane_records,
        "quarantine_root": str(quarantine),
        "selection_performed": False,
        "winner_selected": False,
        "current_dev_used_for_selection": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
