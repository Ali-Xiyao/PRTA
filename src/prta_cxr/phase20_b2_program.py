from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import sha256_file
from prta_cxr.data.hard_cmcp import read_counterfactual_prior_map
from prta_cxr.phase20_b2_statistics import COMPARATOR_SYSTEMS, SEEDS, _load_receipt
from prta_cxr.phase20_program import LANES
from prta_cxr.provenance import resolve_source_commit

B2_STATUS = "PASS_PHASE20_B2_PROGRAM_FROZEN"
B2_PROTOCOL = "phase20-post-comparator-probability-and-statistics-v1"
B2_LANE = "rtx3090_0"
B2_DEFAULT_LANES = tuple(LANES)
B2_LOCAL_RUNTIME_MULTIPLIER = 1.50


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _role(system: str, seed: int, kind: str) -> str:
    normalized = system.lower().replace("-", "_")
    return f"b2_{normalized}_{kind}_{seed}"


def _validate_lanes(lanes: Sequence[str], statistics_lane: str) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(map(str, lanes)))
    if not normalized or any(lane not in LANES for lane in normalized):
        raise ValueError("Phase20-B2 contains an unsupported lane")
    if statistics_lane not in normalized:
        raise ValueError("Phase20-B2 statistics lane is not an active lane")
    return normalized


def _balanced_artifact_lanes(
    lanes: Sequence[str], *, statistics_lane: str
) -> dict[tuple[str, int], str]:
    """Greedily balance equal export cells using observed B2 hardware ratios."""
    normalized = _validate_lanes(lanes, statistics_lane)
    multipliers = {
        lane: (
            B2_LOCAL_RUNTIME_MULTIPLIER
            if LANES[lane]["host"] == "local"
            else float(LANES[lane]["runtime_multiplier"])
        )
        for lane in normalized
    }
    loads = {lane: 0.0 for lane in normalized}
    loads[statistics_lane] = 1800.0
    result: dict[tuple[str, int], str] = {}
    for system in COMPARATOR_SYSTEMS:
        for seed in SEEDS:
            lane = min(
                normalized,
                key=lambda candidate: (loads[candidate], normalized.index(candidate)),
            )
            result[(system, seed)] = lane
            loads[lane] += 1500.0 * multipliers[lane]
    return result


def build_phase20_b2_jobs(
    *,
    lanes: Sequence[str] = (B2_LANE,),
    statistics_lane: str = B2_LANE,
    artifact_lanes: Mapping[tuple[str, int], str] | None = None,
) -> list[dict[str, Any]]:
    normalized_lanes = _validate_lanes(lanes, statistics_lane)
    expected_artifacts = {
        (system, seed) for system in COMPARATOR_SYSTEMS for seed in SEEDS
    }
    if artifact_lanes is None:
        if len(normalized_lanes) == 1:
            artifact_lanes = {
                artifact: normalized_lanes[0] for artifact in expected_artifacts
            }
        else:
            artifact_lanes = _balanced_artifact_lanes(
                normalized_lanes, statistics_lane=statistics_lane
            )
    if set(artifact_lanes) != expected_artifacts:
        raise ValueError("Phase20-B2 lane inventory is not exact 9x3")
    if any(lane not in normalized_lanes for lane in artifact_lanes.values()):
        raise ValueError("Phase20-B2 artifact is assigned to an inactive lane")
    jobs = []
    for system in COMPARATOR_SYSTEMS:
        for seed in SEEDS:
            lane = str(artifact_lanes[(system, seed)])
            checkpoint_role = _role(system, seed, "checkpoint")
            receipt_role = _role(system, seed, "training_receipt")
            output = f"{{output_root}}/probability/{system}/S{seed}"
            jobs.append(
                {
                    "job_id": f"b2-export-{system}-S{seed}",
                    "group": "phase20_b2_probability_export",
                    "lane": lane,
                    "host": LANES[lane]["host"],
                    "hardware_class": LANES[lane]["hardware_class"],
                    "estimated_seconds": 1500,
                    "dependencies": [],
                    "command": [
                        "{python}",
                        "{source}/scripts/45_evaluate_prta_v2_mechanisms.py",
                        "--checkpoint",
                        f"{{{checkpoint_role}}}",
                        "--training-receipt",
                        f"{{{receipt_role}}}",
                        "--split-manifest",
                        "{split_manifest}",
                        "--cleaned-split-freeze",
                        "{cleaned_split_freeze}",
                        "--cleaned-split-platform-root",
                        "{cleaned_split_platform_root}",
                        "--cache-root",
                        "{cache_root}",
                        "--text-cache",
                        "{text_cache}",
                        "--matched-hard-prior-map",
                        "{matched_hard_prior_map}",
                        "--weights",
                        "{weights}",
                        "--label-quality-audit",
                        "{label_quality_audit}",
                        "--output",
                        output,
                        "--device",
                        "{device}",
                        "--batch-size",
                        "16",
                        "--diagnostic-scope",
                        "phase20_b2",
                        "--retain-logits",
                        "--true-only",
                        "--formal",
                    ],
                    "expected_outputs": [
                        f"{output}/candidate_probability_diagnostic_receipt.json"
                    ],
                }
            )
    export_ids = [str(job["job_id"]) for job in jobs]
    stats_command = [
        "{python}",
        "{source}/scripts/124_run_phase20_b2_statistics.py",
    ]
    for seed in SEEDS:
        stats_command.extend(["--s1-receipt", f"{{s1_probability_receipt_{seed}}}"])
    for system in COMPARATOR_SYSTEMS:
        for seed in SEEDS:
            stats_command.extend(
                [
                    "--comparator-receipt",
                    (
                        f"{system}={{output_root}}/probability/{system}/S{seed}/"
                        "candidate_probability_diagnostic_receipt.json"
                    ),
                ]
            )
    stats_command.extend(
        [
            "--replicates",
            "10000",
            "--rng-seed",
            "20260818",
            "--output",
            "{output_root}/b2_statistics.json",
            "--formal",
        ]
    )
    jobs.append(
        {
            "job_id": "b2-post-comparator-statistics",
            "group": "phase20_b2_statistics",
            "lane": statistics_lane,
            "host": LANES[statistics_lane]["host"],
            "hardware_class": "CPU",
            "estimated_seconds": 1800,
            "dependencies": export_ids,
            "command": stats_command,
            "expected_outputs": ["{output_root}/b2_statistics.json"],
        }
    )
    if len(jobs) != 28 or len({str(job["job_id"]) for job in jobs}) != 28:
        raise ValueError("Phase20-B2 must contain 27 exports plus one statistics job")
    for index, job in enumerate(jobs):
        job["queue_index"] = index
    return jobs


