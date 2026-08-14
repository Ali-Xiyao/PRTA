from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from prta_cxr.artifacts import write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.hard_cmcp import read_matched_hard_prior_map
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.provenance import resolve_source_commit
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import (
    adapter_scope_cache_entry_block,
    load_biomedclip_visual,
    tail_modules,
)

INTERVENTIONS = ("true", "matched_hard", "null", "reversed")
LEGACY_DIAGNOSTIC_VARIANTS = {"V3", "V4", "V5"}
CANDIDATE_CONFIRMATION_VARIANTS = {"V0", "V1", "V2"}


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _distribution(values: list[torch.Tensor]) -> dict[str, float] | None:
    if not values:
        return None
    flat = torch.cat([value.detach().float().cpu().reshape(-1) for value in values])
    quantiles = torch.quantile(flat, torch.tensor([0.1, 0.5, 0.9]))
    return {
        "count": int(flat.numel()),
        "mean": float(flat.mean()),
        "std": float(flat.std(unbiased=False)),
        "p10": float(quantiles[0]),
        "p50": float(quantiles[1]),
        "p90": float(quantiles[2]),
        "minimum": float(flat.min()),
        "maximum": float(flat.max()),
    }


def _state_value(state: Mapping[str, Any] | None, suffix: str) -> float | None:
    if state is None:
        return None
    matches = [value for key, value in state.items() if str(key).endswith(suffix)]
    if len(matches) != 1:
        return None
    tensor = torch.as_tensor(matches[0]).detach().float().reshape(-1)
    if tensor.numel() != 1:
        return None
    return float(tensor.item())


@torch.no_grad()
def _evaluate_intervention(
    model: torch.nn.Module,
    loader: DataLoader,
    *,
    device: torch.device,
    selective_state_beta: float,
) -> dict[str, Any]:
    model.eval()
    rows: list[dict[str, str]] = []
    predictions: dict[str, int] = {}
    reliability_values: list[torch.Tensor] = []
    change_energy_values: list[torch.Tensor] = []
    state_weight_values: list[torch.Tensor] = []
    for batch in loader:
        output, logits, _ = model(
            batch["prior"].to(device),
            batch["current"].to(device),
            batch["finding_text"].to(device),
        )
        predicted = logits.argmax(dim=-1).cpu()
        target = batch["target"].cpu()
        if output.prior_reliability is not None:
            reliability_values.append(output.prior_reliability)
        if output.change_energy is not None:
            change_energy_values.append(output.change_energy)
            state_weight_values.append(
                torch.exp(-selective_state_beta * output.change_energy)
            )
        for sample_id, patient, truth, prediction in zip(
            batch["sample_id"],
            batch["patient_id_hash"],
            target.tolist(),
            predicted.tolist(),
            strict=True,
        ):
            sample = str(sample_id)
            predictions[sample] = int(prediction)
            rows.append(
                {
                    "patient_id": str(patient),
                    "observation_id": sample,
                    "target": PROGRESSION_LABELS[int(truth)],
                    "prediction": PROGRESSION_LABELS[int(prediction)],
                }
            )
    metrics = classification_metrics(rows, labels=PROGRESSION_LABELS)
    return {
        "metrics": metrics,
        "predictions": predictions,
        "prediction_rows": rows,
        "prior_reliability": _distribution(reliability_values),
        "change_energy": _distribution(change_energy_values),
        "selective_state_weight": _distribution(state_weight_values),
    }


def _input_hashes(args: argparse.Namespace) -> dict[str, str]:
    return {
        "split_manifest": sha256_file(args.split_manifest),
        "text_cache": sha256_file(args.text_cache),
        "weights": sha256_file(args.weights),
        "cache_manifest": sha256_file(args.cache_root / "cache_manifest.json"),
        "label_quality_audit": sha256_file(args.label_quality_audit),
        "cleaned_split_freeze": sha256_file(args.cleaned_split_freeze),
        "matched_hard_prior_map": sha256_file(args.matched_hard_prior_map),
    }


