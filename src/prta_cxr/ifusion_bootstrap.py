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
IF_VARIANTS = (
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
)
SYSTEMS = ("V2", *IF_VARIANTS)
INTERVENTIONS = ("true", "matched_hard", "null", "reversed")
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
    rows: list[dict[str, Any]] = []
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


def _validate_receipt(
    receipt_path: Path,
    *,
    system: str,
    seed: int,
    expected_status: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    receipt = _read_json(receipt_path)
    identity = (str(receipt.get("variant")), int(receipt.get("seed", -1)))
    if identity != (system, seed):
        raise ValueError(f"diagnostic identity drift: {receipt_path}")
    if receipt.get("status") != expected_status:
        raise ValueError(
            f"diagnostic is not the expected PASS status: {system}/S{seed}"
        )
    if receipt.get("protected_outcome_read_count") != 0:
        raise ValueError(f"diagnostic reports protected reads: {system}/S{seed}")
    if receipt.get("internal_test_opened") is not False:
        raise ValueError(f"diagnostic reports Internal-test access: {system}/S{seed}")
    if receipt.get("gold_opened") is not False:
        raise ValueError(f"diagnostic reports Gold access: {system}/S{seed}")
    if receipt.get("selection_performed") is not False:
        raise ValueError(f"diagnostic reports selection: {system}/S{seed}")

    blocks = receipt.get("prediction_blocks")
    if not isinstance(blocks, dict) or set(blocks) != set(INTERVENTIONS):
        raise ValueError(f"diagnostic intervention set drift: {system}/S{seed}")
    block_inventory: dict[str, dict[str, Any]] = {}
    true_rows: list[dict[str, Any]] | None = None
    receipt_parent = receipt_path.parent.resolve()
    for intervention in INTERVENTIONS:
        block = blocks[intervention]
        if not isinstance(block, dict):
            raise ValueError(
                f"invalid prediction block: {system}/S{seed}/{intervention}"
            )
        block_path = (receipt_path.parent / str(block["path"])).resolve()
        if block_path.parent != receipt_parent:
            raise ValueError(f"prediction path escapes receipt directory: {block_path}")
        block_sha256 = sha256_file(block_path)
        if block_sha256 != str(block["sha256"]):
            raise ValueError(f"prediction hash drift: {system}/S{seed}/{intervention}")
        rows = _read_jsonl(block_path)
        if len(rows) != int(block["rows"]):
            raise ValueError(f"prediction row drift: {system}/S{seed}/{intervention}")
        for row in rows:
            row_identity = (str(row.get("system")), int(row.get("training_seed", -1)))
            if row_identity != (system, seed):
                raise ValueError(
                    f"prediction identity drift: {system}/S{seed}/{intervention}"
                )
            if str(row.get("cohort")) != "dev":
                raise ValueError("IF bootstrap accepts Dev predictions only")
            if str(row.get("prior_intervention")) != intervention:
                raise ValueError("prediction intervention drift")
        block_inventory[intervention] = {
            "rows": len(rows),
            "sha256": block_sha256,
        }
        if intervention == "true":
            true_rows = rows
    if true_rows is None:
        raise ValueError(f"missing true prediction block: {system}/S{seed}")
    return (
        {
            "system": system,
            "seed": seed,
            "status": str(receipt["status"]),
            "receipt_sha256": sha256_file(receipt_path),
            "prediction_blocks": block_inventory,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
        true_rows,
    )


def collect_diagnostic_evidence(
    if_roots: Sequence[Path],
    v2_manifest_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not if_roots:
        raise ValueError("at least one IF diagnostic root is required")
    if_paths: dict[tuple[str, int], Path] = {}
    seen_paths: set[Path] = set()
    for root in if_roots:
        for receipt_path in sorted(root.rglob("ifusion_dev_diagnostic_receipt.json")):
            resolved = receipt_path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            receipt = _read_json(receipt_path)
            key = (str(receipt.get("variant")), int(receipt.get("seed", -1)))
            if key in if_paths:
                raise ValueError(f"duplicate IF diagnostic receipt: {key}")
            if_paths[key] = receipt_path
    expected_if = {(variant, seed) for variant in IF_VARIANTS for seed in SEEDS}
    if set(if_paths) != expected_if:
        missing = sorted(expected_if - set(if_paths))
        unexpected = sorted(set(if_paths) - expected_if)
        raise ValueError(
            f"IF diagnostic matrix mismatch: missing={missing}, unexpected={unexpected}"
        )

    manifest = _read_json(v2_manifest_path)
    if manifest.get("status") != "PASS_WAVE047_CANDIDATE_DIAGNOSTICS_FROZEN":
        raise ValueError("V2 diagnostic manifest is not frozen PASS")
    if manifest.get("protected_outcome_read_count") != 0:
        raise ValueError("V2 diagnostic manifest reports protected reads")
    if manifest.get("internal_test_opened") is not False:
        raise ValueError("V2 diagnostic manifest reports Internal-test access")
    if manifest.get("gold_opened") is not False:
        raise ValueError("V2 diagnostic manifest reports Gold access")

    v2_paths: dict[int, Path] = {}
    for item in manifest.get("diagnostic_receipts", []):
        if str(item.get("variant")) != "V2":
            continue
        seed = int(item["seed"])
        receipt_path = Path(item["receipt_path"])
        if seed in v2_paths:
            raise ValueError(f"duplicate V2 diagnostic receipt: S{seed}")
        if sha256_file(receipt_path) != str(item["receipt_sha256"]):
            raise ValueError(f"V2 diagnostic receipt hash drift: S{seed}")
        v2_paths[seed] = receipt_path
    if set(v2_paths) != set(SEEDS):
        raise ValueError("V2 diagnostic seed set is incomplete")

    inventory: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for seed in SEEDS:
        record, block_rows = _validate_receipt(
            v2_paths[seed],
            system="V2",
            seed=seed,
            expected_status="PASS_WAVE047_CANDIDATE_TRAIN_DEV_PRIOR_DIAGNOSTIC",
        )
        inventory.append(record)
        rows.extend(block_rows)
    for variant in IF_VARIANTS:
        for seed in SEEDS:
            record, block_rows = _validate_receipt(
                if_paths[(variant, seed)],
                system=variant,
                seed=seed,
                expected_status="PASS_IFUSION_TRAIN_DEV_PRIOR_DIAGNOSTIC",
            )
            inventory.append(record)
            rows.extend(block_rows)

    return (
        {
            "schema": "prta-cxr.ifusion-diagnostic-36-block-manifest.v1",
            "status": "PASS_IFUSION_DIAGNOSTIC_EVIDENCE_RECONCILED",
            "created_at": datetime.now(UTC).isoformat(),
            "systems": list(SYSTEMS),
            "seeds": list(SEEDS),
            "diagnostic_receipt_count": len(inventory),
            "if_diagnostic_cell_count": len(expected_if),
            "v2_reference_cell_count": len(SEEDS),
            "diagnostic_receipts": inventory,
            "v2_manifest_sha256": sha256_file(v2_manifest_path),
            "selection_performed": False,
            "winner_selected": False,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
        rows,
    )


def _metric_vector(matrix: np.ndarray) -> np.ndarray:
    metrics = metrics_from_confusion(
        matrix,
        labels=PROGRESSION_LABELS,
        require_all_labels=False,
    )
    return np.asarray([float(metrics[name]) for name in SCALAR_METRICS])


def _interval(values: np.ndarray) -> dict[str, float]:
    lower, upper = np.quantile(values, [0.025, 0.975], method="linear")
    return {"lower": float(lower), "upper": float(upper), "level": 0.95}


def paired_ifusion_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    *,
    replicates: int = 10_000,
    rng_seed: int = 20260814,
) -> dict[str, Any]:
    if replicates < 2:
        raise ValueError("at least two bootstrap replicates are required")
    blocks: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for source in rows:
        row = dict(source)
        key = (str(row["system"]), int(row["training_seed"]))
        if key[0] not in SYSTEMS or key[1] not in SEEDS:
            raise ValueError(f"unexpected prediction block: {key}")
        if str(row.get("cohort")) != "dev":
            raise ValueError("IF bootstrap accepts Dev predictions only")
        if str(row.get("prior_intervention")) != "true":
            raise ValueError("IF bootstrap accepts true PRIOR blocks only")
        blocks[key].append(row)
    expected_blocks = {(system, seed) for system in SYSTEMS for seed in SEEDS}
    if set(blocks) != expected_blocks:
        raise ValueError("IF bootstrap matrix is not fully crossed")

    reference_layout = sorted(
        (
            str(row["patient_id"]),
            str(row["observation_id"]),
            str(row["target"]),
        )
        for row in blocks[("V2", SEEDS[0])]
    )
    label_index = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
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
        if len({observation for _, observation, _ in layout}) != len(layout):
            raise ValueError(f"duplicate observation in block {key!r}")

    patients = sorted({patient for patient, _, _ in reference_layout})
    patient_index = {patient: index for index, patient in enumerate(patients)}
    system_index = {system: index for index, system in enumerate(SYSTEMS)}
    seed_index = {seed: index for index, seed in enumerate(SEEDS)}
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

    def evaluate(patient_draw: np.ndarray) -> np.ndarray:
        counts = np.bincount(patient_draw, minlength=len(patients))
        output = np.empty((len(SYSTEMS), len(SEEDS), len(SCALAR_METRICS)))
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
    point_delta = point[0][None, :, :] - point[1:]
    samples = np.empty(
        (replicates, len(IF_VARIANTS), len(SEEDS) + 1, len(SCALAR_METRICS)),
        dtype=np.float64,
    )
    rng = np.random.default_rng(rng_seed)
    for replicate in range(replicates):
        evaluated = evaluate(
            rng.integers(0, len(patients), size=len(patients), endpoint=False)
        )
        delta = evaluated[0][None, :, :] - evaluated[1:]
        samples[replicate, :, : len(SEEDS), :] = delta
        samples[replicate, :, len(SEEDS), :] = np.mean(delta, axis=1)

    scopes = (*[f"seed{seed}" for seed in SEEDS], "mean_across_seeds")
    contrast_results: dict[str, Any] = {}
    for variant_position, variant in enumerate(IF_VARIANTS):
        scope_results: dict[str, Any] = {}
        for scope_position, scope in enumerate(scopes):
            metric_results: dict[str, Any] = {}
            for metric_position, metric in enumerate(SCALAR_METRICS):
                values = samples[:, variant_position, scope_position, metric_position]
                if scope == "mean_across_seeds":
                    point_value = float(
                        np.mean(point_delta[variant_position, :, metric_position])
                    )
                else:
                    point_value = float(
                        point_delta[variant_position, scope_position, metric_position]
                    )
                metric_results[metric] = {
                    "point": point_value,
                    "interval": _interval(values),
                    "empirical_two_sided_p": min(
                        1.0,
                        2.0
                        * min(
                            (int(np.count_nonzero(values <= 0)) + 1) / (replicates + 1),
                            (int(np.count_nonzero(values >= 0)) + 1) / (replicates + 1),
                        ),
                    ),
                }
            scope_results[scope] = metric_results

        exclusive = {}
        for seed in SEEDS:
            counts: Counter[str] = Counter()
            for _, observation, target in reference_layout:
                v2_correct = predictions[("V2", seed, observation)] == target
                variant_correct = predictions[(variant, seed, observation)] == target
                if v2_correct and not variant_correct:
                    counts["v2_only_correct"] += 1
                elif variant_correct and not v2_correct:
                    counts["variant_only_correct"] += 1
                elif v2_correct and variant_correct:
                    counts["both_correct"] += 1
                else:
                    counts["both_wrong"] += 1
            exclusive[f"seed{seed}"] = dict(sorted(counts.items()))
        contrast_results[f"V2_minus_{variant}"] = {
            "left": "V2",
            "right": variant,
            "delta_definition": "left_minus_right",
            "scopes": scope_results,
            "exclusive_counts": exclusive,
        }

    point_metrics = {
        system: {
            f"seed{seed}": {
                metric: float(point[system_index[system], seed_index[seed], index])
                for index, metric in enumerate(SCALAR_METRICS)
            }
            for seed in SEEDS
        }
        for system in SYSTEMS
    }
    return {
        "systems": list(SYSTEMS),
        "seeds": list(SEEDS),
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


def ifusion_bootstrap_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile IF diagnostics and run paired patient bootstrap"
    )
    parser.add_argument("--if-root", type=Path, action="append", required=True)
    parser.add_argument("--v2-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=10_000)
    parser.add_argument("--rng-seed", type=int, default=20260814)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")

    manifest, rows = collect_diagnostic_evidence(args.if_root, args.v2_manifest)
    result = paired_ifusion_bootstrap(
        rows,
        replicates=args.replicates,
        rng_seed=args.rng_seed,
    )
    args.output.mkdir(parents=True, exist_ok=False)
    manifest_path = args.output / "diagnostic_manifest.json"
    _write_new_json(manifest_path, manifest)
    result.update(
        {
            "schema": "prta-cxr.ifusion-paired-patient-bootstrap.v1",
            "status": "PASS_IFUSION_PAIRED_PATIENT_BOOTSTRAP",
            "created_at": datetime.now(UTC).isoformat(),
            "diagnostic_manifest_sha256": sha256_file(manifest_path),
            "selection_performed": False,
            "winner_selected": False,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        }
    )
    result_path = args.output / "paired_patient_bootstrap.json"
    _write_new_json(result_path, result)
    completion = {
        "schema": "prta-cxr.ifusion-bootstrap-completion.v1",
        "status": "PASS_IFUSION_BOOTSTRAP_COMPLETE",
        "created_at": datetime.now(UTC).isoformat(),
        "diagnostic_manifest_sha256": sha256_file(manifest_path),
        "result_sha256": sha256_file(result_path),
        "if_diagnostic_cell_count": manifest["if_diagnostic_cell_count"],
        "v2_reference_cell_count": manifest["v2_reference_cell_count"],
        "replicates": args.replicates,
        "rng_seed": args.rng_seed,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(args.output / "completion_receipt.json", completion)
    print(json.dumps(completion, indent=2, sort_keys=True))
    return 0