def validate_artifact_inventory(
    artifacts: Mapping[tuple[str, int], tuple[Path, Path]],
    *,
    phase20_a_final: Mapping[str, Any],
    comparator_final: Mapping[str, Any],
) -> None:
    expected = {(system, seed) for system in COMPARATOR_SYSTEMS for seed in SEEDS}
    if set(artifacts) != expected:
        raise ValueError("Phase20-B2 checkpoint inventory is not exact 9x3")
    a_rows = {
        str(row["experiment_id"]): dict(row)
        for row in phase20_a_final.get("training", [])
    }
    comparator_rows = {
        (str(row["method"]), int(row["seed"])): dict(row)
        for row in comparator_final.get("cells", [])
    }
    for (system, seed), (checkpoint, receipt) in artifacts.items():
        if system == "F02-DMW0":
            expected_row = a_rows.get(f"P20-F02-DMW0-S{seed}")
        else:
            expected_row = comparator_rows.get((system, seed))
        if expected_row is None:
            raise ValueError(
                f"Phase20-B2 finalizer inventory missing: {system}/S{seed}"
            )
        if (
            not checkpoint.is_file()
            or sha256_file(checkpoint) != expected_row.get("checkpoint_sha256")
            or not receipt.is_file()
            or sha256_file(receipt) != expected_row.get("training_receipt_sha256")
        ):
            raise ValueError(
                f"Phase20-B2 checkpoint/receipt hash drift: {system}/S{seed}"
            )


def artifact_hash_inventory_from_finalizers(
    *,
    phase20_a_final: Mapping[str, Any],
    comparator_final: Mapping[str, Any],
) -> dict[tuple[str, int], tuple[str, str]]:
    a_rows = {
        str(row["experiment_id"]): dict(row)
        for row in phase20_a_final.get("training", [])
    }
    comparator_rows = {
        (str(row["method"]), int(row["seed"])): dict(row)
        for row in comparator_final.get("cells", [])
    }
    result = {}
    for system in COMPARATOR_SYSTEMS:
        for seed in SEEDS:
            row = (
                a_rows.get(f"P20-F02-DMW0-S{seed}")
                if system == "F02-DMW0"
                else comparator_rows.get((system, seed))
            )
            if row is None:
                raise ValueError(
                    f"Phase20-B2 finalizer inventory missing: {system}/S{seed}"
                )
            checkpoint_sha256 = str(row.get("checkpoint_sha256", ""))
            receipt_sha256 = str(row.get("training_receipt_sha256", ""))
            if len(checkpoint_sha256) != 64 or len(receipt_sha256) != 64:
                raise ValueError(
                    f"Phase20-B2 finalizer hash malformed: {system}/S{seed}"
                )
            result[(system, seed)] = (checkpoint_sha256, receipt_sha256)
    return result


