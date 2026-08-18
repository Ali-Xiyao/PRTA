from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.hard_cmcp import read_counterfactual_prior_map
from prta_cxr.phase20_program import LANES, PHASE20_PROTOCOL, SEEDS
from prta_cxr.provenance import resolve_source_commit

COMPARATOR_PROTOCOL = "phase20-post-cleanup-comparator-rebuild-v1"
COMPARATOR_STATUS = "PASS_PHASE20_COMPARATOR_REBUILD_PROGRAM_FROZEN"
COMPARATOR_SPECS: dict[str, dict[str, Any]] = {
    "V2": {
        "family": "prta",
        "estimated_seconds": 15_250,
        "prototype_alignment": 0.01,
        "direction_margin": 0.01,
        "inversion": 0.0,
        "priority": 10,
        "method_provenance": "historical_v2_exact_contract_rebuild",
    },
    "S0": {
        "family": "prta",
        "estimated_seconds": 15_250,
        "prototype_alignment": 0.01,
        "direction_margin": 0.0,
        "inversion": 0.0,
        "priority": 0,
        "method_provenance": "audited_if_a10_semantic_rebuild",
    },
    "B401": {
        "family": "current_only",
        "estimated_seconds": 10_000,
        "inversion": 0.0,
        "priority": 0,
        "method_provenance": "native_current_only_rebuild",
    },
    "B402": {
        "family": "siamese_diff",
        "estimated_seconds": 10_500,
        "inversion": 0.0,
        "priority": 20,
        "method_provenance": "native_siamese_difference_rebuild",
    },
    "TILA8": {
        "family": "tila",
        "estimated_seconds": 15_000,
        "inversion": 0.0,
        "priority": 10,
        "method_provenance": "tail8_internal_tila_rebuild",
    },
    "BioViLT": {
        "family": "biovilt_adapted",
        "estimated_seconds": 15_000,
        "inversion": 0.0,
        "priority": 30,
        "method_provenance": "architecture_inspired_internal_reimplementation",
    },
    "CheXRelNet": {
        "family": "chexrelnet_adapted",
        "estimated_seconds": 12_000,
        "inversion": 0.0,
        "priority": 30,
        "method_provenance": "architecture_inspired_internal_reimplementation",
    },
    "TILAPaper": {
        "family": "tila",
        "estimated_seconds": 15_000,
        "inversion": 0.10,
        "priority": 30,
        "method_provenance": "independent_paper_based_reimplementation",
    },
}


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


def _zero_auxiliary_losses(config: dict[str, Any], *, inversion: float) -> None:
    weights = config["loss_weights"]
    for name in weights:
        weights[name] = 1.0 if name == "classification" else 0.0
    weights["inversion"] = inversion