def _validate_checkpoint_input_hashes(
    checkpoint_hashes: Mapping[str, str], diagnostic_hashes: Mapping[str, str]
) -> None:
    """Validate an immutable checkpoint against the diagnostic input contract.

    V0/V1 checkpoints predate matched-hard PRIOR use and therefore omit only
    that hash. V2 checkpoints used the map during training and bind the full
    diagnostic input set. No other key-set difference is allowed.
    """
    diagnostic_keys = set(diagnostic_hashes)
    base_keys = diagnostic_keys - {"matched_hard_prior_map"}
    checkpoint_keys = set(checkpoint_hashes)
    if checkpoint_keys not in (base_keys, diagnostic_keys):
        raise ValueError("unsupported checkpoint input-hash key set")
    for key, value in checkpoint_hashes.items():
        if diagnostic_hashes.get(key) != value:
            raise ValueError(f"diagnostic input hash mismatch for {key}")


def diagnostic_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run aggregate-only Wave045 Train/Dev mechanism diagnostics"
    )
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--matched-hard-prior-map", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument(
        "--diagnostic-scope",
        choices=("legacy_v3_v5", "candidate_v0_v2"),
        default="legacy_v3_v5",
    )
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")

    cleaned = require_cleaned_manifest(
        args.split_manifest,
        receipt_path=args.cleaned_split_freeze,
        role="train_dev",
        portable_root=args.cleaned_split_platform_root,
    )
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported checkpoint schema")
    config = dict(checkpoint["config"])
    variant = str(config.get("prta_v2_variant", ""))
    allowed_variants = (
        CANDIDATE_CONFIRMATION_VARIANTS
        if args.diagnostic_scope == "candidate_v0_v2"
        else LEGACY_DIAGNOSTIC_VARIANTS
    )
    if variant not in allowed_variants:
        raise ValueError(
            f"{args.diagnostic_scope} does not permit Wave045 variant {variant!r}"
        )
    experiment_id = str(config.get("experiment_id", ""))
    if not experiment_id.startswith(f"W045-{variant}-S"):
        raise ValueError("checkpoint experiment identity is not Wave045")
    training_receipt = json.loads(args.training_receipt.read_text(encoding="utf-8"))
    if training_receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError("training receipt is not terminal PASS")
    if training_receipt.get("internal_test_opened") is not False:
        raise ValueError("training receipt reports Internal-test access")
    if training_receipt.get("protected_outcomes_opened") is not False:
        raise ValueError("training receipt reports protected-outcome access")
    if training_receipt.get("config_sha256") != canonical_sha256(config):
        raise ValueError("checkpoint/training-receipt config identity mismatch")

    input_hashes = _input_hashes(args)
    checkpoint_input_hashes = dict(checkpoint.get("input_hashes", {}))
    _validate_checkpoint_input_hashes(checkpoint_input_hashes, input_hashes)
    if dict(training_receipt.get("input_hashes", {})) != checkpoint_input_hashes:
        raise ValueError("checkpoint/training-receipt input identity mismatch")
    adapter_scope = str(config["model"].get("adapter_scope", "tail4"))
    cache_entry_block = adapter_scope_cache_entry_block(adapter_scope)
    matched_map = read_matched_hard_prior_map(
        args.matched_hard_prior_map,
        expected_split_manifest_sha256=input_hashes["split_manifest"],
        expected_cache_manifest_sha256=input_hashes["cache_manifest"],
        expected_cache_entry_block=cache_entry_block,
    )
    rows = read_jsonl(args.split_manifest)
    if {str(row.get("split")) for row in rows} - {"train", "dev"}:
        raise ValueError("diagnostic manifest contains a non-Train/Dev split")

    visual, _ = load_biomedclip_visual(args.weights)
    blocks, final_norm = tail_modules(visual, start_block=cache_entry_block)
    model = build_train_model(blocks, final_norm, config)
    model.load_state_dict(checkpoint["model_state"])
    device = torch.device(args.device)
    model.to(device)
    cache = Block8CacheIndex(args.cache_root)
    beta = float(
        dict(config["model"].get("components", {})).get("selective_state_beta", 1.0)
    )

    intervention_results: dict[str, Any] = {}
    prediction_rows: dict[str, list[dict[str, str]]] = {}
    for intervention in INTERVENTIONS:
        dataset = PRTAFeatureDataset(
            rows,
            cache=cache,
            text_cache_path=args.text_cache,
            split="dev",
            prior_intervention=intervention,
            matched_hard_prior_map=matched_map,
        )
        loader = DataLoader(
            dataset,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=0,
        )
        result = _evaluate_intervention(
            model,
            loader,
            device=device,
            selective_state_beta=beta,
        )
        prediction_rows[intervention] = result.pop("prediction_rows")
        intervention_results[intervention] = result

    true_predictions = intervention_results["true"]["predictions"]
    true_ordinary = intervention_results["true"]["metrics"]["ordinary"]
    report: dict[str, Any] = {}
    for intervention in INTERVENTIONS:
        result = intervention_results[intervention]
        predictions = result.pop("predictions")
        ordinary = result["metrics"]["ordinary"]
        flips = sum(
            predictions[sample] != true_predictions[sample]
            for sample in sorted(true_predictions)
        )
        result["comparison_to_true"] = {
            "prediction_flip_count": flips,
            "prediction_flip_rate": flips / len(true_predictions),
            "macro_f1_delta": float(ordinary["macro_f1"])
            - float(true_ordinary["macro_f1"]),
            "true_minus_intervention_macro_f1": float(true_ordinary["macro_f1"])
            - float(ordinary["macro_f1"]),
            "opposite_direction_error_rate_delta": float(
                ordinary["opposite_direction_error_rate"]
            )
            - float(true_ordinary["opposite_direction_error_rate"]),
        }
        report[intervention] = result

    evaluation_scale = _state_value(
        checkpoint.get("model_state"), "adapter.relation_residual_scale"
    )
    training_scale = _state_value(
        checkpoint.get("training_model_state"),
        "adapter.relation_residual_scale",
    )
    candidate_mode = args.diagnostic_scope == "candidate_v0_v2"
    receipt = {
        "schema": (
            "prta-cxr.wave047-candidate-prior-diagnostic.v1"
            if candidate_mode
            else "prta-cxr.wave045-mechanism-diagnostic.v1"
        ),
        "status": (
            "PASS_WAVE047_CANDIDATE_TRAIN_DEV_PRIOR_DIAGNOSTIC"
            if candidate_mode
            else "PASS_WAVE045_TRAIN_DEV_MECHANISM_DIAGNOSTIC"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "experiment_id": experiment_id,
        "variant": variant,
        "seed": int(config["seed"]),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "training_receipt_sha256": sha256_file(args.training_receipt),
        "config_sha256": canonical_sha256(config),
        "input_hashes": input_hashes,
        "checkpoint_input_hashes": checkpoint_input_hashes,
        "cleaned_split_freeze_sha256": cleaned["receipt_sha256"],
        "interventions": report,
        "mechanism": {
            "evaluation_checkpoint_relation_residual_scale": evaluation_scale,
            "training_checkpoint_relation_residual_scale": training_scale,
            "relation_residual_scale_is_signed_unbounded": True,
            "relation_residual_scale_trajectory_retained": False,
            "prior_reliability_is_indirectly_supervised": variant in {"V4", "V5"},
            "change_energy_scope": "global_token_dimension_mean_squared_difference",
            "selective_state_beta": beta if variant == "V5" else None,
        },
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    if candidate_mode:
        staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
        if staging.exists():
            raise FileExistsError(f"candidate diagnostic staging exists: {staging}")
        staging.mkdir(parents=True, exist_ok=False)
        prediction_blocks = {}
        for intervention in INTERVENTIONS:
            block = [
                {
                    **row,
                    "system": variant,
                    "training_seed": int(config["seed"]),
                    "cohort": "dev",
                    "prior_intervention": intervention,
                }
                for row in prediction_rows[intervention]
            ]
            path = staging / f"{intervention}.predictions.jsonl"
            write_jsonl_atomic(path, block)
            prediction_blocks[intervention] = {
                "path": path.name,
                "rows": len(block),
                "sha256": sha256_file(path),
            }
        receipt["prediction_blocks"] = prediction_blocks
        receipt["checkpoint_only"] = True
        receipt["candidate_status"] = "PENDING_CONFIRMATION"
        _write_new_json(staging / "candidate_prior_diagnostic_receipt.json", receipt)
        staging.replace(args.output)
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        _write_new_json(args.output / "mechanism_diagnostic_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
