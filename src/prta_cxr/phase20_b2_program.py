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
from prta_cxr.provenance import resolve_source_commit

B2_STATUS = "PASS_PHASE20_B2_PROGRAM_FROZEN"
B2_PROTOCOL = "phase20-post-comparator-probability-and-statistics-v1"
B2_LANE = "rtx3090_0"


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


def build_phase20_b2_jobs() -> list[dict[str, Any]]:
    jobs = []
    for system in COMPARATOR_SYSTEMS:
        for seed in SEEDS:
            checkpoint_role = _role(system, seed, "checkpoint")
            receipt_role = _role(system, seed, "training_receipt")
            output = f"{{output_root}}/probability/{system}/S{seed}"
            jobs.append(
                {
                    "job_id": f"b2-export-{system}-S{seed}",
                    "group": "phase20_b2_probability_export",
                    "lane": B2_LANE,
                    "host": "local",
                    "hardware_class": "RTX3090",
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
            "lane": B2_LANE,
            "host": "local",
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


def prepare_phase20_b2_program_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze Phase20-B2 probability queue")
    parser.add_argument("--phase20-a-program", type=Path, required=True)
    parser.add_argument("--phase20-a-final", type=Path, required=True)
    parser.add_argument("--comparator-final", type=Path, required=True)
    parser.add_argument("--s1-probability-receipt", type=Path, nargs=3, required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        help="Repeat SYSTEM=SEED=CHECKPOINT=TRAINING_RECEIPT",
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
    for raw in args.artifact:
        values = raw.split("=", 3)
        if len(values) != 4:
            parser.error("--artifact must use SYSTEM=SEED=CHECKPOINT=RECEIPT")
        system, raw_seed, checkpoint, receipt = values
        seed = int(raw_seed)
        key = (system, seed)
        if key in artifacts:
            parser.error(f"duplicate Phase20-B2 artifact: {system}/S{seed}")
        artifacts[key] = (Path(checkpoint), Path(receipt))
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
    for (system, seed), (checkpoint, receipt) in artifacts.items():
        input_paths[_role(system, seed, "checkpoint")] = checkpoint
        input_paths[_role(system, seed, "training_receipt")] = receipt
    for seed, path in zip(SEEDS, args.s1_probability_receipt, strict=True):
        input_paths[f"s1_probability_receipt_{seed}"] = path
    input_hashes = {role: sha256_file(path) for role, path in input_paths.items()}
    jobs = build_phase20_b2_jobs()
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
    queue_path = staging / "queue" / f"{B2_LANE}.json"
    _write_new_json(queue_path, jobs)
    receipt = {
        "schema": "prta-cxr.phase20-b2-preparation.v1",
        "status": B2_STATUS,
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": B2_PROTOCOL,
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "lane": B2_LANE,
        "systems": list(COMPARATOR_SYSTEMS),
        "seeds": list(SEEDS),
        "job_count": 28,
        "queue_hashes": {queue_path.name: sha256_file(queue_path)},
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
