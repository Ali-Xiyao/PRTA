from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.audit.tracin import AuditContractError, audit_path
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key
from prta_cxr.development_selection import _completed_runs, _write_queue
from prta_cxr.formal_matrix import development_gate_decision

EXPECTED_SPLITS = {"train": 89_406, "dev": 13_420}
PRTA_RUNS = (
    ("SOLR1-PRTA-S17", 17),
    ("SOLR1-PRTA-S29", 29),
    ("SOLR1-PRTA-S43", 43),
)
BASELINE_RUNS = (
    ("SOLR1-B402-S17", "siamese_diff"),
    ("SOLR1-B403-S17", "tila"),
)


def _stream_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise AuditContractError(
                    f"non-object manifest row at {path}:{line_number}"
                )
            yield value


def validate_rerun_manifest(
    rows: Iterable[Mapping[str, Any]],
    *,
    cache: Block8CacheIndex,
    text_cache: Mapping[str, Any],
    expected_splits: Mapping[str, int] = EXPECTED_SPLITS,
) -> dict[str, Any]:
    split_counts: Counter[str] = Counter()
    label_counts: dict[str, Counter[str]] = {
        split: Counter() for split in expected_splits
    }
    sources: Counter[str] = Counter()
    findings: Counter[str] = Counter()
    sample_ids: set[str] = set()
    patient_splits: dict[str, str] = {}
    missing_cache_keys: list[str] = []
    finding_embeddings = text_cache.get("finding_embeddings", {})
    transition_prototypes = text_cache.get("transition_prototypes", {})
    transition_embeddings = text_cache.get("transition_embeddings", {})
    if transition_embeddings:
        raise AuditContractError(
            "sample-keyed transition embeddings are label-version unsafe"
        )
    if not isinstance(finding_embeddings, dict) or not isinstance(
        transition_prototypes, dict
    ):
        raise AuditContractError("text cache lacks prototype dictionaries")
    required = {
        "sample_id",
        "patient_id_hash",
        "split",
        "source",
        "finding",
        "progression_label",
        "prior_image_path",
        "current_image_path",
        "interval_days",
    }
    for index, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            raise AuditContractError(
                f"rerun row {index} fields missing: {sorted(missing)}"
            )
        split = str(row["split"])
        if split not in expected_splits:
            raise AuditContractError("rerun manifest contains a protected split")
        sample_id = str(row["sample_id"])
        if not sample_id or sample_id in sample_ids:
            raise AuditContractError("rerun sample IDs must be nonempty and unique")
        sample_ids.add(sample_id)
        patient = str(row["patient_id_hash"])
        previous_split = patient_splits.setdefault(patient, split)
        if previous_split != split:
            raise AuditContractError("patient leakage across Train and Dev")
        label = str(row["progression_label"])
        finding = str(row["finding"])
        source = str(row["source"])
        interval = float(row["interval_days"])
        if label not in PROGRESSION_LABELS or not math.isfinite(interval):
            raise AuditContractError("invalid label or non-finite interval")
        if finding not in finding_embeddings:
            raise AuditContractError(f"missing finding prototype: {finding}")
        if f"{finding}|{label}" not in transition_prototypes:
            raise AuditContractError(
                f"missing transition prototype: {finding}|{label}"
            )
        split_counts[split] += 1
        label_counts[split][label] += 1
        sources[source] += 1
        findings[finding] += 1
        for path_key in ("prior_image_path", "current_image_path"):
            key = image_cache_key(source, row[path_key])
            if key not in cache.locations and len(missing_cache_keys) < 10:
                missing_cache_keys.append(key)
    if dict(split_counts) != dict(expected_splits):
        raise AuditContractError(
            f"rerun split conservation failed: {dict(split_counts)}"
        )
    if missing_cache_keys:
        raise AuditContractError(
            f"manifest references uncached images: {missing_cache_keys[:3]}"
        )
    for split in expected_splits:
        if set(label_counts[split]) != set(PROGRESSION_LABELS):
            raise AuditContractError(f"{split} does not cover all five labels")
    return {
        "split_counts": dict(split_counts),
        "label_counts": {
            split: dict(sorted(counts.items()))
            for split, counts in label_counts.items()
        },
        "source_counts": dict(sorted(sources.items())),
        "finding_counts": dict(sorted(findings.items())),
        "unique_sample_ids": len(sample_ids),
        "unique_patients": len(patient_splits),
        "missing_cache_keys": 0,
        "patient_overlap": 0,
        "text_cache_mode": "finding_and_transition_prototypes_only",
    }


