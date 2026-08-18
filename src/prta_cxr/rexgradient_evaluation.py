from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from prta_cxr.artifacts import (
    replace_json_atomic,
    write_json_atomic,
    write_jsonl_atomic,
)
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.evaluation.progression import classification_metrics
from prta_cxr.label_rules import (
    CUE_PATTERNS,
    FINDING_ALIASES,
    RULESET_VERSION,
    extract_report_annotations,
)
from prta_cxr.provenance import resolve_source_commit
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import (
    adapter_scope_cache_entry_block,
    load_biomedclip_visual,
    tail_modules,
)

SEEDS = (17, 28, 43)
LABEL_STATUS = "PASS_REXGRADIENT_EXTERNAL_LABELS"
DEDUP_STATUS = "PASS_REXGRADIENT_STRICT_IMAGE_DEDUP"
PROTOCOL_STATUS = "PASS_REXGRADIENT_EXTERNAL_PROTOCOL_FROZEN"
INFERENCE_STATUS = "PASS_REXGRADIENT_SLIM_S1_EXTERNAL_INFERENCE"
FINAL_STATUS = "PASS_REXGRADIENT_PUBLIC_TEST_FINAL"
PROGRAM_STATUS = "PASS_REXGRADIENT_EXTERNAL_PROGRAM_TEMPLATE_FROZEN"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _fresh_staging(output: Path) -> Path:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {output}")
    staging = output.with_name(f".{output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    return staging


def rules_contract_sha256() -> str:
    return canonical_sha256(
        {
            "ruleset_version": RULESET_VERSION,
            "finding_aliases": FINDING_ALIASES,
            "cue_patterns": CUE_PATTERNS,
        }
    )


def validate_mapping_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(spec)
    if value.get("schema") != "prta-cxr.rexgradient-label-mapping-spec.v1":
        raise ValueError("unsupported ReXGradient mapping specification")
    if value.get("ruleset_version") != RULESET_VERSION:
        raise ValueError("mapping ruleset version drift")
    if tuple(value.get("progression_labels", ())) != PROGRESSION_LABELS:
        raise ValueError("mapping progression-label order drift")
    if set(value.get("findings", ())) != set(FINDING_ALIASES):
        raise ValueError("mapping finding roster drift")
    for key in (
        "test_mapping_tuning_allowed",
        "model_selection_allowed",
        "threshold_tuning_allowed",
    ):
        if value.get(key) is not False:
            raise ValueError(f"external mapping must prohibit {key}")
    if int(value.get("minimum_validation_support_per_class", 0)) <= 0:
        raise ValueError("mapping minimum class support must be positive")
    if int(value.get("bootstrap_replicates", 0)) < 1000:
        raise ValueError("external bootstrap must request at least 1000 replicates")
    return value


def _report_text(value: object) -> str:
    if not isinstance(value, Mapping):
        raise ValueError("external report must be a mapping")
    findings = str(value.get("findings") or "").strip()
    impression = str(value.get("impression") or "").strip()
    return f"FINDINGS: {findings}\nIMPRESSION: {impression}"


def derive_external_labels(
    pairs: Sequence[Mapping[str, Any]],
    *,
    split: str,
    mapping_spec: Mapping[str, Any],
    blocked_image_paths: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = validate_mapping_spec(mapping_spec)
    if split not in {"validation", "test"}:
        raise ValueError("external split must be validation or test")
    findings = set(map(str, spec["findings"]))
    labels = set(map(str, spec["progression_labels"]))
    spec_hash = canonical_sha256(spec)
    rows: list[dict[str, Any]] = []
    excluded_dedup = 0
    without_explicit_label = 0
    for raw in pairs:
        pair = dict(raw)
        if pair.get("schema") != "prta-cxr.rexgradient-unlabeled-pair.v1":
            raise ValueError("unexpected ReXGradient pair schema")
        if pair.get("external_split") != split:
            raise ValueError("ReXGradient split identity drift")
        paths = {
            str(pair["prior_image_path"]),
            str(pair["current_image_path"]),
        }
        if paths.intersection(blocked_image_paths):
            excluded_dedup += 1
            continue
        annotations = extract_report_annotations(_report_text(pair["current_report"]))
        annotations = [
            item
            for item in annotations
            if str(item["finding"]) in findings and str(item["label"]) in labels
        ]
        if not annotations:
            without_explicit_label += 1
            continue
        for annotation in annotations:
            finding = str(annotation["finding"])
            label = str(annotation["label"])
            identity = "|".join((str(pair["sample_id"]), finding, label, spec_hash))
            rows.append(
                {
                    "schema": "prta-cxr.rexgradient-external-silver-row.v1",
                    "sample_id": hashlib.sha256(identity.encode()).hexdigest(),
                    "split": split,
                    "source": "rexgradient_160k",
                    "patient_id_hash": str(pair["patient_id_hash"]),
                    "prior_study_id": str(pair["prior_study_id_hash"]),
                    "current_study_id": str(pair["current_study_id_hash"]),
                    "prior_image_path": str(pair["prior_image_path"]),
                    "current_image_path": str(pair["current_image_path"]),
                    "prior_datetime": str(pair["prior_datetime"]),
                    "current_datetime": str(pair["current_datetime"]),
                    "interval_days": float(pair["interval_days"]),
                    "interval_basis": "calendar",
                    "calendar_interval_available": True,
                    "interval_semantics": "elapsed_calendar_days",
                    "prior_view": str(pair["prior_view"]),
                    "current_view": str(pair["current_view"]),
                    "finding": finding,
                    "progression_label": label,
                    "label_source": RULESET_VERSION,
                    "label_tier": str(spec["label_tier"]),
                    "label_evidence_section": str(annotation["section"]),
                    "label_evidence_cue": str(annotation["cue"]),
                }
            )
    rows.sort(key=lambda row: str(row["sample_id"]))
    identifiers = [str(row["sample_id"]) for row in rows]
    if not rows or len(identifiers) != len(set(identifiers)):
        raise ValueError("external label rows are empty or non-unique")
    audit = {
        "pairs": len(pairs),
        "labeled_rows": len(rows),
        "labeled_pairs": len({str(row["current_study_id"]) for row in rows}),
        "patients": len({str(row["patient_id_hash"]) for row in rows}),
        "excluded_pairs_due_to_dedup": excluded_dedup,
        "pairs_without_explicit_transition_label": without_explicit_label,
        "label_counts": dict(Counter(str(row["progression_label"]) for row in rows)),
        "finding_counts": dict(Counter(str(row["finding"]) for row in rows)),
    }
    return rows, audit


def _claim_test_access(external_root: Path, protocol_path: Path) -> dict[str, Any]:
    protocol = _read_json(protocol_path)
    if protocol.get("status") != PROTOCOL_STATUS:
        raise ValueError("public test requires a frozen external protocol")
    claim = {
        "schema": "prta-cxr.rexgradient-test-access-claim.v1",
        "status": "CLAIMED_ONE_TIME_EXTERNAL_TEST_SESSION",
        "protocol_sha256": sha256_file(protocol_path),
        "mapping_spec_sha256": protocol["mapping_spec_sha256"],
        "checkpoint_roster_sha256": protocol["checkpoint_roster_sha256"],
        "selection_performed": False,
        "threshold_tuning_performed": False,
    }
    path = external_root / "receipts" / "test_evaluation_claim.json"
    if path.is_file():
        existing = _read_json(path)
        if existing != claim:
            raise ValueError(
                "public-test session was already claimed by another protocol"
            )
    else:
        write_json_atomic(path, claim)
    return claim


def label_external_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive frozen ReXGradient silver labels"
    )
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--split", choices=("validation", "test"), required=True)
    parser.add_argument("--mapping-spec", type=Path, required=True)
    parser.add_argument("--dedup-receipt", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    migration = _read_json(args.external_root / "receipts" / "migration_receipt.json")
    if migration.get("status") != "PASS_REXGRADIENT_SELECTED_SUBSET_MIGRATED":
        raise ValueError("external data migration receipt is not PASS")
    spec = validate_mapping_spec(_read_json(args.mapping_spec))
    dedup = _read_json(args.dedup_receipt)
    if dedup.get("status") != DEDUP_STATUS:
        raise ValueError("external labels require strict dedup PASS")
    if args.split == "test":
        if args.protocol is None:
            parser.error("test labeling requires --protocol")
        protocol = _read_json(args.protocol)
        if protocol.get("mapping_spec_sha256") != sha256_file(args.mapping_spec):
            raise ValueError("test mapping differs from frozen protocol")
        if protocol.get("dedup_receipt_sha256") != sha256_file(args.dedup_receipt):
            raise ValueError("test dedup receipt differs from frozen protocol")
        _claim_test_access(args.external_root, args.protocol)
    elif args.protocol is not None:
        parser.error("validation labeling must precede protocol freeze")
    pairs_path = (
        args.external_root / "manifests" / f"{args.split}_unlabeled_pairs.jsonl"
    )
    rows, audit = derive_external_labels(
        _read_jsonl(pairs_path),
        split=args.split,
        mapping_spec=spec,
        blocked_image_paths=set(map(str, dedup.get("blocked_external_paths", ()))),
    )
    staging = _fresh_staging(args.output)
    manifest_path = staging / f"{args.split}_labeled_rows.jsonl"
    write_jsonl_atomic(manifest_path, rows)
    receipt = {
        "schema": "prta-cxr.rexgradient-label-receipt.v1",
        "status": LABEL_STATUS,
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "external_split": args.split,
        "mapping_spec_sha256": sha256_file(args.mapping_spec),
        "mapping_spec_canonical_sha256": canonical_sha256(spec),
        "rules_contract_sha256": rules_contract_sha256(),
        "dedup_receipt_sha256": sha256_file(args.dedup_receipt),
        "source_pair_manifest_sha256": sha256_file(pairs_path),
        "labeled_manifest": manifest_path.name,
        "labeled_manifest_sha256": sha256_file(manifest_path),
        "audit": audit,
        "labeling_protocol_frozen_before_test": args.split == "test",
        "test_outcomes_used_for_mapping": False,
        "model_selection_performed": False,
    }
    write_json_atomic(staging / "label_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def _resolve_inside(root: Path, raw: object) -> Path:
    root = root.resolve()
    value = Path(str(raw))
    path = value.resolve() if value.is_absolute() else (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("image path escapes its registered root") from error
    if not path.is_file():
        raise FileNotFoundError("registered image is missing")
    return path


def bind_external_image_root(
    rows: Sequence[Mapping[str, Any]], image_root: Path
) -> list[dict[str, Any]]:
    result = []
    for raw in rows:
        row = dict(raw)
        for key in ("prior_image_path", "current_image_path"):
            row[key] = str(_resolve_inside(image_root, row[key]))
        result.append(row)
    return result


def _dhash64(path: Path) -> int:
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise RuntimeError("perceptual deduplication requires Pillow") from error
    with Image.open(path) as image:
        pixels = np.asarray(
            ImageOps.exif_transpose(image).convert("L").resize((9, 8)),
            dtype=np.uint8,
        )
    bits = pixels[:, 1:] > pixels[:, :-1]
    value = 0
    for bit in bits.reshape(-1):
        value = (value << 1) | int(bit)
    return value


class _BKTree:
    def __init__(self) -> None:
        self.root: tuple[int, dict[int, Any]] | None = None

    @staticmethod
    def _distance(left: int, right: int) -> int:
        return (left ^ right).bit_count()

    def add(self, value: int) -> None:
        if self.root is None:
            self.root = (value, {})
            return
        node = self.root
        while True:
            distance = self._distance(value, node[0])
            child = node[1].get(distance)
            if child is None:
                node[1][distance] = (value, {})
                return
            node = child

    def query(self, value: int, threshold: int) -> list[tuple[int, int]]:
        if self.root is None:
            return []
        found: list[tuple[int, int]] = []
        pending = [self.root]
        while pending:
            node = pending.pop()
            distance = self._distance(value, node[0])
            if distance <= threshold:
                found.append((distance, node[0]))
            lower = distance - threshold
            upper = distance + threshold
            pending.extend(
                child for edge, child in node[1].items() if lower <= edge <= upper
            )
        return found


def _fingerprint(path: Path) -> tuple[str, int]:
    return sha256_file(path), _dhash64(path)


def deduplicate_external_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strict ReXGradient cross-dataset dedup"
    )
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--internal-manifest", type=Path, required=True)
    parser.add_argument("--internal-image-root", type=Path, required=True)
    parser.add_argument("--perceptual-threshold", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if not 0 <= args.perceptual_threshold <= 8:
        parser.error("--perceptual-threshold must be between 0 and 8")
    inventory_path = args.external_root / "manifests" / "image_inventory.jsonl"
    external_inventory = _read_jsonl(inventory_path)
    internal_rows = _read_jsonl(args.internal_manifest)
    internal_images: dict[str, Path] = {}
    for row in internal_rows:
        source = str(row.get("source", "internal"))
        for key in ("prior_image_path", "current_image_path"):
            if key not in row:
                continue
            path = _resolve_inside(args.internal_image_root, row[key])
            private_key = hashlib.sha256(f"{source}|{row[key]}".encode()).hexdigest()
            internal_images.setdefault(private_key, path)
    if not internal_images:
        raise ValueError("internal dedup surface is empty")
    sha_index: dict[str, list[str]] = defaultdict(list)
    dhash_index: dict[int, list[str]] = defaultdict(list)
    tree = _BKTree()
    for private_key, path in sorted(internal_images.items()):
        digest, perceptual = _fingerprint(path)
        sha_index[digest].append(private_key)
        if perceptual not in dhash_index:
            tree.add(perceptual)
        dhash_index[perceptual].append(private_key)
    candidates = []
    blocked: set[str] = set()
    for item in external_inventory:
        relative = str(item["relative_path"])
        path = _resolve_inside(args.external_root, relative)
        digest, perceptual = _fingerprint(path)
        exact = sha_index.get(digest, [])
        matches = tree.query(perceptual, args.perceptual_threshold)
        if exact or matches:
            blocked.add(relative)
            candidates.append(
                {
                    "external_relative_path": relative,
                    "external_sha256": digest,
                    "exact_internal_key_hashes": sorted(exact),
                    "perceptual_candidates": [
                        {
                            "distance": distance,
                            "internal_key_hashes": sorted(dhash_index[value]),
                        }
                        for distance, value in sorted(matches)
                    ],
                    "decision": "EXCLUDE_EXTERNAL_IMAGE_CONSERVATIVELY",
                }
            )
    staging = _fresh_staging(args.output)
    candidate_path = staging / "private_dedup_candidates.jsonl"
    write_jsonl_atomic(candidate_path, candidates)
    receipt = {
        "schema": "prta-cxr.rexgradient-dedup-receipt.v1",
        "status": DEDUP_STATUS,
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "external_inventory_sha256": sha256_file(inventory_path),
        "internal_manifest_sha256": sha256_file(args.internal_manifest),
        "internal_unique_images": len(internal_images),
        "external_unique_images": len(external_inventory),
        "perceptual_algorithm": "grayscale_dhash64_v1",
        "perceptual_hamming_threshold": args.perceptual_threshold,
        "blocked_external_paths": sorted(blocked),
        "blocked_external_image_count": len(blocked),
        "candidate_manifest_sha256": sha256_file(candidate_path),
        "candidate_rows": len(candidates),
        "unresolved_candidate_count": 0,
        "candidate_policy": "conservative_exclusion",
        "raw_internal_paths_written": False,
    }
    write_json_atomic(staging / "dedup_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def validate_slim_s1_checkpoint(
    checkpoint: Mapping[str, Any], training_receipt: Mapping[str, Any]
) -> tuple[int, dict[str, Any]]:
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported checkpoint schema")
    if (
        training_receipt.get("schema") != "prta-cxr.training-receipt.v1"
        or training_receipt.get("status") != "PASS_TRAINING_FINISHED"
        or training_receipt.get("formal_experiment") is not True
    ):
        raise ValueError("Slim-S1 training receipt is not terminal formal PASS")
    config = dict(checkpoint.get("config", {}))
    seed = int(config.get("seed", -1))
    if seed not in SEEDS or config.get("experiment_id") != f"P20-FINAL-S1-S{seed}":
        raise ValueError("checkpoint is not a registered final Slim-S1 seed")
    if (
        config.get("final_mainline") != "Slim-S1"
        or config.get("prta_v2_variant") != "Slim-S1"
        or config.get("phase20_axis") != "final_mainline_confirmation"
    ):
        raise ValueError("checkpoint final-mainline identity drift")
    model = dict(config.get("model", {}))
    components = dict(model.get("components", {}))
    if (
        model.get("family") != "prta"
        or model.get("adapter_scope") != "tail8"
        or model.get("native_head") != "H0"
        or int(model.get("adapter_rank", -1)) != 32
    ):
        raise ValueError("checkpoint Slim-S1 model contract drift")
    for key in (
        "finding_conditioning",
        "cross_time_alignment",
        "temporal_relation_residual",
        "matched_hard_cmcp",
    ):
        if components.get(key) is not True:
            raise ValueError(f"checkpoint Slim-S1 component drift: {key}")
    weights = dict(config.get("loss_weights", {}))
    expected_weights = {
        "prototype_alignment": 0.0,
        "state": 0.025,
        "opposite_direction_cost": 0.05,
        "cmcp": 0.01,
        "direction_margin": 0.0,
    }
    for key, expected in expected_weights.items():
        if float(weights.get(key, -1.0)) != expected:
            raise ValueError(f"checkpoint Slim-S1 loss drift: {key}")
    if dict(config.get("cmcp", {})).get("matching") != "offline_hard_v1":
        raise ValueError("checkpoint Slim-S1 CMCP matching drift")
    config_hash = canonical_sha256(config)
    if training_receipt.get("config_sha256") != config_hash:
        raise ValueError("checkpoint/training config identity drift")
    if dict(training_receipt.get("input_hashes", {})) != dict(
        checkpoint.get("input_hashes", {})
    ):
        raise ValueError("checkpoint/training input identity drift")
    return seed, config


def freeze_external_protocol_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze ReXGradient test protocol")
    parser.add_argument("--mapping-spec", type=Path, required=True)
    parser.add_argument("--validation-label-receipt", type=Path, required=True)
    parser.add_argument("--dedup-receipt", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, nargs=3, required=True)
    parser.add_argument("--training-receipt", type=Path, nargs=3, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    spec = validate_mapping_spec(_read_json(args.mapping_spec))
    validation = _read_json(args.validation_label_receipt)
    if (
        validation.get("status") != LABEL_STATUS
        or validation.get("external_split") != "validation"
        or validation.get("mapping_spec_sha256") != sha256_file(args.mapping_spec)
        or validation.get("test_outcomes_used_for_mapping") is not False
    ):
        raise ValueError("validation mapping receipt is not freeze-eligible")
    minimum = int(spec["minimum_validation_support_per_class"])
    counts = dict(dict(validation.get("audit", {})).get("label_counts", {}))
    insufficient = {
        label: int(counts.get(label, 0))
        for label in PROGRESSION_LABELS
        if int(counts.get(label, 0)) < minimum
    }
    if insufficient:
        raise ValueError(
            f"validation mapping lacks minimum class support: {insufficient}"
        )
    dedup = _read_json(args.dedup_receipt)
    if (
        dedup.get("status") != DEDUP_STATUS
        or int(dedup.get("unresolved_candidate_count", -1)) != 0
    ):
        raise ValueError("strict dedup is not closed PASS")
    roster = []
    for checkpoint_path, receipt_path in zip(
        args.checkpoint, args.training_receipt, strict=True
    ):
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        training = _read_json(receipt_path)
        seed, config = validate_slim_s1_checkpoint(checkpoint, training)
        input_hashes = dict(checkpoint.get("input_hashes", {}))
        if input_hashes.get("weights") != sha256_file(args.weights):
            raise ValueError(f"Slim-S1 S{seed} BiomedCLIP weight identity drift")
        roster.append(
            {
                "seed": seed,
                "experiment_id": config["experiment_id"],
                "checkpoint_sha256": sha256_file(checkpoint_path),
                "training_receipt_sha256": sha256_file(receipt_path),
                "config_sha256": canonical_sha256(config),
            }
        )
    roster.sort(key=lambda item: int(item["seed"]))
    if tuple(int(item["seed"]) for item in roster) != SEEDS:
        raise ValueError("external checkpoint roster must be S17/S28/S43")
    receipt = {
        "schema": "prta-cxr.rexgradient-external-protocol.v1",
        "status": PROTOCOL_STATUS,
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "mapping_spec_sha256": sha256_file(args.mapping_spec),
        "mapping_spec_canonical_sha256": canonical_sha256(spec),
        "rules_contract_sha256": rules_contract_sha256(),
        "validation_label_receipt_sha256": sha256_file(args.validation_label_receipt),
        "validation_label_counts": counts,
        "dedup_receipt_sha256": sha256_file(args.dedup_receipt),
        "weights_sha256": sha256_file(args.weights),
        "checkpoint_roster": roster,
        "checkpoint_roster_sha256": canonical_sha256(roster),
        "primary_metric": "three_seed_mean_patient_balanced_macro_f1",
        "secondary_metrics": [
            "balanced_accuracy",
            "opposite_direction_error_rate",
            "per_class_f1",
        ],
        "bootstrap_unit": "patient",
        "bootstrap_replicates": int(spec["bootstrap_replicates"]),
        "bootstrap_seed": int(spec["bootstrap_seed"]),
        "public_test_accesses_allowed": 1,
        "model_selection_allowed": False,
        "threshold_tuning_allowed": False,
        "external_outcomes_used_for_training": False,
    }
    staging = _fresh_staging(args.output)
    write_json_atomic(staging / "protocol_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


@torch.inference_mode()
def _predict_external(
    model: torch.nn.Module, loader: DataLoader, *, device: torch.device
) -> list[dict[str, Any]]:
    model.eval()
    rows = []
    for batch in loader:
        _, logits, _ = model(
            batch["prior"].to(device),
            batch["current"].to(device),
            batch["finding_text"].to(device),
        )
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
                    "probabilities": probabilities[index].tolist(),
                    "source": str(batch["source"][index]),
                    "finding": str(batch["finding"][index]),
                }
            )
    return rows


def external_inference_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run frozen Slim-S1 on ReXGradient")
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--split", choices=("validation", "test"), required=True)
    parser.add_argument("--label-manifest", type=Path, required=True)
    parser.add_argument("--label-receipt", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    protocol = _read_json(args.protocol)
    if protocol.get("status") != PROTOCOL_STATUS:
        raise ValueError("external inference requires frozen protocol PASS")
    label_receipt = _read_json(args.label_receipt)
    if (
        label_receipt.get("status") != LABEL_STATUS
        or label_receipt.get("external_split") != args.split
        or label_receipt.get("labeled_manifest_sha256")
        != sha256_file(args.label_manifest)
        or label_receipt.get("mapping_spec_sha256")
        != protocol.get("mapping_spec_sha256")
        or label_receipt.get("dedup_receipt_sha256")
        != protocol.get("dedup_receipt_sha256")
    ):
        raise ValueError("external label artifact drifts from frozen protocol")
    if args.split == "test":
        _claim_test_access(args.external_root, args.protocol)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    training = _read_json(args.training_receipt)
    seed, config = validate_slim_s1_checkpoint(checkpoint, training)
    roster = {int(item["seed"]): dict(item) for item in protocol["checkpoint_roster"]}
    if seed not in roster:
        raise ValueError("checkpoint seed is absent from frozen external roster")
    frozen = roster[seed]
    if (
        frozen["checkpoint_sha256"] != sha256_file(args.checkpoint)
        or frozen["training_receipt_sha256"] != sha256_file(args.training_receipt)
        or frozen["config_sha256"] != canonical_sha256(config)
        or protocol.get("weights_sha256") != sha256_file(args.weights)
    ):
        raise ValueError("external inference checkpoint/input identity drift")
    cache_manifest_path = args.cache_root / "cache_manifest.json"
    cache_manifest = _read_json(cache_manifest_path)
    expected_block = adapter_scope_cache_entry_block(config["model"]["adapter_scope"])
    if (
        int(cache_manifest.get("cache_entry_block", -1)) != expected_block
        or cache_manifest.get("status") != f"PASS_PRTA_CXR_BLOCK{expected_block}_CACHE"
        or dict(cache_manifest.get("formal_input", {})).get(
            "sample_manifest_file_sha256"
        )
        != sha256_file(args.label_manifest)
    ):
        raise ValueError("external feature cache identity drift")
    rows = bind_external_image_root(read_jsonl(args.label_manifest), args.external_root)
    cache = Block8CacheIndex(args.cache_root)
    dataset = PRTAFeatureDataset(
        rows,
        cache=cache,
        text_cache_path=args.cache_root / "text_cache.pt",
        split=args.split,
    )
    loader = DataLoader(
        dataset, batch_size=args.batch_size, shuffle=False, num_workers=0
    )
    visual, _ = load_biomedclip_visual(args.weights)
    blocks, final_norm = tail_modules(visual, start_block=expected_block)
    model = build_train_model(blocks, final_norm, config)
    model.load_state_dict(checkpoint["model_state"], strict=True)
    device = torch.device(args.device)
    model.to(device)
    predictions = _predict_external(model, loader, device=device)
    metrics = classification_metrics(predictions, labels=PROGRESSION_LABELS)
    staging = _fresh_staging(args.output)
    prediction_path = staging / "predictions.jsonl"
    write_jsonl_atomic(prediction_path, predictions)
    receipt = {
        "schema": "prta-cxr.rexgradient-external-inference.v1",
        "status": INFERENCE_STATUS,
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "external_split": args.split,
        "seed": seed,
        "experiment_id": config["experiment_id"],
        "rows": len(predictions),
        "patients": len({row["patient_id"] for row in predictions}),
        "metrics": metrics,
        "protocol_sha256": sha256_file(args.protocol),
        "label_manifest_sha256": sha256_file(args.label_manifest),
        "label_receipt_sha256": sha256_file(args.label_receipt),
        "cache_manifest_sha256": sha256_file(cache_manifest_path),
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "training_receipt_sha256": sha256_file(args.training_receipt),
        "prediction_sha256": sha256_file(prediction_path),
        "selection_performed": False,
        "threshold_tuning_performed": False,
    }
    write_json_atomic(staging / "inference_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def bootstrap_external_metrics(
    rows: Sequence[Mapping[str, Any]], *, replicates: int, rng_seed: int
) -> dict[str, Any]:
    if replicates < 2:
        raise ValueError("at least two bootstrap replicates are required")
    by_patient: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_patient[str(row["patient_id"])].append(dict(row))
    patients = sorted(by_patient)
    if len(patients) < 2:
        raise ValueError("patient bootstrap requires at least two patients")
    point = classification_metrics(rows, labels=PROGRESSION_LABELS)
    keys = (
        "macro_f1",
        "balanced_accuracy",
        "opposite_direction_error_rate",
    )
    samples = {key: [] for key in keys}
    invalid = 0
    rng = np.random.default_rng(rng_seed)
    for _ in range(replicates):
        selected = rng.integers(0, len(patients), size=len(patients))
        drawn = []
        for draw_index, patient_index in enumerate(selected):
            patient = patients[int(patient_index)]
            for raw in by_patient[patient]:
                row = dict(raw)
                row["patient_id"] = f"bootstrap-{draw_index}"
                drawn.append(row)
        try:
            metrics = classification_metrics(drawn, labels=PROGRESSION_LABELS)[
                "patient_balanced"
            ]
        except ValueError:
            invalid += 1
            continue
        for key in keys:
            samples[key].append(float(metrics[key]))
    valid = replicates - invalid
    if valid < max(2, round(0.95 * replicates)):
        raise ValueError("fewer than 95% valid patient-bootstrap replicates")
    return {
        "point": point,
        "intervals": {
            key: {
                "lower": float(np.quantile(values, 0.025)),
                "upper": float(np.quantile(values, 0.975)),
                "level": 0.95,
            }
            for key, values in samples.items()
        },
        "requested_replicates": replicates,
        "valid_replicates": valid,
        "invalid_replicates": invalid,
        "rng_seed": rng_seed,
        "resampling_unit": "patient",
    }


def finalize_external_test_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize one-time ReXGradient test")
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--inference", type=Path, nargs=3, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    protocol = _read_json(args.protocol)
    if protocol.get("status") != PROTOCOL_STATUS:
        raise ValueError("external finalizer requires frozen protocol PASS")
    claim = _claim_test_access(args.external_root, args.protocol)
    completion_path = (
        args.external_root / "receipts" / "test_evaluation_completion.json"
    )
    if completion_path.exists():
        raise FileExistsError("ReXGradient public test was already finalized")
    blocks: dict[int, list[dict[str, Any]]] = {}
    receipts = {}
    for root in args.inference:
        receipt_path = root / "inference_receipt.json"
        prediction_path = root / "predictions.jsonl"
        receipt = _read_json(receipt_path)
        if (
            receipt.get("status") != INFERENCE_STATUS
            or receipt.get("external_split") != "test"
            or receipt.get("protocol_sha256") != sha256_file(args.protocol)
            or receipt.get("prediction_sha256") != sha256_file(prediction_path)
            or receipt.get("selection_performed") is not False
        ):
            raise ValueError("external test inference receipt is invalid")
        seed = int(receipt["seed"])
        if seed in blocks:
            raise ValueError("duplicate external inference seed")
        blocks[seed] = _read_jsonl(prediction_path)
        receipts[seed] = {
            "inference_receipt_sha256": sha256_file(receipt_path),
            "prediction_sha256": sha256_file(prediction_path),
            "metrics": receipt["metrics"],
        }
    if tuple(sorted(blocks)) != SEEDS:
        raise ValueError("external test finalizer requires S17/S28/S43")
    indexed_blocks = {
        seed: {str(row["observation_id"]): dict(row) for row in rows}
        for seed, rows in blocks.items()
    }
    if any(len(indexed_blocks[seed]) != len(blocks[seed]) for seed in SEEDS):
        raise ValueError("external prediction IDs are not unique")
    reference = indexed_blocks[SEEDS[0]]
    for seed in SEEDS[1:]:
        candidate = indexed_blocks[seed]
        if set(candidate) != set(reference):
            raise ValueError("external prediction layout differs across seeds")
        for sample_id, row in reference.items():
            other = candidate[sample_id]
            if (
                other["patient_id"] != row["patient_id"]
                or other["target"] != row["target"]
                or other["finding"] != row["finding"]
            ):
                raise ValueError("external target/patient/finding drift across seeds")
    ensemble = []
    for sample_id in sorted(reference):
        row = reference[sample_id]
        probabilities = np.mean(
            [
                np.asarray(
                    indexed_blocks[seed][sample_id]["probabilities"],
                    dtype=np.float64,
                )
                for seed in SEEDS
            ],
            axis=0,
        )
        prediction = PROGRESSION_LABELS[int(probabilities.argmax())]
        ensemble.append(
            {
                "patient_id": str(row["patient_id"]),
                "observation_id": sample_id,
                "target": str(row["target"]),
                "prediction": prediction,
                "probabilities": probabilities.tolist(),
                "finding": str(row["finding"]),
                "source": "rexgradient_160k",
            }
        )
    bootstrap = bootstrap_external_metrics(
        ensemble,
        replicates=int(protocol["bootstrap_replicates"]),
        rng_seed=int(protocol["bootstrap_seed"]),
    )
    seed_primary = {
        str(seed): float(receipts[seed]["metrics"]["patient_balanced"]["macro_f1"])
        for seed in SEEDS
    }
    staging = _fresh_staging(args.output)
    ensemble_path = staging / "ensemble_predictions.jsonl"
    write_jsonl_atomic(ensemble_path, ensemble)
    receipt = {
        "schema": "prta-cxr.rexgradient-public-test-final.v1",
        "status": FINAL_STATUS,
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "protocol_sha256": sha256_file(args.protocol),
        "test_access_claim_sha256": canonical_sha256(claim),
        "seed_receipts": receipts,
        "seed_patient_balanced_macro_f1": seed_primary,
        "three_seed_mean_patient_balanced_macro_f1": float(
            np.mean(list(seed_primary.values()))
        ),
        "three_seed_sd_patient_balanced_macro_f1": float(
            np.std(list(seed_primary.values()), ddof=1)
        ),
        "ensemble": bootstrap,
        "ensemble_prediction_sha256": sha256_file(ensemble_path),
        "rows": len(ensemble),
        "patients": len({row["patient_id"] for row in ensemble}),
        "selection_performed": False,
        "threshold_tuning_performed": False,
        "checkpoint_reselection_performed": False,
        "external_test_access_count": 1,
    }
    receipt_path = staging / "external_test_final_receipt.json"
    write_json_atomic(receipt_path, receipt)
    staging.replace(args.output)
    completion = {
        "schema": "prta-cxr.rexgradient-test-completion.v1",
        "status": "SEALED_ONE_TIME_EXTERNAL_TEST_COMPLETE",
        "protocol_sha256": sha256_file(args.protocol),
        "final_receipt_sha256": sha256_file(args.output / receipt_path.name),
        "selection_performed": False,
    }
    write_json_atomic(completion_path, completion)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def external_stage_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ReXGradient external evaluation stages"
    )
    parser.add_argument(
        "stage",
        choices=("dedup", "label", "freeze", "infer", "finalize"),
    )
    args, remainder = parser.parse_known_args(argv)
    functions = {
        "dedup": deduplicate_external_main,
        "label": label_external_main,
        "freeze": freeze_external_protocol_main,
        "infer": external_inference_main,
        "finalize": finalize_external_test_main,
    }
    return functions[args.stage](remainder)


def build_external_program_jobs() -> dict[str, list[dict[str, Any]]]:
    script = "{source}/scripts/128_rexgradient_external_evaluation.py"

    def stage(name: str, *arguments: str) -> list[str]:
        return ["{python}", script, name, *arguments, "--formal"]

    jobs = [
        {
            "job_id": "rex-dedup",
            "lane": "external_gpu0",
            "group": "data_gate",
            "estimated_seconds": 7200,
            "dependencies": [],
            "command": stage(
                "dedup",
                "--external-root",
                "{external_root}",
                "--internal-manifest",
                "{internal_manifest}",
                "--internal-image-root",
                "{internal_image_root}",
                "--output",
                "{output_root}/runs/dedup",
            ),
            "expected_outputs": ["{output_root}/runs/dedup/dedup_receipt.json"],
        },
        {
            "job_id": "rex-label-validation",
            "lane": "external_gpu0",
            "group": "mapping_gate",
            "estimated_seconds": 300,
            "dependencies": ["rex-dedup"],
            "command": stage(
                "label",
                "--external-root",
                "{external_root}",
                "--split",
                "validation",
                "--mapping-spec",
                "{mapping_spec}",
                "--dedup-receipt",
                "{output_root}/runs/dedup/dedup_receipt.json",
                "--output",
                "{output_root}/runs/label-validation",
            ),
            "expected_outputs": [
                "{output_root}/runs/label-validation/label_receipt.json",
                "{output_root}/runs/label-validation/validation_labeled_rows.jsonl",
            ],
        },
        {
            "job_id": "rex-freeze-protocol",
            "lane": "external_gpu0",
            "group": "protocol_gate",
            "estimated_seconds": 120,
            "dependencies": ["rex-label-validation"],
            "command": stage(
                "freeze",
                "--mapping-spec",
                "{mapping_spec}",
                "--validation-label-receipt",
                "{output_root}/runs/label-validation/label_receipt.json",
                "--dedup-receipt",
                "{output_root}/runs/dedup/dedup_receipt.json",
                "--checkpoint",
                "{checkpoint_17}",
                "{checkpoint_28}",
                "{checkpoint_43}",
                "--training-receipt",
                "{training_receipt_17}",
                "{training_receipt_28}",
                "{training_receipt_43}",
                "--weights",
                "{weights}",
                "--output",
                "{output_root}/runs/protocol",
            ),
            "expected_outputs": ["{output_root}/runs/protocol/protocol_receipt.json"],
        },
        {
            "job_id": "rex-cache-validation",
            "lane": "external_gpu0",
            "group": "validation_cache",
            "estimated_seconds": 2400,
            "dependencies": ["rex-freeze-protocol"],
            "command": [
                "{python}",
                "{source}/scripts/06_cache_vit_tokens.py",
                "--mode",
                "formal",
                "--sample-manifest",
                "{output_root}/runs/label-validation/validation_labeled_rows.jsonl",
                "--image-root",
                "{external_root}",
                "--weights",
                "{weights}",
                "--model-root",
                "{model_root}",
                "--output-block",
                "4",
                "--output",
                "{output_root}/runs/cache-validation",
                "--device",
                "{device}",
                "--formal",
            ],
            "expected_outputs": [
                "{output_root}/runs/cache-validation/cache_manifest.json",
                "{output_root}/runs/cache-validation/text_cache.pt",
            ],
        },
        {
            "job_id": "rex-label-test",
            "lane": "external_gpu1",
            "group": "sealed_test_gate",
            "estimated_seconds": 300,
            "dependencies": ["rex-freeze-protocol"],
            "command": stage(
                "label",
                "--external-root",
                "{external_root}",
                "--split",
                "test",
                "--mapping-spec",
                "{mapping_spec}",
                "--dedup-receipt",
                "{output_root}/runs/dedup/dedup_receipt.json",
                "--protocol",
                "{output_root}/runs/protocol/protocol_receipt.json",
                "--output",
                "{output_root}/runs/label-test",
            ),
            "expected_outputs": [
                "{output_root}/runs/label-test/label_receipt.json",
                "{output_root}/runs/label-test/test_labeled_rows.jsonl",
            ],
        },
        {
            "job_id": "rex-cache-test",
            "lane": "external_gpu1",
            "group": "sealed_test_cache",
            "estimated_seconds": 2400,
            "dependencies": ["rex-label-test"],
            "command": [
                "{python}",
                "{source}/scripts/06_cache_vit_tokens.py",
                "--mode",
                "formal",
                "--sample-manifest",
                "{output_root}/runs/label-test/test_labeled_rows.jsonl",
                "--image-root",
                "{external_root}",
                "--weights",
                "{weights}",
                "--model-root",
                "{model_root}",
                "--output-block",
                "4",
                "--output",
                "{output_root}/runs/cache-test",
                "--device",
                "{device}",
                "--formal",
            ],
            "expected_outputs": [
                "{output_root}/runs/cache-test/cache_manifest.json",
                "{output_root}/runs/cache-test/text_cache.pt",
            ],
        },
    ]

    for split in ("validation", "test"):
        cache_job = f"rex-cache-{split}"
        label_dir = f"label-{split}"
        cache_dir = f"cache-{split}"
        for seed in SEEDS:
            if split == "validation":
                lane = "external_gpu0" if seed in {17, 28} else "external_gpu1"
            else:
                lane = "external_gpu0" if seed == 17 else "external_gpu1"
            job_id = f"rex-infer-{split}-s{seed}"
            jobs.append(
                {
                    "job_id": job_id,
                    "lane": lane,
                    "group": f"{split}_inference",
                    "estimated_seconds": 900,
                    "dependencies": [cache_job],
                    "command": stage(
                        "infer",
                        "--external-root",
                        "{external_root}",
                        "--split",
                        split,
                        "--label-manifest",
                        f"{{output_root}}/runs/{label_dir}/{split}_labeled_rows.jsonl",
                        "--label-receipt",
                        f"{{output_root}}/runs/{label_dir}/label_receipt.json",
                        "--protocol",
                        "{output_root}/runs/protocol/protocol_receipt.json",
                        "--cache-root",
                        f"{{output_root}}/runs/{cache_dir}",
                        "--checkpoint",
                        f"{{checkpoint_{seed}}}",
                        "--training-receipt",
                        f"{{training_receipt_{seed}}}",
                        "--weights",
                        "{weights}",
                        "--output",
                        f"{{output_root}}/runs/infer-{split}-s{seed}",
                        "--device",
                        "{device}",
                    ),
                    "expected_outputs": [
                        f"{{output_root}}/runs/infer-{split}-s{seed}/inference_receipt.json",
                        f"{{output_root}}/runs/infer-{split}-s{seed}/predictions.jsonl",
                    ],
                }
            )
    jobs.append(
        {
            "job_id": "rex-finalize-test",
            "lane": "external_gpu1",
            "group": "sealed_test_finalizer",
            "estimated_seconds": 900,
            "dependencies": [f"rex-infer-test-s{seed}" for seed in SEEDS],
            "command": stage(
                "finalize",
                "--external-root",
                "{external_root}",
                "--protocol",
                "{output_root}/runs/protocol/protocol_receipt.json",
                "--inference",
                "{output_root}/runs/infer-test-s17",
                "{output_root}/runs/infer-test-s28",
                "{output_root}/runs/infer-test-s43",
                "--output",
                "{output_root}/runs/final-test",
            ),
            "expected_outputs": [
                "{output_root}/runs/final-test/external_test_final_receipt.json"
            ],
        }
    )
    queues = {lane: [] for lane in ("external_gpu0", "external_gpu1")}
    for job in jobs:
        queues[str(job["lane"])].append(job)
    for queue in queues.values():
        for index, job in enumerate(queue):
            job["queue_index"] = index
    identifiers = [str(job["job_id"]) for queue in queues.values() for job in queue]
    if len(identifiers) != len(set(identifiers)) or len(identifiers) != 13:
        raise ValueError("ReXGradient program must contain 13 unique jobs")
    return queues


def prepare_external_program_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze ReXGradient queue template")
    parser.add_argument("--mapping-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    spec = validate_mapping_spec(_read_json(args.mapping_spec))
    staging = _fresh_staging(args.output)
    queues = build_external_program_jobs()
    queue_hashes = {}
    lane_loads = {}
    for lane, queue in queues.items():
        path = staging / "queue" / f"{lane}.json"
        write_json_atomic(path, queue)
        queue_hashes[lane] = sha256_file(path)
        lane_loads[lane] = sum(int(job["estimated_seconds"]) for job in queue)
    roles = [
        "external_root",
        "internal_manifest",
        "internal_image_root",
        "mapping_spec",
        "weights",
        "model_root",
        *(f"checkpoint_{seed}" for seed in SEEDS),
        *(f"training_receipt_{seed}" for seed in SEEDS),
    ]
    write_json_atomic(
        staging / "platform_template.json",
        {
            "schema": "prta-cxr.rexgradient-platform-template.v1",
            "required_roles": roles,
            "note": (
                "Populate these roles in a private runtime JSON; do not commit paths."
            ),
        },
    )
    receipt = {
        "schema": "prta-cxr.rexgradient-program-template.v1",
        "status": PROGRAM_STATUS,
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "mapping_spec_sha256": sha256_file(args.mapping_spec),
        "mapping_spec_canonical_sha256": canonical_sha256(spec),
        "rules_contract_sha256": rules_contract_sha256(),
        "job_count": 13,
        "lane_count": 2,
        "queue_sha256": queue_hashes,
        "lane_estimated_seconds": lane_loads,
        "lane_gpu_estimated_seconds": {
            lane: sum(
                int(job["estimated_seconds"])
                for job in queue
                if job["group"]
                in {
                    "validation_cache",
                    "sealed_test_cache",
                    "validation_inference",
                    "test_inference",
                }
            )
            for lane, queue in queues.items()
        },
        "public_test_jobs_depend_on_protocol_freeze": True,
        "formal_execution_started": False,
        "external_outcomes_opened": False,
    }
    write_json_atomic(staging / "preparation_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def _render_external(
    values: Sequence[object], replacements: Mapping[str, str]
) -> list[str]:
    rendered = []
    for raw in values:
        value = str(raw)
        for key, replacement in replacements.items():
            value = value.replace("{" + key + "}", replacement)
        if "{" in value or "}" in value:
            raise ValueError(f"unresolved external-program placeholder: {value}")
        rendered.append(value)
    return rendered


def run_external_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one ReXGradient queue lane")
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--platform", type=Path, required=True)
    parser.add_argument(
        "--lane", choices=("external_gpu0", "external_gpu1"), required=True
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-state", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    program = _read_json(args.program / "preparation_receipt.json")
    if program.get("status") != PROGRAM_STATUS or program.get(
        "source_commit"
    ) != resolve_source_commit(args.source):
        raise ValueError("external program/source identity drift")
    queue_path = args.program / "queue" / f"{args.lane}.json"
    if program["queue_sha256"][args.lane] != sha256_file(queue_path):
        raise ValueError("external queue hash drift")
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    platform = _read_json(args.platform)
    required = set(
        _read_json(args.program / "platform_template.json")["required_roles"]
    )
    if set(platform) != required:
        raise ValueError("external platform role set drift")
    paths = {key: Path(str(value)).resolve() for key, value in platform.items()}
    for role in ("external_root", "internal_image_root", "model_root"):
        if not paths[role].is_dir():
            raise FileNotFoundError(f"external platform directory missing: {role}")
    for role, path in paths.items():
        if (
            role not in {"external_root", "internal_image_root", "model_root"}
            and not path.is_file()
        ):
            raise FileNotFoundError(f"external platform file missing: {role}")
    if sha256_file(paths["mapping_spec"]) != program["mapping_spec_sha256"]:
        raise ValueError("external platform mapping-spec drift")
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.shared_state.mkdir(parents=True, exist_ok=True)
    logs = args.output_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    replacements = {
        "python": sys.executable,
        "source": str(args.source.resolve()),
        "output_root": str(args.output_root.resolve()),
        "device": args.device,
        **{role: str(path) for role, path in paths.items()},
    }
    completed = []
    environment = os.environ.copy()
    environment["PRTA_CXR_ALLOW_FORMAL"] = "I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN"
    for job in queue:
        job_id = str(job["job_id"])
        state_path = args.shared_state / f"{job_id}.json"
        if state_path.is_file():
            existing = _read_json(state_path)
            if existing.get("status") == "PASS":
                completed.append(job_id)
                continue
            raise RuntimeError(f"non-PASS external state already exists: {job_id}")
        while True:
            dependencies = []
            for dependency in job.get("dependencies", []):
                dependency_path = args.shared_state / f"{dependency}.json"
                status = (
                    _read_json(dependency_path).get("status")
                    if dependency_path.is_file()
                    else "PENDING"
                )
                dependencies.append(str(status))
            if any(status == "FAILED" for status in dependencies):
                raise RuntimeError(f"external dependency failed: {job_id}")
            if all(status == "PASS" for status in dependencies):
                break
            time.sleep(args.poll_seconds)
        command = _render_external(job["command"], replacements)
        running = {
            "schema": "prta-cxr.rexgradient-job-state.v1",
            "status": "RUNNING",
            "job_id": job_id,
            "lane": args.lane,
            "started_at": _now(),
            "queue_sha256": sha256_file(queue_path),
            "command": command,
        }
        replace_json_atomic(state_path, running)
        stdout_path = logs / f"{job_id}.stdout.log"
        stderr_path = logs / f"{job_id}.stderr.log"
        with (
            stdout_path.open("x", encoding="utf-8") as stdout,
            stderr_path.open("x", encoding="utf-8") as stderr,
        ):
            result = subprocess.run(
                command,
                cwd=args.source,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        checks = []
        for path_value in _render_external(job["expected_outputs"], replacements):
            path = Path(path_value)
            checks.append(
                {
                    "path": str(path),
                    "exists": path.is_file(),
                    "sha256": sha256_file(path) if path.is_file() else None,
                }
            )
        passed = result.returncode == 0 and all(item["exists"] for item in checks)
        terminal = {
            **running,
            "status": "PASS" if passed else "FAILED",
            "finished_at": _now(),
            "return_code": result.returncode,
            "output_checks": checks,
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_sha256": sha256_file(stderr_path),
        }
        replace_json_atomic(state_path, terminal)
        if not passed:
            raise RuntimeError(f"external job failed: {job_id}")
        completed.append(job_id)
    completion = {
        "schema": "prta-cxr.rexgradient-lane-completion.v1",
        "status": "PASS_REXGRADIENT_LANE_COMPLETE",
        "lane": args.lane,
        "jobs": completed,
        "queue_sha256": sha256_file(queue_path),
    }
    write_json_atomic(args.output_root / f"{args.lane}_completion.json", completion)
    print(json.dumps(completion, indent=2, sort_keys=True))
    return 0
