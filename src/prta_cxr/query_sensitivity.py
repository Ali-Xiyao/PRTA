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

from prta_cxr.attention_flow import EXPECTED_SEEDS, SELECTION_SALT
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