def build_rerun_configs(
    *,
    prta_parent: Mapping[str, Any],
    baseline_parents: Mapping[str, Mapping[str, Any]],
    train_class_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    ordered_counts = [int(train_class_counts[label]) for label in PROGRESSION_LABELS]
    configs: list[dict[str, Any]] = []
    for experiment_id, seed in PRTA_RUNS:
        config = deepcopy(dict(prta_parent))
        config["experiment_id"] = experiment_id
        config["seed"] = seed
        config["development_axis"] = "sol_all_risk_authoritative_rerun"
        config["classification_loss"]["class_counts"] = ordered_counts
        configs.append(config)
    for experiment_id, family in BASELINE_RUNS:
        config = deepcopy(dict(baseline_parents[family]))
        config["experiment_id"] = experiment_id
        config["seed"] = 17
        config["development_axis"] = "sol_all_risk_authoritative_rerun_baseline"
        config["classification_loss"]["class_counts"] = ordered_counts
        configs.append(config)
    ids = [str(config["experiment_id"]) for config in configs]
    if ids != [value[0] for value in (*PRTA_RUNS, *BASELINE_RUNS)]:
        raise AuditContractError("rerun config identity/order drift")
    if any(float(config["data"]["train_fraction"]) != 1.0 for config in configs):
        raise AuditContractError("rerun configs must use the full Train split")
    return configs


def _git_commit(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def prepare_sol_rerun_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the Sol-label Dev rerun")
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--quality-audit", type=Path, required=True)
    parser.add_argument("--prta-parent", type=Path, required=True)
    parser.add_argument("--b402-parent", type=Path, required=True)
    parser.add_argument("--b403-parent", type=Path, required=True)
    parser.add_argument("--historical-gate", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    roles = {
        "split_manifest": args.split_manifest,
        "cache_root": args.cache_root,
        "text_cache": args.text_cache,
        "weights": args.weights,
        "quality_audit": args.quality_audit,
        "prta_parent": args.prta_parent,
        "b402_parent": args.b402_parent,
        "b403_parent": args.b403_parent,
        "historical_gate": args.historical_gate,
        "output_root": args.output_root,
    }
    paths = {role: audit_path(path, role=role) for role, path in roles.items()}
    try:
        paths["output_root"].relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise AuditContractError("rerun output must stay outside Git")
    if paths["output_root"].exists():
        raise FileExistsError(f"refusing existing rerun root: {paths['output_root']}")
    input_files = {
        role: path
        for role, path in paths.items()
        if role not in {"cache_root", "output_root"}
    }
    input_files["cache_manifest"] = paths["cache_root"] / "cache_manifest.json"
    input_files["training_store"] = paths["cache_root"] / (
        "block8_features.f16.bin"
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
        rows, cache=cache, text_cache=text_cache
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
    configs = build_rerun_configs(
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
        stage="sol_all_risk_authoritative_dev_gate_rerun",
    )
    # The queue runner uses a separate runs directory below this root.
    (output_root / "runs").mkdir()
    historical_gate = json.loads(
        paths["historical_gate"].read_text(encoding="utf-8")
    )
    hashes_after = {role: sha256_file(path) for role, path in input_files.items()}
    if hashes_after != hashes_before:
        raise AuditContractError("rerun preparation changed an immutable input")
    result = {
        "schema": "prta-cxr.sol-all-risk-rerun-preparation.v1",
        "status": "PASS_SOL_ALL_RISK_RERUN_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(repo_root),
        "input_paths": {role: str(path) for role, path in input_files.items()},
        "input_sha256": hashes_before,
        "manifest_audit": manifest_audit,
        "run_ids": [row["experiment_id"] for row in queue],
        "queue_sha256": canonical_sha256(queue),
        "historical_gate_status": historical_gate.get("status"),
        "historical_mean_macro_f1": historical_gate.get("mean_macro_f1"),
        "historical_seed17_gain": historical_gate.get(
            "seed17_gain_vs_strongest_temporal"
        ),
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    write_json_atomic(output_root / "preparation_receipt.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def compare_gate_results(
    new_gate: Mapping[str, Any], historical_gate: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "new_status": new_gate["status"],
        "historical_status": historical_gate["status"],
        "new_mean_macro_f1": float(new_gate["mean_macro_f1"]),
        "historical_mean_macro_f1": float(historical_gate["mean_macro_f1"]),
        "mean_macro_f1_delta": float(new_gate["mean_macro_f1"])
        - float(historical_gate["mean_macro_f1"]),
        "new_seed17_gain": float(
            new_gate["seed17_gain_vs_strongest_temporal"]
        ),
        "historical_seed17_gain": float(
            historical_gate["seed17_gain_vs_strongest_temporal"]
        ),
        "seed17_gain_delta": float(
            new_gate["seed17_gain_vs_strongest_temporal"]
        )
        - float(historical_gate["seed17_gain_vs_strongest_temporal"]),
        "all_frozen_checks_passed": all(new_gate["checks"].values()),
    }


def finalize_sol_rerun_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize the Sol-label Dev rerun")
    parser.add_argument("--run-registry", type=Path, required=True)
    parser.add_argument("--preparation-receipt", type=Path, required=True)
    parser.add_argument("--historical-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    paths = {
        role: audit_path(path, role=role)
        for role, path in {
            "run_registry": args.run_registry,
            "preparation_receipt": args.preparation_receipt,
            "historical_gate": args.historical_gate,
            "output": args.output,
        }.items()
    }
    receipts, _ = _completed_runs(paths["run_registry"])
    gate = development_gate_decision(
        prta_seed_ids=[value[0] for value in PRTA_RUNS],
        baseline_ids=[value[0] for value in BASELINE_RUNS],
        receipts=receipts,
    )
    historical = json.loads(
        paths["historical_gate"].read_text(encoding="utf-8")
    )
    preparation = json.loads(
        paths["preparation_receipt"].read_text(encoding="utf-8")
    )
    gate.update(
        {
            "comparison_to_historical": compare_gate_results(gate, historical),
            "registry_sha256": sha256_file(paths["run_registry"]),
            "preparation_receipt_sha256": sha256_file(
                paths["preparation_receipt"]
            ),
            "active_split_manifest_sha256": preparation["input_sha256"][
                "split_manifest"
            ],
            "protected_outcome_read_count": 0,
        }
    )
    write_json_atomic(paths["output"], gate)
    print(json.dumps(gate, indent=2, sort_keys=True))
    return 0

