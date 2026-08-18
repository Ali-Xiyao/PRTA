from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.evaluation.progression import metrics_from_confusion

SEEDS = (17, 28, 43)
COMPARATOR_SYSTEMS = (
    "V2",
    "S0",
    "B401",
    "B402",
    "TILA8",
    "BioViLT",
    "CheXRelNet",
    "TILAPaper",
    "F02-DMW0",
)
SYSTEMS = ("Slim-S1", *COMPARATOR_SYSTEMS)
PRIMARY_COMPARATORS = ("S0", "V2", "F02-DMW0", "TILA8")
STRONGEST_COMPATIBLE_CANDIDATES = (
    "B401",
    "B402",
    "BioViLT",
    "CheXRelNet",
    "TILAPaper",
)
METRICS = (
    "macro_f1",
    "balanced_accuracy",
    "opposite_direction_error_rate",
)
INTERVENTIONS = ("true", "matched_hard", "null", "reversed")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"empty or invalid prediction block: {path}")
    return rows


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _closed(receipt: Mapping[str, Any], *, label: str) -> None:
    if receipt.get("internal_test_opened") is not False:
        raise ValueError(f"{label} reports Internal-test access")
    if receipt.get("gold_opened") is not False:
        raise ValueError(f"{label} reports Gold access")
    if int(receipt.get("protected_outcome_read_count", -1)) != 0:
        raise ValueError(f"{label} reports protected reads")
    if receipt.get("selection_performed") is not False:
        raise ValueError(f"{label} reports model selection")


def _load_receipt(
    path: Path, *, expected_system: str
) -> tuple[int, dict[str, list[dict[str, Any]]], dict[str, Any]]:
    receipt = _read_json(path)
    expected_status = (
        "PASS_PHASE20_S1_DEV_PROBABILITY_EXPORT"
        if expected_system == "Slim-S1"
        else "PASS_PHASE20_B2_COMPARATOR_DEV_PROBABILITY_EXPORT"
    )
    if (
        receipt.get("status") != expected_status
        or receipt.get("variant") != expected_system
        or int(receipt.get("seed", -1)) not in SEEDS
        or receipt.get("probability_export") is not True
    ):
        raise ValueError(f"Phase20-B2 probability receipt identity drift: {path}")
    _closed(receipt, label=f"probability receipt {expected_system}")
    required = INTERVENTIONS if expected_system == "Slim-S1" else ("true",)
    inventory = receipt.get("prediction_blocks")
    if not isinstance(inventory, dict) or not set(required) <= set(inventory):
        raise ValueError(f"Phase20-B2 prediction block roster drift: {path}")
    blocks = {}
    parent = path.parent.resolve()
    for intervention in required:
        block = dict(inventory[intervention])
        block_path = (path.parent / str(block["path"])).resolve()
        if block_path.parent != parent:
            raise ValueError("Phase20-B2 prediction block escapes receipt root")
        if sha256_file(block_path) != block.get("sha256"):
            raise ValueError(f"Phase20-B2 prediction hash drift: {block_path}")
        rows = _read_jsonl(block_path)
        if len(rows) != int(block["rows"]):
            raise ValueError(f"Phase20-B2 prediction row-count drift: {block_path}")
        for row in rows:
            if (
                row.get("system") != expected_system
                or int(row.get("training_seed", -1)) != int(receipt["seed"])
                or row.get("cohort") != "dev"
                or row.get("prior_intervention") != intervention
            ):
                raise ValueError("Phase20-B2 prediction row identity drift")
        blocks[intervention] = rows
    return int(receipt["seed"]), blocks, receipt


def load_phase20_b2_matrix(
    s1_receipts: Sequence[Path], comparator_receipts: Mapping[str, Sequence[Path]]
) -> tuple[dict[str, dict[int, dict[str, list[dict[str, Any]]]]], dict[str, str]]:
    if set(comparator_receipts) != set(COMPARATOR_SYSTEMS):
        raise ValueError("Phase20-B2 comparator system roster drift")
    loaded: dict[str, dict[int, dict[str, list[dict[str, Any]]]]] = defaultdict(dict)
    receipt_hashes = {}
    for system, paths in (("Slim-S1", s1_receipts), *comparator_receipts.items()):
        for path in paths:
            seed, blocks, _ = _load_receipt(path, expected_system=system)
            if seed in loaded[system]:
                raise ValueError(f"duplicate Phase20-B2 receipt: {system}/S{seed}")
            loaded[system][seed] = blocks
            receipt_hashes[f"{system}/S{seed}"] = sha256_file(path)
        if set(loaded[system]) != set(SEEDS):
            raise ValueError(f"incomplete Phase20-B2 Seed roster: {system}")
    return dict(loaded), receipt_hashes


