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

SYSTEMS = ("V0", "V1", "V2")
SEEDS = (17, 28, 43)
INTERVENTIONS = ("true", "matched_hard", "null", "reversed")
CONTRASTS = {
    "V2_minus_V0": ("V2", "V0"),
    "V2_minus_V1": ("V2", "V1"),
    "V1_minus_V0": ("V1", "V0"),
}
SCALAR_METRICS = (
    "macro_f1",
    "balanced_accuracy",
    "opposite_direction_error_rate",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            rows.append(value)
    if not rows:
        raise ValueError(f"empty prediction block: {path}")
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


def _metric_vector(matrix: np.ndarray) -> dict[str, float]:
    metrics = metrics_from_confusion(
        matrix,
        labels=PROGRESSION_LABELS,
        require_all_labels=False,
    )
    output = {name: float(metrics[name]) for name in SCALAR_METRICS}
    for label in PROGRESSION_LABELS:
        output[f"recall:{label}"] = float(metrics["per_class_recall"][label])
        output[f"f1:{label}"] = float(metrics["per_class_f1"][label])
    return output


def _interval(values: Sequence[float]) -> dict[str, float]:
    lower, upper = np.quantile(values, [0.025, 0.975], method="linear")
    return {"lower": float(lower), "upper": float(upper), "level": 0.95}


def paired_patient_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    *,
    replicates: int = 10_000,
    rng_seed: int = 20260814,
) -> dict[str, Any]:
    if replicates < 2:
        raise ValueError("at least two bootstrap replicates are required")
    materialized = [dict(row) for row in rows]
    systems = tuple(SYSTEMS)
    seeds = tuple(SEEDS)
    label_index = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
    blocks: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in materialized:
        system = str(row["system"])
        seed = int(row["training_seed"])
        if system not in systems or seed not in seeds:
            raise ValueError(f"unexpected prediction block: {system}/{seed}")
        if str(row.get("cohort")) != "dev":
            raise ValueError("candidate bootstrap accepts Dev predictions only")
        if str(row.get("prior_intervention")) != "true":
            raise ValueError("candidate bootstrap accepts true PRIOR blocks only")
        blocks[(system, seed)].append(row)
    expected_blocks = {(system, seed) for system in systems for seed in seeds}
    if set(blocks) != expected_blocks:
        raise ValueError("candidate bootstrap matrix is not fully crossed")

    reference_layout = sorted(
        (
            str(row["patient_id"]),
            str(row["observation_id"]),
            str(row["target"]),
        )
        for row in blocks[(systems[0], seeds[0])]
    )
    if any(target not in label_index for _, _, target in reference_layout):
        raise ValueError("reference block contains an unknown target")
    for key, block in blocks.items():
        layout = sorted(
            (
                str(row["patient_id"]),
                str(row["observation_id"]),
                str(row["target"]),
            )
            for row in block
        )
        if layout != reference_layout:
            raise ValueError(f"prediction layout mismatch in block {key!r}")
        if len({row[1] for row in layout}) != len(layout):
            raise ValueError(f"duplicate observation in block {key!r}")

    patients = sorted({patient for patient, _, _ in reference_layout})
    patient_index = {patient: index for index, patient in enumerate(patients)}
    system_index = {system: index for index, system in enumerate(systems)}
    seed_index = {seed: index for index, seed in enumerate(seeds)}
    confusion = np.zeros(
        (
            len(systems),
            len(seeds),
            len(patients),
            len(PROGRESSION_LABELS),
            len(PROGRESSION_LABELS),
        ),
        dtype=np.float64,
    )
    predictions: dict[tuple[str, int, str], str] = {}
    targets: dict[str, str] = {}
    for (system, seed), block in blocks.items():
        for row in block:
            patient = str(row["patient_id"])
            observation = str(row["observation_id"])
            target = str(row["target"])
            prediction = str(row["prediction"])
            if prediction not in label_index:
                raise ValueError("prediction block contains an unknown prediction")
            prior_target = targets.setdefault(observation, target)
            if prior_target != target:
                raise ValueError("target drift across prediction blocks")
            predictions[(system, seed, observation)] = prediction
            confusion[
                system_index[system],
                seed_index[seed],
                patient_index[patient],
                label_index[target],
                label_index[prediction],
            ] += 1.0

    def evaluate(patient_draw: np.ndarray) -> dict[tuple[str, int], dict[str, float]]:
        counts = np.bincount(patient_draw, minlength=len(patients))
        return {
            (system, seed): _metric_vector(
                np.tensordot(
                    counts,
                    confusion[system_index[system], seed_index[seed]],
                    axes=(0, 0),
                )
            )
            for system in systems
            for seed in seeds
        }

    point = evaluate(np.arange(len(patients)))
    metric_names = tuple(next(iter(point.values())))
    samples: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    rng = np.random.default_rng(rng_seed)
    for _ in range(replicates):
        evaluated = evaluate(
            rng.integers(0, len(patients), size=len(patients), endpoint=False)
        )
        for contrast, (left, right) in CONTRASTS.items():
            for metric in metric_names:
                seed_values = []
                for seed in seeds:
                    delta = (
                        evaluated[(left, seed)][metric]
                        - evaluated[(right, seed)][metric]
                    )
                    samples[(contrast, f"seed{seed}", metric)].append(delta)
                    seed_values.append(delta)
                samples[(contrast, "mean_across_seeds", metric)].append(
                    float(np.mean(seed_values))
                )

    contrast_results: dict[str, Any] = {}
    for contrast, (left, right) in CONTRASTS.items():
        scopes = {}
        for scope in (*[f"seed{seed}" for seed in seeds], "mean_across_seeds"):
            metrics = {}
            for metric in metric_names:
                if scope == "mean_across_seeds":
                    point_delta = float(
                        np.mean(
                            [
                                point[(left, seed)][metric]
                                - point[(right, seed)][metric]
                                for seed in seeds
                            ]
                        )
                    )
                else:
                    seed = int(scope.removeprefix("seed"))
                    point_delta = (
                        point[(left, seed)][metric] - point[(right, seed)][metric]
                    )
                values = samples[(contrast, scope, metric)]
                metrics[metric] = {
                    "point": float(point_delta),
                    "interval": _interval(values),
                    "empirical_two_sided_p": min(
                        1.0,
                        2.0
                        * min(
                            (sum(value <= 0 for value in values) + 1)
                            / (len(values) + 1),
                            (sum(value >= 0 for value in values) + 1)
                            / (len(values) + 1),
                        ),
                    ),
                }
            scopes[scope] = metrics

        exclusive = {}
        for seed in seeds:
            counts = Counter()
            for _, observation, target in reference_layout:
                left_correct = predictions[(left, seed, observation)] == target
                right_correct = predictions[(right, seed, observation)] == target
                if left_correct and not right_correct:
                    counts["left_only_correct"] += 1
                elif right_correct and not left_correct:
                    counts["right_only_correct"] += 1
                elif left_correct and right_correct:
                    counts["both_correct"] += 1
                else:
                    counts["both_wrong"] += 1
            exclusive[f"seed{seed}"] = dict(sorted(counts.items()))
        contrast_results[contrast] = {
            "left": left,
            "right": right,
            "scopes": scopes,
            "exclusive_counts": exclusive,
        }

    point_metrics = {
        system: {f"seed{seed}": point[(system, seed)] for seed in seeds}
        for system in systems
    }
    return {
        "systems": list(systems),
        "seeds": list(seeds),
        "patients": len(patients),
        "observations": len(reference_layout),
        "point_metrics": point_metrics,
        "contrasts": contrast_results,
        "bootstrap": {
            "requested_replicates": replicates,
            "valid_replicates": replicates,
            "rng_seed": rng_seed,
            "resampled_level": "patient",
            "paired_systems": True,
            "training_seeds_treated_as_fixed_confirmatory_blocks": True,
        },
    }


