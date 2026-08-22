from __future__ import annotations

import argparse
import json
import os
import string
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
IFUSION_FINAL_VARIANTS = {
    "IF-A01",
    "IF-A02",
    "IF-A03",
    "IF-A04",
    "IF-A05",
    "IF-A06",
    "IF-A08",
    "IF-A10",
    "IF-A11",
    "IF-F01",
    "IF-F02",
}
FORMAL_BASELINE_VARIANTS = {"B401", "TILA8"}
PROBABILITY_COMPARATORS = {"B401", "TILA8", "IF-F01", "IF-F02"}
PHASE20_FINAL_VARIANTS = {"Slim-S1"}
PHASE20_B2_VARIANTS = {
    "V2",
    "S0",
    "B401",
    "B402",
    "TILA8",
    "BioViLT",
    "CheXRelNet",
    "TILAPaper",
    "F02-DMW0",
}


def _load_matched_map(
    path: Path,
    *,
    true_only: bool,
    split_manifest_sha256: str,
    cache_manifest_sha256: str,
    cache_entry_block: int,
) -> Mapping[str, str] | None:
    if true_only:
        return None
    return read_matched_hard_prior_map(
        path,
        expected_split_manifest_sha256=split_manifest_sha256,
        expected_cache_manifest_sha256=cache_manifest_sha256,
        expected_cache_entry_block=cache_entry_block,
    )


def _resolve_diagnostic_variant(
    config: Mapping[str, Any], diagnostic_scope: str
) -> tuple[str, set[str], str]:
    if diagnostic_scope == "phase20_s1":
        return (
            str(config.get("prta_v2_variant", "")),
            PHASE20_FINAL_VARIANTS,
            "P20-FINAL-S1-S",
        )
    if diagnostic_scope == "phase20_b2":
        experiment_id = str(config.get("experiment_id", ""))
        if experiment_id.startswith("P20-F02-DMW0-S"):
            variant = "F02-DMW0"
        else:
            variant = str(config.get("phase20_role", ""))
        return variant, PHASE20_B2_VARIANTS, "P20-"
    if diagnostic_scope == "ifusion_final":
        return (
            str(config.get("ifusion_variant", "")),
            IFUSION_FINAL_VARIANTS,
            "IF-",
        )
    if diagnostic_scope == "candidate_v0_v2":
        return (
            str(config.get("prta_v2_variant", "")),
            CANDIDATE_CONFIRMATION_VARIANTS,
            "W045-",
        )
    if diagnostic_scope == "formal_baseline":
        model = dict(config.get("model", {}))
        family = str(model.get("family", ""))
        variant = "B401" if family == "current_only" else ""
        if family == "tila" and model.get("adapter_scope") == "tail8":
            variant = "TILA8"
        return variant, FORMAL_BASELINE_VARIANTS, "B4"
    return (
        str(config.get("prta_v2_variant", "")),
        LEGACY_DIAGNOSTIC_VARIANTS,
        "W045-",
    )


def _experiment_identity_matches(
    experiment_id: str, *, diagnostic_scope: str, variant: str
) -> bool:
    if diagnostic_scope == "ifusion_final":
        return experiment_id.startswith(f"{variant}-S")
    if diagnostic_scope == "phase20_s1":
        return variant == "Slim-S1" and experiment_id.startswith("P20-FINAL-S1-S")
    if diagnostic_scope == "phase20_b2":
        if variant == "F02-DMW0":
            return experiment_id.startswith("P20-F02-DMW0-S")
        return experiment_id.startswith(f"P20-REBUILD-{variant}-S")
    if diagnostic_scope in {"candidate_v0_v2", "legacy_v3_v5"}:
        return experiment_id.startswith(f"W045-{variant}-S")
    if diagnostic_scope == "formal_baseline":
        allowed_prefixes = {
            "B401": ("W046-B401-S", "CLN1-B401-S", "B401-S", "M305-B401-S"),
            "TILA8": ("W047-TILA8-S",),
        }
        return experiment_id.startswith(allowed_prefixes.get(variant, ()))
    return False


