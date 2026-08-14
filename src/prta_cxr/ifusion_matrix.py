from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.hard_cmcp import (
    build_random_counterfactual_prior_entries,
    read_matched_hard_prior_map,
)
from prta_cxr.data.training_dataset import read_jsonl
from prta_cxr.provenance import resolve_source_commit

BASE_MAIN_COMMIT = "f4218064d76e6d53e154f1cc1204ba425d95b3ab"
SEEDS = (17, 28, 43)
ABLATIONS = (
    "IF-A01",
    "IF-A02",
    "IF-A03",
    "IF-A04",
    "IF-A05",
    "IF-A06",
    "IF-A08",
    "IF-A10",
    "IF-A11",
)
FUSION_FAMILIES = {
    "IF-F01": "early_concat",
    "IF-F02": "symmetric_cross_attention",
}
AXIS = "ifusion_final_evidence_v1"
RANDOM_CMCP_SALT = "prta-cxr-ifusion-random-cmcp-v1"

LANES = (
    {
        "lane": "server3066",
        "hardware_class": "A800-80GB",
        "runtime_multiplier": 1.0,
        "allocation": 3066,
    },
    {
        "lane": "server9929",
        "hardware_class": "A800-80GB",
        "runtime_multiplier": 1.0,
        "allocation": 9929,
    },
    {
        "lane": "local_gpu0",
        "hardware_class": "RTX3090-24GB",
        "runtime_multiplier": 1.22,
        "device_index": 0,
    },
    {
        "lane": "local_gpu1",
        "hardware_class": "RTX3090-24GB",
        "runtime_multiplier": 1.22,
        "device_index": 1,
    },
)


def _normalized_parent(config: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(config))
    value.pop("experiment_id", None)
    value.pop("seed", None)
    return value


def validate_v2_parents(parents: Mapping[int, Mapping[str, Any]]) -> None:
    if set(parents) != set(SEEDS):
        raise ValueError("V2 parents must be exactly seeds 17/28/43")
    normalized = []
    for seed in SEEDS:
        config = parents[seed]
        if int(config.get("seed", -1)) != seed:
            raise ValueError(f"V2 parent seed drift: {seed}")
        if config.get("experiment_id") != f"W045-V2-S{seed}":
            raise ValueError(f"V2 parent identity drift: {seed}")
        if config.get("prta_v2_variant") != "V2":
            raise ValueError("parent is not frozen V2")
        model = config["model"]
        components = model["components"]
        weights = config["loss_weights"]
        required = {
            "family": "prta",
            "adapter_scope": "tail8",
            "native_head": "H0",
            "adapter_rank": 32,
        }
        for key, expected in required.items():
            if model.get(key) != expected:
                raise ValueError(f"V2 model contract drift: {key}")
        expected_weights = {
            "direction_margin": 0.01,
            "opposite_direction_cost": 0.05,
            "state": 0.025,
            "prototype_alignment": 0.01,
            "cmcp": 0.01,
        }
        for key, expected in expected_weights.items():
            if float(weights.get(key, -1)) != expected:
                raise ValueError(f"V2 loss contract drift: {key}")
        if not bool(components.get("finding_conditioning")):
            raise ValueError("V2 finding conditioning is not enabled")
        if not bool(components.get("cross_time_alignment")):
            raise ValueError("V2 cross-time alignment is not enabled")
        if not bool(components.get("matched_hard_cmcp")):
            raise ValueError("V2 matched-hard CMCP is not enabled")
        if config.get("cmcp", {}).get("matching") != "offline_hard_v1":
            raise ValueError("V2 CMCP matching drift")
        normalized.append(_normalized_parent(config))
    if any(value != normalized[0] for value in normalized[1:]):
        raise ValueError("V2 parent configs differ beyond seed and experiment ID")


def _base_variant(parent: Mapping[str, Any], variant: str, seed: int) -> dict[str, Any]:
    config = deepcopy(dict(parent))
    config["experiment_id"] = f"{variant}-S{seed}"
    config["seed"] = seed
    config["development_axis"] = AXIS
    config["ifusion_variant"] = variant
    components = config["model"]["components"]
    components.setdefault("unaligned_prior_mode", "conditioned")
    components.setdefault("temporal_relation_residual", True)
    return config


