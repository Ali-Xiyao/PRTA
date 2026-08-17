from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.training_dataset import read_jsonl
from prta_cxr.evaluation.progression import deterministic_patient_folds, fold_audit
from prta_cxr.ifusion_matrix import validate_v2_parents
from prta_cxr.phase16_queue import allocate_lanes
from prta_cxr.provenance import resolve_source_commit

SEEDS = (17, 28, 43)
SLIM_ARMS: dict[str, tuple[bool, bool]] = {
    "Slim-S0": (True, True),
    "Slim-S1": (False, True),
    "Slim-S2": (True, False),
    "Slim-S3": (False, False),
}
SPLIT_SALT = "prta-cxr-slim-train-only-five-fold-v1"
SLIM_DEV_FOLD = 0
FOLD_COUNT = 5


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _write_new_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")
    temporary.replace(path)


def build_train_only_selection_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    train_rows = [dict(row) for row in rows if row.get("split") == "train"]
    if not train_rows:
        raise ValueError("source cleaned manifest has no Train rows")
    sample_ids = [str(row.get("sample_id", "")) for row in train_rows]
    if any(not value for value in sample_ids) or len(sample_ids) != len(
        set(sample_ids)
    ):
        raise ValueError("source Train sample IDs must be non-empty and unique")
    assignment = deterministic_patient_folds(
        train_rows,
        labels=PROGRESSION_LABELS,
        fold_count=FOLD_COUNT,
        salt=SPLIT_SALT,
    )
    derived = []
    for raw in train_rows:
        row = dict(raw)
        fold = assignment[str(row["patient_id_hash"])]
        row["split"] = "dev" if fold == SLIM_DEV_FOLD else "train"
        derived.append(row)
    derived.sort(
        key=lambda row: (
            0 if row["split"] == "train" else 1,
            str(row["patient_id_hash"]),
            str(row["sample_id"]),
        )
    )
    train_patients = {
        str(row["patient_id_hash"]) for row in derived if row["split"] == "train"
    }
    dev_patients = {
        str(row["patient_id_hash"]) for row in derived if row["split"] == "dev"
    }
    if train_patients & dev_patients:
        raise ValueError("Slim Train/Dev patient leakage")
    for split in ("train", "dev"):
        selected = [row for row in derived if row["split"] == split]
        observed = Counter(str(row["progression_label"]) for row in selected)
        missing = set(PROGRESSION_LABELS) - set(observed)
        if missing:
            raise ValueError(f"Slim {split} lacks labels: {sorted(missing)}")
    audit = {
        "schema": "prta-cxr.slim-train-only-split-audit.v1",
        "status": "PASS_SLIM_TRAIN_ONLY_PATIENT_SPLIT",
        "salt": SPLIT_SALT,
        "fold_count": FOLD_COUNT,
        "slim_dev_fold": SLIM_DEV_FOLD,
        "source_train_rows": len(train_rows),
        "derived_rows": len(derived),
        "source_non_train_rows_excluded": len(rows) - len(train_rows),
        "train_rows": sum(row["split"] == "train" for row in derived),
        "dev_rows": sum(row["split"] == "dev" for row in derived),
        "train_patients": len(train_patients),
        "dev_patients": len(dev_patients),
        "patient_overlap": [],
        "source_train_roster_sha256": canonical_sha256(sorted(sample_ids)),
        "derived_roster_sha256": canonical_sha256(
            sorted(str(row["sample_id"]) for row in derived)
        ),
        "fold_audit": fold_audit(
            train_rows,
            assignment,
            labels=PROGRESSION_LABELS,
            fold_count=FOLD_COUNT,
        ),
        "current_dev_used_for_selection": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }
    return derived, audit


