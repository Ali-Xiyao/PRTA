from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import torch
from torch.utils.data import DataLoader

from prta_cxr.artifacts import write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.hard_cmcp import read_matched_hard_prior_map
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.provenance import resolve_source_commit
from prta_cxr.prta_v2_diagnostics import _validate_checkpoint_input_hashes
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import (
    load_biomedclip_visual,
    tail_modules,
)

PRIOR_CONDITIONS = {
    "P0_true": "true",
    "P1_null": "null",
    "P2_random": "random",
    "P3_same_finding_wrong": "matched_wrong",
    "P4_matched_hard": "matched_hard",
    "P5_older_same_current": "older_same_current",
    "P6_reversed": "reversed",
    "P7_wrong_patient_view_mismatched": "wrong_patient_view_mismatched",
    "P8_token_scrambled": "token_scrambled",
}
RANDOM_FINDING_CONDITIONS = {
    "F4_random_perm_17": "prta-cxr-sample-random-finding-S17-v2",
    "F4_random_perm_28": "prta-cxr-sample-random-finding-S28-v2",
    "F4_random_perm_43": "prta-cxr-sample-random-finding-S43-v2",
}
FINDING_CONDITIONS = (
    "F0_correct",
    "F1_zero",
    "F2_generic",
    "F3_wrong",
    *RANDOM_FINDING_CONDITIONS,
    "F5_clinical_semantic_alternative",
    "F6_typo",
    "F7_paraphrase",
)
CURRENT_CONDITIONS = (
    "C0_original",
    "C1_blur",
    "C2_contrast",
    "C3_jpeg",
    "C4_lung_occlusion",
    "C5_bbox_occlusion",
    "C6_outside_bbox",
)


def _ece(rows: Sequence[Mapping[str, Any]], bins: int = 15) -> float:
    total = len(rows)
    value = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        selected = [
            row
            for row in rows
            if low <= max(map(float, row["probabilities"])) < high
            or (index == bins - 1 and max(map(float, row["probabilities"])) == 1.0)
        ]
        if not selected:
            continue
        confidence = sum(
            max(map(float, row["probabilities"])) for row in selected
        ) / len(selected)
        accuracy = sum(row["prediction"] == row["target"] for row in selected) / len(
            selected
        )
        value += len(selected) / total * abs(confidence - accuracy)
    return value


def compare_condition_rows(
    baseline: Sequence[Mapping[str, Any]], condition: Sequence[Mapping[str, Any]]
) -> dict[str, float | int]:
    left = {str(row["observation_id"]): row for row in baseline}
    right = {str(row["observation_id"]): row for row in condition}
    if set(left) != set(right):
        raise ValueError("modality condition roster drift")
    flips = 0
    js_values = []
    kl_values = []
    probability_drops = []
    confidence_deltas = []
    for sample_id in sorted(left):
        a, b = left[sample_id], right[sample_id]
        if a["target"] != b["target"]:
            raise ValueError("modality condition target drift")
        flips += a["prediction"] != b["prediction"]
        p = torch.tensor(a["probabilities"], dtype=torch.float64).clamp_min(1e-12)
        q = torch.tensor(b["probabilities"], dtype=torch.float64).clamp_min(1e-12)
        m = 0.5 * (p + q)
        kl = float((p * (p.log() - q.log())).sum())
        js = float(
            0.5 * (p * (p.log() - m.log())).sum()
            + 0.5 * (q * (q.log() - m.log())).sum()
        )
        target_index = PROGRESSION_LABELS.index(str(a["target"]))
        js_values.append(js)
        kl_values.append(kl)
        probability_drops.append(float(p[target_index] - q[target_index]))
        confidence_deltas.append(float(q.max() - p.max()))
    return {
        "prediction_flip_count": flips,
        "prediction_flip_rate": flips / len(left),
        "mean_js_divergence": sum(js_values) / len(js_values),
        "mean_kl_true_to_condition": sum(kl_values) / len(kl_values),
        "mean_true_label_probability_drop": sum(probability_drops)
        / len(probability_drops),
        "mean_confidence_delta": sum(confidence_deltas) / len(confidence_deltas),
        "ece_delta": _ece(condition) - _ece(baseline),
    }