def prepare_phase20_b2_program_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze Phase20-B2 probability queue")
    parser.add_argument("--phase20-a-program", type=Path, required=True)
    parser.add_argument("--phase20-a-final", type=Path, required=True)
    parser.add_argument("--comparator-final", type=Path, required=True)
    parser.add_argument("--s1-probability-receipt", type=Path, nargs=3, required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        help="Repeat SYSTEM=SEED=CHECKPOINT=TRAINING_RECEIPT",
    )
    parser.add_argument(
        "--artifact-from-finalizers",
        action="store_true",
        help=(
            "Freeze checkpoint hashes from the two already-PASS finalizers. This is "
            "required for a cross-host queue whose artifacts are not all mounted on "
            "the preparation host."
        ),
    )
    parser.add_argument(
        "--lane",
        action="append",
        choices=tuple(LANES),
        help="Repeat to activate multiple B2 lanes; defaults to rtx3090_0.",
    )
    parser.add_argument(
        "--statistics-lane",
        choices=tuple(LANES),
        help="Lane that owns the cross-lane paired-statistics job.",
    )
    parser.add_argument(
        "--artifact-lane",
        action="append",
        default=[],
        help="Optional exact assignment repeated as SYSTEM=SEED=LANE.",
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--matched-hard-prior-map", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    phase20_a_final = _read_json(args.phase20_a_final)
    comparator_final = _read_json(args.comparator_final)
    if (
        phase20_a_final.get("status") != "PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE"
        or comparator_final.get("status")
        != "PASS_PHASE20_COMPARATOR_FINAL_NO_SELECTION_AGGREGATE"
    ):
        raise ValueError("Phase20-B2 requires both upstream finalizers PASS")
    artifacts = {}
    for raw in args.artifact or []:
        values = raw.split("=", 3)
        if len(values) != 4:
            parser.error("--artifact must use SYSTEM=SEED=CHECKPOINT=RECEIPT")
        system, raw_seed, checkpoint, receipt = values
        seed = int(raw_seed)
        key = (system, seed)
        if key in artifacts:
            parser.error(f"duplicate Phase20-B2 artifact: {system}/S{seed}")
        artifacts[key] = (Path(checkpoint), Path(receipt))
    lanes = tuple(args.lane or (B2_LANE,))
    statistics_lane = str(args.statistics_lane or lanes[0])
    _validate_lanes(lanes, statistics_lane)
    artifact_lanes = {}
    for raw in args.artifact_lane:
        values = raw.split("=", 2)
        if len(values) != 3:
            parser.error("--artifact-lane must use SYSTEM=SEED=LANE")
        system, raw_seed, lane = values
        key = (system, int(raw_seed))
        if key in artifact_lanes:
            parser.error(f"duplicate Phase20-B2 artifact lane: {system}/S{raw_seed}")
        artifact_lanes[key] = lane
    expected_artifacts = {
        (system, seed) for system in COMPARATOR_SYSTEMS for seed in SEEDS
    }
    if artifact_lanes and set(artifact_lanes) != expected_artifacts:
        parser.error("--artifact-lane must cover the exact 9x3 artifact inventory")
    frozen_artifact_hashes = artifact_hash_inventory_from_finalizers(
        phase20_a_final=phase20_a_final, comparator_final=comparator_final
    )
    if args.artifact_from_finalizers:
        if artifacts:
            parser.error(
                "--artifact and --artifact-from-finalizers are mutually exclusive"
            )
    else:
        if not artifacts:
            parser.error(
                "provide the exact 9x3 --artifact inventory or "
                "--artifact-from-finalizers"
            )
        validate_artifact_inventory(
            artifacts,
            phase20_a_final=phase20_a_final,
            comparator_final=comparator_final,
        )
    for seed, path in zip(SEEDS, args.s1_probability_receipt, strict=True):
        observed_seed, _, _ = _load_receipt(path, expected_system="Slim-S1")
        if observed_seed != seed:
            raise ValueError("Phase20-B2 S1 probability receipt order drift")
    require_cleaned_manifest(
        args.split_manifest,
        receipt_path=args.cleaned_split_freeze,
        role="train_dev",
        portable_root=args.cleaned_split_platform_root,
    )
    base_paths = {
        "split_manifest": args.split_manifest,
        "cleaned_split_freeze": args.cleaned_split_freeze,
        "cache_manifest": args.cache_root / "cache_manifest.json",
        "text_cache": args.text_cache,
        "matched_hard_prior_map": args.matched_hard_prior_map,
        "weights": args.weights,
        "label_quality_audit": args.label_quality_audit,
    }
    phase20_a_inputs = _read_json(args.phase20_a_program / "input_manifest.json")[
        "input_sha256"
    ]
    if {role: sha256_file(path) for role, path in base_paths.items()} != dict(
        phase20_a_inputs
    ):
        raise ValueError("Phase20-B2 base inputs drift from Phase20-A")
    read_counterfactual_prior_map(
        args.matched_hard_prior_map,
        expected_matching="offline_hard_v1",
        expected_split_manifest_sha256=phase20_a_inputs["split_manifest"],
        expected_cache_manifest_sha256=phase20_a_inputs["cache_manifest"],
        expected_cache_entry_block=4,
    )
    input_paths = dict(base_paths)
    for seed, path in zip(SEEDS, args.s1_probability_receipt, strict=True):
        input_paths[f"s1_probability_receipt_{seed}"] = path
    input_hashes = {role: sha256_file(path) for role, path in input_paths.items()}
    for (system, seed), (
        checkpoint_sha256,
        receipt_sha256,
    ) in frozen_artifact_hashes.items():
        input_hashes[_role(system, seed, "checkpoint")] = checkpoint_sha256
        input_hashes[_role(system, seed, "training_receipt")] = receipt_sha256
    jobs = build_phase20_b2_jobs(
        lanes=lanes,
        statistics_lane=statistics_lane,
        artifact_lanes=artifact_lanes or None,
    )
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    _write_new_json(
        staging / "input_manifest.json",
        {
            "schema": "prta-cxr.phase20-input-manifest.v1",
            "status": "PASS_PHASE20_B2_INPUTS_FROZEN",
            "input_sha256": input_hashes,
            "cleaned_split_platform_root_required": True,
            "external_included": False,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
    )
    _write_new_json(staging / "job_registry.json", {"jobs": jobs, "job_count": 28})
    queue_paths = {}
    lane_manifest_hashes = {}
    base_roles = set(base_paths)
    for lane in lanes:
        lane_jobs = [job for job in jobs if job["lane"] == lane]
        if not lane_jobs:
            raise ValueError(f"Phase20-B2 active lane has no work: {lane}")
        queue_path = staging / "queue" / f"{lane}.json"
        _write_new_json(queue_path, lane_jobs)
        queue_paths[lane] = queue_path
        lane_roles = set(base_roles)
        for job in lane_jobs:
            if job["group"] == "phase20_b2_probability_export":
                system, raw_seed = str(job["job_id"])[len("b2-export-") :].rsplit(
                    "-S", 1
                )
                seed = int(raw_seed)
                lane_roles.add(_role(system, seed, "checkpoint"))
                lane_roles.add(_role(system, seed, "training_receipt"))
        if lane == statistics_lane:
            lane_roles.update(f"s1_probability_receipt_{seed}" for seed in SEEDS)
        lane_manifest_path = staging / "input_manifests" / f"{lane}.json"
        _write_new_json(
            lane_manifest_path,
            {
                "schema": "prta-cxr.phase20-input-manifest.v1",
                "status": "PASS_PHASE20_B2_LANE_INPUTS_FROZEN",
                "lane": lane,
                "input_sha256": {
                    role: input_hashes[role] for role in sorted(lane_roles)
                },
                "cleaned_split_platform_root_required": True,
                "external_included": False,
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            },
        )
        lane_manifest_hashes[lane] = sha256_file(lane_manifest_path)
    receipt = {
        "schema": "prta-cxr.phase20-b2-preparation.v1",
        "status": B2_STATUS,
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": B2_PROTOCOL,
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "lanes": list(lanes),
        "statistics_lane": statistics_lane,
        "systems": list(COMPARATOR_SYSTEMS),
        "seeds": list(SEEDS),
        "job_count": 28,
        "queue_hashes": {path.name: sha256_file(path) for path in queue_paths.values()},
        "lane_input_manifest_hashes": lane_manifest_hashes,
        "registry_sha256": sha256_file(staging / "job_registry.json"),
        "input_manifest_sha256": sha256_file(staging / "input_manifest.json"),
        "phase20_a_final_sha256": sha256_file(args.phase20_a_final),
        "comparator_final_sha256": sha256_file(args.comparator_final),
        "selection_performed": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "preparation_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
