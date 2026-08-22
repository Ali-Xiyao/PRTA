from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch

from prta_cxr.attention_flow import (
    EXPECTED_SEEDS,
    SELECTION_SALT,
    capture_true_attention,
)
from prta_cxr.contracts import sha256_file

BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20_260_818
MINIMUM_CELL_SUPPORT = 100


def _pair_identity(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row["source"]),
        str(row["patient_id_hash"]),
        str(row["prior_image_path"]),
        str(row["current_image_path"]),
    )


def _salted_pair_hash(identity: Sequence[str], *, salt: str) -> str:
    return hashlib.sha256(f"{salt}|pair|{'|'.join(identity)}".encode()).hexdigest()


def _prediction_index(
    seed_blocks: Sequence[tuple[int, Sequence[Mapping[str, Any]]]],
) -> dict[int, dict[str, Mapping[str, Any]]]:
    blocks = sorted((int(seed), list(rows)) for seed, rows in seed_blocks)
    if tuple(seed for seed, _ in blocks) != EXPECTED_SEEDS:
        raise ValueError("query sensitivity requires S17/S28/S43 predictions")
    result: dict[int, dict[str, Mapping[str, Any]]] = {}
    reference: dict[str, tuple[str, str, str]] | None = None
    for seed, rows in blocks:
        indexed = {str(row["observation_id"]): row for row in rows}
        if len(indexed) != len(rows):
            raise ValueError(f"duplicate observation_id in S{seed}")
        identity = {
            sample_id: (
                str(row["patient_id"]),
                str(row["finding"]),
                str(row["target"]),
            )
            for sample_id, row in indexed.items()
        }
        if reference is None:
            reference = identity
        elif identity != reference:
            raise ValueError("query-sensitivity prediction cohort drift")
        result[seed] = indexed
    return result