def _probability_export_allowed(diagnostic_scope: str, variant: str) -> bool:
    if diagnostic_scope == "phase20_s1":
        return variant == "Slim-S1"
    if diagnostic_scope == "phase20_b2":
        return variant in PHASE20_B2_VARIANTS
    if diagnostic_scope == "candidate_v0_v2":
        return variant == "V2"
    return variant in PROBABILITY_COMPARATORS and diagnostic_scope in {
        "ifusion_final",
        "formal_baseline",
    }


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
    retain_logits: bool = False,
    deployment_prune_state: bool = False,
) -> dict[str, Any]:
    model.eval()
    rows: list[dict[str, Any]] = []
    predictions: dict[str, int] = {}
    reliability_values: list[torch.Tensor] = []
    change_energy_values: list[torch.Tensor] = []
    state_weight_values: list[torch.Tensor] = []
    for batch in loader:
        model_inputs = (
            batch["prior"].to(device),
            batch["current"].to(device),
            batch["finding_text"].to(device),
        )
        if deployment_prune_state:
            output, logits, _ = model(*model_inputs, deployment_prune_state=True)
        else:
            output, logits, _ = model(*model_inputs)
        predicted = logits.argmax(dim=-1).cpu()
        cpu_logits = logits.detach().float().cpu()
        probabilities = cpu_logits.softmax(dim=-1)
        target = batch["target"].cpu()
        prior_reliability = getattr(output, "prior_reliability", None)
        change_energy = getattr(output, "change_energy", None)
        if prior_reliability is not None:
            reliability_values.append(prior_reliability)
        if change_energy is not None:
            change_energy_values.append(change_energy)
            state_weight_values.append(torch.exp(-selective_state_beta * change_energy))
        for index, (sample_id, patient, truth, prediction) in enumerate(
            zip(
                batch["sample_id"],
                batch["patient_id_hash"],
                target.tolist(),
                predicted.tolist(),
                strict=True,
            )
        ):
            sample = str(sample_id)
            predictions[sample] = int(prediction)
            row: dict[str, Any] = {
                "patient_id": str(patient),
                "observation_id": sample,
                "target": PROGRESSION_LABELS[int(truth)],
                "prediction": PROGRESSION_LABELS[int(prediction)],
            }
            if retain_logits:
                row.update(
                    {
                        "logits": cpu_logits[index].tolist(),
                        "probabilities": probabilities[index].tolist(),
                        "confidence": float(probabilities[index].max()),
                        "source": str(batch["source"][index]),
                        "finding": str(batch["finding"][index]),
                        "prior_view": str(batch["prior_view"][index]),
                        "current_view": str(batch["current_view"][index]),
                        "interval_days": float(batch["interval_days"][index]),
                        "interval_basis": str(batch["interval_basis"][index]),
                        "calendar_interval_available": bool(
                            batch["calendar_interval_available"][index]
                        ),
                    }
                )
            rows.append(row)
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


def _checkpoint_validation_hashes(
    diagnostic_hashes: Mapping[str, str], *, variant: str
) -> dict[str, str]:
    result = dict(diagnostic_hashes)
    if variant == "IF-A08":
        if "random_counterfactual_prior_map" not in result:
            raise ValueError("IF-A08 requires the frozen random counterfactual map")
        result.pop("matched_hard_prior_map")
    return result


