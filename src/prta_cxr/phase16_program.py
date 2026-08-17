from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.provenance import resolve_source_commit

SEEDS = (17, 28, 43)
FRACTIONS = (0.10, 0.25, 0.50, 0.75)
NOISE_RATES = (0.05, 0.10, 0.20)
NOISE_FAMILIES = ("symmetric", "plausible")
INTERNAL_LONGITUDINAL_COMPARATORS = {
    "BioViLT": {
        "family": "biovilt_adapted",
        "estimated_seconds": 15000,
        "inversion_weight": 0.0,
        "method_label": "BioViL-T-style Temporal Transformer",
    },
    "CheXRelNet": {
        "family": "chexrelnet_adapted",
        "estimated_seconds": 12000,
        "inversion_weight": 0.0,
        "method_label": "CheXRelNet-inspired Global Relation Network",
    },
    "TILAOfficial": {
        "family": "tila",
        "estimated_seconds": 15000,
        "inversion_weight": 0.10,
        "method_label": "TILA-style + Temporal Inversion",
    },
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


def _v2_config(
    base: Mapping[str, Any], *, experiment_id: str, seed: int
) -> dict[str, Any]:
    config = deepcopy(dict(base))
    config["experiment_id"] = experiment_id
    config["seed"] = seed
    config["phase16_parent_config_sha256"] = canonical_sha256(base)
    config["phase16_protocol"] = "dev-only-continuation-v1"
    return config


def build_phase16_configs(
    base: Mapping[str, Any], sources: Sequence[str]
) -> dict[str, dict[str, Any]]:
    if len(sources) != 2:
        raise ValueError("source-held-out program requires exactly two sources")
    configs: dict[str, dict[str, Any]] = {}
    for fraction in FRACTIONS:
        tag = f"F{int(fraction * 100):02d}"
        for seed in SEEDS:
            experiment_id = f"P16-SCALE-{tag}-S{seed}"
            config = _v2_config(base, experiment_id=experiment_id, seed=seed)
            config["data"]["train_fraction"] = fraction
            config["phase16_axis"] = "data_scaling"
            configs[experiment_id] = config
    for train_source in sources:
        source_tag = "CHEX" if "chex" in train_source.lower() else "MIMIC"
        target_source = next(source for source in sources if source != train_source)
        for seed in SEEDS:
            experiment_id = f"P16-SOURCE-ROLL-{source_tag}-S{seed}"
            config = _v2_config(base, experiment_id=experiment_id, seed=seed)
            config["data"].update(
                {
                    "train_fraction": 1.0,
                    "train_sources": [train_source],
                    "dev_sources": [train_source],
                }
            )
            components = dict(config["model"].get("components", {}))
            components["matched_hard_cmcp"] = False
            config["model"]["components"] = components
            cmcp = dict(config.get("cmcp", {}))
            cmcp["matching"] = "in_batch_roll_v1"
            config["cmcp"] = cmcp
            config["phase16_axis"] = "source_held_out"
            config["source_held_out_protocol"] = "exploratory_v2_in_batch_roll_v1"
            config["source_held_out_role"] = "exploratory"
            config["phase16_protocol_amendment"] = (
                "source-held-out uses symmetric in-batch CMCP because strict "
                "different-patient/different-label maps are not complete after "
                "single-source filtering"
            )
            config["source_held_out_target"] = target_source
            configs[experiment_id] = config
            v1_experiment_id = f"P16-SOURCE-V1-{source_tag}-S{seed}"
            v1 = _v2_config(base, experiment_id=v1_experiment_id, seed=seed)
            v1["prta_v2_variant"] = "V1"
            v1["data"].update(
                {
                    "train_fraction": 1.0,
                    "train_sources": [train_source],
                    "dev_sources": [train_source],
                }
            )
            v1_components = dict(v1["model"].get("components", {}))
            v1_components["matched_hard_cmcp"] = False
            v1["model"]["components"] = v1_components
            v1_weights = dict(v1.get("loss_weights", {}))
            v1_weights["prototype_alignment"] = 0.01
            v1_weights["cmcp"] = 0.0
            v1["loss_weights"] = v1_weights
            v1_cmcp = dict(v1.get("cmcp", {}))
            v1_cmcp["matching"] = "in_batch_roll_v1"
            v1["cmcp"] = v1_cmcp
            v1["phase16_axis"] = "source_held_out"
            v1["source_held_out_protocol"] = "confirmatory_v1_no_cmcp_v1"
            v1["source_held_out_role"] = "confirmatory"
            v1["source_held_out_target"] = target_source
            configs[v1_experiment_id] = v1
    for family in NOISE_FAMILIES:
        for rate in NOISE_RATES:
            for seed in SEEDS:
                experiment_id = (
                    f"P16-NOISE-{family.upper()}-{int(rate * 100):02d}-S{seed}"
                )
                config = _v2_config(base, experiment_id=experiment_id, seed=seed)
                config["data"]["train_fraction"] = 1.0
                config["data"]["label_noise"] = {
                    "rate": rate,
                    "family": family,
                    "salt": f"prta-cxr-label-noise-{family}-{int(rate * 100):02d}-v1",
                }
                config["phase16_axis"] = "label_noise"
                configs[experiment_id] = config
    for method, specification in INTERNAL_LONGITUDINAL_COMPARATORS.items():
        for seed in SEEDS:
            experiment_id = f"P16-{method}-S{seed}"
            config = _v2_config(base, experiment_id=experiment_id, seed=seed)
            config["model"]["family"] = str(specification["family"])
            config["model"].pop("components", None)
            config["cmcp"] = {"matching": "in_batch_roll_v1"}
            config["loss_weights"] = {
                "classification": 1.0,
                "alignment": 0.0,
                "state": 0.0,
                "inversion": float(specification["inversion_weight"]),
                "cmcp": 0.0,
                "prototype_alignment": 0.0,
                "direction_margin": 0.0,
                "opposite_direction_cost": 0.0,
                "branch_decorrelation": 0.0,
            }
            config["phase16_axis"] = "internal_longitudinal_comparator"
            config["method_key"] = method
            config["method_provenance"] = (
                "architecture_inspired_internal_reimplementation"
            )
            config["method_label"] = str(specification["method_label"])
            config["official_implementation"] = False
            config["official_checkpoint"] = False
            configs[experiment_id] = config
    return configs


def _training_command(
    *,
    config_path: str,
    inputs: Mapping[str, Any],
    experiment_id: str,
    map_path: str | None,
) -> list[str]:
    command = [
        "{python}",
        "{source}/scripts/07_train.py",
        "--mode",
        "formal",
        "--config",
        config_path,
        "--split-manifest",
        str(inputs["split_manifest"]),
        "--cleaned-split-freeze",
        str(inputs["cleaned_split_freeze"]),
        "--cleaned-split-platform-root",
        str(inputs["cleaned_split_platform_root"]),
        "--cache-root",
        str(inputs["cache_root"]),
        "--text-cache",
        str(inputs["text_cache"]),
        "--weights",
        str(inputs["weights"]),
        "--label-quality-audit",
        str(inputs["label_quality_audit"]),
        "--run-registry",
        f"{{output_root}}/registries/{experiment_id}.jsonl",
        "--output",
        f"{{output_root}}/runs/{experiment_id}",
        "--device",
        "{device}",
        "--formal",
    ]
    if map_path is not None:
        command.extend(["--counterfactual-prior-map", map_path])
    return command


def build_phase16_jobs(
    configs: Mapping[str, Mapping[str, Any]],
    *,
    inputs: Mapping[str, Any],
    remote_program_root: str,
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    map_specs: dict[str, str] = {}
    for experiment_id, config in configs.items():
        axis = str(config["phase16_axis"])
        if axis not in {"data_scaling", "label_noise"}:
            continue
        map_key = experiment_id.rsplit("-S", 1)[0]
        map_specs.setdefault(map_key, experiment_id)
    for map_key, representative in sorted(map_specs.items()):
        config_path = f"{remote_program_root}/configs/{representative}.json"
        map_path = f"{{output_root}}/assets/maps/{map_key}.json"
        data = dict(configs[representative]["data"])
        fraction = float(data.get("train_fraction", 1.0))
        estimate = max(300, round(1200 * fraction))
        jobs.append(
            {
                "job_id": f"map-{map_key}",
                "group": str(configs[representative]["phase16_axis"]),
                "estimated_seconds": estimate,
                "queue_priority": 0,
                "dependencies": [],
                "command": [
                    "{python}",
                    "{source}/scripts/100_build_phase16_map.py",
                    "--config",
                    config_path,
                    "--split-manifest",
                    str(inputs["split_manifest"]),
                    "--cache-root",
                    str(inputs["cache_root"]),
                    "--output",
                    map_path,
                    "--device",
                    "{device}",
                    "--formal",
                ],
                "expected_outputs": [map_path],
            }
        )
    for experiment_id, config in sorted(configs.items()):
        axis = str(config["phase16_axis"])
        map_path = None
        dependencies = []
        if axis in {"data_scaling", "label_noise"}:
            map_key = experiment_id.rsplit("-S", 1)[0]
            map_path = f"{{output_root}}/assets/maps/{map_key}.json"
            dependencies = [f"map-{map_key}"]
        fraction = float(dict(config.get("data", {})).get("train_fraction", 1.0))
        if axis == "data_scaling":
            estimate = round(18600 * max(0.35, fraction))
            group = "data_scaling"
        elif axis == "source_held_out":
            estimate = 10500
            role = str(config.get("source_held_out_role", "exploratory"))
            group = f"source_held_out_{role}"
        elif axis == "label_noise":
            estimate = 18600
            group = "label_noise"
        elif axis == "internal_longitudinal_comparator":
            method = str(config["method_key"])
            estimate = int(
                INTERNAL_LONGITUDINAL_COMPARATORS[method]["estimated_seconds"]
            )
            group = "internal_longitudinal_comparator"
        else:  # pragma: no cover - program construction invariant
            raise ValueError(f"unsupported Phase16 training axis: {axis}")
        config_path = f"{remote_program_root}/configs/{experiment_id}.json"
        jobs.append(
            {
                "job_id": f"train-{experiment_id}",
                "group": group,
                "estimated_seconds": estimate,
                "queue_priority": 100,
                "dependencies": dependencies,
                "command": _training_command(
                    config_path=config_path,
                    inputs=inputs,
                    experiment_id=experiment_id,
                    map_path=map_path,
                ),
                "expected_outputs": [
                    f"{{output_root}}/runs/{experiment_id}/training_receipt.json",
                    f"{{output_root}}/runs/{experiment_id}/best.pt",
                ],
            }
        )
    for seed in SEEDS:
        asset = dict(inputs["v2"][str(seed)])
        export_root = f"{{output_root}}/state_pruning/S{seed}/pruned_export"
        export_job = f"state-pruned-export-S{seed}"
        jobs.append(
            {
                "job_id": export_job,
                "group": "state_pruning",
                "estimated_seconds": 300,
                "queue_priority": 0,
                "dependencies": [],
                "command": [
                    "{python}",
                    "{source}/scripts/45_evaluate_prta_v2_mechanisms.py",
                    "--checkpoint",
                    str(asset["checkpoint"]),
                    "--training-receipt",
                    str(asset["training_receipt"]),
                    "--split-manifest",
                    str(inputs["split_manifest"]),
                    "--cleaned-split-freeze",
                    str(inputs["cleaned_split_freeze"]),
                    "--cleaned-split-platform-root",
                    str(inputs["cleaned_split_platform_root"]),
                    "--cache-root",
                    str(inputs["cache_root"]),
                    "--text-cache",
                    str(inputs["text_cache"]),
                    "--matched-hard-prior-map",
                    str(inputs["matched_hard_prior_map"]),
                    "--weights",
                    str(inputs["weights"]),
                    "--label-quality-audit",
                    str(inputs["label_quality_audit"]),
                    "--output",
                    export_root,
                    "--device",
                    "{device}",
                    "--batch-size",
                    "16",
                    "--diagnostic-scope",
                    "candidate_v0_v2",
                    "--retain-logits",
                    "--true-only",
                    "--deployment-prune-state",
                    "--formal",
                ],
                "expected_outputs": [
                    f"{export_root}/candidate_probability_diagnostic_receipt.json"
                ],
            }
        )
        parity_path = f"{{output_root}}/state_pruning/S{seed}/parity.json"
        jobs.append(
            {
                "job_id": f"state-parity-S{seed}",
                "group": "state_pruning",
                "estimated_seconds": 60,
                "queue_priority": 0,
                "dependencies": [export_job],
                "command": [
                    "{python}",
                    "{source}/scripts/101_compare_state_pruning.py",
                    "--baseline-receipt",
                    str(asset["baseline_probability_receipt"]),
                    "--pruned-receipt",
                    f"{export_root}/candidate_probability_diagnostic_receipt.json",
                    "--output",
                    parity_path,
                    "--formal",
                ],
                "expected_outputs": [parity_path],
            }
        )
    seed43 = dict(inputs["v2"]["43"])
    efficiency_path = "{output_root}/state_pruning/S43/pruned_efficiency.json"
    jobs.append(
        {
            "job_id": "state-pruned-efficiency-S43",
            "group": "state_pruning",
            "estimated_seconds": 180,
            "queue_priority": 0,
            "dependencies": ["state-parity-S43"],
            "command": [
                "{python}",
                "{source}/scripts/90_profile_v2_efficiency.py",
                "--checkpoint",
                str(seed43["checkpoint"]),
                "--training-receipt",
                str(seed43["training_receipt"]),
                "--split-manifest",
                str(inputs["split_manifest"]),
                "--cleaned-split-freeze",
                str(inputs["cleaned_split_freeze"]),
                "--cleaned-split-platform-root",
                str(inputs["cleaned_split_platform_root"]),
                "--cache-root",
                str(inputs["cache_root"]),
                "--text-cache",
                str(inputs["text_cache"]),
                "--matched-hard-prior-map",
                str(inputs["matched_hard_prior_map"]),
                "--weights",
                str(inputs["weights"]),
                "--label-quality-audit",
                str(inputs["label_quality_audit"]),
                "--output",
                efficiency_path,
                "--device",
                "{device}",
                "--warmup",
                "20",
                "--repeats",
                "100",
                "--system",
                "V2",
                "--deployment-prune-state",
                "--formal",
            ],
            "expected_outputs": [efficiency_path],
        }
    )
    for experiment_id, config in sorted(configs.items()):
        if config.get("phase16_axis") != "source_held_out":
            continue
        target = str(config["source_held_out_target"])
        role = str(config.get("source_held_out_role", "exploratory"))
        output = f"{{output_root}}/source_held_out/{experiment_id}"
        jobs.append(
            {
                "job_id": f"evaluate-{experiment_id}",
                "group": f"source_held_out_{role}",
                "estimated_seconds": 300,
                "queue_priority": 100,
                "dependencies": [f"train-{experiment_id}"],
                "command": [
                    "{python}",
                    "{source}/scripts/103_evaluate_source_held_out.py",
                    "--checkpoint",
                    f"{{output_root}}/runs/{experiment_id}/best.pt",
                    "--training-receipt",
                    f"{{output_root}}/runs/{experiment_id}/training_receipt.json",
                    "--split-manifest",
                    str(inputs["split_manifest"]),
                    "--cleaned-split-freeze",
                    str(inputs["cleaned_split_freeze"]),
                    "--cleaned-split-platform-root",
                    str(inputs["cleaned_split_platform_root"]),
                    "--cache-root",
                    str(inputs["cache_root"]),
                    "--text-cache",
                    str(inputs["text_cache"]),
                    "--weights",
                    str(inputs["weights"]),
                    "--target-source",
                    target,
                    "--output",
                    output,
                    "--device",
                    "{device}",
                    "--batch-size",
                    "16",
                    "--formal",
                ],
                "expected_outputs": [
                    f"{output}/source_held_out_evaluation_receipt.json"
                ],
            }
        )
    modality_text = "{output_root}/assets/modality_v2/finding_interventions.pt"
    jobs.append(
        {
            "job_id": "modality-text-cache-v2",
            "group": "modality_stress",
            "estimated_seconds": 600,
            "queue_priority": 0,
            "dependencies": [],
            "command": [
                "{python}",
                "{source}/scripts/104_prepare_modality_text_cache.py",
                "--split-manifest",
                str(inputs["split_manifest"]),
                "--model-root",
                str(inputs["model_root"]),
                "--output",
                modality_text,
                "--formal",
            ],
            "expected_outputs": [modality_text],
        }
    )
    corruption_jobs = []
    corruption_paths = {}
    for condition in ("blur", "contrast", "jpeg"):
        job_id = f"modality-current-cache-v2-{condition}"
        path = f"{{output_root}}/assets/modality_v2/current_{condition}"
        corruption_jobs.append(job_id)
        corruption_paths[condition] = path
        jobs.append(
            {
                "job_id": job_id,
                "group": "modality_stress",
                "estimated_seconds": 1800,
                "queue_priority": 0,
                "dependencies": [],
                "command": [
                    "{python}",
                    "{source}/scripts/105_build_current_corruption_cache.py",
                    "--split-manifest",
                    str(inputs["split_manifest"]),
                    "--weights",
                    str(inputs["weights"]),
                    "--condition",
                    condition,
                    "--output",
                    path,
                    "--device",
                    "{device}",
                    "--batch-size",
                    "32",
                    "--shard-size",
                    "256",
                    "--formal",
                ],
                "expected_outputs": [f"{path}/cache_manifest.json"],
            }
        )
    for seed in SEEDS:
        asset = dict(inputs["v2"][str(seed)])
        output = f"{{output_root}}/modality_stress_v2/S{seed}"
        jobs.append(
            {
                "job_id": f"modality-stress-v2-S{seed}",
                "group": "modality_stress",
                "estimated_seconds": 5400,
                "queue_priority": 10,
                "dependencies": ["modality-text-cache-v2", *corruption_jobs],
                "command": [
                    "{python}",
                    "{source}/scripts/106_evaluate_modality_stress.py",
                    "--checkpoint",
                    str(asset["checkpoint"]),
                    "--training-receipt",
                    str(asset["training_receipt"]),
                    "--split-manifest",
                    str(inputs["split_manifest"]),
                    "--cleaned-split-freeze",
                    str(inputs["cleaned_split_freeze"]),
                    "--cleaned-split-platform-root",
                    str(inputs["cleaned_split_platform_root"]),
                    "--cache-root",
                    str(inputs["cache_root"]),
                    "--text-cache",
                    str(inputs["text_cache"]),
                    "--intervention-text-cache",
                    modality_text,
                    "--matched-hard-prior-map",
                    str(inputs["matched_hard_prior_map"]),
                    "--blur-cache",
                    corruption_paths["blur"],
                    "--contrast-cache",
                    corruption_paths["contrast"],
                    "--jpeg-cache",
                    corruption_paths["jpeg"],
                    "--weights",
                    str(inputs["weights"]),
                    "--label-quality-audit",
                    str(inputs["label_quality_audit"]),
                    "--output",
                    output,
                    "--device",
                    "{device}",
                    "--batch-size",
                    "16",
                    "--formal",
                ],
                "expected_outputs": [f"{output}/modality_stress_receipt.json"],
            }
        )
    return jobs


def prepare_phase16_program_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Phase16 configs and registry")
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--remote-program-root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    checkpoint = torch.load(args.base_checkpoint, map_location="cpu", weights_only=True)
    base = dict(checkpoint["config"])
    if base.get("prta_v2_variant") != "V2":
        raise ValueError("Phase16 base checkpoint must be frozen V2")
    inputs = json.loads(args.inputs.read_text(encoding="utf-8"))
    configs = build_phase16_configs(base, inputs["sources"])
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    config_hashes = {}
    for experiment_id, config in sorted(configs.items()):
        path = staging / "configs" / f"{experiment_id}.json"
        _write_new_json(path, config)
        config_hashes[path.name] = sha256_file(path)
    registry = {
        "schema": "prta-cxr.phase16-job-registry.v1",
        "jobs": build_phase16_jobs(
            configs, inputs=inputs, remote_program_root=args.remote_program_root
        ),
    }
    _write_new_json(staging / "job_registry.json", registry)
    receipt = {
        "schema": "prta-cxr.phase16-program-preparation.v1",
        "status": "PASS_PHASE16_PROGRAM_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "base_checkpoint_sha256": sha256_file(args.base_checkpoint),
        "inputs_sha256": sha256_file(args.inputs),
        "config_count": len(configs),
        "job_count": len(registry["jobs"]),
        "registry_sha256": sha256_file(staging / "job_registry.json"),
        "config_hashes": config_hashes,
        "external_evaluation_included": False,
        "clinician_manual_work_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "preparation_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