def freeze_query_sensitivity_cohort(
    manifest_rows: Sequence[Mapping[str, Any]],
    seed_blocks: Sequence[tuple[int, Sequence[Mapping[str, Any]]]],
    *,
    minimum_cell_support: int = MINIMUM_CELL_SUPPORT,
    salt: str = SELECTION_SALT,
) -> dict[str, Any]:
    """Freeze all reportable multi-finding pairs before qualitative access."""

    if minimum_cell_support < 1:
        raise ValueError("minimum_cell_support must be positive")
    predictions = _prediction_index(seed_blocks)
    dev_rows = [dict(row) for row in manifest_rows if row.get("split") == "dev"]
    if not dev_rows:
        raise ValueError("query sensitivity requires a non-empty Dev split")
    support = Counter(
        (str(row["finding"]), str(row["progression_label"])) for row in dev_rows
    )
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    seen_ids: set[str] = set()
    for row in dev_rows:
        sample_id = str(row["sample_id"])
        if sample_id in seen_ids:
            raise ValueError("duplicate sample_id in Dev manifest")
        seen_ids.add(sample_id)
        if sample_id not in predictions[EXPECTED_SEEDS[0]]:
            raise ValueError("Dev manifest/prediction cohort mismatch")
        cell = (str(row["finding"]), str(row["progression_label"]))
        if support[cell] >= minimum_cell_support:
            grouped[_pair_identity(row)].append(row)

    eligible_pairs: list[dict[str, Any]] = []
    for identity, rows in grouped.items():
        findings = [str(row["finding"]) for row in rows]
        if len(findings) != len(set(findings)):
            raise ValueError("duplicate finding within an identical CXR pair")
        if len(rows) < 2:
            continue
        pair_hash = _salted_pair_hash(identity, salt=salt)
        ordered = sorted(rows, key=lambda row: str(row["finding"]))
        eligible_pairs.append(
            {
                "pair_hash": pair_hash,
                "patient_id_hash": identity[1],
                "source": identity[0],
                "prior_image_path": identity[2],
                "current_image_path": identity[3],
                "rows": [
                    {
                        "sample_id": str(row["sample_id"]),
                        "finding": str(row["finding"]),
                        "reference_progression": str(row["progression_label"]),
                        "cell_support": int(
                            support[
                                (
                                    str(row["finding"]),
                                    str(row["progression_label"]),
                                )
                            ]
                        ),
                    }
                    for row in ordered
                ],
            }
        )
    eligible_pairs.sort(key=lambda pair: pair["pair_hash"])
    if not eligible_pairs:
        raise ValueError("no reportable multi-finding pair")

    qualitative_candidates: list[dict[str, Any]] = []
    for pair in eligible_pairs:
        correct_rows = []
        for row in pair["rows"]:
            sample_id = row["sample_id"]
            values = [predictions[seed][sample_id] for seed in EXPECTED_SEEDS]
            target = row["reference_progression"]
            if all(str(value["prediction"]) == target for value in values):
                correct_rows.append(dict(row))
        if len(correct_rows) < 2:
            continue
        correct_rows.sort(
            key=lambda row: hashlib.sha256(
                f"{salt}|finding|{row['sample_id']}".encode()
            ).hexdigest()
        )
        selected_rows = correct_rows[:3]
        qualitative_candidates.append(
            {
                **{key: value for key, value in pair.items() if key != "rows"},
                "rows": selected_rows,
                "distinct_progression_states": len(
                    {row["reference_progression"] for row in selected_rows}
                ),
            }
        )
    if not qualitative_candidates:
        raise ValueError("no unanimously correct qualitative multi-finding pair")
    preferred = [
        pair
        for pair in qualitative_candidates
        if pair["distinct_progression_states"] >= 2
    ]
    qualitative = (preferred or qualitative_candidates)[0]

    return {
        "schema": "prta-cxr.s3-query-sensitivity-cohort.private.v1",
        "status": "PASS_S3_COHORT_AND_CASE_PRESELECTED",
        "selection_performed_before_image_or_attention_view": True,
        "images_opened": False,
        "attention_opened": False,
        "salt": salt,
        "minimum_cell_support": minimum_cell_support,
        "agreement_seeds_for_qualitative_case": list(EXPECTED_SEEDS),
        "summary_selection_uses_prediction_correctness": False,
        "qualitative_selection_requires_unanimous_correctness": True,
        "qualitative_selection_prioritizes_distinct_progression_states": True,
        "eligible_pair_count": len(eligible_pairs),
        "eligible_row_count": sum(len(pair["rows"]) for pair in eligible_pairs),
        "eligible_patient_count": len(
            {pair["patient_id_hash"] for pair in eligible_pairs}
        ),
        "eligible_pairs": eligible_pairs,
        "qualitative_selection": qualitative,
    }


def attention_flow_distribution(
    r_current: np.ndarray,
    r_prior: np.ndarray,
) -> np.ndarray:
    current = np.asarray(r_current, dtype=np.float64).reshape(-1)
    prior = np.asarray(r_prior, dtype=np.float64).reshape(-1)
    if current.shape != (196,) or prior.shape != (196,):
        raise ValueError("attention-flow maps must each contain 196 patches")
    if (
        not np.isfinite(current).all()
        or not np.isfinite(prior).all()
        or np.any(current < 0)
        or np.any(prior < 0)
        or current.sum() <= 0
        or prior.sum() <= 0
    ):
        raise ValueError("invalid attention-flow probability map")
    current = current / current.sum()
    prior = prior / prior.sum()
    return np.concatenate((0.5 * current, 0.5 * prior))


def jensen_shannon_divergence(p: np.ndarray, q: np.ndarray) -> float:
    first = np.asarray(p, dtype=np.float64).reshape(-1)
    second = np.asarray(q, dtype=np.float64).reshape(-1)
    if first.shape != second.shape or first.size == 0:
        raise ValueError("JSD distributions must have equal non-empty shapes")
    if (
        not np.isfinite(first).all()
        or not np.isfinite(second).all()
        or np.any(first < 0)
        or np.any(second < 0)
        or first.sum() <= 0
        or second.sum() <= 0
    ):
        raise ValueError("invalid JSD distribution")
    first = first / first.sum()
    second = second / second.sum()
    middle = 0.5 * (first + second)

    def kl_divergence(values: np.ndarray) -> float:
        mask = values > 0
        return float(np.sum(values[mask] * np.log2(values[mask] / middle[mask])))

    result = 0.5 * (kl_divergence(first) + kl_divergence(second))
    if result < -1e-12 or result > 1.0 + 1e-12:
        raise ValueError("base-2 JSD fell outside [0,1]")
    return float(np.clip(result, 0.0, 1.0))