def candidate_bootstrap_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run V0/V1/V2 cleaned-Dev paired patient bootstrap"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=10_000)
    parser.add_argument("--rng-seed", type=int, default=20260814)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    manifest = _read_json(args.manifest)
    if manifest.get("status") != "PASS_WAVE047_CANDIDATE_DIAGNOSTICS_FROZEN":
        raise ValueError("candidate diagnostic manifest is not frozen PASS")
    if manifest.get("protected_outcome_read_count") != 0:
        raise ValueError("candidate diagnostic manifest reports protected reads")
    if manifest.get("internal_test_opened") is not False:
        raise ValueError("candidate diagnostic manifest reports Internal-test access")
    if manifest.get("gold_opened") is not False:
        raise ValueError("candidate diagnostic manifest reports Gold access")

    rows = []
    input_hashes = {}
    seen = set()
    for item in manifest.get("diagnostic_receipts", []):
        variant = str(item["variant"])
        seed = int(item["seed"])
        key = (variant, seed)
        if key in seen:
            raise ValueError(f"duplicate candidate diagnostic receipt: {key}")
        seen.add(key)
        receipt_path = Path(item["receipt_path"])
        if sha256_file(receipt_path) != str(item["receipt_sha256"]):
            raise ValueError(f"candidate diagnostic receipt hash drift: {key}")
        receipt = _read_json(receipt_path)
        if receipt.get("status") != (
            "PASS_WAVE047_CANDIDATE_TRAIN_DEV_PRIOR_DIAGNOSTIC"
        ):
            raise ValueError(f"candidate diagnostic is not PASS: {key}")
        if receipt.get("protected_outcome_read_count") != 0:
            raise ValueError(f"candidate diagnostic reports protected reads: {key}")
        if (str(receipt.get("variant")), int(receipt.get("seed"))) != key:
            raise ValueError(f"candidate diagnostic identity drift: {key}")
        for intervention in INTERVENTIONS:
            block = receipt["prediction_blocks"][intervention]
            path = receipt_path.parent / str(block["path"])
            if sha256_file(path) != str(block["sha256"]):
                raise ValueError(
                    f"candidate prediction hash drift: {key}/{intervention}"
                )
            block_rows = _read_jsonl(path)
            if len(block_rows) != int(block["rows"]):
                raise ValueError(
                    f"candidate prediction row drift: {key}/{intervention}"
                )
            input_hashes[f"{variant}-S{seed}-{intervention}"] = str(block["sha256"])
            if intervention == "true":
                rows.extend(block_rows)
    if seen != {(variant, seed) for variant in SYSTEMS for seed in SEEDS}:
        raise ValueError("candidate diagnostic receipt matrix is incomplete")

    result = paired_patient_bootstrap(
        rows,
        replicates=args.replicates,
        rng_seed=args.rng_seed,
    )
    result.update(
        {
            "schema": "prta-cxr.wave047-candidate-paired-bootstrap.v1",
            "status": "PASS_WAVE047_CANDIDATE_PAIRED_BOOTSTRAP",
            "created_at": datetime.now(UTC).isoformat(),
            "manifest_sha256": sha256_file(args.manifest),
            "input_prediction_sha256": dict(sorted(input_hashes.items())),
            "selection_performed": False,
            "winner_selected": False,
            "candidate_status": "PENDING_CONFIRMATION",
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        }
    )
    args.output.mkdir(parents=True, exist_ok=False)
    result_path = args.output / "paired_patient_bootstrap.json"
    _write_new_json(result_path, result)
    receipt = {
        "schema": "prta-cxr.wave047-candidate-bootstrap-receipt.v1",
        "status": "PASS_WAVE047_CANDIDATE_BOOTSTRAP_COMPLETE",
        "created_at": datetime.now(UTC).isoformat(),
        "result_sha256": sha256_file(result_path),
        "manifest_sha256": sha256_file(args.manifest),
        "replicates": args.replicates,
        "rng_seed": args.rng_seed,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(args.output / "completion_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
