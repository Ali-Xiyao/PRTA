from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.audit.tracin import (
    AuditContractError,
    assert_private_output,
    audit_path,
)
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.development_selection import _completed_runs, _write_queue
from prta_cxr.evaluation.inference import predict_loader
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.sol_rerun import validate_rerun_manifest
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules

EXPECTED_SPLITS = {"train": 80_402, "dev": 11_201}
CONDITIONS = ("true", "matched_wrong", "null", "reversed")
RUN_SPECS = (
    ("A508-S17", "prta", 17, "alignment_only_off"),
    ("A509-S17", "prta", 17, "classification_only"),
    ("B403-S28", "tila", 28, "seed_replication"),
    ("B403-S43", "tila", 43, "seed_replication"),
)
OPPOSITE_PAIRS = (
    ("Improved", "Worse"),
    ("Worse", "Improved"),
    ("New", "Resolved"),
    ("Resolved", "New"),
)
PARENT_PRTA_IDS = (
    "CLN1-PRTA-S17",
    "CLN1-PRTA-S28",
    "CLN1-PRTA-S43",
)
PARENT_B403_ID = "CLN1-B403-S17"


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
        result: set[str] = set()
        for key in keys:
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                result.add(child)
            else:
                result.update(_changed_paths(left[key], right[key], child))
        return result
    return set() if left == right else {prefix}