def _record_distributions(record: Mapping[str, Any]) -> dict[str, np.ndarray]:
    current = np.asarray(record["r_current"], dtype=np.float64)
    prior = np.asarray(record["r_prior"], dtype=np.float64)
    return {
        "joint": attention_flow_distribution(current, prior),
        "current": current / current.sum(),
        "prior": prior / prior.sum(),
    }


def compute_jsd_units(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    pair_findings: dict[str, set[str]] = defaultdict(set)
    pair_patients: dict[str, str] = {}
    for record in records:
        key = (
            str(record["pair_hash"]),
            int(record["seed"]),
            str(record["finding"]),
        )
        if key in indexed:
            raise ValueError("duplicate attention-flow record")
        indexed[key] = record
        pair_findings[key[0]].add(key[2])
        patient = str(record["patient_id_hash"])
        if key[0] in pair_patients and pair_patients[key[0]] != patient:
            raise ValueError("pair hash maps to multiple patients")
        pair_patients[key[0]] = patient

    units: list[dict[str, Any]] = []

    def append_unit(
        kind: str,
        pair_hash: str,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
    ) -> None:
        left_maps = _record_distributions(left)
        right_maps = _record_distributions(right)
        units.append(
            {
                "kind": kind,
                "pair_hash": pair_hash,
                "patient_id_hash": pair_patients[pair_hash],
                "left_seed": int(left["seed"]),
                "right_seed": int(right["seed"]),
                "left_finding": str(left["finding"]),
                "right_finding": str(right["finding"]),
                "jsd_joint": jensen_shannon_divergence(
                    left_maps["joint"], right_maps["joint"]
                ),
                "jsd_current": jensen_shannon_divergence(
                    left_maps["current"], right_maps["current"]
                ),
                "jsd_prior": jensen_shannon_divergence(
                    left_maps["prior"], right_maps["prior"]
                ),
            }
        )

    for pair_hash in sorted(pair_findings):
        findings = sorted(pair_findings[pair_hash])
        for seed in EXPECTED_SEEDS:
            for left_finding, right_finding in itertools.combinations(findings, 2):
                append_unit(
                    "between_query",
                    pair_hash,
                    indexed[(pair_hash, seed, left_finding)],
                    indexed[(pair_hash, seed, right_finding)],
                )
        for finding in findings:
            for left_seed, right_seed in itertools.combinations(EXPECTED_SEEDS, 2):
                append_unit(
                    "between_seed",
                    pair_hash,
                    indexed[(pair_hash, left_seed, finding)],
                    indexed[(pair_hash, right_seed, finding)],
                )
    return units


def patient_clustered_median_ci(
    units: Sequence[Mapping[str, Any]],
    *,
    value_key: str,
    replicates: int = BOOTSTRAP_REPLICATES,
    rng_seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    if replicates < 1:
        raise ValueError("bootstrap replicates must be positive")
    clusters: dict[str, np.ndarray] = {}
    grouped: dict[str, list[float]] = defaultdict(list)
    for unit in units:
        value = float(unit[value_key])
        if not np.isfinite(value):
            raise ValueError("non-finite JSD unit")
        grouped[str(unit["patient_id_hash"])].append(value)
    if not grouped:
        raise ValueError("no JSD units for clustered bootstrap")
    clusters = {
        patient: np.asarray(values, dtype=np.float64)
        for patient, values in grouped.items()
    }
    patients = sorted(clusters)
    values = np.concatenate([clusters[patient] for patient in patients])
    rng = np.random.default_rng(rng_seed)
    bootstrap = np.empty(replicates, dtype=np.float64)
    for index in range(replicates):
        sampled = rng.integers(0, len(patients), size=len(patients))
        bootstrap[index] = np.median(
            np.concatenate([clusters[patients[value]] for value in sampled])
        )
    low, high = np.quantile(bootstrap, (0.025, 0.975))
    return {
        "median": float(np.median(values)),
        "ci95_low": float(low),
        "ci95_high": float(high),
        "unit_count": int(values.size),
        "patient_cluster_count": len(patients),
        "bootstrap_replicates": replicates,
        "bootstrap_rng_seed": rng_seed,
    }


def summarize_jsd_units(
    units: Sequence[Mapping[str, Any]],
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    rng_seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    by_kind = {
        kind: [unit for unit in units if unit["kind"] == kind]
        for kind in ("between_query", "between_seed")
    }
    if any(not values for values in by_kind.values()):
        raise ValueError("both JSD comparison groups are required")
    result = {
        kind: {
            metric: patient_clustered_median_ci(
                values,
                value_key=f"jsd_{metric}",
                replicates=replicates,
                rng_seed=rng_seed,
            )
            for metric in ("joint", "current", "prior")
        }
        for kind, values in by_kind.items()
    }
    query_interval = result["between_query"]["joint"]
    seed_interval = result["between_seed"]["joint"]
    result["query_sensitive_routing_supported"] = bool(
        query_interval["ci95_low"] > seed_interval["ci95_high"]
    )
    result["claim_gate"] = (
        "between_query.joint.ci95_low > between_seed.joint.ci95_high"
    )
    return result


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def query_sensitivity_preselection_main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the Figure S3 cohort before qualitative access."
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    for seed in EXPECTED_SEEDS:
        parser.add_argument(f"--s{seed}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--minimum-cell-support", type=int, default=MINIMUM_CELL_SUPPORT
    )
    args = parser.parse_args(argv)
    prediction_paths = {
        seed: getattr(args, f"s{seed}") for seed in EXPECTED_SEEDS
    }
    report = freeze_query_sensitivity_cohort(
        _load_jsonl(args.split_manifest),
        [(seed, _load_jsonl(path)) for seed, path in prediction_paths.items()],
        minimum_cell_support=args.minimum_cell_support,
    )
    report["input_sha256"] = {
        "split_manifest": sha256_file(args.split_manifest),
        **{
            f"S{seed}_predictions": sha256_file(path)
            for seed, path in prediction_paths.items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "eligible_pair_count",
                    "eligible_row_count",
                    "eligible_patient_count",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _batch_patch_attention_flow(
    w_align: torch.Tensor,
    w_trans: torch.Tensor,
) -> tuple[np.ndarray, np.ndarray]:
    if tuple(w_align.shape[1:]) != (12, 197, 197):
        raise ValueError("W_align must have shape [B,12,197,197]")
    if tuple(w_trans.shape[1:]) != (12, 20, 197):
        raise ValueError("W_trans must have shape [B,12,20,197]")
    align = w_align.float()[:, :, 1:, 1:]
    transition = w_trans.float()[:, :, :, 1:]
    align = align / align.sum(dim=-1, keepdim=True)
    transition = transition / transition.sum(dim=-1, keepdim=True)
    a_bar = align.mean(dim=1)
    current = transition.mean(dim=(1, 2))
    current = current / current.sum(dim=-1, keepdim=True)
    prior = torch.bmm(current.unsqueeze(1), a_bar).squeeze(1)
    prior = prior / prior.sum(dim=-1, keepdim=True)
    return (
        current.detach().cpu().numpy().astype(np.float32),
        prior.detach().cpu().numpy().astype(np.float32),
    )


def _flatten_cohort_rows(cohort: Mapping[str, Any]) -> list[dict[str, Any]]:
    if cohort.get("status") != "PASS_S3_COHORT_AND_CASE_PRESELECTED":
        raise ValueError("S3 cohort is not terminal PASS")
    if not cohort.get("selection_performed_before_image_or_attention_view"):
        raise ValueError("S3 cohort was not selected before viewing")
    if cohort.get("images_opened") or cohort.get("attention_opened"):
        raise ValueError("S3 cohort reports premature qualitative access")
    rows = []
    for pair in cohort["eligible_pairs"]:
        for row in pair["rows"]:
            rows.append(
                {
                    **dict(row),
                    "pair_hash": str(pair["pair_hash"]),
                    "patient_id_hash": str(pair["patient_id_hash"]),
                }
            )
    if len(rows) != int(cohort["eligible_row_count"]):
        raise ValueError("S3 cohort row count drift")
    return rows


def query_sensitivity_export_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export one frozen seed's S3 attention-flow maps."
    )
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=12)
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        raise ValueError("batch size must be positive")
    if args.output.exists():
        raise ValueError("refusing to overwrite an S3 seed export")

    from prta_cxr.data.token_cache import Block8CacheIndex
    from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
    from prta_cxr.training.engine import build_train_model
    from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported S3 checkpoint schema")
    seed = int(checkpoint["config"].get("seed", -1))
    if seed not in EXPECTED_SEEDS:
        raise ValueError("S3 checkpoint seed is not frozen")
    expected = checkpoint["input_hashes"]
    actual = {
        "split_manifest": sha256_file(args.split_manifest),
        "cache_manifest": sha256_file(args.cache_root / "cache_manifest.json"),
        "text_cache": sha256_file(args.text_cache),
        "weights": sha256_file(args.weights),
    }
    if {key: expected.get(key) for key in actual} != actual:
        raise ValueError("S3 replay inputs do not match checkpoint hashes")

    cohort = json.loads(args.cohort.read_text(encoding="utf-8"))
    cohort_rows = _flatten_cohort_rows(cohort)
    cohort_ids = [row["sample_id"] for row in cohort_rows]
    prediction_rows = _load_jsonl(args.predictions)
    predictions = {str(row["observation_id"]): row for row in prediction_rows}
    if len(predictions) != len(prediction_rows):
        raise ValueError("duplicate S3 prediction observation_id")
    if any(sample_id not in predictions for sample_id in cohort_ids):
        raise ValueError("S3 prediction block does not cover the cohort")
    if any(
        int(predictions[sample_id]["training_seed"]) != seed
        for sample_id in cohort_ids
    ):
        raise ValueError("S3 prediction seed drift")

    manifest_index = {
        str(row["sample_id"]): row for row in read_jsonl(args.split_manifest)
    }
    selected_rows = [manifest_index[sample_id] for sample_id in cohort_ids]
    cache = Block8CacheIndex(args.cache_root)
    dataset = PRTAFeatureDataset(
        selected_rows,
        cache=cache,
        text_cache_path=args.text_cache,
        split="dev",
    )
    visual, _ = load_biomedclip_visual(args.weights)
    config = checkpoint["config"]
    start_block = int(config.get("cache_entry_block", 8))
    frozen_tail, final_norm = tail_modules(visual, start_block=start_block)
    model = build_train_model(frozen_tail, final_norm, config)
    model.load_state_dict(checkpoint["model_state"])
    device = torch.device(args.device)
    model.to(device).eval()

    current_maps = np.empty((len(cohort_rows), 196), dtype=np.float32)
    prior_maps = np.empty((len(cohort_rows), 196), dtype=np.float32)
    maximum_probability_drift = 0.0
    for start in range(0, len(cohort_rows), args.batch_size):
        stop = min(start + args.batch_size, len(cohort_rows))
        items = [
            dataset[dataset.sample_indices[value]]
            for value in cohort_ids[start:stop]
        ]
        logits, w_align, w_trans = capture_true_attention(
            model,
            prior=torch.stack([item["prior"] for item in items]).to(device),
            current=torch.stack([item["current"] for item in items]).to(device),
            finding_text=torch.stack(
                [item["finding_text"] for item in items]
            ).to(device),
        )
        probabilities = torch.softmax(logits.float(), dim=-1).cpu().numpy()
        expected_probabilities = np.asarray(
            [predictions[value]["probabilities"] for value in cohort_ids[start:stop]],
            dtype=np.float64,
        )
        drift = float(np.max(np.abs(probabilities - expected_probabilities)))
        maximum_probability_drift = max(maximum_probability_drift, drift)
        if drift > 2e-5:
            raise ValueError(f"S{seed} probability replay drift; maximum_abs={drift}")
        current, prior = _batch_patch_attention_flow(w_align, w_trans)
        current_maps[start:stop] = current
        prior_maps[start:stop] = prior
        print(f"S{seed} {stop}/{len(cohort_rows)}", flush=True)

    if not np.allclose(current_maps.sum(axis=1), 1.0, atol=2e-6):
        raise ValueError("S3 current maps are not normalized")
    if not np.allclose(prior_maps.sum(axis=1), 1.0, atol=2e-6):
        raise ValueError("S3 prior maps are not normalized")
    args.output.mkdir(parents=True, exist_ok=False)
    maps_path = args.output / f"S{seed}_flow_maps.private.npz"
    np.savez_compressed(
        maps_path, r_current=current_maps, r_prior=prior_maps
    )
    index_path = args.output / f"S{seed}_flow_index.private.jsonl"
    with index_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in cohort_rows:
            handle.write(
                json.dumps(
                    {
                        "sample_id": row["sample_id"],
                        "pair_hash": row["pair_hash"],
                        "patient_id_hash": row["patient_id_hash"],
                        "finding": row["finding"],
                        "reference_progression": row["reference_progression"],
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    receipt = {
        "schema": "prta-cxr.s3-seed-flow-export.private.v1",
        "status": "PASS_S3_SEED_TRUE_ATTENTION_FLOW_EXPORTED",
        "source_commit": args.source_commit,
        "seed": seed,
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "prediction_sha256": sha256_file(args.predictions),
        "cohort_sha256": sha256_file(args.cohort),
        "input_sha256": actual,
        "row_count": len(cohort_rows),
        "patient_cluster_count": int(cohort["eligible_patient_count"]),
        "maps_sha256": sha256_file(maps_path),
        "index_sha256": sha256_file(index_path),
        "tensor_shapes": {
            "W_align_batch_item": [12, 197, 197],
            "W_trans_batch_item": [12, 20, 197],
            "r_current": list(current_maps.shape),
            "r_prior": list(prior_maps.shape),
        },
        "maximum_probability_replay_drift": maximum_probability_drift,
        "native_post_softmax_attention": True,
        "need_weights": True,
        "average_attn_weights": False,
        "cls_removed_and_patch_renormalized": True,
        "images_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    receipt_path = args.output / f"S{seed}_flow_export_receipt.private.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def _load_seed_export(
    directory: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, np.ndarray]]:
    receipts = list(directory.glob("S*_flow_export_receipt.private.json"))
    if len(receipts) != 1:
        raise ValueError("S3 seed directory must contain one receipt")
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    seed = int(receipt["seed"])
    if receipt.get("status") != "PASS_S3_SEED_TRUE_ATTENTION_FLOW_EXPORTED":
        raise ValueError("S3 seed export is not terminal PASS")
    index_path = directory / f"S{seed}_flow_index.private.jsonl"
    maps_path = directory / f"S{seed}_flow_maps.private.npz"
    if sha256_file(index_path) != receipt["index_sha256"]:
        raise ValueError("S3 seed index hash mismatch")
    if sha256_file(maps_path) != receipt["maps_sha256"]:
        raise ValueError("S3 seed maps hash mismatch")
    index = _load_jsonl(index_path)
    with np.load(maps_path, allow_pickle=False) as bundle:
        maps = {name: bundle[name].copy() for name in ("r_current", "r_prior")}
    if any(value.shape != (len(index), 196) for value in maps.values()):
        raise ValueError("S3 seed map/index shape mismatch")
    return receipt, index, maps


def query_sensitivity_analysis_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute private S3 JSD units and Git-safe aggregate statistics."
    )
    parser.add_argument("--cohort", type=Path, required=True)
    for seed in EXPECTED_SEEDS:
        parser.add_argument(f"--s{seed}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("refusing to overwrite an S3 analysis")
    cohort = json.loads(args.cohort.read_text(encoding="utf-8"))
    cohort_rows = _flatten_cohort_rows(cohort)
    records = []
    receipts = {}
    for seed in EXPECTED_SEEDS:
        receipt, index, maps = _load_seed_export(getattr(args, f"s{seed}"))
        if int(receipt["seed"]) != seed:
            raise ValueError("S3 seed directory mismatch")
        if receipt["cohort_sha256"] != sha256_file(args.cohort):
            raise ValueError("S3 seed cohort hash drift")
        expected_ids = [row["sample_id"] for row in cohort_rows]
        if [row["sample_id"] for row in index] != expected_ids:
            raise ValueError("S3 seed index order drift")
        receipts[f"S{seed}"] = receipt
        for position, row in enumerate(index):
            records.append(
                {
                    **row,
                    "seed": seed,
                    "r_current": maps["r_current"][position],
                    "r_prior": maps["r_prior"][position],
                }
            )
    units = compute_jsd_units(records)
    statistics = summarize_jsd_units(units)
    args.output.mkdir(parents=True, exist_ok=False)
    units_path = args.output / "s3_jsd_units.private.jsonl"
    with units_path.open("w", encoding="utf-8", newline="\n") as handle:
        for unit in units:
            handle.write(json.dumps(unit, sort_keys=True) + "\n")
    private_manifest = {
        "schema": "prta-cxr.s3-query-sensitivity-analysis.private.v1",
        "status": "PASS_S3_JSD_AND_CLUSTERED_BOOTSTRAP",
        "source_commit": args.source_commit,
        "cohort_sha256": sha256_file(args.cohort),
        "checkpoint_sha256": {
            seed: receipts[seed]["checkpoint_sha256"] for seed in receipts
        },
        "seed_export_receipts": {
            seed: {
                "maps_sha256": receipt["maps_sha256"],
                "index_sha256": receipt["index_sha256"],
                "prediction_sha256": receipt["prediction_sha256"],
            }
            for seed, receipt in receipts.items()
        },
        "cohort": {
            "pair_count": int(cohort["eligible_pair_count"]),
            "row_count": int(cohort["eligible_row_count"]),
            "patient_cluster_count": int(cohort["eligible_patient_count"]),
        },
        "jsd": {
            "logarithm_base": 2,
            "range": [0.0, 1.0],
            "primary_distribution": (
                "equal-mass concatenation [0.5*r_current, 0.5*r_prior]"
            ),
            "sensitivity_distributions": ["r_current", "r_prior"],
        },
        "bootstrap": {
            "cluster": "patient",
            "replicates": BOOTSTRAP_REPLICATES,
            "rng_seed": BOOTSTRAP_SEED,
            "interval": "percentile 95%",
        },
        "statistics": statistics,
        "private_units_sha256": sha256_file(units_path),
        "qualitative_selection": cohort["qualitative_selection"],
        "selection_performed_before_image_or_attention_view": True,
        "attention_opened_only_after_selection_lock": True,
        "source_images_opened": False,
    }
    private_path = args.output / "s3_analysis_manifest.private.json"
    private_path.write_text(
        json.dumps(private_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    public = {
        "schema": "prta-cxr.s3-query-sensitivity-aggregate.v1",
        "status": "PASS_S3_AGGREGATE_GIT_SAFE",
        "source_commit": args.source_commit,
        "cohort_receipt_sha256": sha256_file(args.cohort),
        "cohort": private_manifest["cohort"],
        "checkpoint_sha256": private_manifest["checkpoint_sha256"],
        "jsd": private_manifest["jsd"],
        "bootstrap": private_manifest["bootstrap"],
        "statistics": statistics,
        "qualitative_queries": [
            {
                "finding": row["finding"],
                "reference_progression": row["reference_progression"],
            }
            for row in cohort["qualitative_selection"]["rows"]
        ],
        "qualitative_selection_rule": (
            "salted pre-view pair order; unanimous-correct S17/S28/S43; "
            "distinct progression states prioritized"
        ),
        "contains_source_pixels": False,
        "contains_patient_level_rows": False,
        "contains_sample_identifiers": False,
    }
    public_path = args.output / "s3_query_sensitivity_aggregate.json"
    public_path.write_text(
        json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(public, indent=2, sort_keys=True))
    return 0