def _validate_checkpoint_input_hashes(
    checkpoint_hashes: Mapping[str, str], diagnostic_hashes: Mapping[str, str]
) -> None:
    """Validate an immutable checkpoint against the diagnostic input contract.

    V0/V1 checkpoints predate matched-hard PRIOR use and therefore omit only
    that hash. V2 checkpoints used the map during training and bind the full
    diagnostic input set. Phase20 Final-S1 checkpoints additionally bind a
    source-filter audit as immutable training provenance; it is not a runtime
    diagnostic input. No other key-set difference is allowed.
    """
    diagnostic_keys = set(diagnostic_hashes)
    base_keys = diagnostic_keys - {"matched_hard_prior_map"}
    checkpoint_keys = set(checkpoint_hashes)
    source_filter_key = "source_filter_audit"
    allowed_key_sets = {
        frozenset(base_keys),
        frozenset(diagnostic_keys),
        frozenset({*base_keys, source_filter_key}),
        frozenset({*diagnostic_keys, source_filter_key}),
    }
    if frozenset(checkpoint_keys) not in allowed_key_sets:
        raise ValueError("unsupported checkpoint input-hash key set")
    if source_filter_key in checkpoint_hashes:
        source_filter_hash = str(checkpoint_hashes[source_filter_key])
        if len(source_filter_hash) != 64 or any(
            character not in string.hexdigits for character in source_filter_hash
        ):
            raise ValueError("invalid source-filter audit hash")
    for key, value in checkpoint_hashes.items():
        if key == source_filter_key:
            continue
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
    parser.add_argument("--random-counterfactual-prior-map", type=Path)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument(
        "--retain-logits",
        action="store_true",
        help="write raw Dev logits/probabilities for calibration evidence",
    )
    parser.add_argument(
        "--true-only",
        action="store_true",
        help="evaluate only true PRIOR for allowlisted probability comparators",
    )
    parser.add_argument(
        "--deployment-prune-state",
        action="store_true",
        help="skip the unused state branch for frozen H0 deployment parity",
    )
    parser.add_argument(
        "--diagnostic-scope",
        choices=(
            "legacy_v3_v5",
            "candidate_v0_v2",
            "ifusion_final",
            "formal_baseline",
            "phase20_s1",
            "phase20_b2",
        ),
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
    variant, allowed_variants, _ = _resolve_diagnostic_variant(
        config, args.diagnostic_scope
    )
    if variant not in allowed_variants:
        raise ValueError(
            f"{args.diagnostic_scope} does not permit Wave045 variant {variant!r}"
        )
    if args.retain_logits and not _probability_export_allowed(
        args.diagnostic_scope, variant
    ):
        parser.error("--retain-logits is restricted to frozen probability systems")
    if args.true_only and not (
        args.retain_logits
        and _probability_export_allowed(args.diagnostic_scope, variant)
    ):
        parser.error("--true-only requires an allowlisted probability comparator")
    if args.deployment_prune_state and not (
        variant in {"V2", "Slim-S1"} and args.true_only and args.retain_logits
    ):
        parser.error(
            "--deployment-prune-state requires V2/Slim-S1 --true-only --retain-logits"
        )
    experiment_id = str(config.get("experiment_id", ""))
    if args.diagnostic_scope == "phase20_s1" and (
        config.get("phase20_protocol")
        != "full-train-official-dev-slim-s1-confirmation-v1"
        or config.get("phase20_axis") != "final_mainline_confirmation"
    ):
        raise ValueError("Phase20 Slim-S1 diagnostic protocol drift")
    if not _experiment_identity_matches(
        experiment_id,
        diagnostic_scope=args.diagnostic_scope,
        variant=variant,
    ):
        raise ValueError("checkpoint experiment identity does not match scope")
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
    if variant == "IF-A08":
        if args.random_counterfactual_prior_map is None:
            parser.error("IF-A08 requires --random-counterfactual-prior-map")
        input_hashes["random_counterfactual_prior_map"] = sha256_file(
            args.random_counterfactual_prior_map
        )
    checkpoint_input_hashes = dict(checkpoint.get("input_hashes", {}))
    _validate_checkpoint_input_hashes(
        checkpoint_input_hashes,
        _checkpoint_validation_hashes(input_hashes, variant=variant),
    )
    if dict(training_receipt.get("input_hashes", {})) != checkpoint_input_hashes:
        raise ValueError("checkpoint/training-receipt input identity mismatch")
    adapter_scope = str(config["model"].get("adapter_scope", "tail4"))
    cache_entry_block = adapter_scope_cache_entry_block(adapter_scope)
    matched_map = _load_matched_map(
        args.matched_hard_prior_map,
        true_only=args.true_only,
        split_manifest_sha256=input_hashes["split_manifest"],
        cache_manifest_sha256=input_hashes["cache_manifest"],
        cache_entry_block=cache_entry_block,
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
    evaluation_interventions = ("true",) if args.true_only else INTERVENTIONS
    for intervention in evaluation_interventions:
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
            retain_logits=args.retain_logits,
            deployment_prune_state=args.deployment_prune_state,
        )
        prediction_rows[intervention] = result.pop("prediction_rows")
        intervention_results[intervention] = result

    true_predictions = intervention_results["true"]["predictions"]
    true_ordinary = intervention_results["true"]["metrics"]["ordinary"]
    report: dict[str, Any] = {}
    for intervention in evaluation_interventions:
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
    prediction_block_mode = args.diagnostic_scope in {
        "candidate_v0_v2",
        "ifusion_final",
        "formal_baseline",
        "phase20_s1",
        "phase20_b2",
    }
    ifusion_mode = args.diagnostic_scope == "ifusion_final"
    phase20_mode = args.diagnostic_scope == "phase20_s1"
    receipt = {
        "schema": (
            (
                (
                    "prta-cxr.phase20-s1-dev-probability-diagnostic.v1"
                    if phase20_mode
                    else "prta-cxr.wave047-candidate-probability-diagnostic.v1"
                )
                if variant in {"V2", "Slim-S1"}
                else "prta-cxr.comparator-dev-probability-diagnostic.v1"
            )
            if args.retain_logits
            else (
                "prta-cxr.phase20-s1-prior-diagnostic.v1"
                if phase20_mode
                else (
                    "prta-cxr.ifusion-dev-diagnostic.v1"
                    if ifusion_mode
                    else (
                        "prta-cxr.wave047-candidate-prior-diagnostic.v1"
                        if prediction_block_mode
                        else "prta-cxr.wave045-mechanism-diagnostic.v1"
                    )
                )
            )
        ),
        "status": (
            (
                (
                    "PASS_PHASE20_S1_DEV_PROBABILITY_EXPORT"
                    if phase20_mode
                    else "PASS_WAVE047_V2_DEV_PROBABILITY_EXPORT"
                )
                if variant in {"V2", "Slim-S1"}
                else "PASS_COMPARATOR_DEV_PROBABILITY_EXPORT"
            )
            if args.retain_logits
            else (
                "PASS_PHASE20_S1_DEV_PRIOR_DIAGNOSTIC"
                if phase20_mode
                else (
                    "PASS_IFUSION_TRAIN_DEV_PRIOR_DIAGNOSTIC"
                    if ifusion_mode
                    else (
                        "PASS_WAVE047_CANDIDATE_TRAIN_DEV_PRIOR_DIAGNOSTIC"
                        if prediction_block_mode
                        else "PASS_WAVE045_TRAIN_DEV_MECHANISM_DIAGNOSTIC"
                    )
                )
            )
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
        "probability_export": bool(args.retain_logits),
        "evaluation_interventions": list(evaluation_interventions),
        "deployment_state_pruned": bool(args.deployment_prune_state),
    }
    if args.diagnostic_scope == "phase20_b2":
        receipt["schema"] = "prta-cxr.phase20-b2-comparator-probability-diagnostic.v1"
        receipt["status"] = "PASS_PHASE20_B2_COMPARATOR_DEV_PROBABILITY_EXPORT"
    if prediction_block_mode:
        staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
        if staging.exists():
            raise FileExistsError(f"candidate diagnostic staging exists: {staging}")
        staging.mkdir(parents=True, exist_ok=False)
        prediction_blocks = {}
        for intervention in evaluation_interventions:
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
        if args.retain_logits:
            receipt["evidence_status"] = "PENDING_CALIBRATION_EVALUATION"
            receipt_name = "candidate_probability_diagnostic_receipt.json"
        elif ifusion_mode:
            receipt["evidence_status"] = "PENDING_PAIRED_BOOTSTRAP"
            receipt_name = "ifusion_dev_diagnostic_receipt.json"
        else:
            receipt["candidate_status"] = "PENDING_CONFIRMATION"
            receipt_name = "candidate_prior_diagnostic_receipt.json"
        _write_new_json(staging / receipt_name, receipt)
        staging.replace(args.output)
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        _write_new_json(args.output / "mechanism_diagnostic_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
