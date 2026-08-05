from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.evaluation.inference import predict_loader
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules

ACTIVE_COUNTS = {
    "train": 89_406,
    "dev": 13_420,
    "internal_test": 13_588,
    "gold": 250,
}
EXCLUDED_COUNTS = {
    "train": 9_004,
    "dev": 2_219,
    "internal_test": 369,
    "gold": 75,
}
RETAINED_COUNTS = {
    split: ACTIVE_COUNTS[split] - EXCLUDED_COUNTS[split]
    for split in ACTIVE_COUNTS
}
BAND_COUNTS = {"Top 3%": 3_500, "3-5%": 2_334, "5-10%": 5_833}
DIAGNOSTIC_RUN_ID = "RISKF10-PRTA-S17"


class RiskFilterContractError(ValueError):
    pass


def _git_commit(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_risk_candidates(
    path: Path,
    *,
    expected_splits: Mapping[str, int] = EXCLUDED_COUNTS,
    expected_bands: Mapping[str, int] = BAND_COUNTS,
) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    required = {
        "sample_id",
        "split",
        "rank_global",
        "priority_band",
        "candidate_reasons",
        "active_inclusion",
    }
    if not rows or required - set(rows[0]):
        raise RiskFilterContractError("risk candidate CSV lacks required fields")
    sample_ids = [str(row["sample_id"]) for row in rows]
    if not all(sample_ids) or len(set(sample_ids)) != len(sample_ids):
        raise RiskFilterContractError("risk candidate sample IDs are not unique")
    ranks = [int(row["rank_global"]) for row in rows]
    if sorted(ranks) != list(range(1, len(rows) + 1)):
        raise RiskFilterContractError("global risk ranks are not contiguous")
    if any(str(row["active_inclusion"]).lower() != "true" for row in rows):
        raise RiskFilterContractError("candidate lies outside the active universe")
    split_counts = Counter(str(row["split"]) for row in rows)
    band_counts = Counter(str(row["priority_band"]) for row in rows)
    if dict(split_counts) != dict(expected_splits):
        raise RiskFilterContractError(
            f"risk split counts differ: {dict(split_counts)}"
        )
    if dict(band_counts) != dict(expected_bands):
        raise RiskFilterContractError(
            f"risk band counts differ: {dict(band_counts)}"
        )
    return sorted(rows, key=lambda row: int(row["rank_global"]))


def build_diagnostic_config(
    parent: Mapping[str, Any],
    *,
    train_label_counts: Mapping[str, int],
    exclusion_sha256: str,
) -> dict[str, Any]:
    config = deepcopy(dict(parent))
    if config.get("model", {}).get("family") != "prta":
        raise RiskFilterContractError("diagnostic parent must be PRTA")
    config["experiment_id"] = DIAGNOSTIC_RUN_ID
    config["seed"] = 17
    config["development_axis"] = "posthoc_global_top10_risk_exclusion"
    config["classification_loss"]["class_counts"] = [
        int(train_label_counts[label]) for label in PROGRESSION_LABELS
    ]
    config["diagnostic_metadata"] = {
        "selection": "global_top10_risk_union",
        "review_status": "SUSPICIOUS_PENDING_REVIEW",
        "excluded_rows": sum(EXCLUDED_COUNTS.values()),
        "retained_rows": sum(RETAINED_COUNTS.values()),
        "candidate_sha256": exclusion_sha256,
        "outcome_adaptive_selection_bias": True,
        "formal_result_replacement": False,
    }
    return config


def _filter_jsonl_byte_exact(
    source: Path,
    output: Path,
    *,
    candidate_index: Mapping[str, Mapping[str, str]],
    allowed_splits: set[str],
    implicit_split: str | None = None,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
    seen: set[str] = set()
    removed: set[str] = set()
    retained_ids: set[str] = set()
    split_counts: Counter[str] = Counter()
    label_counts: dict[str, Counter[str]] = {
        split: Counter() for split in allowed_splits
    }
    patient_splits: dict[str, str] = {}
    try:
        with Path(source).open("rb") as reader, temporary.open("wb") as writer:
            for line_number, line in enumerate(reader, start=1):
                if not line.strip():
                    continue
                row = json.loads(line.decode("utf-8"))
                sample_id = str(row.get("sample_id", ""))
                if not sample_id or sample_id in seen:
                    raise RiskFilterContractError(
                        f"invalid/duplicate sample ID at {source}:{line_number}"
                    )
                seen.add(sample_id)
                split = str(row.get("split", implicit_split or ""))
                if split not in allowed_splits:
                    raise RiskFilterContractError(
                        f"unexpected split {split!r} at {source}:{line_number}"
                    )
                target = candidate_index.get(sample_id)
                if target is not None:
                    if str(target["split"]) != split:
                        raise RiskFilterContractError(
                            f"risk/source split mismatch for {sample_id}"
                        )
                    removed.add(sample_id)
                    continue
                retained_ids.add(sample_id)
                split_counts[split] += 1
                label_key = "human_label" if split == "gold" else "progression_label"
                label = str(row.get(label_key, ""))
                if label not in PROGRESSION_LABELS:
                    raise RiskFilterContractError(
                        f"invalid retained label for {sample_id}: {label!r}"
                    )
                label_counts[split][label] += 1
                if split in {"train", "dev"}:
                    patient = str(row.get("patient_id_hash", ""))
                    previous = patient_splits.setdefault(patient, split)
                    if not patient or previous != split:
                        raise RiskFilterContractError(
                            "patient leakage across retained Train and Dev"
                        )
                writer.write(line if line.endswith(b"\n") else line + b"\n")
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "source_rows": len(seen),
        "retained_rows": len(retained_ids),
        "removed_rows": len(removed),
        "seen_ids": seen,
        "retained_ids": retained_ids,
        "removed_ids": removed,
        "split_counts": dict(split_counts),
        "label_counts": {
            split: dict(sorted(counts.items()))
            for split, counts in label_counts.items()
        },
        "patient_splits": patient_splits,
    }


def _write_exclusion_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "sample_id",
        "split",
        "rank_global",
        "priority_band",
        "candidate_score",
        "candidate_reasons",
        "review_status",
        "diagnostic_action",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in fields} for row in rows
        )