def build_ifusion_training_configs(
    parents: Mapping[int, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    validate_v2_parents(parents)
    configs: list[dict[str, Any]] = []
    for variant in ABLATIONS:
        for seed in SEEDS:
            config = _base_variant(parents[seed], variant, seed)
            components = config["model"]["components"]
            weights = config["loss_weights"]
            if variant == "IF-A01":
                components["finding_conditioning"] = False
            elif variant == "IF-A02":
                components["cross_time_alignment"] = False
                components["unaligned_prior_mode"] = "raw"
            elif variant == "IF-A03":
                components["temporal_relation_residual"] = False
            elif variant == "IF-A04":
                weights["state"] = 0.0
            elif variant == "IF-A05":
                weights["direction_margin"] = 0.0
                weights["opposite_direction_cost"] = 0.0
            elif variant == "IF-A06":
                weights["prototype_alignment"] = 0.0
            elif variant == "IF-A08":
                components["matched_hard_cmcp"] = False
                config["cmcp"]["matching"] = "offline_random_v1"
            elif variant == "IF-A10":
                weights["direction_margin"] = 0.0
            elif variant == "IF-A11":
                weights["opposite_direction_cost"] = 0.0
            configs.append(config)

    for variant, family in FUSION_FAMILIES.items():
        for seed in SEEDS:
            config = _base_variant(parents[seed], variant, seed)
            config["model"]["family"] = family
            config["model"]["components"] = {}
            config["cmcp"]["matching"] = "disabled"
            for name in (
                "alignment",
                "state",
                "inversion",
                "cmcp",
                "prototype_alignment",
                "branch_decorrelation",
            ):
                config["loss_weights"][name] = 0.0
            configs.append(config)
    validate_ifusion_training_configs(configs)
    return configs


def validate_ifusion_training_configs(configs: Sequence[Mapping[str, Any]]) -> None:
    expected_ids = {
        f"{variant}-S{seed}"
        for variant in (*ABLATIONS, *FUSION_FAMILIES)
        for seed in SEEDS
    }
    actual_ids = {str(config.get("experiment_id")) for config in configs}
    if len(configs) != 33 or actual_ids != expected_ids:
        raise ValueError("Information Fusion core matrix must contain 33 cells")
    for config in configs:
        variant = str(config["ifusion_variant"])
        model = config["model"]
        weights = config["loss_weights"]
        if model.get("adapter_scope") != "tail8" or int(model["adapter_rank"]) != 32:
            raise ValueError("Information Fusion matrix changed Tail8/rank32")
        if int(config["seed"]) not in SEEDS:
            raise ValueError("Information Fusion matrix seed drift")
        if variant in FUSION_FAMILIES:
            if model.get("family") != FUSION_FAMILIES[variant]:
                raise ValueError("fusion family drift")
            if float(weights["direction_margin"]) != 0.01:
                raise ValueError("fusion comparator DMW mismatch")
            if float(weights["opposite_direction_cost"]) != 0.05:
                raise ValueError("fusion comparator ODC mismatch")
            forbidden = ("state", "cmcp", "prototype_alignment")
            if any(float(weights[name]) for name in forbidden):
                raise ValueError("fusion comparator retained PRTA-only loss")
        else:
            if model.get("family") != "prta":
                raise ValueError("ablation changed PRTA family")
            if variant == "IF-A08":
                if config["cmcp"]["matching"] != "offline_random_v1":
                    raise ValueError("IF-A08 random CMCP matching drift")
            elif config["cmcp"]["matching"] != "offline_hard_v1":
                raise ValueError("non-random ablation changed hard CMCP")


def _a800_estimate(config: Mapping[str, Any]) -> int:
    family = str(config["model"]["family"])
    if family == "early_concat":
        return 13_800
    if family == "symmetric_cross_attention":
        return 14_200
    if config["ifusion_variant"] == "IF-A03":
        return 14_700
    return 15_250


def allocate_duration_balanced(
    configs: Sequence[Mapping[str, Any]],
    lanes: Sequence[Mapping[str, Any]] = LANES,
) -> dict[str, list[dict[str, Any]]]:
    if not lanes:
        raise ValueError("at least one hardware lane is required")
    assignments = {str(lane["lane"]): [] for lane in lanes}
    loads = {str(lane["lane"]): 0 for lane in lanes}
    lane_by_name = {str(lane["lane"]): lane for lane in lanes}
    jobs = sorted(
        configs,
        key=lambda config: (-_a800_estimate(config), str(config["experiment_id"])),
    )
    for config in jobs:
        base_seconds = _a800_estimate(config)
        selected = min(
            lanes,
            key=lambda lane: (
                loads[str(lane["lane"])]
                + round(base_seconds * float(lane["runtime_multiplier"])),
                str(lane["lane"]),
            ),
        )
        name = str(selected["lane"])
        estimate = round(base_seconds * float(selected["runtime_multiplier"]))
        assignments[name].append(
            {
                "experiment_id": str(config["experiment_id"]),
                "seed": int(config["seed"]),
                "ifusion_variant": str(config["ifusion_variant"]),
                "family": str(config["model"]["family"]),
                "estimated_seconds": estimate,
                "estimated_a800_seconds": base_seconds,
                "status": "PLANNED",
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            }
        )
        loads[name] += estimate
    for name, rows in assignments.items():
        rows.sort(
            key=lambda row: (-int(row["estimated_seconds"]), row["experiment_id"])
        )
        for index, row in enumerate(rows):
            row["queue_index"] = index
            row["lane"] = name
            row["hardware_class"] = str(lane_by_name[name]["hardware_class"])
    return assignments


def _write_matrix_configs(
    root: Path, configs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    config_root = root / "configs"
    config_root.mkdir(parents=True)
    result = {}
    for config in configs:
        run_id = str(config["experiment_id"])
        path = config_root / f"{run_id}.json"
        write_json_atomic(path, dict(config))
        result[run_id] = {
            "path": f"configs/{path.name}",
            "file_sha256": sha256_file(path),
            "effective_config_sha256": canonical_sha256(config),
        }
    return result


def prepare_ifusion_matrix_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the final Information Fusion Train/Dev matrix"
    )
    parser.add_argument("--v2-config", type=Path, nargs=3, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--matched-hard-prior-map", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--external-manifest", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing existing ifusion root: {output_root}")
    try:
        output_root.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Information Fusion runtime root must stay outside Git")

    parent_values = [
        json.loads(path.read_text(encoding="utf-8")) for path in args.v2_config
    ]
    parents = {int(value["seed"]): value for value in parent_values}
    configs = build_ifusion_training_configs(parents)
    cache_manifest = args.cache_root / "cache_manifest.json"
    input_paths = {
        "split_manifest": args.split_manifest,
        "cleaned_split_freeze": args.cleaned_split_freeze,
        "cache_manifest": cache_manifest,
        "text_cache": args.text_cache,
        "matched_hard_prior_map": args.matched_hard_prior_map,
        "weights": args.weights,
        "label_quality_audit": args.label_quality_audit,
    }
    for role, path in input_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Information Fusion input missing: {role}")
    input_sha256 = {role: sha256_file(path) for role, path in input_paths.items()}
    read_matched_hard_prior_map(
        args.matched_hard_prior_map,
        expected_split_manifest_sha256=input_sha256["split_manifest"],
        expected_cache_manifest_sha256=input_sha256["cache_manifest"],
        expected_cache_entry_block=4,
    )

    rows = read_jsonl(args.split_manifest)
    random_entries, random_audit = build_random_counterfactual_prior_entries(
        rows, salt=RANDOM_CMCP_SALT
    )
    output_root.mkdir(parents=True)
    random_map_path = output_root / "random_counterfactual_prior_map.json"
    random_map = {
        "schema": "prta-cxr.counterfactual-prior-map.v1",
        "status": "PASS_IFUSION_RANDOM_CMCP_MAP_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "matching": "offline_random_v1",
        "split_manifest_sha256": input_sha256["split_manifest"],
        "cache_manifest_sha256": input_sha256["cache_manifest"],
        "cache_entry_block": 4,
        "selection_audit": random_audit,
        "entries": random_entries,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(random_map_path, random_map)

    config_receipts = _write_matrix_configs(output_root, configs)
    assignments = allocate_duration_balanced(configs)
    for lane, queue in assignments.items():
        for row in queue:
            row["config"] = config_receipts[row["experiment_id"]]
            row["counterfactual_map_role"] = (
                "random_counterfactual_prior_map"
                if row["ifusion_variant"] == "IF-A08"
                else (
                    "matched_hard_prior_map"
                    if row["ifusion_variant"] in ABLATIONS
                    else None
                )
            )
        write_json_atomic(output_root / "queue" / f"{lane}.json", queue)

    loads = {
        lane: sum(int(row["estimated_seconds"]) for row in queue)
        for lane, queue in assignments.items()
    }
    external_sha = (
        sha256_file(args.external_manifest) if args.external_manifest else None
    )
    matrix_identity = [
        {
            "experiment_id": row["experiment_id"],
            "config_sha256": config_receipts[row["experiment_id"]][
                "effective_config_sha256"
            ],
            "lane": lane,
            "queue_index": row["queue_index"],
        }
        for lane, queue in sorted(assignments.items())
        for row in queue
    ]
    receipt = {
        "schema": "prta-cxr.ifusion-final-evidence-preparation.v1",
        "status": "PASS_IFUSION_CORE_MATRIX_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "repository_commit": resolve_source_commit(repo_root),
        "base_main_commit": BASE_MAIN_COMMIT,
        "seed_set": list(SEEDS),
        "input_sha256": input_sha256,
        "parent_config_sha256": {
            str(value["seed"]): sha256_file(path)
            for value, path in zip(parent_values, args.v2_config, strict=True)
        },
        "random_counterfactual_prior_map_sha256": sha256_file(random_map_path),
        "external_manifest_sha256": external_sha,
        "external_manifest_status": (
            "FROZEN" if external_sha else "PENDING_NOT_REQUIRED_FOR_CORE_TRAIN_DEV"
        ),
        "experiment_matrix_sha256": canonical_sha256(matrix_identity),
        "matrix": matrix_identity,
        "lane_load_estimated_seconds": loads,
        "estimated_imbalance_seconds": max(loads.values()) - min(loads.values()),
        "duration_model": {
            "a800_v2_seconds_per_epoch": 1694,
            "rtx3090_to_a800_multiplier": 1.22,
            "source": "Wave045 V2 terminal receipt timestamps, seeds17/28/43",
        },
        "training_cell_count": len(configs),
        "training_started": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(output_root / "preparation_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
