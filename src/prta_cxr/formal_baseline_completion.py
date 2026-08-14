from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.audit.tracin import AuditContractError, audit_path
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.development_selection import _write_queue
from prta_cxr.sol_rerun import _stream_jsonl, validate_rerun_manifest

EXPECTED_SPLITS = {"train": 80_402, "dev": 11_201}
RUN_SPECS = (
    ("W046-B401-S17", "current_only", 17),
    ("W046-B401-S28", "current_only", 28),
    ("W046-B401-S43", "current_only", 43),
    ("W046-B402-S28", "siamese_diff", 28),
    ("W046-B402-S43", "siamese_diff", 43),
)
REUSED_SPECS = (
    ("CLN1-B402-S17", "siamese_diff", 17),
    ("CLN1-B403-S17", "tila", 17),
    ("B403-S28", "tila", 28),
    ("B403-S43", "tila", 43),
)
AXIS = "formal_native_baseline_completion_v1"


def _git_commit(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _changed_paths(left: Any, right: Any, prefix: str = "") -> set[str]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        keys = set(left) | set(right)
        changed: set[str] = set()
        for key in keys:
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                changed.add(child)
            else:
                changed.update(_changed_paths(left[key], right[key], child))
        return changed
    return set() if left == right else {prefix}


def _without_family(config: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(config))
    for key in ("experiment_id", "development_axis", "seed"):
        value.pop(key, None)
    value["model"].pop("family", None)
    return value


def build_formal_baseline_completion_configs(
    *,
    b401_parent: Mapping[str, Any],
    b402_parent: Mapping[str, Any],
    train_class_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    if b401_parent["model"]["family"] != "current_only":
        raise AuditContractError("B401 parent family drift")
    if b402_parent["model"]["family"] != "siamese_diff":
        raise AuditContractError("B402 parent family drift")
    if float(b401_parent["data"]["train_fraction"]) != 1.0:
        raise AuditContractError("B401 parent must use full retained Train")
    if float(b402_parent["data"]["train_fraction"]) != 1.0:
        raise AuditContractError("B402 parent must use full retained Train")

    ordered_counts = [int(train_class_counts[label]) for label in PROGRESSION_LABELS]
    cleaned_b401 = deepcopy(dict(b401_parent))
    cleaned_b401["classification_loss"]["class_counts"] = ordered_counts
    cleaned_b402 = deepcopy(dict(b402_parent))
    cleaned_b402["classification_loss"]["class_counts"] = ordered_counts
    if _without_family(cleaned_b401) != _without_family(cleaned_b402):
        raise AuditContractError("B401/B402 native baseline budgets differ")

    configs: list[dict[str, Any]] = []
    for experiment_id, family, seed in RUN_SPECS:
        parent = cleaned_b401 if family == "current_only" else cleaned_b402
        config = deepcopy(parent)
        config["experiment_id"] = experiment_id
        config["development_axis"] = AXIS
        config["seed"] = seed
        configs.append(config)

    b401_allowed = {
        "experiment_id",
        "development_axis",
        "classification_loss.class_counts",
    }
    b402_allowed = {
        "experiment_id",
        "development_axis",
        "seed",
        "classification_loss.class_counts",
    }
    for config in configs:
        if config["model"]["family"] == "current_only":
            allowed = set(b401_allowed)
            if int(config["seed"]) != int(b401_parent["seed"]):
                allowed.add("seed")
            changed = _changed_paths(b401_parent, config)
        else:
            changed = _changed_paths(b402_parent, config)
            allowed = set(b402_allowed)
            if b402_parent["classification_loss"]["class_counts"] == ordered_counts:
                allowed.remove("classification_loss.class_counts")
        if changed != allowed:
            detail = f"{config['experiment_id']} {sorted(changed)}"
            raise AuditContractError(f"formal baseline config drift: {detail}")
    return configs


def verify_reused_run(
    *,
    config_path: Path,
    receipt_path: Path,
    expected_id: str,
    expected_family: str,
    expected_seed: int,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if config.get("experiment_id") != expected_id:
        raise AuditContractError(f"reused config ID drift for {expected_id}")
    if config.get("model", {}).get("family") != expected_family:
        raise AuditContractError(f"reused family drift for {expected_id}")
    if int(config.get("seed", -1)) != expected_seed:
        raise AuditContractError(f"reused seed drift for {expected_id}")
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise AuditContractError(f"reused receipt is not PASS for {expected_id}")
    config_file_sha = sha256_file(config_path)
    effective_config_sha = canonical_sha256(config)
    if receipt.get("config_sha256") != effective_config_sha:
        raise AuditContractError(f"reused config hash mismatch for {expected_id}")
    if receipt.get("protected_outcomes_opened") is not False:
        raise AuditContractError(f"reused protected outcome opened for {expected_id}")
    if receipt.get("internal_test_opened") is not False:
        raise AuditContractError(f"reused Internal-test opened for {expected_id}")
    checkpoint = audit_path(Path(str(receipt["checkpoint_path"])), role="checkpoint")
    return {
        "experiment_id": expected_id,
        "family": expected_family,
        "seed": expected_seed,
        "config_path": str(config_path),
        "config_file_sha256": config_file_sha,
        "effective_config_sha256": effective_config_sha,
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "checkpoint_path": str(checkpoint),
        "checkpoint_sha256": sha256_file(checkpoint),
        "zero_protected_reads": True,
    }


def _validate_b403_seed_reuse(rows: Sequence[Mapping[str, Any]]) -> None:
    b403 = [row for row in rows if row["family"] == "tila"]
    if [int(row["seed"]) for row in b403] != [17, 28, 43]:
        raise AuditContractError("B403 reuse must be exactly seeds 17/28/43")


def prepare_formal_baseline_completion_main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze missing cleaned Train/Dev native baselines"
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--quality-audit", type=Path, required=True)
    parser.add_argument("--b401-parent", type=Path, required=True)
    parser.add_argument("--b402-parent", type=Path, required=True)
    parser.add_argument("--reuse", type=Path, nargs=8, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    roles = {
        "split_manifest": args.split_manifest,
        "cleaned_split_freeze": args.cleaned_split_freeze,
        "cache_root": args.cache_root,
        "text_cache": args.text_cache,
        "weights": args.weights,
        "quality_audit": args.quality_audit,
        "b401_parent": args.b401_parent,
        "b402_parent": args.b402_parent,
        "output_root": args.output_root,
    }
    paths = {role: audit_path(path, role=role) for role, path in roles.items()}
    try:
        paths["output_root"].relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise AuditContractError("baseline output must stay outside Git")
    if paths["output_root"].exists():
        raise FileExistsError(
            f"refusing existing baseline root: {paths['output_root']}"
        )

    freeze = require_cleaned_manifest(
        paths["split_manifest"],
        receipt_path=paths["cleaned_split_freeze"],
        role="train_dev",
    )
    input_files = {
        role: path
        for role, path in paths.items()
        if role not in {"cache_root", "output_root"}
    }
    input_files["cache_manifest"] = paths["cache_root"] / "cache_manifest.json"
    input_files["training_store"] = paths["cache_root"] / "block8_features.f16.bin"
    hashes_before = {role: sha256_file(path) for role, path in input_files.items()}
    cache_manifest = json.loads(
        input_files["cache_manifest"].read_text(encoding="utf-8")
    )
    if (
        cache_manifest.get("encoder", {}).get("weights_sha256")
        != hashes_before["weights"]
    ):
        raise AuditContractError("cache encoder and live weights hashes differ")
    if (
        cache_manifest.get("training_store", {}).get("file_sha256")
        != hashes_before["training_store"]
    ):
        raise AuditContractError("training store hash differs from cache receipt")
    text_cache = torch.load(paths["text_cache"], map_location="cpu", weights_only=True)
    if not isinstance(text_cache, dict):
        raise AuditContractError("text cache must be a dictionary")
    cache = Block8CacheIndex(paths["cache_root"])
    manifest_rows = list(_stream_jsonl(paths["split_manifest"]))
    manifest_audit = validate_rerun_manifest(
        manifest_rows,
        cache=cache,
        text_cache=text_cache,
        expected_splits=EXPECTED_SPLITS,
    )
    train_counts = Counter(
        str(row["progression_label"])
        for row in manifest_rows
        if row["split"] == "train"
    )
    parents = {
        "b401": json.loads(paths["b401_parent"].read_text(encoding="utf-8")),
        "b402": json.loads(paths["b402_parent"].read_text(encoding="utf-8")),
    }
    configs = build_formal_baseline_completion_configs(
        b401_parent=parents["b401"],
        b402_parent=parents["b402"],
        train_class_counts=train_counts,
    )

    reuse_paths = [audit_path(path, role="reuse") for path in args.reuse]
    reused = []
    for index, (expected_id, family, seed) in enumerate(REUSED_SPECS):
        reused.append(
            verify_reused_run(
                config_path=reuse_paths[index * 2],
                receipt_path=reuse_paths[index * 2 + 1],
                expected_id=expected_id,
                expected_family=family,
                expected_seed=seed,
            )
        )
    _validate_b403_seed_reuse(reused)

    queue = _write_queue(paths["output_root"], configs, stage=AXIS)
    (paths["output_root"] / "runs").mkdir()
    hashes_after = {role: sha256_file(path) for role, path in input_files.items()}
    if hashes_after != hashes_before:
        raise AuditContractError("baseline preparation changed an input")
    result = {
        "schema": "prta-cxr.formal-native-baseline-completion.v1",
        "status": "PASS_FORMAL_NATIVE_BASELINE_COMPLETION_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(repo_root),
        "dataset_version": freeze["dataset_version"],
        "cleaned_split_freeze_sha256": freeze["receipt_sha256"],
        "input_paths": {role: str(path) for role, path in input_files.items()},
        "input_sha256": hashes_before,
        "manifest_audit": manifest_audit,
        "new_run_ids": [row["experiment_id"] for row in queue],
        "new_seeds": [17, 28, 43],
        "queue_sha256": canonical_sha256(queue),
        "reused_runs": reused,
        "complete_matrix": {
            "B401": ["W046-B401-S17", "W046-B401-S28", "W046-B401-S43"],
            "B402": ["CLN1-B402-S17", "W046-B402-S28", "W046-B402-S43"],
            "B403": ["CLN1-B403-S17", "B403-S28", "B403-S43"],
        },
        "no_outcome_selection": True,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "training_started": False,
    }
    write_json_atomic(paths["output_root"] / "preparation_receipt.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