def prepare_risk_filter_diagnostic_main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a post-hoc global Top-10% risk exclusion diagnostic"
    )
    parser.add_argument("--candidate-top10-csv", type=Path, required=True)
    parser.add_argument("--train-dev-manifest", type=Path, required=True)
    parser.add_argument("--internal-test-manifest", type=Path, required=True)
    parser.add_argument("--gold-manifest", type=Path, required=True)
    parser.add_argument("--parent-config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--confirm-posthoc-selection-bias", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_posthoc_selection_bias:
        raise RiskFilterContractError(
            "explicit --confirm-posthoc-selection-bias is required"
        )
    repo_root = Path(__file__).resolve().parents[2]
    output_root = args.output_root.resolve()
    try:
        output_root.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise RiskFilterContractError("private diagnostic output must stay outside Git")
    if output_root.exists():
        raise FileExistsError(f"refusing existing output root: {output_root}")
    inputs = {
        "candidate_top10_csv": args.candidate_top10_csv.resolve(),
        "train_dev_manifest": args.train_dev_manifest.resolve(),
        "internal_test_manifest": args.internal_test_manifest.resolve(),
        "gold_manifest": args.gold_manifest.resolve(),
        "parent_config": args.parent_config.resolve(),
    }
    hashes_before = {name: sha256_file(path) for name, path in inputs.items()}
    candidates = load_risk_candidates(inputs["candidate_top10_csv"])
    candidate_index = {str(row["sample_id"]): row for row in candidates}
    marked = [
        {
            **row,
            "review_status": "SUSPICIOUS_PENDING_REVIEW",
            "diagnostic_action": "EXCLUDED_FROM_TOP10_POSTHOC_DIAGNOSTIC",
            "proven_error": False,
        }
        for row in candidates
    ]
    output_root.mkdir(parents=True)
    private = output_root / "private"
    private.mkdir()
    roster_jsonl = private / "suspicious_pending_review.jsonl"
    roster_csv = private / "suspicious_pending_review.csv"
    write_jsonl_atomic(roster_jsonl, marked)
    _write_exclusion_csv(roster_csv, marked)
    train_dev_output = private / "train_dev_retained_top10_excluded.jsonl"
    internal_output = private / "internal_test_retained_top10_excluded.jsonl"
    gold_output = private / "gold_retained_top10_excluded.jsonl"
    train_dev = _filter_jsonl_byte_exact(
        inputs["train_dev_manifest"],
        train_dev_output,
        candidate_index=candidate_index,
        allowed_splits={"train", "dev"},
    )
    internal = _filter_jsonl_byte_exact(
        inputs["internal_test_manifest"],
        internal_output,
        candidate_index=candidate_index,
        allowed_splits={"internal_test"},
    )
    gold = _filter_jsonl_byte_exact(
        inputs["gold_manifest"],
        gold_output,
        candidate_index=candidate_index,
        allowed_splits={"gold"},
        implicit_split="gold",
    )
    audits = {"train_dev": train_dev, "internal_test": internal, "gold": gold}
    seen_union = set().union(*(audit["seen_ids"] for audit in audits.values()))
    retained_union = set().union(
        *(audit["retained_ids"] for audit in audits.values())
    )
    removed_union = set().union(
        *(audit["removed_ids"] for audit in audits.values())
    )
    if len(seen_union) != sum(ACTIVE_COUNTS.values()):
        raise RiskFilterContractError("active universe ID conservation failed")
    if removed_union != set(candidate_index):
        raise RiskFilterContractError("not every Top-10% candidate was excluded")
    if retained_union.intersection(candidate_index):
        raise RiskFilterContractError("risk candidate remains in retained manifests")
    retained_counts = {
        **train_dev["split_counts"],
        **internal["split_counts"],
        **gold["split_counts"],
    }
    if retained_counts != RETAINED_COUNTS:
        raise RiskFilterContractError(
            f"retained split counts differ: {retained_counts}"
        )
    if any(
        set(audit["label_counts"][split]) != set(PROGRESSION_LABELS)
        for audit in audits.values()
        for split in audit["label_counts"]
    ):
        raise RiskFilterContractError("retained split lacks a progression class")
    train_counts = train_dev["label_counts"]["train"]
    parent = json.loads(inputs["parent_config"].read_text(encoding="utf-8"))
    config = build_diagnostic_config(
        parent,
        train_label_counts=train_counts,
        exclusion_sha256=hashes_before["candidate_top10_csv"],
    )
    config_path = output_root / "config.json"
    write_json_atomic(config_path, config)
    hashes_after = {name: sha256_file(path) for name, path in inputs.items()}
    if hashes_after != hashes_before:
        raise RiskFilterContractError("preparation mutated an immutable input")
    output_hashes = {
        "exclusion_jsonl": sha256_file(roster_jsonl),
        "exclusion_csv": sha256_file(roster_csv),
        "train_dev": sha256_file(train_dev_output),
        "internal_test": sha256_file(internal_output),
        "gold": sha256_file(gold_output),
        "config": sha256_file(config_path),
    }
    result = {
        "schema": "prta-cxr.top10-risk-exclusion-preparation.v1",
        "status": "PASS_TOP10_RISK_EXCLUSION_DIAGNOSTIC_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(repo_root),
        "run_id": DIAGNOSTIC_RUN_ID,
        "review_status": "SUSPICIOUS_PENDING_REVIEW",
        "selection": {
            "mode": "single_global_ranking_without_split_quotas",
            "bands": dict(BAND_COUNTS),
            "excluded_union": len(candidate_index),
            "strictly_nested_source": True,
        },
        "active_counts": dict(ACTIVE_COUNTS),
        "excluded_counts": dict(EXCLUDED_COUNTS),
        "retained_counts": retained_counts,
        "retained_total": len(retained_union),
        "input_paths": {name: str(path) for name, path in inputs.items()},
        "input_sha256": hashes_before,
        "output_paths": {
            "exclusion_jsonl": str(roster_jsonl.resolve()),
            "exclusion_csv": str(roster_csv.resolve()),
            "train_dev": str(train_dev_output.resolve()),
            "internal_test": str(internal_output.resolve()),
            "gold": str(gold_output.resolve()),
            "config": str(config_path.resolve()),
        },
        "output_sha256": output_hashes,
        "train_label_counts": train_counts,
        "patient_overlap_train_dev": 0,
        "retained_fields_rewritten": 0,
        "original_artifacts_mutated": False,
        "outcome_adaptive_selection_bias": True,
        "formal_result_replacement": False,
        "training_started": False,
    }
    write_json_atomic(output_root / "preparation_receipt.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _cohort_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = classification_metrics(rows, labels=PROGRESSION_LABELS)
    return {
        "rows": values["rows"],
        "patients": values["patients"],
        "accuracy": values["ordinary"]["accuracy"],
        "macro_f1": values["ordinary"]["macro_f1"],
        "balanced_accuracy": values["ordinary"]["balanced_accuracy"],
        "min_class_recall": values["ordinary"]["min_class_recall"],
        "opposite_direction_error_rate": values["ordinary"][
            "opposite_direction_error_rate"
        ],
        "ordinary": values["ordinary"],
        "patient_balanced": values["patient_balanced"],
    }


def evaluate_risk_filter_diagnostic_main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the post-hoc Top-10%-excluded diagnostic"
    )
    parser.add_argument("--preparation-receipt", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--main-cache-root", type=Path, required=True)
    parser.add_argument("--gold-cache-root", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--confirm-posthoc-selection-bias", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_posthoc_selection_bias:
        raise RiskFilterContractError(
            "explicit --confirm-posthoc-selection-bias is required"
        )
    if args.output_root.exists():
        raise FileExistsError(
            f"refusing existing evaluation output: {args.output_root}"
        )
    preparation = json.loads(args.preparation_receipt.read_text(encoding="utf-8"))
    training = json.loads(args.training_receipt.read_text(encoding="utf-8"))
    if preparation.get("status") != (
        "PASS_TOP10_RISK_EXCLUSION_DIAGNOSTIC_PREPARED"
    ):
        raise RiskFilterContractError("preparation receipt is not PASS")
    if training.get("status") != "PASS_TRAINING_FINISHED":
        raise RiskFilterContractError("training receipt is not PASS")
    if training.get("internal_test_opened") or training.get(
        "protected_outcomes_opened"
    ):
        raise RiskFilterContractError("training opened a protected outcome")
    output_paths = {
        name: Path(path) for name, path in preparation["output_paths"].items()
    }
    for name in ("train_dev", "internal_test", "gold", "config"):
        if sha256_file(output_paths[name]) != preparation["output_sha256"][name]:
            raise RiskFilterContractError(f"prepared output hash changed: {name}")
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise RiskFilterContractError("unsupported diagnostic checkpoint")
    if checkpoint["input_hashes"]["split_manifest"] != preparation[
        "output_sha256"
    ]["train_dev"]:
        raise RiskFilterContractError("checkpoint used a different Train/Dev manifest")
    expected_inputs = {
        "weights": sha256_file(args.weights),
        "cache_manifest": sha256_file(args.main_cache_root / "cache_manifest.json"),
        "text_cache": sha256_file(args.main_cache_root / "text_cache.pt"),
    }
    if any(
        checkpoint["input_hashes"][name] != value
        for name, value in expected_inputs.items()
    ):
        raise RiskFilterContractError("checkpoint model/cache input hash mismatch")
    device = torch.device(args.device)
    visual, _ = load_biomedclip_visual(args.weights)
    blocks, final_norm = tail_modules(visual)
    model = build_train_model(blocks, final_norm, checkpoint["config"])
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    main_rows = read_jsonl(output_paths["train_dev"])
    internal_rows = read_jsonl(output_paths["internal_test"])
    gold_rows = [
        {**row, "split": "gold"} for row in read_jsonl(output_paths["gold"])
    ]
    main_cache = Block8CacheIndex(args.main_cache_root)
    gold_cache = Block8CacheIndex(args.gold_cache_root)
    specs = {
        "dev": (
            main_rows,
            main_cache,
            args.main_cache_root / "text_cache.pt",
            "progression_label",
        ),
        "internal_test": (
            internal_rows,
            main_cache,
            args.main_cache_root / "text_cache.pt",
            "progression_label",
        ),
        "gold": (
            gold_rows,
            gold_cache,
            args.gold_cache_root / "text_cache.pt",
            "human_label",
        ),
    }
    args.output_root.mkdir(parents=True)
    prediction_root = args.output_root / "predictions"
    prediction_root.mkdir()
    metrics: dict[str, Any] = {}
    prediction_hashes: dict[str, str] = {}
    for cohort, (rows, cache, text_cache, label_key) in specs.items():
        dataset = PRTAFeatureDataset(
            rows,
            cache=cache,
            text_cache_path=text_cache,
            split=cohort,
            label_key=label_key,
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
            system="RISKF10-PRTA",
            seed=17,
            cohort=cohort,
        )
        prediction_path = prediction_root / f"{cohort}.predictions.jsonl"
        write_jsonl_atomic(prediction_path, predictions)
        metrics[cohort] = _cohort_metrics(predictions)
        prediction_hashes[cohort] = sha256_file(prediction_path)
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    result = {
        "schema": "prta-cxr.top10-risk-exclusion-evaluation.v1",
        "status": "PASS_POSTHOC_TOP10_EXCLUSION_DIAGNOSTIC",
        "created_at": datetime.now(UTC).isoformat(),
        "run_id": DIAGNOSTIC_RUN_ID,
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "preparation_receipt_sha256": sha256_file(args.preparation_receipt),
        "training_receipt_sha256": sha256_file(args.training_receipt),
        "metrics": metrics,
        "prediction_sha256": prediction_hashes,
        "retained_counts": preparation["retained_counts"],
        "excluded_counts": preparation["excluded_counts"],
        "outcome_adaptive_selection_bias": True,
        "formal_result_replacement": False,
        "interpretation": (
            "post-hoc performance after excluding globally ranked risk candidates; "
            "not an unbiased estimate on the original clinical distribution"
        ),
    }
    write_json_atomic(args.output_root / "evaluation_receipt.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