def build_minimum_wave_configs(
    *, prta_parent: Mapping[str, Any], b403_parent: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if prta_parent["model"]["family"] != "prta":
        raise AuditContractError("minimum-wave PRTA parent family drift")
    if b403_parent["model"]["family"] != "tila":
        raise AuditContractError("minimum-wave B403 parent family drift")
    configs = []
    for experiment_id, family, seed, variant in RUN_SPECS:
        parent = prta_parent if family == "prta" else b403_parent
        config = deepcopy(dict(parent))
        config["experiment_id"] = experiment_id
        config["seed"] = seed
        config["development_axis"] = "minimum_contribution_wave_v1"
        if variant == "alignment_only_off":
            config["loss_weights"]["alignment"] = 0.0
        elif variant == "classification_only":
            for name in ("alignment", "cmcp", "inversion", "state"):
                config["loss_weights"][name] = 0.0
        configs.append(config)

    shared = {"experiment_id", "development_axis"}
    expected_diffs = {
        "A508-S17": shared | {"loss_weights.alignment"},
        "A509-S17": shared
        | {
            "loss_weights.alignment",
            "loss_weights.cmcp",
            "loss_weights.inversion",
            "loss_weights.state",
        },
        "B403-S28": shared | {"seed"},
        "B403-S43": shared | {"seed"},
    }
    for config in configs:
        parent = (
            prta_parent
            if config["model"]["family"] == "prta"
            else b403_parent
        )
        changed = _changed_paths(parent, config)
        if changed != expected_diffs[str(config["experiment_id"])]:
            detail = f"{config['experiment_id']} {sorted(changed)}"
            raise AuditContractError(
                f"minimum-wave config drift: {detail}"
            )
        if float(config["data"]["train_fraction"]) != 1.0:
            raise AuditContractError("minimum-wave runs must use full cleaned Train")
    if [str(value["experiment_id"]) for value in configs] != [
        value[0] for value in RUN_SPECS
    ]:
        raise AuditContractError("minimum-wave config order drift")
    return configs


def prepare_minimum_wave_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the four-run PRTA minimum contribution wave"
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--quality-audit", type=Path, required=True)
    parser.add_argument("--prta-parent", type=Path, required=True)
    parser.add_argument("--b403-parent", type=Path, required=True)
    parser.add_argument("--previous-gate", type=Path, required=True)
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
        "b403_parent": args.b403_parent,
        "previous_gate": args.previous_gate,
        "output_root": args.output_root,
    }
    paths = {role: audit_path(path, role=role) for role, path in roles.items()}
    assert_private_output(paths["output_root"], repo_root)
    if paths["output_root"].exists():
        raise FileExistsError(
            f"refusing existing minimum-wave root: {paths['output_root']}"
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
    hashes_before = {role: sha256_file(path) for role, path in input_files.items()}
    rows = read_jsonl(paths["split_manifest"])
    text_cache = torch.load(
        paths["text_cache"], map_location="cpu", weights_only=True
    )
    manifest_audit = validate_rerun_manifest(
        rows,
        cache=Block8CacheIndex(paths["cache_root"]),
        text_cache=text_cache,
        expected_splits=EXPECTED_SPLITS,
    )
    prta_parent = json.loads(paths["prta_parent"].read_text(encoding="utf-8"))
    b403_parent = json.loads(paths["b403_parent"].read_text(encoding="utf-8"))
    configs = build_minimum_wave_configs(
        prta_parent=prta_parent, b403_parent=b403_parent
    )
    queue = _write_queue(
        paths["output_root"], configs, stage="minimum_contribution_wave_v1"
    )
    (paths["output_root"] / "runs").mkdir()
    previous_gate = json.loads(paths["previous_gate"].read_text(encoding="utf-8"))
    hashes_after = {role: sha256_file(path) for role, path in input_files.items()}
    if hashes_after != hashes_before:
        raise AuditContractError("minimum-wave preparation changed an input")
    receipt = {
        "schema": "prta-cxr.minimum-contribution-wave-preparation.v1",
        "status": "PASS_MINIMUM_CONTRIBUTION_WAVE_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(repo_root),
        "dataset_version": freeze["dataset_version"],
        "manifest_audit": manifest_audit,
        "run_ids": [row["experiment_id"] for row in queue],
        "queue_sha256": canonical_sha256(queue),
        "input_paths": {role: str(path) for role, path in input_files.items()},
        "input_sha256": hashes_before,
        "cleaned_split_freeze_sha256": freeze["receipt_sha256"],
        "previous_gate_status": previous_gate.get("status"),
        "previous_gate_immutable": True,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "training_started": False,
    }
    write_json_atomic(paths["output_root"] / "preparation_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def _load_dev_model(
    *,
    checkpoint_path: Path,
    split_manifest: Path,
    cache_root: Path,
    text_cache: Path,
    weights: Path,
    device: torch.device,
):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise AuditContractError("unsupported minimum-wave checkpoint")
    expected = checkpoint["input_hashes"]
    current = {
        "split_manifest": sha256_file(split_manifest),
        "cache_manifest": sha256_file(cache_root / "cache_manifest.json"),
        "text_cache": sha256_file(text_cache),
        "weights": sha256_file(weights),
    }
    if {key: expected.get(key) for key in current} != current:
        raise AuditContractError("Dev inference inputs differ from checkpoint")
    visual, _ = load_biomedclip_visual(weights)
    blocks, final_norm = tail_modules(visual)
    model = build_train_model(blocks, final_norm, checkpoint["config"])
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    return model, checkpoint, current


def predict_minimum_wave_dev_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic cleaned-Dev predictions only"
    )
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    roles = {
        "checkpoint": args.checkpoint,
        "split_manifest": args.split_manifest,
        "cleaned_split_freeze": args.cleaned_split_freeze,
        "cache_root": args.cache_root,
        "text_cache": args.text_cache,
        "weights": args.weights,
        "output_root": args.output_root,
    }
    paths = {role: audit_path(path, role=role) for role, path in roles.items()}
    assert_private_output(paths["output_root"], repo_root)
    if paths["output_root"].exists():
        raise FileExistsError(
            f"refusing existing Dev prediction root: {paths['output_root']}"
        )
    freeze = require_cleaned_manifest(
        paths["split_manifest"],
        receipt_path=paths["cleaned_split_freeze"],
        role="train_dev",
    )
    rows = read_jsonl(paths["split_manifest"])
    counts = Counter(str(row.get("split")) for row in rows)
    if dict(counts) != EXPECTED_SPLITS:
        raise AuditContractError(f"cleaned Train/Dev counts drift: {dict(counts)}")
    device = torch.device(args.device)
    model, checkpoint, input_hashes = _load_dev_model(
        checkpoint_path=paths["checkpoint"],
        split_manifest=paths["split_manifest"],
        cache_root=paths["cache_root"],
        text_cache=paths["text_cache"],
        weights=paths["weights"],
        device=device,
    )
    output_root = paths["output_root"]
    output_root.mkdir(parents=True)
    cache = Block8CacheIndex(paths["cache_root"])
    condition_receipts = {}
    experiment_id = str(checkpoint["config"]["experiment_id"])
    for condition in CONDITIONS:
        dataset = PRTAFeatureDataset(
            rows,
            cache=cache,
            text_cache_path=paths["text_cache"],
            split="dev",
            prior_intervention=condition,
        )
        loader = DataLoader(
            dataset,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=args.workers,
        )
        predictions = predict_loader(
            model,
            loader,
            device=device,
            system=experiment_id,
            seed=int(checkpoint["config"]["seed"]),
            cohort="dev",
        )
        if len(predictions) != EXPECTED_SPLITS["dev"]:
            raise AuditContractError("Dev prediction row conservation failed")
        path = output_root / f"{condition}.predictions.jsonl"
        write_jsonl_atomic(path, predictions)
        condition_receipts[condition] = {
            "rows": len(predictions),
            "prediction_sha256": sha256_file(path),
            "metrics": classification_metrics(
                predictions, labels=PROGRESSION_LABELS
            ),
        }
    receipt = {
        "schema": "prta-cxr.minimum-wave-dev-predictions.v1",
        "status": "PASS_MINIMUM_WAVE_DEV_PREDICTIONS",
        "created_at": datetime.now(UTC).isoformat(),
        "experiment_id": experiment_id,
        "checkpoint_sha256": sha256_file(paths["checkpoint"]),
        "checkpoint_best_epoch": int(checkpoint["epoch"]),
        "input_hashes": input_hashes,
        "cleaned_split_freeze_sha256": freeze["receipt_sha256"],
        "conditions": condition_receipts,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "training_started": False,
    }
    write_json_atomic(output_root / "prediction_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def _aligned_rows(
    prta_rows: Sequence[Mapping[str, Any]],
    b403_rows: Sequence[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    left = {str(row["observation_id"]): row for row in prta_rows}
    right = {str(row["observation_id"]): row for row in b403_rows}
    if len(left) != len(prta_rows) or len(right) != len(b403_rows):
        raise AuditContractError("paired predictions contain duplicate IDs")
    if set(left) != set(right):
        raise AuditContractError("paired prediction IDs differ")
    result = []
    for sample_id in sorted(left):
        one, two = left[sample_id], right[sample_id]
        keys = ("patient_id", "target", "source", "finding")
        if any(str(one[key]) != str(two[key]) for key in keys):
            raise AuditContractError(f"paired prediction metadata differs: {sample_id}")
        result.append((one, two))
    return result


def _confusion_metrics(confusion: np.ndarray) -> tuple[float, float, float]:
    tp = np.diag(confusion)
    support = confusion.sum(axis=1)
    fp = confusion.sum(axis=0) - tp
    fn = support - tp
    denominator = 2 * tp + fp + fn
    f1 = np.divide(2 * tp, denominator, out=np.zeros_like(tp), where=denominator > 0)
    total = float(confusion.sum())
    accuracy = 0.0 if total == 0 else float(tp.sum() / total)
    index = {label: offset for offset, label in enumerate(PROGRESSION_LABELS)}
    opposite = sum(confusion[index[a], index[b]] for a, b in OPPOSITE_PAIRS)
    oder = 0.0 if total == 0 else float(opposite / total)
    return float(f1.mean()), accuracy, oder


def patient_bootstrap_deltas(
    prta_rows: Sequence[Mapping[str, Any]],
    b403_rows: Sequence[Mapping[str, Any]],
    *,
    repetitions: int = 10_000,
    seed: int = 20260806,
) -> dict[str, Any]:
    if repetitions < 100:
        raise ValueError("patient bootstrap requires at least 100 repetitions")
    pairs = _aligned_rows(prta_rows, b403_rows)
    label_index = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
    patients = sorted({str(one["patient_id"]) for one, _ in pairs})
    patient_index = {patient: index for index, patient in enumerate(patients)}
    left = np.zeros((len(patients), 5, 5), dtype=np.float64)
    right = np.zeros_like(left)
    for one, two in pairs:
        patient = patient_index[str(one["patient_id"])]
        target = label_index[str(one["target"])]
        left[patient, target, label_index[str(one["prediction"])]] += 1.0
        right[patient, target, label_index[str(two["prediction"])]] += 1.0
    rng = np.random.default_rng(seed)
    deltas = np.empty((repetitions, 3), dtype=np.float64)
    for iteration in range(repetitions):
        sampled = rng.integers(0, len(patients), size=len(patients))
        one = _confusion_metrics(left[sampled].sum(axis=0))
        two = _confusion_metrics(right[sampled].sum(axis=0))
        deltas[iteration] = np.asarray(one) - np.asarray(two)
    names = ("macro_f1", "accuracy", "opposite_direction_error_rate")
    result = {}
    for offset, name in enumerate(names):
        values = deltas[:, offset]
        result[name] = {
            "mean_delta": float(values.mean()),
            "ci95_low": float(np.quantile(values, 0.025)),
            "ci95_high": float(np.quantile(values, 0.975)),
            "probability_delta_le_zero": float(
                (np.sum(values <= 0) + 1) / (repetitions + 1)
            ),
        }
    result.update(
        {
            "patients": len(patients),
            "rows": len(pairs),
            "repetitions": repetitions,
            "seed": seed,
        }
    )
    return result


def _stratum_summary(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], key: str
) -> list[dict[str, Any]]:
    grouped: dict[
        str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]
    ] = defaultdict(list)
    for pair in pairs:
        grouped[str(pair[0][key])].append(pair)
    result = []
    for value, rows in sorted(grouped.items()):
        prta_correct = sum(one["prediction"] == one["target"] for one, _ in rows)
        b403_correct = sum(two["prediction"] == two["target"] for _, two in rows)
        result.append(
            {
                key: value,
                "rows": len(rows),
                "prta_accuracy": prta_correct / len(rows),
                "b403_accuracy": b403_correct / len(rows),
                "prta_minus_b403_accuracy": (prta_correct - b403_correct) / len(rows),
                "prta_only_correct": sum(
                    one["prediction"] == one["target"]
                    and two["prediction"] != two["target"]
                    for one, two in rows
                ),
                "b403_only_correct": sum(
                    two["prediction"] == two["target"]
                    and one["prediction"] != one["target"]
                    for one, two in rows
                ),
            }
        )
    return result


