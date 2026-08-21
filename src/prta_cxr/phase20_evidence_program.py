from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.hard_cmcp import read_counterfactual_prior_map
from prta_cxr.data.token_cache import image_cache_key
from prta_cxr.data.training_dataset import read_jsonl
from prta_cxr.phase20_program import PHASE20_PROTOCOL, SEEDS
from prta_cxr.provenance import resolve_source_commit

EVIDENCE_PROTOCOL = "phase20-slim-s1-focused-trustworthiness-v2"
FINAL_SYSTEM = "Slim-S1"
EVIDENCE_LANES = ("a800_3066", "a800_9929", "rtx3090_0")
PHASE_B_JOB_COUNT = 6
PHASE_C_OPTIONAL_JOB_COUNT = 11


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def raw_image_root_identity(
    split_manifest: Path, raw_image_root: Path
) -> dict[str, Any]:
    keys = sorted(
        {
            image_cache_key(str(row["source"]), str(row["current_image_path"]))
            for row in read_jsonl(split_manifest)
            if row.get("split") == "dev"
        }
    )
    roster = []
    for key in keys:
        path = raw_image_root / f"{key}.jpg"
        if not path.is_file():
            raise FileNotFoundError(f"Phase20 raw-image mirror missing: {path}")
        roster.append((path.name, int(path.stat().st_size)))
    if not roster:
        raise ValueError("Phase20 raw-image mirror has an empty Dev roster")
    return {
        "dev_current_image_count": len(roster),
        "filename_size_roster_sha256": canonical_sha256(roster),
    }