def _index(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {str(row["observation_id"]): dict(row) for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate Phase20-B2 observation ID")
    return result


def _validate_layout(
    loaded: Mapping[str, Mapping[int, Mapping[str, Sequence[Mapping[str, Any]]]]],
) -> list[tuple[str, str, str]]:
    reference = sorted(
        (
            str(row["patient_id"]),
            str(row["observation_id"]),
            str(row["target"]),
        )
        for row in loaded["Slim-S1"][SEEDS[0]]["true"]
    )
    for system in SYSTEMS:
        for seed in SEEDS:
            layout = sorted(
                (
                    str(row["patient_id"]),
                    str(row["observation_id"]),
                    str(row["target"]),
                )
                for row in loaded[system][seed]["true"]
            )
            if layout != reference:
                raise ValueError(f"Phase20-B2 layout drift: {system}/S{seed}")
    return reference


def _metric_vector(matrix: np.ndarray) -> np.ndarray:
    result = metrics_from_confusion(
        matrix, labels=PROGRESSION_LABELS, require_all_labels=False
    )
    return np.asarray([float(result[name]) for name in METRICS])


def _holm(p_values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    adjusted = {}
    running = 0.0
    count = len(ordered)
    for rank, (name, value) in enumerate(ordered):
        running = max(running, min(1.0, (count - rank) * float(value)))
        adjusted[name] = running
    return dict(sorted(adjusted.items()))


def _risk_coverage(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        rows,
        key=lambda row: (-float(row["confidence"]), str(row["observation_id"])),
    )
    label_index = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
    result = {}
    for coverage in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
        retained = ordered[: max(1, int(round(len(ordered) * coverage)))]
        matrix = np.zeros((len(PROGRESSION_LABELS), len(PROGRESSION_LABELS)))
        for row in retained:
            target = label_index[str(row["target"])]
            prediction = label_index[str(row["prediction"])]
            matrix[target, prediction] += 1
        metrics = metrics_from_confusion(
            matrix, labels=PROGRESSION_LABELS, require_all_labels=False
        )
        result[f"{coverage:.1f}"] = {
            "retained": len(retained),
            "selective_risk": 1.0 - float(np.trace(matrix) / matrix.sum()),
            "macro_f1": float(metrics["macro_f1"]),
            "opposite_direction_error_rate": float(
                metrics["opposite_direction_error_rate"]
            ),
        }
    return result


def _disagreement(blocks: Mapping[int, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    indexed = {seed: _index(blocks[seed]) for seed in SEEDS}
    observations = sorted(indexed[SEEDS[0]])
    distribution = Counter()
    correct_votes = Counter()
    pairwise = {}
    for left, right in ((17, 28), (17, 43), (28, 43)):
        pairwise[f"S{left}_S{right}"] = sum(
            indexed[left][observation]["prediction"]
            == indexed[right][observation]["prediction"]
            for observation in observations
        ) / len(observations)
    for observation in observations:
        predictions = [indexed[seed][observation]["prediction"] for seed in SEEDS]
        target = indexed[SEEDS[0]][observation]["target"]
        distribution[str(len(set(predictions)))] += 1
        correct_votes[str(sum(prediction == target for prediction in predictions))] += 1
    return {
        "rows": len(observations),
        "unique_prediction_count_distribution": dict(sorted(distribution.items())),
        "correct_seed_vote_distribution": dict(sorted(correct_votes.items())),
        "pairwise_prediction_agreement": pairwise,
        "unanimous_prediction_rate": distribution["1"] / len(observations),
    }


def phase20_b2_statistics(
    loaded: Mapping[str, Mapping[int, Mapping[str, Sequence[Mapping[str, Any]]]]],
    *,
    replicates: int = 10_000,
    rng_seed: int = 20260818,
) -> dict[str, Any]:
    if replicates < 2:
        raise ValueError("Phase20-B2 requires at least two bootstrap replicates")
    layout = _validate_layout(loaded)
    labels = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
    patients = sorted({patient for patient, _, _ in layout})
    patient_index = {patient: index for index, patient in enumerate(patients)}
    systems = {system: index for index, system in enumerate(SYSTEMS)}
    seeds = {seed: index for index, seed in enumerate(SEEDS)}
    confusion = np.zeros(
        (
            len(SYSTEMS),
            len(SEEDS),
            len(patients),
            len(PROGRESSION_LABELS),
            len(PROGRESSION_LABELS),
        ),
        dtype=np.float64,
    )
    indexed = {}
    for system in SYSTEMS:
        for seed in SEEDS:
            block = _index(loaded[system][seed]["true"])
            indexed[(system, seed)] = block
            for patient, observation, target in layout:
                prediction = str(block[observation]["prediction"])
                confusion[
                    systems[system],
                    seeds[seed],
                    patient_index[patient],
                    labels[target],
                    labels[prediction],
                ] += 1

    def evaluate(draw: np.ndarray) -> np.ndarray:
        counts = np.bincount(draw, minlength=len(patients))
        output = np.empty((len(SYSTEMS), len(SEEDS), len(METRICS)))
        for system_position in range(len(SYSTEMS)):
            for seed_position in range(len(SEEDS)):
                matrix = np.tensordot(
                    counts,
                    confusion[system_position, seed_position],
                    axes=(0, 0),
                )
                output[system_position, seed_position] = _metric_vector(matrix)
        return output

    point = evaluate(np.arange(len(patients)))
    mean_macro_f1 = {
        system: float(point[position, :, 0].mean())
        for system, position in systems.items()
    }
    strongest = max(
        STRONGEST_COMPATIBLE_CANDIDATES,
        key=lambda system: (mean_macro_f1[system], system),
    )
    contrasts = (*PRIMARY_COMPARATORS, strongest)
    rng = np.random.default_rng(rng_seed)
    samples = {
        comparator: np.empty((replicates, len(SEEDS) + 1, len(METRICS)))
        for comparator in contrasts
    }
    for replicate in range(replicates):
        result = evaluate(
            rng.integers(0, len(patients), size=len(patients), endpoint=False)
        )
        for comparator in contrasts:
            delta = result[systems["Slim-S1"]] - result[systems[comparator]]
            samples[comparator][replicate, : len(SEEDS)] = delta
            samples[comparator][replicate, len(SEEDS)] = delta.mean(axis=0)
    scopes = (*[f"seed{seed}" for seed in SEEDS], "mean_across_seeds")
    contrast_results = {}
    primary_p = {}
    for comparator in contrasts:
        scope_results = {}
        for scope_index, scope in enumerate(scopes):
            metric_results = {}
            for metric_index, metric in enumerate(METRICS):
                values = samples[comparator][:, scope_index, metric_index]
                point_delta = (
                    point[systems["Slim-S1"], :, metric_index]
                    - point[systems[comparator], :, metric_index]
                )
                point_value = float(
                    point_delta.mean()
                    if scope == "mean_across_seeds"
                    else point_delta[scope_index]
                )
                p_value = min(
                    1.0,
                    2
                    * min(
                        (int(np.count_nonzero(values <= 0)) + 1) / (replicates + 1),
                        (int(np.count_nonzero(values >= 0)) + 1) / (replicates + 1),
                    ),
                )
                metric_results[metric] = {
                    "point_s1_minus_comparator": point_value,
                    "interval_95": {
                        "lower": float(np.quantile(values, 0.025)),
                        "upper": float(np.quantile(values, 0.975)),
                    },
                    "empirical_two_sided_p": p_value,
                }
                if comparator in PRIMARY_COMPARATORS and scope == "mean_across_seeds":
                    primary_p[f"S1_vs_{comparator}/{metric}"] = p_value
            scope_results[scope] = metric_results
        exclusive = {}
        for seed in SEEDS:
            counts = Counter()
            for _, observation, target in layout:
                left = indexed[("Slim-S1", seed)][observation]["prediction"] == target
                right = indexed[(comparator, seed)][observation]["prediction"] == target
                counts[
                    "s1_only_correct"
                    if left and not right
                    else "comparator_only_correct"
                    if right and not left
                    else "both_correct"
                    if left
                    else "both_wrong"
                ] += 1
            exclusive[str(seed)] = dict(sorted(counts.items()))
        contrast_results[f"S1_vs_{comparator}"] = {
            "comparator": comparator,
            "inference_role": (
                "predeclared_primary"
                if comparator in PRIMARY_COMPARATORS
                else "outcome_ranked_exploratory"
            ),
            "scopes": scope_results,
            "exclusive_correct_wrong": exclusive,
        }
    holm = _holm(primary_p)
    for name, adjusted in holm.items():
        contrast, metric = name.split("/", 1)
        contrast_results[contrast]["scopes"]["mean_across_seeds"][metric][
            "holm_adjusted_p"
        ] = adjusted
    risk_coverage = {
        system: {
            str(seed): _risk_coverage(loaded[system][seed]["true"]) for seed in SEEDS
        }
        for system in SYSTEMS
    }
    disagreement = {
        system: _disagreement({seed: loaded[system][seed]["true"] for seed in SEEDS})
        for system in SYSTEMS
    }
    safety_routing = {}
    for intervention in INTERVENTIONS:
        by_seed = {}
        for seed in SEEDS:
            s1 = loaded["Slim-S1"][seed][intervention]
            b401 = loaded["B401"][seed]["true"]
            by_seed[str(seed)] = {
                "always_s1": _risk_coverage(s1)["1.0"],
                "invalid_to_current_only": _risk_coverage(
                    b401 if intervention != "true" else s1
                )["1.0"],
                "invalid_to_abstain": {
                    "coverage": 0.0 if intervention != "true" else 1.0,
                    "status": "ABSTAIN_ALL"
                    if intervention != "true"
                    else "ROUTE_NOT_TRIGGERED",
                },
            }
        safety_routing[intervention] = by_seed
    return {
        "schema": "prta-cxr.phase20-b2-post-comparator-statistics.v1",
        "status": "PASS_PHASE20_B2_POST_COMPARATOR_STATISTICS",
        "created_at": datetime.now(UTC).isoformat(),
        "systems": list(SYSTEMS),
        "seeds": list(SEEDS),
        "patients": len(patients),
        "observations": len(layout),
        "bootstrap": {
            "replicates": replicates,
            "rng_seed": rng_seed,
            "sampling_unit": "patient_cluster",
            "contrasts": contrast_results,
            "primary_holm_family": sorted(primary_p),
        },
        "strongest_compatible_comparator": {
            "system": strongest,
            "criterion": "highest three-seed mean Dev Macro-F1",
            "inference_role": "outcome-ranked exploratory; excluded from Holm family",
            "mean_macro_f1_by_candidate": {
                system: mean_macro_f1[system]
                for system in STRONGEST_COMPATIBLE_CANDIDATES
            },
        },
        "three_seed_disagreement": disagreement,
        "risk_coverage": risk_coverage,
        "safety_routing": {
            "routing_detector": "known synthetic intervention identity",
            "interpretation": "oracle-detectable invalid-history routing simulation",
            "threshold_tuning_performed": False,
            "by_intervention": safety_routing,
        },
        "selection_performed": False,
        "winner_selected": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def phase20_b2_statistics_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase20-B2 paired statistics")
    parser.add_argument("--s1-receipt", type=Path, action="append", required=True)
    parser.add_argument("--comparator-receipt", action="append", required=True)
    parser.add_argument("--replicates", type=int, default=10_000)
    parser.add_argument("--rng-seed", type=int, default=20260818)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    comparator_paths: dict[str, list[Path]] = defaultdict(list)
    for raw in args.comparator_receipt:
        if "=" not in raw:
            parser.error("--comparator-receipt must use SYSTEM=PATH")
        system, path = raw.split("=", 1)
        if system not in COMPARATOR_SYSTEMS:
            parser.error(f"unknown comparator system: {system}")
        comparator_paths[system].append(Path(path))
    loaded, receipt_hashes = load_phase20_b2_matrix(args.s1_receipt, comparator_paths)
    result = phase20_b2_statistics(
        loaded, replicates=args.replicates, rng_seed=args.rng_seed
    )
    result["probability_receipt_sha256"] = receipt_hashes
    _write_new_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