@torch.no_grad()
def _predict(
    model,
    loader: DataLoader,
    *,
    device: torch.device,
    finding_transform: Callable[[Mapping[str, Any], torch.Tensor], torch.Tensor]
    | None = None,
    current_cache: Block8CacheIndex | None = None,
) -> list[dict[str, Any]]:
    model.eval()
    rows = []
    for batch in loader:
        prior = batch["prior"].to(device)
        current = batch["current"]
        if current_cache is not None:
            keys = [
                image_cache_key(source, path)
                for source, path in zip(
                    batch["current_source"], batch["current_image_path"], strict=True
                )
            ]
            current = current_cache.get_many(keys).float()
        finding = batch["finding_text"]
        if finding_transform is not None:
            finding = finding_transform(batch, finding)
        _, logits, _ = model(prior, current.to(device), finding.to(device))
        probabilities = logits.detach().float().cpu().softmax(dim=-1)
        predictions = probabilities.argmax(dim=-1)
        for index, sample_id in enumerate(batch["sample_id"]):
            target = int(batch["target"][index])
            prediction = int(predictions[index])
            rows.append(
                {
                    "patient_id": str(batch["patient_id_hash"][index]),
                    "observation_id": str(sample_id),
                    "target": PROGRESSION_LABELS[target],
                    "prediction": PROGRESSION_LABELS[prediction],
                    "logits": logits[index].detach().float().cpu().tolist(),
                    "probabilities": probabilities[index].tolist(),
                    "source": str(batch["source"][index]),
                    "finding": str(batch["finding"][index]),
                    "special_prior_available": bool(
                        batch["special_prior_available"][index]
                    ),
                    "special_prior_sample_id": str(
                        batch["special_prior_sample_id"][index]
                    ),
                }
            )
    return rows


def _finding_transform(
    condition: str,
    *,
    base_embeddings: Mapping[str, Any],
    intervention_embeddings: Mapping[str, Mapping[str, Any]],
):
    findings = sorted(base_embeddings)
    wrong = {
        finding: findings[(index + 1) % len(findings)]
        for index, finding in enumerate(findings)
    }

    def transform(batch: Mapping[str, Any], values: torch.Tensor) -> torch.Tensor:
        if condition == "F0_correct":
            return values
        if condition == "F1_zero":
            return torch.zeros_like(values)
        output = []
        for finding, sample_id in zip(
            map(str, batch["finding"]), map(str, batch["sample_id"]), strict=True
        ):
            if condition == "F2_generic":
                value = intervention_embeddings["generic"][finding]
            elif condition == "F3_wrong":
                value = base_embeddings[wrong[finding]]
            elif condition in RANDOM_FINDING_CONDITIONS:
                candidates = [name for name in findings if name != finding]
                digest = hashlib.sha256(
                    f"{RANDOM_FINDING_CONDITIONS[condition]}|{sample_id}".encode()
                ).digest()
                value = base_embeddings[
                    candidates[int.from_bytes(digest[:8], "big") % len(candidates)]
                ]
            else:
                key = {
                    "F5_clinical_semantic_alternative": (
                        "clinical_semantic_alternative"
                    ),
                    "F6_typo": "typo",
                    "F7_paraphrase": "paraphrase",
                }[condition]
                value = intervention_embeddings[key][finding]
            output.append(torch.as_tensor(value, dtype=torch.float32))
        return torch.stack(output)

    return transform