def validate_final_s1_artifact(
    checkpoint_path: Path,
    training_receipt_path: Path,
    *,
    seed: int,
    expected_input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("Phase20 evidence checkpoint schema drift")
    config = dict(checkpoint["config"])
    expected_id = f"P20-FINAL-S1-S{seed}"
    if (
        config.get("experiment_id") != expected_id
        or int(config.get("seed", -1)) != seed
        or config.get("prta_v2_variant") != FINAL_SYSTEM
        or config.get("phase20_protocol") != PHASE20_PROTOCOL
        or config.get("phase20_axis") != "final_mainline_confirmation"
    ):
        raise ValueError(f"Phase20 final-S1 checkpoint identity drift: S{seed}")
    receipt = json.loads(training_receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError(f"Phase20 final-S1 training is not PASS: S{seed}")
    if receipt.get("config_sha256") != canonical_sha256(config):
        raise ValueError(f"Phase20 final-S1 config/receipt drift: S{seed}")
    if receipt.get("internal_test_opened") is not False:
        raise ValueError(f"Phase20 final-S1 opened Internal-test: S{seed}")
    if receipt.get("protected_outcomes_opened") is not False:
        raise ValueError(f"Phase20 final-S1 opened protected outcomes: S{seed}")
    checkpoint_inputs = dict(checkpoint.get("input_hashes", {}))
    if checkpoint_inputs != dict(expected_input_hashes):
        raise ValueError(f"Phase20 final-S1 checkpoint input drift: S{seed}")
    if dict(receipt.get("input_hashes", {})) != checkpoint_inputs:
        raise ValueError(f"Phase20 final-S1 training input drift: S{seed}")
    return {
        "experiment_id": expected_id,
        "seed": seed,
        "config_sha256": canonical_sha256(config),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "training_receipt_sha256": sha256_file(training_receipt_path),
    }


def _diagnostic_command(seed: int, *, pruned: bool) -> list[str]:
    output = (
        f"{{output_root}}/state_pruning/S{seed}/pruned_export"
        if pruned
        else f"{{output_root}}/probability/S{seed}"
    )
    command = [
        "{python}",
        "{source}/scripts/45_evaluate_prta_v2_mechanisms.py",
        "--checkpoint",
        f"{{s1_checkpoint_{seed}}}",
        "--training-receipt",
        f"{{s1_training_receipt_{seed}}}",
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
        "phase20_s1",
        "--retain-logits",
        "--formal",
    ]
    if pruned:
        command.extend(["--true-only", "--deployment-prune-state"])
    return command


def _order_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(job["job_id"]): job for job in jobs}
    if len(by_id) != len(jobs):
        raise ValueError("Phase20 evidence job IDs are not unique")
    ranks: dict[str, int] = {}

    def rank(job_id: str) -> int:
        if job_id not in ranks:
            dependencies = [str(value) for value in by_id[job_id]["dependencies"]]
            internal = [value for value in dependencies if value in by_id]
            ranks[job_id] = 0 if not internal else 1 + max(map(rank, internal))
        return ranks[job_id]

    jobs.sort(
        key=lambda job: (
            rank(str(job["job_id"])),
            -int(job["estimated_seconds"]),
            str(job["job_id"]),
        )
    )
    for index, job in enumerate(jobs):
        job["queue_index"] = index
    return jobs


def _diagnostic_receipts() -> list[str]:
    return [
        value
        for seed in SEEDS
        for value in (
            "--diagnostic-receipt",
            f"{{output_root}}/probability/S{seed}/candidate_probability_diagnostic_receipt.json",
        )
    ]


def build_phase20_evidence_jobs(*, lane: str) -> list[dict[str, Any]]:
    """Build the mandatory Phase B focused trustworthiness queue."""
    if lane not in EVIDENCE_LANES:
        raise ValueError(f"unsupported Phase20 evidence lane: {lane}")
    jobs: list[dict[str, Any]] = []
    probability_jobs: list[str] = []
    for seed in SEEDS:
        probability_job = f"evidence-probability-S{seed}"
        probability_jobs.append(probability_job)
        probability_receipt = (
            f"{{output_root}}/probability/S{seed}/"
            "candidate_probability_diagnostic_receipt.json"
        )
        jobs.append(
            {
                "job_id": probability_job,
                "group": "probability_and_prior_stress",
                "lane": lane,
                "estimated_seconds": 1500,
                "dependencies": [],
                "command": _diagnostic_command(seed, pruned=False),
                "expected_outputs": [probability_receipt],
            }
        )
    diagnostic_receipts = _diagnostic_receipts()
    jobs.extend(
        [
            {
                "job_id": "evidence-calibration",
                "group": "calibration_selective_prediction",
                "lane": lane,
                "estimated_seconds": 300,
                "dependencies": probability_jobs,
                "command": [
                    "{python}",
                    "{source}/scripts/89_evaluate_v2_calibration.py",
                    *diagnostic_receipts,
                    "--system",
                    FINAL_SYSTEM,
                    "--output",
                    "{output_root}/calibration",
                    "--formal",
                ],
                "expected_outputs": ["{output_root}/calibration/manifest.json"],
            },
            {
                "job_id": "evidence-subgroups",
                "group": "subgroup_long_tail",
                "lane": lane,
                "estimated_seconds": 300,
                "dependencies": probability_jobs,
                "command": [
                    "{python}",
                    "{source}/scripts/94_evaluate_subgroups.py",
                    *diagnostic_receipts,
                    "--split-manifest",
                    "{split_manifest}",
                    "--system",
                    FINAL_SYSTEM,
                    "--output",
                    "{output_root}/subgroups",
                    "--formal",
                ],
                "expected_outputs": ["{output_root}/subgroups/manifest.json"],
            },
            {
                "job_id": "evidence-state-efficiency-S43",
                "group": "state_pruning_and_efficiency",
                "lane": lane,
                "estimated_seconds": 1200,
                "dependencies": ["evidence-probability-S43"],
                "command": [
                    "{python}",
                    "{source}/scripts/131_profile_phase20_state_efficiency.py",
                    "--checkpoint",
                    "{s1_checkpoint_43}",
                    "--training-receipt",
                    "{s1_training_receipt_43}",
                    "--baseline-receipt",
                    "{output_root}/probability/S43/candidate_probability_diagnostic_receipt.json",
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
                    "{output_root}/efficiency/S43",
                    "--device",
                    "{device}",
                    "--warmup",
                    "20",
                    "--repeats",
                    "100",
                    "--formal",
                ],
                "expected_outputs": ["{output_root}/efficiency/S43/manifest.json"],
            },
        ]
    )
    if len(jobs) != PHASE_B_JOB_COUNT:
        raise ValueError("Phase20-B focused evidence queue must contain exactly 6 jobs")
    return _order_jobs(jobs)


def build_phase20_phase_c_jobs(*, lane: str) -> list[dict[str, Any]]:
    """Catalog optional Phase C jobs; these are not placed in the active queue."""
    if lane not in EVIDENCE_LANES:
        raise ValueError(f"unsupported Phase20 evidence lane: {lane}")
    jobs: list[dict[str, Any]] = [
        {
            "job_id": "phase-c-modality-text-cache",
            "group": "optional_modality_assets",
            "lane": lane,
            "estimated_seconds": 600,
            "dependencies": [],
            "command": [
                "{python}",
                "{source}/scripts/104_prepare_modality_text_cache.py",
                "--split-manifest",
                "{split_manifest}",
                "--model-root",
                "{model_root}",
                "--output",
                "{output_root}/phase_c/assets/modality/finding_interventions.pt",
                "--formal",
            ],
            "expected_outputs": [
                "{output_root}/phase_c/assets/modality/finding_interventions.pt"
            ],
        }
    ]
    corruption_jobs: list[str] = []
    for condition in ("blur", "contrast", "jpeg"):
        job_id = f"phase-c-current-cache-{condition}"
        corruption_jobs.append(job_id)
        output = f"{{output_root}}/phase_c/assets/modality/current_{condition}"
        jobs.append(
            {
                "job_id": job_id,
                "group": "optional_generic_corruption",
                "lane": lane,
                "estimated_seconds": 1800,
                "dependencies": [],
                "command": [
                    "{python}",
                    "{source}/scripts/105_build_current_corruption_cache.py",
                    "--split-manifest",
                    "{split_manifest}",
                    "--weights",
                    "{weights}",
                    "--raw-image-root",
                    "{raw_image_root}",
                    "--condition",
                    condition,
                    "--output",
                    output,
                    "--device",
                    "{device}",
                    "--batch-size",
                    "32",
                    "--shard-size",
                    "256",
                    "--formal",
                ],
                "expected_outputs": [f"{output}/cache_manifest.json"],
            }
        )
    for seed in SEEDS:
        modality_output = f"{{output_root}}/phase_c/modality/S{seed}"
        jobs.append(
            {
                "job_id": f"phase-c-modality-S{seed}",
                "group": "optional_extended_modality_stress",
                "lane": lane,
                "estimated_seconds": 5400,
                "dependencies": [
                    "phase-c-modality-text-cache",
                    *corruption_jobs,
                    f"evidence-probability-S{seed}",
                ],
                "command": [
                    "{python}",
                    "{source}/scripts/106_evaluate_modality_stress.py",
                    "--checkpoint",
                    f"{{s1_checkpoint_{seed}}}",
                    "--training-receipt",
                    f"{{s1_training_receipt_{seed}}}",
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
                    "--intervention-text-cache",
                    "{output_root}/phase_c/assets/modality/finding_interventions.pt",
                    "--matched-hard-prior-map",
                    "{matched_hard_prior_map}",
                    "--blur-cache",
                    "{output_root}/phase_c/assets/modality/current_blur",
                    "--contrast-cache",
                    "{output_root}/phase_c/assets/modality/current_contrast",
                    "--jpeg-cache",
                    "{output_root}/phase_c/assets/modality/current_jpeg",
                    "--weights",
                    "{weights}",
                    "--label-quality-audit",
                    "{label_quality_audit}",
                    "--output",
                    modality_output,
                    "--device",
                    "{device}",
                    "--batch-size",
                    "16",
                    "--formal",
                ],
                "expected_outputs": [f"{modality_output}/modality_stress_receipt.json"],
            }
        )
    for seed in (17, 28):
        pruned_job = f"phase-c-state-pruned-S{seed}"
        pruned_receipt = (
            f"{{output_root}}/phase_c/state_pruning/S{seed}/pruned_export/"
            "candidate_probability_diagnostic_receipt.json"
        )
        command = _diagnostic_command(seed, pruned=True)
        command[command.index("--output") + 1] = (
            f"{{output_root}}/phase_c/state_pruning/S{seed}/pruned_export"
        )
        jobs.append(
            {
                "job_id": pruned_job,
                "group": "optional_multiseed_state_pruning",
                "lane": lane,
                "estimated_seconds": 500,
                "dependencies": [f"evidence-probability-S{seed}"],
                "command": command,
                "expected_outputs": [pruned_receipt],
            }
        )
        parity_output = f"{{output_root}}/phase_c/state_pruning/S{seed}/parity.json"
        jobs.append(
            {
                "job_id": f"phase-c-state-parity-S{seed}",
                "group": "optional_multiseed_state_pruning",
                "lane": lane,
                "estimated_seconds": 60,
                "dependencies": [pruned_job],
                "command": [
                    "{python}",
                    "{source}/scripts/101_compare_state_pruning.py",
                    "--baseline-receipt",
                    f"{{output_root}}/probability/S{seed}/candidate_probability_diagnostic_receipt.json",
                    "--pruned-receipt",
                    pruned_receipt,
                    "--output",
                    parity_output,
                    "--formal",
                ],
                "expected_outputs": [parity_output],
            }
        )
    if len(jobs) != PHASE_C_OPTIONAL_JOB_COUNT:
        raise ValueError("Phase20-C optional evidence catalog must contain 11 jobs")
    return _order_jobs(jobs)


def prepare_phase20_evidence_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the post-training Phase20 Slim-S1 Dev evidence queue"
    )
    parser.add_argument("--phase20-a-program", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, nargs=3, required=True)
    parser.add_argument("--training-receipt", type=Path, nargs=3, required=True)
    parser.add_argument("--lane", choices=EVIDENCE_LANES, default="rtx3090_0")
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
    phase20_a = json.loads(
        (args.phase20_a_program / "preparation_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        phase20_a.get("status") != "PASS_PHASE20_SLIM_S1_PROGRAM_FROZEN"
        or int(phase20_a.get("training_cell_count", -1)) != 63
        or int(phase20_a.get("job_count", -1)) != 88
        or phase20_a.get("final_mainline") != FINAL_SYSTEM
    ):
        raise ValueError("Phase20-A program is not the frozen 63-cell/88-job S1 run")
    require_cleaned_manifest(
        args.split_manifest,
        receipt_path=args.cleaned_split_freeze,
        role="train_dev",
        portable_root=args.cleaned_split_platform_root,
    )
    input_paths = {
        "split_manifest": args.split_manifest,
        "cleaned_split_freeze": args.cleaned_split_freeze,
        "cache_manifest": args.cache_root / "cache_manifest.json",
        "text_cache": args.text_cache,
        "matched_hard_prior_map": args.matched_hard_prior_map,
        "weights": args.weights,
        "label_quality_audit": args.label_quality_audit,
    }
    for seed, checkpoint, receipt in zip(
        SEEDS, args.checkpoint, args.training_receipt, strict=True
    ):
        input_paths[f"s1_checkpoint_{seed}"] = checkpoint
        input_paths[f"s1_training_receipt_{seed}"] = receipt
    for role, path in input_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Phase20 evidence input missing: {role}")
    input_hashes = {role: sha256_file(path) for role, path in input_paths.items()}
    phase20_a_inputs = json.loads(
        (args.phase20_a_program / "input_manifest.json").read_text(encoding="utf-8")
    )["input_sha256"]
    required_phase20_a = {
        key: input_hashes[key]
        for key in (
            "split_manifest",
            "cleaned_split_freeze",
            "cache_manifest",
            "text_cache",
            "matched_hard_prior_map",
            "weights",
            "label_quality_audit",
        )
    }
    if required_phase20_a != dict(phase20_a_inputs):
        raise ValueError("Phase20 evidence inputs drift from Phase20-A")
    read_counterfactual_prior_map(
        args.matched_hard_prior_map,
        expected_matching="offline_hard_v1",
        expected_split_manifest_sha256=input_hashes["split_manifest"],
        expected_cache_manifest_sha256=input_hashes["cache_manifest"],
        expected_cache_entry_block=4,
    )
    artifact_evidence = {
        str(seed): validate_final_s1_artifact(
            checkpoint,
            receipt,
            seed=seed,
            expected_input_hashes=required_phase20_a,
        )
        for seed, checkpoint, receipt in zip(
            SEEDS, args.checkpoint, args.training_receipt, strict=True
        )
    }
    jobs = build_phase20_evidence_jobs(lane=args.lane)
    phase_c_jobs = build_phase20_phase_c_jobs(lane=args.lane)
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    input_manifest = {
        "schema": "prta-cxr.phase20-evidence-input-manifest.v2",
        "status": "PASS_PHASE20_EVIDENCE_INPUTS_FROZEN",
        "input_sha256": input_hashes,
        "cleaned_split_platform_root_required": True,
        "model_root_required": False,
        "raw_image_root_required": False,
        "external_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "input_manifest.json", input_manifest)
    _write_new_json(staging / "final_s1_artifacts.json", artifact_evidence)
    _write_new_json(staging / "queue.json", jobs)
    _write_new_json(
        staging / "job_registry.json",
        {
            "schema": "prta-cxr.phase20-evidence-job-registry.v1",
            "status": "PASS_PHASE20_EVIDENCE_REGISTRY_FROZEN",
            "job_count": len(jobs),
            "jobs": jobs,
        },
    )
    _write_new_json(
        staging / "phase_c_optional_registry.json",
        {
            "schema": "prta-cxr.phase20-phase-c-optional-registry.v1",
            "status": "NOT_FROZEN_PHASE_C_OPTIONAL",
            "runnable": False,
            "job_count": len(phase_c_jobs),
            "jobs": phase_c_jobs,
            "deferred_unbuilt_families": [
                "older PRIOR",
                "view-mismatch PRIOR",
                "token-scrambled PRIOR",
                "typo/synonym/paraphrase/random-finding salts",
            ],
            "activation_rule": (
                "Requires an explicit later Phase C decision and a separately frozen "
                "queue; it is not part of the Phase B completion gate."
            ),
        },
    )
    receipt = {
        "schema": "prta-cxr.phase20-evidence-preparation.v1",
        "status": "PASS_PHASE20_SLIM_S1_EVIDENCE_PROGRAM_FROZEN",
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "protocol": EVIDENCE_PROTOCOL,
        "system": FINAL_SYSTEM,
        "seeds": list(SEEDS),
        "lane": args.lane,
        "job_count": len(jobs),
        "phase_b_required_job_count": len(jobs),
        "phase_c_optional_job_count": len(phase_c_jobs),
        "queue_sha256": sha256_file(staging / "queue.json"),
        "registry_sha256": sha256_file(staging / "job_registry.json"),
        "phase_c_optional_registry_sha256": sha256_file(
            staging / "phase_c_optional_registry.json"
        ),
        "input_manifest_sha256": sha256_file(staging / "input_manifest.json"),
        "phase20_a_preparation_sha256": sha256_file(
            args.phase20_a_program / "preparation_receipt.json"
        ),
        "groups": {
            group: sum(job["group"] == group for job in jobs)
            for group in sorted({str(job["group"]) for job in jobs})
        },
        "selection_performed": False,
        "external_included": False,
        "clinician_manual_work_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "preparation_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