def build_phase20_comparator_configs(
    final_s1_configs: Mapping[int, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if set(final_s1_configs) != set(SEEDS):
        raise ValueError("Phase20 comparator rebuild requires final-S1 config seeds")
    configs: dict[str, dict[str, Any]] = {}
    for seed in SEEDS:
        parent = dict(final_s1_configs[seed])
        if (
            parent.get("experiment_id") != f"P20-FINAL-S1-S{seed}"
            or parent.get("prta_v2_variant") != "Slim-S1"
            or parent.get("phase20_protocol") != PHASE20_PROTOCOL
        ):
            raise ValueError(f"Phase20 comparator parent identity drift: S{seed}")
        for key, specification in COMPARATOR_SPECS.items():
            experiment_id = f"P20-REBUILD-{key}-S{seed}"
            config = deepcopy(parent)
            config["experiment_id"] = experiment_id
            config["seed"] = seed
            config["development_axis"] = COMPARATOR_PROTOCOL
            config["phase20_protocol"] = COMPARATOR_PROTOCOL
            config["phase20_axis"] = "comparator_rebuild_after_private_cleanup"
            config["phase20_role"] = key
            config["final_mainline_reference"] = "Slim-S1"
            config["phase20_parent_s1_config_sha256"] = canonical_sha256(parent)
            config["method_provenance"] = specification["method_provenance"]
            config["official_implementation"] = False
            config["official_checkpoint"] = False
            config.pop("final_mainline", None)
            family = str(specification["family"])
            config["model"]["family"] = family
            if family == "prta":
                config["prta_v2_variant"] = key
                config["loss_weights"]["prototype_alignment"] = float(
                    specification["prototype_alignment"]
                )
                config["loss_weights"]["direction_margin"] = float(
                    specification["direction_margin"]
                )
                config["loss_weights"]["inversion"] = 0.0
                config["loss_weights"]["state"] = 0.025
                config["loss_weights"]["opposite_direction_cost"] = 0.05
                config["loss_weights"]["cmcp"] = 0.01
                config["model"]["components"]["matched_hard_cmcp"] = True
                config["cmcp"]["matching"] = "offline_hard_v1"
            else:
                config["prta_v2_variant"] = key
                config["model"].pop("components", None)
                _zero_auxiliary_losses(
                    config, inversion=float(specification["inversion"])
                )
                config["cmcp"] = {"matching": "disabled"}
            configs[experiment_id] = config
    validate_phase20_comparator_configs(configs)
    return configs


def validate_phase20_comparator_configs(
    configs: Mapping[str, Mapping[str, Any]],
) -> None:
    expected = {
        f"P20-REBUILD-{key}-S{seed}" for key in COMPARATOR_SPECS for seed in SEEDS
    }
    if set(configs) != expected or len(configs) != 24:
        raise ValueError("Phase20 comparator rebuild must contain 24 unique cells")
    for experiment_id, raw in configs.items():
        config = dict(raw)
        key = str(config.get("phase20_role", ""))
        specification = COMPARATOR_SPECS.get(key)
        if specification is None:
            raise ValueError("unknown Phase20 comparator identity")
        if config.get("experiment_id") != experiment_id:
            raise ValueError("Phase20 comparator experiment ID drift")
        if int(config.get("seed", -1)) not in SEEDS:
            raise ValueError("Phase20 comparator seed drift")
        if config.get("phase20_protocol") != COMPARATOR_PROTOCOL:
            raise ValueError("Phase20 comparator protocol drift")
        if config.get("method_provenance") != specification["method_provenance"]:
            raise ValueError("Phase20 comparator method provenance drift")
        if config.get("official_implementation") is not False or config.get(
            "official_checkpoint"
        ) is not False:
            raise ValueError("Phase20 comparator cannot claim official assets")
        model = dict(config["model"])
        if model.get("family") != specification["family"]:
            raise ValueError("Phase20 comparator family drift")
        if model.get("adapter_scope") != "tail8":
            raise ValueError("Phase20 comparator must use Tail8")
        weights = dict(config["loss_weights"])
        if specification["family"] == "prta":
            if float(weights["prototype_alignment"]) != float(
                specification["prototype_alignment"]
            ):
                raise ValueError("Phase20 PRTA comparator prototype drift")
            if float(weights["direction_margin"]) != float(
                specification["direction_margin"]
            ):
                raise ValueError("Phase20 PRTA comparator DMW drift")
        else:
            expected_inversion = float(specification["inversion"])
            if float(weights["inversion"]) != expected_inversion:
                raise ValueError("Phase20 longitudinal comparator inversion drift")
            if any(
                float(value) != 0.0
                for name, value in weights.items()
                if name not in {"classification", "inversion"}
            ):
                raise ValueError("Phase20 native comparator retained auxiliary loss")


def _training_command(config: Mapping[str, Any]) -> list[str]:
    experiment_id = str(config["experiment_id"])
    command = [
        "{python}",
        "{source}/scripts/07_train.py",
        "--mode",
        "formal",
        "--config",
        f"{{runtime_root}}/configs/{experiment_id}.json",
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
        "--weights",
        "{weights}",
        "--label-quality-audit",
        "{label_quality_audit}",
        "--run-registry",
        f"{{output_root}}/registries/{experiment_id}.jsonl",
        "--owner",
        "PRTA-CXR Phase20 comparator rebuild after private cleanup",
        "--output",
        f"{{output_root}}/runs/{experiment_id}",
        "--device",
        "{device}",
        "--formal",
    ]
    if str(config["model"]["family"]) == "prta":
        command.extend(
            ["--counterfactual-prior-map", "{matched_hard_prior_map}"]
        )
    return command


def allocate_phase20_comparator_jobs(
    configs: Mapping[str, Mapping[str, Any]], *, active_lanes: Sequence[str]
) -> dict[str, list[dict[str, Any]]]:
    if not active_lanes or len(active_lanes) != len(set(active_lanes)):
        raise ValueError("Phase20 comparator active lanes must be unique")
    if any(lane not in LANES for lane in active_lanes):
        raise ValueError("unknown Phase20 comparator lane")
    queues = {lane: [] for lane in active_lanes}
    loads = {lane: 0 for lane in active_lanes}
    ordered = sorted(
        configs.values(),
        key=lambda config: (
            -int(COMPARATOR_SPECS[str(config["phase20_role"])]["estimated_seconds"]),
            str(config["experiment_id"]),
        ),
    )
    for config in ordered:
        base = int(COMPARATOR_SPECS[str(config["phase20_role"])]["estimated_seconds"])
        lane = min(
            active_lanes,
            key=lambda name: (
                loads[name] + round(base * float(LANES[name]["runtime_multiplier"])),
                name,
            ),
        )
        estimate = round(base * float(LANES[lane]["runtime_multiplier"]))
        experiment_id = str(config["experiment_id"])
        queues[lane].append(
            {
                "job_id": f"train-{experiment_id}",
                "experiment_id": experiment_id,
                "group": "comparator_rebuild",
                "comparator": str(config["phase20_role"]),
                "lane": lane,
                "host": LANES[lane]["host"],
                "hardware_class": LANES[lane]["hardware_class"],
                "estimated_seconds": estimate,
                "queue_priority": int(
                    COMPARATOR_SPECS[str(config["phase20_role"])]["priority"]
                ),
                "dependencies": [],
                "command": _training_command(config),
                "expected_outputs": [
                    f"{{output_root}}/runs/{experiment_id}/training_receipt.json",
                    f"{{output_root}}/runs/{experiment_id}/best.pt",
                ],
            }
        )
        loads[lane] += estimate
    for queue in queues.values():
        queue.sort(
            key=lambda job: (
                int(job["queue_priority"]),
                -int(job["estimated_seconds"]),
                str(job["job_id"]),
            )
        )
        for index, job in enumerate(queue):
            job["queue_index"] = index
    identifiers = [str(job["job_id"]) for queue in queues.values() for job in queue]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Phase20 comparator job IDs are not unique")
    return queues


def prepare_phase20_comparator_program_main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze post-cleanup nonexternal comparator rebuild queues"
    )
    parser.add_argument("--phase20-a-program", type=Path, required=True)
    parser.add_argument(
        "--active-lane", nargs="+", choices=tuple(LANES), required=True
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
    phase20_a_receipt_path = args.phase20_a_program / "preparation_receipt.json"
    phase20_a_receipt = json.loads(
        phase20_a_receipt_path.read_text(encoding="utf-8")
    )
    if (
        phase20_a_receipt.get("status") != "PASS_PHASE20_SLIM_S1_PROGRAM_FROZEN"
        or int(phase20_a_receipt.get("training_cell_count", -1)) != 63
        or int(phase20_a_receipt.get("job_count", -1)) != 88
    ):
        raise ValueError("Phase20-A program is not the frozen 63-cell/88-job run")
    final_configs = {
        seed: json.loads(
            (
                args.phase20_a_program / "configs" / f"P20-FINAL-S1-S{seed}.json"
            ).read_text(encoding="utf-8")
        )
        for seed in SEEDS
    }
    configs = build_phase20_comparator_configs(final_configs)
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
    for role, path in input_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Phase20 comparator input missing: {role}")
    input_sha256 = {role: sha256_file(path) for role, path in input_paths.items()}
    phase20_a_inputs = json.loads(
        (args.phase20_a_program / "input_manifest.json").read_text(encoding="utf-8")
    )
    if input_sha256 != dict(phase20_a_inputs.get("input_sha256", {})):
        raise ValueError("Phase20 comparator inputs drift from Phase20-A")
    read_counterfactual_prior_map(
        args.matched_hard_prior_map,
        expected_matching="offline_hard_v1",
        expected_split_manifest_sha256=input_sha256["split_manifest"],
        expected_cache_manifest_sha256=input_sha256["cache_manifest"],
        expected_cache_entry_block=4,
    )
    queues = allocate_phase20_comparator_jobs(configs, active_lanes=args.active_lane)
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    config_hashes = {}
    for experiment_id, config in sorted(configs.items()):
        path = staging / "configs" / f"{experiment_id}.json"
        _write_new_json(path, config)
        config_hashes[path.name] = {
            "file_sha256": sha256_file(path),
            "canonical_sha256": canonical_sha256(config),
        }
    input_manifest = {
        "schema": "prta-cxr.phase20-input-manifest.v1",
        "status": "PASS_PHASE20_COMPARATOR_INPUTS_FROZEN",
        "input_sha256": input_sha256,
        "cleaned_split_platform_root_required": True,
        "external_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "input_manifest.json", input_manifest)
    all_jobs = [job for queue in queues.values() for job in queue]
    _write_new_json(
        staging / "job_registry.json",
        {
            "schema": "prta-cxr.phase20-comparator-job-registry.v1",
            "status": "PASS_PHASE20_COMPARATOR_REGISTRY_FROZEN",
            "training_cell_count": len(configs),
            "job_count": len(all_jobs),
            "jobs": all_jobs,
        },
    )
    queue_hashes = {}
    loads = {}
    counts = {}
    for lane, queue in queues.items():
        path = staging / "queue" / f"{lane}.json"
        _write_new_json(path, queue)
        queue_hashes[path.name] = sha256_file(path)
        loads[lane] = sum(int(job["estimated_seconds"]) for job in queue)
        counts[lane] = len(queue)
    receipt = {
        "schema": "prta-cxr.phase20-comparator-preparation.v1",
        "status": COMPARATOR_STATUS,
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "protocol": COMPARATOR_PROTOCOL,
        "active_lanes": list(args.active_lane),
        "reserved_lanes": [lane for lane in LANES if lane not in args.active_lane],
        "training_cell_count": len(configs),
        "job_count": len(all_jobs),
        "systems": list(COMPARATOR_SPECS),
        "config_hashes": config_hashes,
        "input_manifest_sha256": sha256_file(staging / "input_manifest.json"),
        "registry_sha256": sha256_file(staging / "job_registry.json"),
        "queue_hashes": queue_hashes,
        "lane_load_estimated_seconds": loads,
        "lane_training_cell_count": counts,
        "estimated_imbalance_seconds": max(loads.values()) - min(loads.values()),
        "phase20_a_preparation_sha256": sha256_file(phase20_a_receipt_path),
        "reason_retraining_required": (
            "user-authorized deletion removed all pre-Phase20 private checkpoints"
        ),
        "selection_performed": False,
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