def require_train_only_selection_manifest(
    manifest_path: Path,
    *,
    selection_receipt_path: Path,
    cleaned_split_freeze: Path,
) -> dict[str, Any]:
    receipt = json.loads(selection_receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "prta-cxr.slim-selection-manifest.v1":
        raise ValueError("unsupported Slim selection receipt schema")
    if receipt.get("status") != "PASS_SLIM_SELECTION_MANIFEST_FROZEN":
        raise ValueError("Slim selection manifest is not frozen")
    if sha256_file(manifest_path) != receipt.get("derived_manifest_sha256"):
        raise ValueError("Slim derived manifest hash drift")
    if sha256_file(cleaned_split_freeze) != receipt.get("cleaned_split_freeze_sha256"):
        raise ValueError("Slim cleaned-split authority drift")
    audit = dict(receipt.get("split_audit", {}))
    if audit.get("status") != "PASS_SLIM_TRAIN_ONLY_PATIENT_SPLIT":
        raise ValueError("Slim split audit is not PASS")
    if audit.get("patient_overlap") != []:
        raise ValueError("Slim split audit reports patient leakage")
    if audit.get("source_train_rows") != audit.get("derived_rows"):
        raise ValueError("Slim derived roster is incomplete")
    if audit.get("source_train_roster_sha256") != audit.get("derived_roster_sha256"):
        raise ValueError("Slim derived roster identity drift")
    for key in (
        "current_dev_used_for_selection",
        "internal_test_opened",
        "gold_opened",
        "external_opened",
    ):
        if audit.get(key) is not False:
            raise ValueError(f"Slim protected split flag is not closed: {key}")
    if audit.get("protected_outcome_read_count") != 0:
        raise ValueError("Slim split reports protected reads")
    for key in (
        "current_dev_used_for_selection",
        "internal_test_opened",
        "gold_opened",
        "external_opened",
    ):
        if receipt.get(key) is not False:
            raise ValueError(f"Slim selection receipt is not closed: {key}")
    if receipt.get("protected_outcome_read_count") != 0:
        raise ValueError("Slim selection receipt reports protected reads")
    return receipt


def build_slim_configs(
    parents: Mapping[int, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    validate_v2_parents(parents)
    configs: dict[str, dict[str, Any]] = {}
    for arm, (prototype_on, state_on) in SLIM_ARMS.items():
        for seed in SEEDS:
            config = deepcopy(dict(parents[seed]))
            experiment_id = f"{arm}-S{seed}"
            config["experiment_id"] = experiment_id
            config["seed"] = seed
            config["development_axis"] = "slim_train_only_2x2_v1"
            config["slim_arm"] = arm
            config["slim_factors"] = {
                "dmw": False,
                "prototype_alignment": prototype_on,
                "state_anchor": state_on,
                "odc": True,
                "matched_hard_cmcp": True,
            }
            weights = dict(config["loss_weights"])
            weights["direction_margin"] = 0.0
            weights["prototype_alignment"] = 0.01 if prototype_on else 0.0
            weights["state"] = 0.025 if state_on else 0.0
            config["loss_weights"] = weights
            configs[experiment_id] = config
    validate_slim_configs(configs)
    return configs


def validate_slim_configs(configs: Mapping[str, Mapping[str, Any]]) -> None:
    expected = {f"{arm}-S{seed}" for arm in SLIM_ARMS for seed in SEEDS}
    if set(configs) != expected or len(configs) != 12:
        raise ValueError("Slim matrix must contain exactly 12 cells")
    for experiment_id, config in configs.items():
        if config.get("experiment_id") != experiment_id:
            raise ValueError("Slim experiment identity drift")
        arm = str(config.get("slim_arm"))
        prototype_on, state_on = SLIM_ARMS[arm]
        weights = dict(config["loss_weights"])
        components = dict(config["model"]["components"])
        required_components = {
            "finding_conditioning": True,
            "cross_time_alignment": True,
            "temporal_relation_residual": True,
            "matched_hard_cmcp": True,
        }
        for key, expected_value in required_components.items():
            if bool(components.get(key, key == "temporal_relation_residual")) is not (
                expected_value
            ):
                raise ValueError(f"Slim structural core drift: {key}")
        if config.get("cmcp", {}).get("matching") != "offline_hard_v1":
            raise ValueError("Slim matched-hard CMCP drift")
        expected_weights = {
            "direction_margin": 0.0,
            "opposite_direction_cost": 0.05,
            "cmcp": 0.01,
            "prototype_alignment": 0.01 if prototype_on else 0.0,
            "state": 0.025 if state_on else 0.0,
        }
        for key, expected_value in expected_weights.items():
            if float(weights.get(key, -1.0)) != expected_value:
                raise ValueError(f"Slim loss drift: {key}")


def _training_command(
    experiment_id: str,
    *,
    inputs: Mapping[str, str],
) -> list[str]:
    return [
        "{python}",
        "{source}/scripts/07_train.py",
        "--mode",
        "formal",
        "--config",
        f"{{runtime_root}}/configs/{experiment_id}.json",
        "--split-manifest",
        "{runtime_root}/selection/train_only_selection_v1.jsonl",
        "--derived-train-only-selection-receipt",
        "{runtime_root}/selection/selection_manifest_receipt.json",
        "--cleaned-split-freeze",
        inputs["cleaned_split_freeze"],
        "--cleaned-split-platform-root",
        inputs["cleaned_split_platform_root"],
        "--cache-root",
        inputs["cache_root"],
        "--text-cache",
        inputs["text_cache"],
        "--weights",
        inputs["weights"],
        "--label-quality-audit",
        inputs["label_quality_audit"],
        "--counterfactual-prior-map",
        "{output_root}/assets/slim_matched_hard_map.json",
        "--run-registry",
        f"{{output_root}}/registries/{experiment_id}.jsonl",
        "--owner",
        "PRTA-CXR-Slim frozen Train-only matrix",
        "--output",
        f"{{output_root}}/runs/{experiment_id}",
        "--device",
        "{device}",
        "--formal",
    ]


def build_slim_jobs(
    configs: Mapping[str, Mapping[str, Any]], *, inputs: Mapping[str, str]
) -> list[dict[str, Any]]:
    representative = "Slim-S0-S17"
    map_path = "{output_root}/assets/slim_matched_hard_map.json"
    jobs: list[dict[str, Any]] = [
        {
            "job_id": "map-slim-train-only",
            "group": "slim_matrix",
            "estimated_seconds": 1200,
            "queue_priority": 0,
            "dependencies": [],
            "command": [
                "{python}",
                "{source}/scripts/100_build_phase16_map.py",
                "--config",
                f"{{runtime_root}}/configs/{representative}.json",
                "--split-manifest",
                "{runtime_root}/selection/train_only_selection_v1.jsonl",
                "--cache-root",
                inputs["cache_root"],
                "--output",
                map_path,
                "--device",
                "{device}",
                "--formal",
            ],
            "expected_outputs": [map_path],
        }
    ]
    for experiment_id in sorted(configs):
        jobs.append(
            {
                "job_id": f"train-{experiment_id}",
                "group": "slim_matrix",
                "estimated_seconds": 15250,
                "queue_priority": 10,
                "dependencies": ["map-slim-train-only"],
                "command": _training_command(experiment_id, inputs=inputs),
                "expected_outputs": [
                    f"{{output_root}}/runs/{experiment_id}/training_receipt.json",
                    f"{{output_root}}/runs/{experiment_id}/best.pt",
                ],
            }
        )
    return jobs


def prepare_slim_matrix_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the Train-only PRTA-CXR-Slim 2x2 matrix"
    )
    parser.add_argument("--v2-config", type=Path, nargs=3, required=True)
    parser.add_argument("--source-cleaned-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be new")
    require_cleaned_manifest(
        args.source_cleaned_manifest,
        receipt_path=args.cleaned_split_freeze,
        role="train_dev",
        portable_root=args.cleaned_split_platform_root,
    )
    input_paths = {
        "source_cleaned_manifest": args.source_cleaned_manifest,
        "cleaned_split_freeze": args.cleaned_split_freeze,
        "cache_manifest": args.cache_root / "cache_manifest.json",
        "text_cache": args.text_cache,
        "weights": args.weights,
        "label_quality_audit": args.label_quality_audit,
    }
    for role, path in input_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Slim input missing: {role}")
    parent_values = [
        json.loads(path.read_text(encoding="utf-8")) for path in args.v2_config
    ]
    parents = {int(value["seed"]): value for value in parent_values}
    configs = build_slim_configs(parents)
    derived, split_audit = build_train_only_selection_rows(
        read_jsonl(args.source_cleaned_manifest)
    )
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    manifest_path = staging / "selection" / "train_only_selection_v1.jsonl"
    _write_new_jsonl(manifest_path, derived)
    selection_receipt = {
        "schema": "prta-cxr.slim-selection-manifest.v1",
        "status": "PASS_SLIM_SELECTION_MANIFEST_FROZEN",
        "created_at": _now(),
        "source_cleaned_manifest_sha256": sha256_file(args.source_cleaned_manifest),
        "cleaned_split_freeze_sha256": sha256_file(args.cleaned_split_freeze),
        "derived_manifest_sha256": sha256_file(manifest_path),
        "split_audit": split_audit,
        "selection_surface": "original Train patients only",
        "current_dev_used_for_selection": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(
        staging / "selection" / "selection_manifest_receipt.json",
        selection_receipt,
    )
    config_hashes = {}
    config_file_hashes = {}
    for experiment_id, config in sorted(configs.items()):
        path = staging / "configs" / f"{experiment_id}.json"
        _write_new_json(path, config)
        config_hashes[path.name] = canonical_sha256(config)
        config_file_hashes[path.name] = sha256_file(path)
    string_inputs = {
        "cleaned_split_freeze": str(args.cleaned_split_freeze.resolve()),
        "cleaned_split_platform_root": str(args.cleaned_split_platform_root.resolve()),
        "cache_root": str(args.cache_root.resolve()),
        "text_cache": str(args.text_cache.resolve()),
        "weights": str(args.weights.resolve()),
        "label_quality_audit": str(args.label_quality_audit.resolve()),
    }
    jobs = build_slim_jobs(configs, inputs=string_inputs)
    registry = {
        "schema": "prta-cxr.phase16-job-registry.v1",
        "status": "PASS_SLIM_JOB_REGISTRY_FROZEN",
        "jobs": jobs,
    }
    _write_new_json(staging / "job_registry.json", registry)
    assignments = allocate_lanes(jobs)
    queue_hashes = {}
    loads = {}
    for lane, queue in assignments.items():
        path = staging / "queue" / f"{lane}.json"
        _write_new_json(path, queue)
        queue_hashes[path.name] = sha256_file(path)
        loads[lane] = sum(int(job["estimated_seconds"]) for job in queue)
    preparation = {
        "schema": "prta-cxr.slim-matrix-preparation.v1",
        "status": "PASS_SLIM_MATRIX_FROZEN",
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "seeds": list(SEEDS),
        "arms": {
            arm: {"prototype_alignment": factors[0], "state_anchor": factors[1]}
            for arm, factors in SLIM_ARMS.items()
        },
        "cell_count": len(configs),
        "config_hashes": config_hashes,
        "config_file_hashes": config_file_hashes,
        "input_sha256": {role: sha256_file(path) for role, path in input_paths.items()},
        "parent_config_sha256": {
            str(value["seed"]): sha256_file(path)
            for value, path in zip(parent_values, args.v2_config, strict=True)
        },
        "selection_manifest_receipt_sha256": sha256_file(
            staging / "selection" / "selection_manifest_receipt.json"
        ),
        "derived_manifest_sha256": sha256_file(manifest_path),
        "registry_sha256": sha256_file(staging / "job_registry.json"),
        "queue_hashes": queue_hashes,
        "lane_load_estimated_seconds": loads,
        "estimated_imbalance_seconds": max(loads.values()) - min(loads.values()),
        "selection_rule": {
            "macro_f1_tolerance": 0.003,
            "oder_tolerance": 0.0005,
            "per_class_recall_tolerance": 0.01,
            "tie_break": "fewest optional modules then lexical arm ID",
            "no_admissible_fallback": "Slim-S0 no-simplification reference",
        },
        "priority": "after currently running cells; before all other Phase16 work",
        "current_dev_used_for_selection": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "preparation_receipt.json", preparation)
    staging.replace(args.output)
    print(json.dumps(preparation, indent=2, sort_keys=True))
    return 0
