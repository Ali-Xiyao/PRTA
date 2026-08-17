from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.phase15_queue import SEEDS, SYSTEMS, validate_job_registry

PLAN_SCHEMA = "prta-cxr.phase15-asset-plan.v1"
OUTPUT_SCHEMA = "prta-cxr.phase15-asset-registry.v1"


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _validate_remote_path(value: object, *, role: str) -> str:
    path = PurePosixPath(str(value))
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{role} must be a normalized absolute POSIX path")
    return str(path)


def _bind_file(asset: Mapping[str, Any], *, role: str) -> dict[str, Any]:
    remote = _validate_remote_path(asset.get(f"remote_{role}"), role=role)
    local_value = asset.get(f"local_{role}")
    expected = str(asset.get(f"{role}_sha256", ""))
    size_value = asset.get(f"{role}_bytes")
    if local_value:
        local = Path(str(local_value))
        if not local.is_file():
            raise FileNotFoundError(f"missing local {role}: {local}")
        actual = sha256_file(local)
        if expected and expected != actual:
            raise ValueError(f"local {role} hash drift: {local}")
        return {
            "local_path": str(local.resolve()),
            "remote_path": remote,
            "sha256": actual,
            "bytes": local.stat().st_size,
            "transfer_required": True,
        }
    if len(expected) != 64 or size_value is None or int(size_value) <= 0:
        raise ValueError(
            f"server-resident {role} requires a SHA-256 and positive byte size"
        )
    return {
        "local_path": None,
        "remote_path": remote,
        "sha256": expected,
        "bytes": int(size_value),
        "transfer_required": False,
    }


def build_phase15_registries(plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("unsupported Phase 15 asset-plan schema")
    shared = dict(plan.get("shared_inputs", {}))
    required_shared = {
        "split_manifest",
        "cleaned_split_freeze",
        "matched_hard_prior_map",
        "weights",
        "label_quality_audit",
    }
    if set(shared) != required_shared:
        raise ValueError("Phase 15 shared input surface is incomplete or expanded")
    shared = {
        key: _validate_remote_path(value, role=key) for key, value in shared.items()
    }
    cache_inputs = dict(plan.get("cache_inputs", {}))
    if set(cache_inputs) != set(SYSTEMS):
        raise ValueError("Phase 15 cache inputs must cover exactly the four systems")
    for system, values in cache_inputs.items():
        values = dict(values)
        if set(values) != {"cache_root", "text_cache"}:
            raise ValueError(f"cache input drift for {system}")
        cache_inputs[system] = {
            key: _validate_remote_path(value, role=f"{system}.{key}")
            for key, value in values.items()
        }
    estimates = dict(plan.get("estimated_seconds", {}))
    if set(estimates) != {"probability", "efficiency"}:
        raise ValueError("Phase 15 estimates need probability and efficiency maps")
    for task in estimates:
        if set(estimates[task]) != set(SYSTEMS):
            raise ValueError(f"Phase 15 {task} estimates do not cover all systems")
        if any(int(value) <= 0 for value in estimates[task].values()):
            raise ValueError("Phase 15 duration estimates must be positive")

    assets = list(plan.get("assets", []))
    expected = {(system, seed) for system in SYSTEMS for seed in SEEDS}
    identities = {
        (str(asset.get("system")), int(asset.get("seed", -1))) for asset in assets
    }
    if len(assets) != len(identities) or identities != expected:
        raise ValueError(
            "Phase 15 asset matrix must contain each system/seed exactly once"
        )

    bound_assets: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    transfers: list[dict[str, Any]] = []
    for raw_asset in sorted(assets, key=lambda value: (value["system"], value["seed"])):
        asset = dict(raw_asset)
        system = str(asset["system"])
        seed = int(asset["seed"])
        checkpoint = _bind_file(asset, role="checkpoint")
        receipt = _bind_file(asset, role="training_receipt")
        bound = {
            "system": system,
            "seed": seed,
            "checkpoint": checkpoint,
            "training_receipt": receipt,
        }
        bound_assets.append(bound)
        for value in (checkpoint, receipt):
            if value["transfer_required"]:
                transfers.append(value)
        inputs = {**shared, **cache_inputs[system]}
        for task in ("probability", "efficiency"):
            if task == "efficiency" and seed != 43:
                continue
            jobs.append(
                {
                    "job_id": f"{task}-{system}-S{seed}",
                    "system": system,
                    "seed": seed,
                    "task": task,
                    "estimated_seconds": int(estimates[task][system]),
                    "checkpoint": checkpoint["remote_path"],
                    "checkpoint_sha256": checkpoint["sha256"],
                    "training_receipt": receipt["remote_path"],
                    "training_receipt_sha256": receipt["sha256"],
                    "inputs": inputs,
                }
            )
    job_registry = {
        "schema": "prta-cxr.phase15-job-registry.v1",
        "jobs": jobs,
    }
    validate_job_registry(job_registry)
    return {
        "asset_registry": {
            "schema": OUTPUT_SCHEMA,
            "status": "PASS_PHASE15_ASSETS_BOUND",
            "created_at": datetime.now(UTC).isoformat(),
            "assets": bound_assets,
            "asset_matrix_sha256": canonical_sha256(bound_assets),
            "transfer_file_count": len(transfers),
            "transfer_bytes": sum(int(value["bytes"]) for value in transfers),
            "server_resident_file_count": 24 - len(transfers),
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
        "job_registry": job_registry,
        "transfer_manifest": {
            "schema": "prta-cxr.phase15-transfer-manifest.v1",
            "files": transfers,
        },
    }


def prepare_phase15_assets_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bind exact Phase 15 local/server assets and job registry"
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    registries = build_phase15_registries(plan)
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    if staging.exists():
        raise FileExistsError(f"Phase 15 asset staging exists: {staging}")
    staging.mkdir(parents=True, exist_ok=False)
    for name, value in registries.items():
        _write_new_json(staging / f"{name}.json", value)
    staging.replace(args.output)
    print(json.dumps(registries["asset_registry"], indent=2, sort_keys=True))
    return 0