def analyze_minimum_wave_dev_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pair PRTA and B403 cleaned-Dev predictions"
    )
    parser.add_argument("--prta-root", type=Path, required=True)
    parser.add_argument("--b403-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260806)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    paths = {
        role: audit_path(path, role=role)
        for role, path in {
            "prta_root": args.prta_root,
            "b403_root": args.b403_root,
            "output_root": args.output_root,
        }.items()
    }
    assert_private_output(paths["output_root"], repo_root)
    if paths["output_root"].exists():
        raise FileExistsError(
            f"refusing existing paired analysis: {paths['output_root']}"
        )
    receipts = {
        name: json.loads(
            (paths[f"{name}_root"] / "prediction_receipt.json").read_text(
                "utf-8"
            )
        )
        for name in ("prta", "b403")
    }
    if any(
        value.get("status") != "PASS_MINIMUM_WAVE_DEV_PREDICTIONS"
        for value in receipts.values()
    ):
        raise AuditContractError("paired prediction receipt is not PASS")
    condition_rows = {}
    for condition in CONDITIONS:
        condition_rows[condition] = {
            name: read_jsonl(paths[f"{name}_root"] / f"{condition}.predictions.jsonl")
            for name in ("prta", "b403")
        }
        if any(
            len(rows) != EXPECTED_SPLITS["dev"]
            for rows in condition_rows[condition].values()
        ):
            raise AuditContractError("paired Dev row conservation failed")
        _aligned_rows(
            condition_rows[condition]["prta"], condition_rows[condition]["b403"]
        )
    true_pairs = _aligned_rows(
        condition_rows["true"]["prta"], condition_rows["true"]["b403"]
    )
    disagreements = []
    direction_rows = []
    for one, two in true_pairs:
        one_correct = one["prediction"] == one["target"]
        two_correct = two["prediction"] == two["target"]
        if one_correct != two_correct:
            disagreements.append(
                {
                    "observation_id": one["observation_id"],
                    "patient_id": one["patient_id"],
                    "source": one["source"],
                    "finding": one["finding"],
                    "target": one["target"],
                    "prta_prediction": one["prediction"],
                    "b403_prediction": two["prediction"],
                    "winner": "prta" if one_correct else "b403",
                }
            )
        for system, row in (("prta", one), ("b403", two)):
            if (str(row["target"]), str(row["prediction"])) in OPPOSITE_PAIRS:
                direction_rows.append(
                    {
                        "system": system,
                        "observation_id": row["observation_id"],
                        "patient_id": row["patient_id"],
                        "source": row["source"],
                        "finding": row["finding"],
                        "target": row["target"],
                        "prediction": row["prediction"],
                    }
                )
    condition_summary = {}
    for condition, systems in condition_rows.items():
        condition_summary[condition] = {}
        for name, rows in systems.items():
            metrics = classification_metrics(rows, labels=PROGRESSION_LABELS)[
                "ordinary"
            ]
            condition_summary[condition][name] = {
                "macro_f1": metrics["macro_f1"],
                "accuracy": metrics["accuracy"],
                "opposite_direction_error_rate": metrics[
                    "opposite_direction_error_rate"
                ],
            }
    true_metrics = condition_summary["true"]
    for condition in CONDITIONS[1:]:
        for name in ("prta", "b403"):
            condition_summary[condition][name]["macro_f1_drop_from_true"] = (
                true_metrics[name]["macro_f1"]
                - condition_summary[condition][name]["macro_f1"]
            )
    direction_counts = Counter(
        (str(row["system"]), str(row["target"]), str(row["prediction"]))
        for row in direction_rows
    )
    summary = {
        "schema": "prta-cxr.minimum-wave-paired-dev-analysis.v1",
        "status": "PASS_MINIMUM_WAVE_PAIRED_DEV_ANALYSIS",
        "created_at": datetime.now(UTC).isoformat(),
        "systems": {
            "prta": receipts["prta"]["experiment_id"],
            "b403": receipts["b403"]["experiment_id"],
        },
        "rows": len(true_pairs),
        "patients": len({str(one["patient_id"]) for one, _ in true_pairs}),
        "true_condition": {
            "prta": true_metrics["prta"],
            "b403": true_metrics["b403"],
            "macro_f1_delta": true_metrics["prta"]["macro_f1"]
            - true_metrics["b403"]["macro_f1"],
        },
        "patient_bootstrap": patient_bootstrap_deltas(
            condition_rows["true"]["prta"],
            condition_rows["true"]["b403"],
            repetitions=args.bootstrap_repetitions,
            seed=args.bootstrap_seed,
        ),
        "paired_correctness": {
            "prta_only_correct": sum(row["winner"] == "prta" for row in disagreements),
            "b403_only_correct": sum(row["winner"] == "b403" for row in disagreements),
            "both_correct": sum(
                one["prediction"] == one["target"]
                and two["prediction"] == two["target"]
                for one, two in true_pairs
            ),
            "both_wrong": sum(
                one["prediction"] != one["target"]
                and two["prediction"] != two["target"]
                for one, two in true_pairs
            ),
        },
        "opposite_direction_counts": [
            {
                "system": system,
                "target": target,
                "prediction": prediction,
                "count": count,
            }
            for (system, target, prediction), count in sorted(direction_counts.items())
        ],
        "by_source": _stratum_summary(true_pairs, "source"),
        "by_finding": _stratum_summary(true_pairs, "finding"),
        "by_class": _stratum_summary(true_pairs, "target"),
        "prior_interventions": condition_summary,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "training_started": False,
    }
    output_root = paths["output_root"]
    output_root.mkdir(parents=True)
    write_jsonl_atomic(output_root / "paired_disagreements.jsonl", disagreements)
    write_jsonl_atomic(output_root / "opposite_direction_errors.jsonl", direction_rows)
    write_json_atomic(output_root / "paired_analysis.json", summary)
    hashes = {
        name: sha256_file(output_root / name)
        for name in (
            "paired_disagreements.jsonl",
            "opposite_direction_errors.jsonl",
            "paired_analysis.json",
        )
    }
    receipt = {
        "schema": "prta-cxr.minimum-wave-paired-dev-receipt.v1",
        "status": summary["status"],
        "output_sha256": hashes,
        "input_prediction_receipt_sha256": {
            name: sha256_file(paths[f"{name}_root"] / "prediction_receipt.json")
            for name in ("prta", "b403")
        },
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(output_root / "audit_receipt.json", receipt)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _best_history_metrics(receipt: Mapping[str, Any]) -> dict[str, float]:
    best_epoch = int(receipt["best_epoch"])
    matches = [
        row for row in receipt["history"] if int(row["epoch"]) == best_epoch
    ]
    if len(matches) != 1:
        raise AuditContractError("training receipt best epoch is not unique")
    row = matches[0]
    result = {
        "macro_f1": float(row["macro_f1"]),
        "accuracy": float(row["accuracy"]),
        "balanced_accuracy": float(row["balanced_accuracy"]),
        "min_class_recall": float(row["min_class_recall"]),
        "opposite_direction_error_rate": float(
            row["opposite_direction_error_rate"]
        ),
        "nll": float(row["nll"]),
        "true_minus_wrong_prior_gap": float(
            receipt["dev_prior_audit"]["true_minus_wrong_prior_gap"]
        ),
    }
    if not np.isfinite(list(result.values())).all():
        raise AuditContractError("training receipt contains non-finite metrics")
    if not np.isclose(result["macro_f1"], receipt["best_dev_macro_f1"]):
        raise AuditContractError("training receipt best metric is inconsistent")
    return result


def _validate_training_receipts(
    receipts: Mapping[str, Mapping[str, Any]], expected_ids: Sequence[str]
) -> None:
    if set(receipts) != set(expected_ids):
        raise AuditContractError("minimum-wave receipt identity mismatch")
    for experiment_id in expected_ids:
        receipt = receipts[experiment_id]
        if receipt.get("status") != "PASS_TRAINING_FINISHED":
            raise AuditContractError(f"incomplete receipt: {experiment_id}")
        if receipt.get("protected_outcomes_opened") is not False:
            raise AuditContractError(f"protected outcome opened: {experiment_id}")
        if receipt.get("internal_test_opened") is not False:
            raise AuditContractError(f"Internal-test opened: {experiment_id}")
        _best_history_metrics(receipt)


def build_minimum_wave_decision(
    *,
    previous_gate: Mapping[str, Any],
    parent_receipts: Mapping[str, Mapping[str, Any]],
    wave_receipts: Mapping[str, Mapping[str, Any]],
    paired_analysis: Mapping[str, Any],
) -> dict[str, Any]:
    if previous_gate.get("status") != "HOLD_DEVELOPMENT_GATE":
        raise AuditContractError("previous development gate is not immutable HOLD")
    expected_parent = (*PARENT_PRTA_IDS, PARENT_B403_ID)
    expected_wave = tuple(spec[0] for spec in RUN_SPECS)
    _validate_training_receipts(parent_receipts, expected_parent)
    _validate_training_receipts(wave_receipts, expected_wave)
    if paired_analysis.get("status") != "PASS_MINIMUM_WAVE_PAIRED_DEV_ANALYSIS":
        raise AuditContractError("paired Dev analysis is not PASS")
    if paired_analysis.get("protected_outcome_read_count") != 0:
        raise AuditContractError("paired analysis read a protected outcome")
    if paired_analysis.get("internal_test_opened") is not False:
        raise AuditContractError("paired analysis opened Internal-test")
    if paired_analysis.get("gold_opened") is not False:
        raise AuditContractError("paired analysis opened Gold")

    prta_metrics = {
        experiment_id: _best_history_metrics(parent_receipts[experiment_id])
        for experiment_id in PARENT_PRTA_IDS
    }
    b403_receipts = {
        PARENT_B403_ID: parent_receipts[PARENT_B403_ID],
        "B403-S28": wave_receipts["B403-S28"],
        "B403-S43": wave_receipts["B403-S43"],
    }
    b403_metrics = {
        experiment_id: _best_history_metrics(receipt)
        for experiment_id, receipt in b403_receipts.items()
    }
    prta_values = [row["macro_f1"] for row in prta_metrics.values()]
    b403_values = [row["macro_f1"] for row in b403_metrics.values()]
    if not np.allclose(prta_values, previous_gate["seed_macro_f1"]):
        raise AuditContractError("previous PRTA seed metrics changed")

    bootstrap = paired_analysis["patient_bootstrap"]
    macro_ci = bootstrap["macro_f1"]
    oder_ci = bootstrap["opposite_direction_error_rate"]
    interventions = paired_analysis["prior_interventions"]
    intervention_names = ("matched_wrong", "null", "reversed")
    mechanism_drop_advantage = all(
        float(interventions[name]["prta"]["macro_f1_drop_from_true"])
        < float(interventions[name]["b403"]["macro_f1_drop_from_true"])
        for name in intervention_names
    )
    paired_performance_advantage = float(macro_ci["ci95_low"]) > 0.0
    paired_oder_not_worse = float(oder_ci["ci95_high"]) <= 0.0
    performance_advantage = (
        paired_performance_advantage
        and paired_oder_not_worse
        and float(np.mean(prta_values)) > float(np.mean(b403_values))
    )
    mechanism_trust_advantage = (
        mechanism_drop_advantage and paired_oder_not_worse
    )
    comparable_performance = (
        float(macro_ci["ci95_low"]) <= 0.0 <= float(macro_ci["ci95_high"])
    )
    if performance_advantage:
        decision = "PRTA_ADVANTAGE"
        supported_claim = "PRTA classification advantage with non-worse ODER"
    elif comparable_performance and mechanism_trust_advantage:
        decision = "COMPARABLE_WITH_MECHANISM_TRUST_ADVANTAGE"
        supported_claim = "Comparable classification with mechanism/trust advantage"
    else:
        decision = "STOP_CURRENT_PRTA_ROUTE"
        supported_claim = (
            "No independent PRTA performance or mechanism/trust advantage"
        )

    ablations = {
        experiment_id: _best_history_metrics(wave_receipts[experiment_id])
        for experiment_id in ("A508-S17", "A509-S17")
    }
    full_seed17 = prta_metrics["CLN1-PRTA-S17"]
    for metrics in ablations.values():
        metrics["macro_f1_delta_vs_full_prta_s17"] = (
            metrics["macro_f1"] - full_seed17["macro_f1"]
        )
        metrics["oder_delta_vs_full_prta_s17"] = (
            metrics["opposite_direction_error_rate"]
            - full_seed17["opposite_direction_error_rate"]
        )
    return {
        "schema": "prta-cxr.minimum-contribution-wave-decision.v1",
        "status": "PASS_MINIMUM_CONTRIBUTION_WAVE_FINALIZED",
        "decision": decision,
        "supported_claim": supported_claim,
        "previous_development_gate_status": previous_gate["status"],
        "previous_hold_unchanged": True,
        "prta_three_seed": {
            "experiment_ids": list(PARENT_PRTA_IDS),
            "macro_f1": prta_values,
            "mean": float(np.mean(prta_values)),
            "sample_sd": float(np.std(prta_values, ddof=1)),
            "mean_oder": float(
                np.mean(
                    [
                        row["opposite_direction_error_rate"]
                        for row in prta_metrics.values()
                    ]
                )
            ),
        },
        "b403_three_seed": {
            "experiment_ids": list(b403_metrics),
            "macro_f1": b403_values,
            "mean": float(np.mean(b403_values)),
            "sample_sd": float(np.std(b403_values, ddof=1)),
            "mean_oder": float(
                np.mean(
                    [
                        row["opposite_direction_error_rate"]
                        for row in b403_metrics.values()
                    ]
                )
            ),
        },
        "prta_minus_b403_mean_macro_f1": float(
            np.mean(prta_values) - np.mean(b403_values)
        ),
        "paired_seed17": {
            "macro_f1_delta": paired_analysis["true_condition"][
                "macro_f1_delta"
            ],
            "macro_f1_ci95": [
                macro_ci["ci95_low"],
                macro_ci["ci95_high"],
            ],
            "oder_delta_ci95": [
                oder_ci["ci95_low"],
                oder_ci["ci95_high"],
            ],
            "comparable_performance": comparable_performance,
            "paired_performance_advantage": paired_performance_advantage,
            "paired_oder_not_worse": paired_oder_not_worse,
        },
        "mechanism": {
            "prta_has_smaller_drop_for_all_interventions": (
                mechanism_drop_advantage
            ),
            "mechanism_trust_advantage": mechanism_trust_advantage,
            "prior_interventions": interventions,
        },
        "ablations_seed17": ablations,
        "checks": {
            "performance_advantage": performance_advantage,
            "comparable_performance": comparable_performance,
            "mechanism_trust_advantage": mechanism_trust_advantage,
            "all_training_receipts_pass": True,
            "previous_hold_preserved": True,
            "protected_outcome_read_count_zero": True,
        },
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
        "training_started_by_finalizer": False,
    }


def finalize_minimum_wave_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Finalize the PRTA minimum contribution wave"
    )
    parser.add_argument("--run-registry", type=Path, required=True)
    parser.add_argument("--parent-run-registry", type=Path, required=True)
    parser.add_argument("--preparation-receipt", type=Path, required=True)
    parser.add_argument("--scheduler-receipt", type=Path, required=True)
    parser.add_argument("--previous-gate", type=Path, required=True)
    parser.add_argument("--paired-analysis", type=Path, required=True)
    parser.add_argument("--paired-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    paths = {
        role: audit_path(path, role=role)
        for role, path in {
            "run_registry": args.run_registry,
            "parent_run_registry": args.parent_run_registry,
            "preparation_receipt": args.preparation_receipt,
            "scheduler_receipt": args.scheduler_receipt,
            "previous_gate": args.previous_gate,
            "paired_analysis": args.paired_analysis,
            "paired_receipt": args.paired_receipt,
            "output": args.output,
        }.items()
    }
    assert_private_output(paths["output"].parent, repo_root)
    if paths["output"].exists():
        raise FileExistsError(f"refusing existing decision: {paths['output']}")
    preparation = json.loads(
        paths["preparation_receipt"].read_text(encoding="utf-8")
    )
    scheduler = json.loads(paths["scheduler_receipt"].read_text(encoding="utf-8"))
    previous_gate = json.loads(paths["previous_gate"].read_text(encoding="utf-8"))
    paired_analysis = json.loads(
        paths["paired_analysis"].read_text(encoding="utf-8")
    )
    paired_receipt = json.loads(
        paths["paired_receipt"].read_text(encoding="utf-8")
    )
    expected_wave = [spec[0] for spec in RUN_SPECS]
    if preparation.get("status") != "PASS_MINIMUM_CONTRIBUTION_WAVE_PREPARED":
        raise AuditContractError("minimum-wave preparation is not PASS")
    if preparation.get("run_ids") != expected_wave:
        raise AuditContractError("minimum-wave preparation IDs changed")
    if preparation.get("previous_gate_immutable") is not True:
        raise AuditContractError("previous development gate was not frozen")
    if sha256_file(paths["previous_gate"]) != preparation["input_sha256"][
        "previous_gate"
    ]:
        raise AuditContractError("previous development gate hash changed")
    if scheduler.get("status") != "PASS_TRAINING_QUEUE_FINISHED":
        raise AuditContractError("minimum-wave scheduler is not PASS")
    if scheduler.get("total") != 4 or scheduler.get("completed") != 4:
        raise AuditContractError("minimum-wave scheduler row count mismatch")
    if scheduler.get("internal_test_opened") is not False:
        raise AuditContractError("scheduler opened Internal-test")
    if scheduler.get("gold_opened") is not False:
        raise AuditContractError("scheduler opened Gold")
    if paired_receipt.get("status") != "PASS_MINIMUM_WAVE_PAIRED_DEV_ANALYSIS":
        raise AuditContractError("paired-analysis receipt is not PASS")
    if paired_receipt.get("protected_outcome_read_count") != 0:
        raise AuditContractError("paired-analysis receipt has protected reads")
    if sha256_file(paths["paired_analysis"]) != paired_receipt["output_sha256"][
        "paired_analysis.json"
    ]:
        raise AuditContractError("paired-analysis output hash changed")

    wave_receipts, _ = _completed_runs(paths["run_registry"])
    parent_all, _ = _completed_runs(paths["parent_run_registry"])
    parent_receipts = {
        experiment_id: parent_all[experiment_id]
        for experiment_id in (*PARENT_PRTA_IDS, PARENT_B403_ID)
    }
    decision = build_minimum_wave_decision(
        previous_gate=previous_gate,
        parent_receipts=parent_receipts,
        wave_receipts=wave_receipts,
        paired_analysis=paired_analysis,
    )
    decision["created_at"] = datetime.now(UTC).isoformat()
    decision["git_commit"] = _git_commit(repo_root)
    decision["input_sha256"] = {
        role: sha256_file(path)
        for role, path in paths.items()
        if role != "output"
    }
    write_json_atomic(paths["output"], decision)
    receipt = {
        "schema": "prta-cxr.minimum-contribution-wave-finalization-receipt.v1",
        "status": decision["status"],
        "decision": decision["decision"],
        "decision_sha256": sha256_file(paths["output"]),
        "input_sha256": decision["input_sha256"],
        "run_count": 4,
        "dev_rows": int(paired_analysis["rows"]),
        "dev_patients": int(paired_analysis["patients"]),
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    receipt_path = paths["output"].with_name("finalization_receipt.json")
    write_json_atomic(receipt_path, receipt)
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0