def modality_stress_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run complete Dev-only modality stress matrix"
    )
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--intervention-text-cache", type=Path, required=True)
    parser.add_argument("--matched-hard-prior-map", type=Path, required=True)
    parser.add_argument("--blur-cache", type=Path, required=True)
    parser.add_argument("--contrast-cache", type=Path, required=True)
    parser.add_argument("--jpeg-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    cleaned = require_cleaned_manifest(
        args.split_manifest,
        receipt_path=args.cleaned_split_freeze,
        role="train_dev",
        portable_root=args.cleaned_split_platform_root,
    )
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    config = dict(checkpoint["config"])
    if config.get("prta_v2_variant") != "V2":
        raise ValueError("modality stress requires frozen V2")
    receipt = json.loads(args.training_receipt.read_text(encoding="utf-8"))
    if receipt.get("status") != "PASS_TRAINING_FINISHED" or receipt.get(
        "config_sha256"
    ) != canonical_sha256(config):
        raise ValueError("modality checkpoint/training receipt identity drift")
    input_hashes = {
        "split_manifest": sha256_file(args.split_manifest),
        "text_cache": sha256_file(args.text_cache),
        "weights": sha256_file(args.weights),
        "cache_manifest": sha256_file(args.cache_root / "cache_manifest.json"),
        "label_quality_audit": sha256_file(args.label_quality_audit),
        "cleaned_split_freeze": sha256_file(args.cleaned_split_freeze),
        "matched_hard_prior_map": sha256_file(args.matched_hard_prior_map),
    }
    _validate_checkpoint_input_hashes(
        dict(checkpoint.get("input_hashes", {})), input_hashes
    )
    matched_map = read_matched_hard_prior_map(
        args.matched_hard_prior_map,
        expected_split_manifest_sha256=input_hashes["split_manifest"],
        expected_cache_manifest_sha256=input_hashes["cache_manifest"],
        expected_cache_entry_block=4,
    )
    rows = read_jsonl(args.split_manifest)
    visual, _ = load_biomedclip_visual(args.weights)
    blocks, final_norm = tail_modules(visual, start_block=4)
    model = build_train_model(blocks, final_norm, config)
    model.load_state_dict(checkpoint["model_state"])
    device = torch.device(args.device)
    model.to(device)
    base_cache = Block8CacheIndex(args.cache_root)
    text_value = torch.load(args.text_cache, map_location="cpu", weights_only=True)
    intervention_value = torch.load(
        args.intervention_text_cache, map_location="cpu", weights_only=True
    )
    if intervention_value.get("schema") != "prta-cxr.modality-finding-text-cache.v2":
        raise ValueError("modality finding cache is not corrected v2")
    if (
        intervention_value.get("split_manifest_sha256")
        != input_hashes["split_manifest"]
    ):
        raise ValueError("modality finding cache split identity drift")
    required_text_conditions = {
        "generic",
        "clinical_semantic_alternative",
        "typo",
        "paraphrase",
    }
    if set(intervention_value.get("embeddings", {})) != required_text_conditions:
        raise ValueError("modality finding cache condition roster drift")
    corruption_roots = {
        "blur": args.blur_cache,
        "contrast": args.contrast_cache,
        "jpeg": args.jpeg_cache,
    }
    for condition, root in corruption_roots.items():
        manifest_path = root / "cache_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        encoder = dict(manifest.get("encoder", {}))
        if encoder.get("modality_condition") != condition:
            raise ValueError(f"current corruption cache condition drift: {condition}")
        if encoder.get("split_manifest_sha256") != input_hashes["split_manifest"]:
            raise ValueError(f"current corruption cache split drift: {condition}")
    conditions: dict[str, dict[str, Any]] = {}
    prediction_blocks: dict[str, list[dict[str, Any]]] = {}
    baseline_rows = None
    for condition, intervention in PRIOR_CONDITIONS.items():
        dataset = PRTAFeatureDataset(
            rows,
            cache=base_cache,
            text_cache_path=args.text_cache,
            split="dev",
            prior_intervention=intervention,
            matched_hard_prior_map=matched_map,
        )
        loader = DataLoader(
            dataset, batch_size=args.batch_size, shuffle=False, num_workers=0
        )
        predictions = _predict(model, loader, device=device)
        if condition == "P0_true":
            baseline_rows = predictions
        prediction_blocks[condition] = predictions
        conditions[condition] = {
            "status": "PASS",
            "metrics": classification_metrics(predictions, labels=PROGRESSION_LABELS),
            "coverage": dataset.special_prior_coverage
            if intervention in {"older_same_current", "wrong_patient_view_mismatched"}
            else 1.0,
            "condition_identity": {
                "P5_older_same_current": (
                    "same patient, finding, current study/image; "
                    "candidate prior time precedes original prior time"
                ),
                "P7_wrong_patient_view_mismatched": (
                    "different-patient and different-prior-view compound stress"
                ),
                "P8_token_scrambled": (
                    "cached PRIOR token-order reversal plus CLS sign inversion; "
                    "not image-level corruption"
                ),
            }.get(condition, intervention),
        }
    if baseline_rows is None:  # pragma: no cover
        raise RuntimeError("missing modality baseline")
    true_dataset = PRTAFeatureDataset(
        rows, cache=base_cache, text_cache_path=args.text_cache, split="dev"
    )
    for condition in FINDING_CONDITIONS:
        loader = DataLoader(
            true_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0
        )
        predictions = _predict(
            model,
            loader,
            device=device,
            finding_transform=_finding_transform(
                condition,
                base_embeddings=text_value["finding_embeddings"],
                intervention_embeddings=intervention_value["embeddings"],
            ),
        )
        prediction_blocks[condition] = predictions
        conditions[condition] = {
            "status": "PASS",
            "metrics": classification_metrics(predictions, labels=PROGRESSION_LABELS),
            "condition_identity": (
                "sample-level wrong-finding permutation"
                if condition in RANDOM_FINDING_CONDITIONS
                else condition
            ),
        }
    current_caches = {
        "C0_original": None,
        "C1_blur": Block8CacheIndex(args.blur_cache),
        "C2_contrast": Block8CacheIndex(args.contrast_cache),
        "C3_jpeg": Block8CacheIndex(args.jpeg_cache),
    }
    for condition in CURRENT_CONDITIONS:
        if condition not in current_caches:
            conditions[condition] = {
                "status": "SKIPPED_DATA_GATED",
                "reason": (
                    "frozen lung/bbox annotations unavailable; "
                    "manual annotation forbidden"
                ),
            }
            continue
        loader = DataLoader(
            true_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0
        )
        predictions = _predict(
            model, loader, device=device, current_cache=current_caches[condition]
        )
        prediction_blocks[condition] = predictions
        conditions[condition] = {
            "status": "PASS",
            "metrics": classification_metrics(predictions, labels=PROGRESSION_LABELS),
        }
    baseline_metrics = classification_metrics(baseline_rows, labels=PROGRESSION_LABELS)[
        "ordinary"
    ]
    for condition, value in conditions.items():
        if value["status"] != "PASS":
            continue
        comparison = compare_condition_rows(baseline_rows, prediction_blocks[condition])
        ordinary = value["metrics"]["ordinary"]
        comparison.update(
            {
                "macro_f1_delta": float(ordinary["macro_f1"])
                - float(baseline_metrics["macro_f1"]),
                "opposite_direction_error_rate_delta": float(
                    ordinary["opposite_direction_error_rate"]
                )
                - float(baseline_metrics["opposite_direction_error_rate"]),
            }
        )
        value["comparison_to_P0_true"] = comparison
        if condition in {
            "P5_older_same_current",
            "P7_wrong_patient_view_mismatched",
        }:
            eligible = [
                row
                for row in prediction_blocks[condition]
                if row["special_prior_available"]
            ]
            eligible_ids = {str(row["observation_id"]) for row in eligible}
            eligible_baseline = [
                row
                for row in baseline_rows
                if str(row["observation_id"]) in eligible_ids
            ]
            value["eligible_subset"] = {
                "rows": len(eligible),
                "roster_sha256": canonical_sha256(sorted(eligible_ids)),
                "metrics": (
                    classification_metrics(eligible, labels=PROGRESSION_LABELS)
                    if eligible
                    else None
                ),
                "comparison_to_P0_true": (
                    compare_condition_rows(eligible_baseline, eligible)
                    if eligible
                    else None
                ),
            }
    random_conditions = [conditions[name] for name in RANDOM_FINDING_CONDITIONS]
    random_summary = {
        "members": list(RANDOM_FINDING_CONDITIONS),
        "salts": dict(RANDOM_FINDING_CONDITIONS),
        "mean_macro_f1": mean(
            float(value["metrics"]["ordinary"]["macro_f1"])
            for value in random_conditions
        ),
        "mean_prediction_flip_rate": mean(
            float(value["comparison_to_P0_true"]["prediction_flip_rate"])
            for value in random_conditions
        ),
        "mean_true_label_probability_drop": mean(
            float(value["comparison_to_P0_true"]["mean_true_label_probability_drop"])
            for value in random_conditions
        ),
    }
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    blocks_receipt = {}
    for condition, predictions in prediction_blocks.items():
        path = staging / f"{condition}.predictions.jsonl"
        write_jsonl_atomic(path, predictions)
        blocks_receipt[condition] = {
            "path": path.name,
            "sha256": sha256_file(path),
            "rows": len(predictions),
        }
    payload = {
        "schema": "prta-cxr.complete-modality-stress.v2",
        "status": "PASS_MODALITY_STRESS_WITH_DATA_GATED_OCCLUSIONS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "experiment_id": config["experiment_id"],
        "seed": int(config["seed"]),
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "input_hashes": {
            **input_hashes,
            "intervention_text_cache": sha256_file(args.intervention_text_cache),
            "blur_cache_manifest": sha256_file(args.blur_cache / "cache_manifest.json"),
            "contrast_cache_manifest": sha256_file(
                args.contrast_cache / "cache_manifest.json"
            ),
            "jpeg_cache_manifest": sha256_file(args.jpeg_cache / "cache_manifest.json"),
        },
        "conditions": conditions,
        "condition_groups": {
            "sample_level_random_finding_three_permutations": random_summary
        },
        "prediction_blocks": blocks_receipt,
        "cleaned_split_freeze_sha256": cleaned["receipt_sha256"],
        "data_gated_conditions": [
            "C4_lung_occlusion",
            "C5_bbox_occlusion",
            "C6_outside_bbox",
        ],
        "manual_annotation_performed": False,
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    receipt_path = staging / "modality_stress_receipt.json"
    receipt_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    staging.replace(args.output)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
