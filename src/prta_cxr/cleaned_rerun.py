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
from prta_cxr.development_selection import _completed_runs, _write_queue
from prta_cxr.formal_matrix import development_gate_decision
from prta_cxr.sol_rerun import (
    _stream_jsonl,
    compare_gate_results,
    validate_rerun_manifest,
)

EXPECTED_CLEANED_SPLITS = {"train": 80_402, "dev": 11_201}
CLEANED_PRTA_RUNS = (
    ("CLN1-PRTA-S17", 17),
    ("CLN1-PRTA-S28", 28),
    ("CLN1-PRTA-S43", 43),
)
CLEANED_BASELINE_RUNS = (
    ("CLN1-B402-S17", "siamese_diff"),
    ("CLN1-B403-S17", "tila"),
)


def build_cleaned_rerun_configs(
    *,
    prta_parent: Mapping[str, Any],
    baseline_parents: Mapping[str, Mapping[str, Any]],
    train_class_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    ordered_counts = [
        int(train_class_counts[label]) for label in PROGRESSION_LABELS
    ]
    configs: list[dict[str, Any]] = []
    for experiment_id, seed in CLEANED_PRTA_RUNS:
        config = deepcopy(dict(prta_parent))
        config["experiment_id"] = experiment_id
        config["seed"] = seed
        config["development_axis"] = "physician_cleaned_formal_dev_gate"
        config["classification_loss"]["class_counts"] = ordered_counts
        configs.append(config)
    for experiment_id, family in CLEANED_BASELINE_RUNS:
        config = deepcopy(dict(baseline_parents[family]))
        config["experiment_id"] = experiment_id
        config["seed"] = 17
        config["development_axis"] = (
            "physician_cleaned_formal_dev_gate_baseline"
        )
        config["classification_loss"]["class_counts"] = ordered_counts
        configs.append(config)
    expected_ids = [
        value[0] for value in (*CLEANED_PRTA_RUNS, *CLEANED_BASELINE_RUNS)
    ]
    if [str(config["experiment_id"]) for config in configs] != expected_ids:
        raise AuditContractError("cleaned rerun config identity/order drift")
    if [int(config["seed"]) for config in configs[:3]] != [17, 28, 43]:
        raise AuditContractError("cleaned PRTA seeds must be exactly 17/28/43")
    if any(float(config["data"]["train_fraction"]) != 1.0 for config in configs):
        raise AuditContractError("cleaned rerun must use full retained Train")
    return configs


def _git_commit(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def prepare_cleaned_rerun_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare physician-cleaned PRTA/B402/B403 Dev gate reruns"
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--quality-audit", type=Path, required=True)
    parser.add_argument("--prta-parent", type=Path, required=True)
    parser.add_argument("--b402-parent", type=Path, required=True)
    parser.add_argument("--b403-parent", type=Path, required=True)
    parser.add_argument("--comparison-gate", type=Path, required=True)
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
        "prta_parent": args.prta_parent,
        "b402_parent": args.b402_parent,
        "b403_parent": args.b403_parent,
        "comparison_gate": args.comparison_gate,
        "output_root": args.output_root,
    }
    paths = {role: audit_path(path, role=role) for role, path in roles.items()}
    try:
        paths["output_root"].relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise AuditContractError("cleaned rerun output must stay outside Git")
    if paths["output_root"].exists():
        raise FileExistsError(
            f"refusing existing cleaned rerun root: {paths['output_root']}"
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
    input_files["training_store"] = (
        paths["cache_root"] / "block8_features.f16.bin"
    )
    hashes_before = {role: sha256_file(path) for role, path in input_files.items()}
    cache_manifest = json.loads(
        input_files["cache_manifest"].read_text(encoding="utf-8")
    )
    if cache_manifest.get("encoder", {}).get("weights_sha256") != hashes_before[
        "weights"
    ]:
        raise AuditContractError("cache encoder and live weights hashes differ")
    if cache_manifest.get("training_store", {}).get("file_sha256") != (
        hashes_before["training_store"]
    ):
        raise AuditContractError("training store hash differs from cache receipt")
    text_cache = torch.load(
        paths["text_cache"], map_location="cpu", weights_only=True
    )
    if not isinstance(text_cache, dict):
        raise AuditContractError("text cache must be a dictionary")
    cache = Block8CacheIndex(paths["cache_root"])
    rows = list(_stream_jsonl(paths["split_manifest"]))
    manifest_audit = validate_rerun_manifest(
        rows,
        cache=cache,
        text_cache=text_cache,
        expected_splits=EXPECTED_CLEANED_SPLITS,
    )
    train_counts = Counter(
        str(row["progression_label"])
        for row in rows
        if row["split"] == "train"
    )
    parent_paths = {
        "prta": paths["prta_parent"],
        "siamese_diff": paths["b402_parent"],
        "tila": paths["b403_parent"],
    }
    parents = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in parent_paths.items()
    }
    if parents["prta"]["model"]["family"] != "prta":
        raise AuditContractError("PRTA parent family drift")
    for family in ("siamese_diff", "tila"):
        if parents[family]["model"]["family"] != family:
            raise AuditContractError(f"{family} parent family drift")
    configs = build_cleaned_rerun_configs(
        prta_parent=parents["prta"],
        baseline_parents={
            "siamese_diff": parents["siamese_diff"],
            "tila": parents["tila"],
        },
        train_class_counts=train_counts,
    )
    output_root = paths["output_root"]
    queue = _write_queue(
        output_root,
        configs,
        stage="physician_cleaned_formal_dev_gate",
    )
    (output_root / "runs").mkdir()
    comparison_gate = json.loads(
        paths["comparison_gate"].read_text(encoding="utf-8")
    )
    hashes_after = {role: sha256_file(path) for role, path in input_files.items()}
    if hashes_after != hashes_before:
        raise AuditContractError("cleaned rerun preparation changed an input")
    result = {
        "schema": "prta-cxr.physician-cleaned-rerun-preparation.v1",
        "status": "PASS_PHYSICIAN_CLEANED_RERUN_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(repo_root),
        "dataset_version": freeze["dataset_version"],
        "cleaned_split_freeze_sha256": freeze["receipt_sha256"],
        "input_paths": {role: str(path) for role, path in input_files.items()},
        "input_sha256": hashes_before,
        "manifest_audit": manifest_audit,
        "run_ids": [row["experiment_id"] for row in queue],
        "prta_seeds": [17, 28, 43],
        "queue_sha256": canonical_sha256(queue),
        "comparison_gate_status": comparison_gate.get("status"),
        "comparison_mean_macro_f1": comparison_gate.get("mean_macro_f1"),
        "comparison_seed17_gain": comparison_gate.get(
            "seed17_gain_vs_strongest_temporal"
        ),
        "outcome_adaptive_cleaned_dev": True,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "training_started": False,
    }
    write_json_atomic(output_root / "preparation_receipt.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def finalize_cleaned_rerun_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Finalize physician-cleaned five-run development gate"
    )
    parser.add_argument("--run-registry", type=Path, required=True)
    parser.add_argument("--preparation-receipt", type=Path, required=True)
    parser.add_argument("--comparison-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    paths = {
        role: audit_path(path, role=role)
        for role, path in {
            "run_registry": args.run_registry,
            "preparation_receipt": args.preparation_receipt,
            "comparison_gate": args.comparison_gate,
            "output": args.output,
        }.items()
    }
    preparation = json.loads(
        paths["preparation_receipt"].read_text(encoding="utf-8")
    )
    expected_ids = [
        value[0] for value in (*CLEANED_PRTA_RUNS, *CLEANED_BASELINE_RUNS)
    ]
    if preparation.get("status") != "PASS_PHYSICIAN_CLEANED_RERUN_PREPARED":
        raise AuditContractError("cleaned rerun preparation is not PASS")
    if preparation.get("run_ids") != expected_ids:
        raise AuditContractError("cleaned rerun preparation IDs changed")
    receipts, _ = _completed_runs(paths["run_registry"])
    gate = development_gate_decision(
        prta_seed_ids=[value[0] for value in CLEANED_PRTA_RUNS],
        baseline_ids=[value[0] for value in CLEANED_BASELINE_RUNS],
        receipts=receipts,
    )
    comparison = json.loads(paths["comparison_gate"].read_text(encoding="utf-8"))
    gate.update(
        {
            "comparison_to_previous_label_version": compare_gate_results(
                gate, comparison
            ),
            "registry_sha256": sha256_file(paths["run_registry"]),
            "preparation_receipt_sha256": sha256_file(
                paths["preparation_receipt"]
            ),
            "active_split_manifest_sha256": preparation["input_sha256"][
                "split_manifest"
            ],
            "cleaned_split_freeze_sha256": preparation[
                "cleaned_split_freeze_sha256"
            ],
            "prta_seeds": [17, 28, 43],
            "outcome_adaptive_cleaned_dev": True,
            "protected_outcome_read_count": 0,
        }
    )
    write_json_atomic(paths["output"], gate)
    print(json.dumps(gate, indent=2, sort_keys=True))
    return 0

