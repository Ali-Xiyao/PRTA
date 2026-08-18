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
from prta_cxr.ifusion_matrix import validate_v2_parents
from prta_cxr.provenance import resolve_source_commit

SEEDS = (17, 28, 43)
FRACTIONS = (0.10, 0.25, 0.50, 0.75)
NOISE_RATES = (0.05, 0.10, 0.20)
NOISE_FAMILIES = ("symmetric", "plausible")
FINAL_MAINLINE = "Slim-S1"
PHASE20_PROTOCOL = "full-train-official-dev-slim-s1-confirmation-v1"

LANES: dict[str, dict[str, Any]] = {
    "a800_3066": {
        "host": "server",
        "hardware_class": "A800-80GB",
        "runtime_multiplier": 1.0,
    },
    "a800_9929": {
        "host": "server",
        "hardware_class": "A800-80GB",
        "runtime_multiplier": 1.0,
    },
    "rtx3090_0": {
        "host": "local",
        "hardware_class": "RTX3090-24GB",
        "runtime_multiplier": 1.22,
    },
    "rtx3090_1": {
        "host": "local",
        "hardware_class": "RTX3090-24GB",
        "runtime_multiplier": 1.22,
    },
}

LOSS_VARIANTS = {
    "NOSTATE": "without_state_anchor",
    "NOCMCP": "without_matched_hard_cmcp",
    "NOODC": "without_opposite_direction_cost",
}
STRUCTURAL_VARIANTS = {
    "NOFINDING": "without_finding_conditioning",
    "NOALIGN": "without_cross_time_alignment",
    "NORELATION": "without_temporal_relation_residual",
}
FUSION_VARIANTS = {
    "F01": "early_concat",
    "F02": "symmetric_cross_attention",
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


def _explicit_core_defaults(config: dict[str, Any]) -> None:
    components = config["model"]["components"]
    components.setdefault("unaligned_prior_mode", "conditioned")
    components.setdefault("temporal_relation_residual", True)


def _mainline_base(
    parent: Mapping[str, Any], *, experiment_id: str, seed: int
) -> dict[str, Any]:
    config = deepcopy(dict(parent))
    config["experiment_id"] = experiment_id
    config["seed"] = seed
    config["prta_v2_variant"] = FINAL_MAINLINE
    config["development_axis"] = PHASE20_PROTOCOL
    config["phase20_protocol"] = PHASE20_PROTOCOL
    config["phase20_parent_config_sha256"] = canonical_sha256(parent)
    config["final_mainline"] = FINAL_MAINLINE
    _explicit_core_defaults(config)
    components = config["model"]["components"]
    components["matched_hard_cmcp"] = True
    weights = config["loss_weights"]
    weights["direction_margin"] = 0.0
    weights["prototype_alignment"] = 0.0
    weights["state"] = 0.025
    weights["opposite_direction_cost"] = 0.05
    weights["cmcp"] = 0.01
    config["cmcp"]["matching"] = "offline_hard_v1"
    return config


def _disable_cmcp(config: dict[str, Any]) -> None:
    config["model"]["components"]["matched_hard_cmcp"] = False
    config["loss_weights"]["cmcp"] = 0.0
    config["cmcp"]["matching"] = "in_batch_roll_v1"


def _source_tags(sources: Sequence[str]) -> dict[str, str]:
    if len(sources) != 2 or len(set(sources)) != 2:
        raise ValueError("Phase20 source-held program requires two distinct sources")
    result: dict[str, str] = {}
    for source in sources:
        lowered = source.lower()
        if "mimic" in lowered:
            tag = "MIMIC"
        elif "chex" in lowered:
            tag = "CHEX"
        else:
            raise ValueError(f"unsupported Phase20 source identity: {source}")
        if tag in result:
            raise ValueError("Phase20 sources collapse to the same source tag")
        result[tag] = source
    if set(result) != {"MIMIC", "CHEX"}:
        raise ValueError("Phase20 requires MIMIC and CHEX source identities")
    return result


def build_phase20_configs(
    parents: Mapping[int, Mapping[str, Any]], sources: Sequence[str]
) -> dict[str, dict[str, Any]]:
    validate_v2_parents(parents)
    source_by_tag = _source_tags(sources)
    configs: dict[str, dict[str, Any]] = {}
    for seed in SEEDS:
        final_id = f"P20-FINAL-S1-S{seed}"
        final = _mainline_base(parents[seed], experiment_id=final_id, seed=seed)
        final["phase20_axis"] = "final_mainline_confirmation"
        final["phase20_role"] = "confirmatory_not_selective"
        configs[final_id] = final

        for tag, role in LOSS_VARIANTS.items():
            experiment_id = f"P20-ABL-{tag}-S{seed}"
            config = _mainline_base(
                parents[seed], experiment_id=experiment_id, seed=seed
            )
            config["phase20_axis"] = "exact_loss_ablation"
            config["phase20_role"] = role
            if tag == "NOSTATE":
                config["loss_weights"]["state"] = 0.0
            elif tag == "NOCMCP":
                _disable_cmcp(config)
            elif tag == "NOODC":
                config["loss_weights"]["opposite_direction_cost"] = 0.0
            configs[experiment_id] = config

        for tag, role in STRUCTURAL_VARIANTS.items():
            experiment_id = f"P20-STRUCT-{tag}-S{seed}"
            config = _mainline_base(
                parents[seed], experiment_id=experiment_id, seed=seed
            )
            config["phase20_axis"] = "exact_structural_ablation"
            config["phase20_role"] = role
            components = config["model"]["components"]
            if tag == "NOFINDING":
                components["finding_conditioning"] = False
            elif tag == "NOALIGN":
                components["cross_time_alignment"] = False
                components["unaligned_prior_mode"] = "raw"
            elif tag == "NORELATION":
                components["temporal_relation_residual"] = False
            configs[experiment_id] = config

        for tag, family in FUSION_VARIANTS.items():
            experiment_id = f"P20-{tag}-DMW0-S{seed}"
            config = _mainline_base(
                parents[seed], experiment_id=experiment_id, seed=seed
            )
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
            config["loss_weights"]["direction_margin"] = 0.0
            config["loss_weights"]["opposite_direction_cost"] = 0.05
            config["phase20_axis"] = "dmw0_fusion_comparator"
            config["phase20_role"] = f"IF-{tag} DMW-off fairness comparator"
            configs[experiment_id] = config

        for source_tag, train_source in source_by_tag.items():
            experiment_id = f"P20-SOURCE-S1CORE-{source_tag}-S{seed}"
            config = _mainline_base(
                parents[seed], experiment_id=experiment_id, seed=seed
            )
            _disable_cmcp(config)
            config["data"].update(
                {
                    "train_fraction": 1.0,
                    "train_sources": [train_source],
                    "dev_sources": [train_source],
                }
            )
            config["phase20_axis"] = "source_held_out"
            config["phase20_role"] = "confirmatory_s1_core_no_cmcp"
            config["source_held_out_protocol"] = "s1_core_no_cmcp_v1"
            config["source_held_out_target"] = next(
                value for value in source_by_tag.values() if value != train_source
            )
            configs[experiment_id] = config

        for fraction in FRACTIONS:
            fraction_tag = f"F{int(fraction * 100):02d}"
            experiment_id = f"P20-SCALE-{fraction_tag}-S{seed}"
            config = _mainline_base(
                parents[seed], experiment_id=experiment_id, seed=seed
            )
            config["data"]["train_fraction"] = fraction
            config["phase20_axis"] = "data_scaling"
            config["phase20_role"] = "final_s1_scaling"
            configs[experiment_id] = config

        for family in NOISE_FAMILIES:
            for rate in NOISE_RATES:
                experiment_id = (
                    f"P20-NOISE-{family.upper()}-{int(rate * 100):02d}-S{seed}"
                )
                config = _mainline_base(
                    parents[seed], experiment_id=experiment_id, seed=seed
                )
                config["data"]["train_fraction"] = 1.0
                config["data"]["label_noise"] = {
                    "rate": rate,
                    "family": family,
                    "salt": (
                        "prta-cxr-phase20-s1-label-noise-"
                        f"{family}-{int(rate * 100):02d}-v1"
                    ),
                }
                config["phase20_axis"] = "label_noise"
                config["phase20_role"] = "final_s1_synthetic_label_noise"
                configs[experiment_id] = config
    validate_phase20_configs(configs, sources=sources)
    return configs


def validate_phase20_configs(
    configs: Mapping[str, Mapping[str, Any]], *, sources: Sequence[str]
) -> None:
    if len(configs) != 63:
        raise ValueError("Phase20 must contain exactly 63 new training cells")
    if len(set(configs)) != 63:
        raise ValueError("Phase20 experiment IDs are not unique")
    source_values = set(sources)
    counts: dict[str, int] = {}
    for experiment_id, raw in configs.items():
        config = dict(raw)
        if config.get("experiment_id") != experiment_id:
            raise ValueError("Phase20 experiment identity drift")
        if int(config.get("seed", -1)) not in SEEDS:
            raise ValueError("Phase20 seed drift")
        if config.get("final_mainline") != FINAL_MAINLINE:
            raise ValueError("Phase20 final-mainline lock drift")
        axis = str(config.get("phase20_axis", ""))
        counts[axis] = counts.get(axis, 0) + 1
        model = dict(config["model"])
        weights = dict(config["loss_weights"])
        if model.get("adapter_scope") != "tail8":
            raise ValueError("Phase20 adapter scope drift")
        if model.get("native_head") != "H0":
            raise ValueError("Phase20 native head drift")
        if int(model.get("adapter_rank", -1)) != 32:
            raise ValueError("Phase20 adapter rank drift")
        if float(weights.get("direction_margin", -1.0)) != 0.0:
            raise ValueError("Phase20 DMW must stay disabled")
        if float(weights.get("prototype_alignment", -1.0)) != 0.0:
            raise ValueError("Phase20 standalone Prototype CE must stay disabled")
        if axis == "dmw0_fusion_comparator":
            if model.get("family") not in set(FUSION_VARIANTS.values()):
                raise ValueError("Phase20 fusion family drift")
            if float(weights.get("opposite_direction_cost", -1.0)) != 0.05:
                raise ValueError("Phase20 fusion ODC mismatch")
            continue
        if model.get("family") != "prta":
            raise ValueError("Phase20 PRTA family drift")
        components = dict(model.get("components", {}))
        role = str(config.get("phase20_role", ""))
        expected_finding = role != "without_finding_conditioning"
        if bool(components.get("finding_conditioning")) is not expected_finding:
            raise ValueError("Phase20 finding-conditioning contract drift")
        expected_alignment = role != "without_cross_time_alignment"
        if bool(components.get("cross_time_alignment")) is not expected_alignment:
            raise ValueError("Phase20 cross-time-alignment contract drift")
        expected_relation = role != "without_temporal_relation_residual"
        if bool(components.get("temporal_relation_residual")) is not expected_relation:
            raise ValueError("Phase20 temporal-relation-residual contract drift")
        if role == "without_cross_time_alignment":
            if components.get("unaligned_prior_mode") != "raw":
                raise ValueError("Phase20 NOALIGN must use raw PRIOR")
        elif components.get("unaligned_prior_mode") != "conditioned":
            raise ValueError("Phase20 aligned variants must retain conditioned PRIOR")
        no_cmcp = axis == "source_held_out" or role == "without_matched_hard_cmcp"
        if bool(components.get("matched_hard_cmcp")) is no_cmcp:
            raise ValueError("Phase20 CMCP component drift")
        expected_cmcp = 0.0 if no_cmcp else 0.01
        if float(weights.get("cmcp", -1.0)) != expected_cmcp:
            raise ValueError("Phase20 CMCP weight drift")
        expected_state = 0.0 if role == "without_state_anchor" else 0.025
        if float(weights.get("state", -1.0)) != expected_state:
            raise ValueError("Phase20 state weight drift")
        expected_odc = 0.0 if role == "without_opposite_direction_cost" else 0.05
        if float(weights.get("opposite_direction_cost", -1.0)) != expected_odc:
            raise ValueError("Phase20 ODC weight drift")
        if axis == "source_held_out":
            data = dict(config["data"])
            train_sources = set(data.get("train_sources", []))
            dev_sources = set(data.get("dev_sources", []))
            if len(train_sources) != 1 or train_sources != dev_sources:
                raise ValueError("Phase20 source-held source roster drift")
            if train_sources - source_values:
                raise ValueError("Phase20 source-held source is unknown")
            if config.get("source_held_out_target") in train_sources:
                raise ValueError("Phase20 source-held target leaked into Train")
    expected_counts = {
        "final_mainline_confirmation": 3,
        "exact_loss_ablation": 9,
        "exact_structural_ablation": 9,
        "dmw0_fusion_comparator": 6,
        "source_held_out": 6,
        "data_scaling": 12,
        "label_noise": 18,
    }
    if counts != expected_counts:
        raise ValueError(f"Phase20 axis coverage drift: {counts}")


_REUSE_METADATA = {
    "experiment_id",
    "seed",
    "development_axis",
    "ifusion_variant",
    "slim_arm",
    "slim_factors",
    "phase20_protocol",
    "phase20_parent_config_sha256",
    "final_mainline",
    "phase20_axis",
    "phase20_role",
}


def normalized_s0_semantics(config: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(config))
    for key in _REUSE_METADATA:
        value.pop(key, None)
    components = value["model"]["components"]
    components.setdefault("unaligned_prior_mode", "conditioned")
    components.setdefault("temporal_relation_residual", True)
    return value


def build_reuse_audit(
    parents: Mapping[int, Mapping[str, Any]],
    *,
    a10_configs: Mapping[int, Mapping[str, Any]],
    a10_receipt_evidence: Mapping[str, Any],
    expected_input_sha256: Mapping[str, str],
    tila8_configs: Mapping[int, Mapping[str, Any]],
    f01_configs: Mapping[int, Mapping[str, Any]],
    f02_configs: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    validate_v2_parents(parents)
    for label, values in {
        "A10": a10_configs,
        "TILA8": tila8_configs,
        "F01": f01_configs,
        "F02": f02_configs,
    }.items():
        if set(values) != set(SEEDS):
            raise ValueError(f"Phase20 {label} reuse audit requires all three seeds")
    a10_matches: dict[str, bool] = {}
    for seed in SEEDS:
        expected = deepcopy(dict(parents[seed]))
        expected["loss_weights"]["direction_margin"] = 0.0
        a10_matches[str(seed)] = normalized_s0_semantics(
            a10_configs[seed]
        ) == normalized_s0_semantics(expected)
    if not all(a10_matches.values()):
        raise ValueError("IF-A10 is not semantically equivalent to full-data S0")
    if (
        a10_receipt_evidence.get("schema") != "prta-cxr.phase20-a10-reuse-evidence.v1"
        or a10_receipt_evidence.get("status")
        != "PASS_PHASE20_A10_ALL_SEED_RECEIPT_AUDIT"
    ):
        raise ValueError("IF-A10 all-seed receipt evidence is not frozen PASS")
    evidence_by_seed = {
        int(value["seed"]): dict(value)
        for value in a10_receipt_evidence.get("seeds", [])
    }
    if set(evidence_by_seed) != set(SEEDS):
        raise ValueError("IF-A10 receipt evidence requires exactly three seeds")
    required_inputs = {
        "split_manifest",
        "cleaned_split_freeze",
        "cache_manifest",
        "text_cache",
        "matched_hard_prior_map",
        "weights",
        "label_quality_audit",
    }
    if set(expected_input_sha256) != required_inputs:
        raise ValueError("Phase20 input roles cannot certify IF-A10 reuse")
    a10_receipt_matches: dict[str, bool] = {}
    for seed in SEEDS:
        evidence = evidence_by_seed[seed]
        valid = (
            evidence.get("training_status") == "PASS_TRAINING_FINISHED"
            and evidence.get("formal_experiment") is True
            and evidence.get("internal_test_opened") is False
            and evidence.get("protected_outcomes_opened") is False
            and evidence.get("config_sha256") == canonical_sha256(a10_configs[seed])
            and dict(evidence.get("input_hashes", {})) == dict(expected_input_sha256)
            and len(str(evidence.get("training_receipt_file_sha256", ""))) == 64
        )
        a10_receipt_matches[str(seed)] = valid
    if not all(a10_receipt_matches.values()):
        raise ValueError("IF-A10 receipt/input evidence is not reusable full-data S0")
    for seed in SEEDS:
        tila = tila8_configs[seed]
        if int(tila.get("seed", -1)) != seed:
            raise ValueError("TILA8 seed drift")
        model = dict(tila["model"])
        weights = dict(tila["loss_weights"])
        if (
            model.get("family") != "tila"
            or model.get("adapter_scope") != "tail8"
            or model.get("native_head") != "H0"
            or float(weights.get("direction_margin", 0.0)) != 0.0
        ):
            raise ValueError("TILA8 is not a reusable DMW-inapplicable comparator")
        for label, configs, family in (
            ("F01", f01_configs, "early_concat"),
            ("F02", f02_configs, "symmetric_cross_attention"),
        ):
            config = configs[seed]
            if (
                config["model"].get("family") != family
                or float(config["loss_weights"].get("direction_margin", -1.0)) != 0.01
            ):
                raise ValueError(f"historical {label} DMW contract drift")
    return {
        "schema": "prta-cxr.phase20-reuse-audit.v1",
        "status": "PASS_PHASE20_CONFIG_REUSE_AUDIT",
        "created_at": _now(),
        "decisions": {
            "full_data_s0": {
                "source": "IF-A10",
                "decision": "REUSE_A10_AS_FULL_DATA_S0",
                "semantic_config_match_by_seed": a10_matches,
                "receipt_input_match_by_seed": a10_receipt_matches,
                "historical_source_commit": a10_receipt_evidence.get(
                    "historical_source_commit"
                ),
                "source_compatibility_audit": a10_receipt_evidence.get(
                    "source_compatibility_audit"
                ),
            },
            "tila_tail8": {
                "decision": "REUSE_DMW_NOT_APPLICABLE",
                "reason": "native TILA loss has no direction-margin field",
            },
            "if_f01": {"decision": "RETRAIN_DMW0", "historical_dmw": 0.01},
            "if_f02": {"decision": "RETRAIN_DMW0", "historical_dmw": 0.01},
            "current_only": {"decision": "REUSE_METHOD_INDEPENDENT"},
            "siamese": {"decision": "REUSE_METHOD_INDEPENDENT"},
        },
        "selection_performed": False,
        "external_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def _a800_estimate(config: Mapping[str, Any]) -> int:
    axis = str(config["phase20_axis"])
    if axis == "data_scaling":
        fraction = float(config["data"]["train_fraction"])
        return round(18_600 * max(0.35, fraction))
    if axis == "source_held_out":
        return 10_500
    if axis == "label_noise":
        return 18_600
    family = str(config["model"]["family"])
    if family == "early_concat":
        return 13_800
    if family == "symmetric_cross_attention":
        return 14_200
    if config.get("phase20_role") == "without_temporal_relation_residual":
        return 14_700
    return 15_250


def _map_key(config: Mapping[str, Any]) -> str | None:
    axis = str(config["phase20_axis"])
    if axis not in {"data_scaling", "label_noise"}:
        return None
    return str(config["experiment_id"]).rsplit("-S", 1)[0]


def _training_command(
    config: Mapping[str, Any], *, transformed_map: str | None
) -> list[str]:
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
        "PRTA-CXR Phase20 frozen Slim-S1 confirmation",
        "--output",
        f"{{output_root}}/runs/{experiment_id}",
        "--device",
        "{device}",
        "--formal",
    ]
    cmcp_weight = float(config["loss_weights"].get("cmcp", 0.0))
    matching = str(config.get("cmcp", {}).get("matching", "in_batch_roll_v1"))
    if cmcp_weight and matching == "offline_hard_v1":
        command.extend(
            [
                "--counterfactual-prior-map",
                transformed_map or "{matched_hard_prior_map}",
            ]
        )
    return command


def _priority(config: Mapping[str, Any]) -> int:
    axis = str(config["phase20_axis"])
    if axis == "final_mainline_confirmation":
        return 0
    if axis in {"exact_loss_ablation", "dmw0_fusion_comparator"}:
        return 10
    if axis == "exact_structural_ablation":
        return 20
    if axis == "source_held_out":
        return 30
    if axis == "data_scaling":
        return 40
    return 50


def allocate_phase20_jobs(
    configs: Mapping[str, Mapping[str, Any]],
    *,
    active_lanes: Sequence[str] = tuple(LANES),
) -> dict[str, list[dict[str, Any]]]:
    lanes = tuple(map(str, active_lanes))
    if not lanes or len(lanes) != len(set(lanes)):
        raise ValueError("Phase20 active lanes must be non-empty and unique")
    unknown_lanes = set(lanes) - set(LANES)
    if unknown_lanes:
        raise ValueError(f"unknown Phase20 active lanes: {sorted(unknown_lanes)}")
    queues: dict[str, list[dict[str, Any]]] = {lane: [] for lane in lanes}
    loads = {lane: 0 for lane in lanes}
    training_jobs = []
    for experiment_id, config in configs.items():
        training_jobs.append(
            {
                "job_id": f"train-{experiment_id}",
                "experiment_id": experiment_id,
                "group": str(config["phase20_axis"]),
                "base_estimated_seconds": _a800_estimate(config),
                "queue_priority": _priority(config),
                "map_key": _map_key(config),
                "dependencies": [],
            }
        )
    for job in sorted(
        training_jobs,
        key=lambda value: (
            int(value["queue_priority"]),
            -int(value["base_estimated_seconds"]),
            str(value["job_id"]),
        ),
    ):
        lane = min(
            lanes,
            key=lambda name: (
                loads[name]
                + round(
                    int(job["base_estimated_seconds"])
                    * float(LANES[name]["runtime_multiplier"])
                ),
                name,
            ),
        )
        estimate = round(
            int(job["base_estimated_seconds"])
            * float(LANES[lane]["runtime_multiplier"])
        )
        job.update(
            {
                "lane": lane,
                "host": LANES[lane]["host"],
                "hardware_class": LANES[lane]["hardware_class"],
                "estimated_seconds": estimate,
            }
        )
        queues[lane].append(job)
        loads[lane] += estimate

    map_consumers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for queue in queues.values():
        for job in queue:
            if job["map_key"] is not None:
                map_consumers.setdefault(
                    (str(job["host"]), str(job["map_key"])), []
                ).append(job)
    for (host, map_key), consumers in sorted(map_consumers.items()):
        host_lanes = [name for name in lanes if LANES[name]["host"] == host]
        representative = min((str(job["experiment_id"]) for job in consumers), key=str)
        config = configs[representative]
        fraction = float(config.get("data", {}).get("train_fraction", 1.0))
        base_estimate = max(300, round(1200 * fraction))
        lane = min(host_lanes, key=lambda name: (loads[name], name))
        estimate = round(base_estimate * float(LANES[lane]["runtime_multiplier"]))
        map_job_id = f"map-{host}-{map_key}"
        map_path = f"{{output_root}}/assets/maps/{map_key}.json"
        queues[lane].append(
            {
                "job_id": map_job_id,
                "group": "phase20_map",
                "lane": lane,
                "host": host,
                "hardware_class": LANES[lane]["hardware_class"],
                "estimated_seconds": estimate,
                "queue_priority": 5,
                "dependencies": [],
                "command": [
                    "{python}",
                    "{source}/scripts/100_build_phase16_map.py",
                    "--config",
                    f"{{runtime_root}}/configs/{representative}.json",
                    "--split-manifest",
                    "{split_manifest}",
                    "--cache-root",
                    "{cache_root}",
                    "--output",
                    map_path,
                    "--device",
                    "{device}",
                    "--formal",
                ],
                "expected_outputs": [map_path],
            }
        )
        loads[lane] += estimate
        for consumer in consumers:
            consumer["dependencies"] = [map_job_id]

    for _lane, queue in queues.items():
        for job in list(queue):
            if not str(job["job_id"]).startswith("train-"):
                continue
            config = configs[str(job["experiment_id"])]
            map_path = (
                f"{{output_root}}/assets/maps/{job['map_key']}.json"
                if job["map_key"] is not None
                else None
            )
            job["command"] = _training_command(config, transformed_map=map_path)
            experiment_id = str(job["experiment_id"])
            job["expected_outputs"] = [
                f"{{output_root}}/runs/{experiment_id}/training_receipt.json",
                f"{{output_root}}/runs/{experiment_id}/best.pt",
            ]
            if config["phase20_axis"] == "source_held_out":
                output = f"{{output_root}}/source_held_out/{experiment_id}"
                evaluation = {
                    "job_id": f"evaluate-{experiment_id}",
                    "group": "source_held_out_evaluation",
                    "lane": str(job["lane"]),
                    "host": job["host"],
                    "hardware_class": job["hardware_class"],
                    "estimated_seconds": round(
                        300 * float(LANES[str(job["lane"])]["runtime_multiplier"])
                    ),
                    "queue_priority": 60,
                    "dependencies": [str(job["job_id"])],
                    "command": [
                        "{python}",
                        "{source}/scripts/103_evaluate_source_held_out.py",
                        "--checkpoint",
                        f"{{output_root}}/runs/{experiment_id}/best.pt",
                        "--training-receipt",
                        f"{{output_root}}/runs/{experiment_id}/training_receipt.json",
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
                        "--target-source",
                        str(config["source_held_out_target"]),
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
                queue.append(evaluation)
                loads[lane] += int(evaluation["estimated_seconds"])

    by_id = {str(job["job_id"]): job for queue in queues.values() for job in queue}
    ranks: dict[str, int] = {}

    def rank(job_id: str) -> int:
        if job_id not in ranks:
            dependencies = [str(value) for value in by_id[job_id]["dependencies"]]
            ranks[job_id] = 0 if not dependencies else 1 + max(map(rank, dependencies))
        return ranks[job_id]

    for _lane, queue in queues.items():
        queue.sort(
            key=lambda job: (
                rank(str(job["job_id"])),
                int(job.get("queue_priority", 100)),
                -int(job["estimated_seconds"]),
                str(job["job_id"]),
            )
        )
        for index, job in enumerate(queue):
            job["queue_index"] = index
            job.pop("base_estimated_seconds", None)
            job.pop("map_key", None)
    identifiers = [str(job["job_id"]) for queue in queues.values() for job in queue]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Phase20 job IDs are not globally unique")
    return queues


def _load_by_seed(paths: Sequence[Path]) -> dict[int, dict[str, Any]]:
    values = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    result = {int(value["seed"]): value for value in values}
    if len(result) != len(values):
        raise ValueError("duplicate seed in Phase20 config inputs")
    return result


def prepare_phase20_program_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze a selected-lane non-external Slim-S1 confirmation program"
    )
    parser.add_argument("--v2-config", type=Path, nargs=3, required=True)
    parser.add_argument("--a10-config", type=Path, nargs=3, required=True)
    parser.add_argument("--a10-reuse-evidence", type=Path, required=True)
    parser.add_argument("--f01-config", type=Path, nargs=3, required=True)
    parser.add_argument("--f02-config", type=Path, nargs=3, required=True)
    parser.add_argument("--tila8-config", type=Path, nargs=3, required=True)
    parser.add_argument("--source", nargs=2, required=True)
    parser.add_argument(
        "--active-lane",
        nargs="+",
        choices=tuple(LANES),
        default=tuple(LANES),
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
            raise FileNotFoundError(f"Phase20 input missing: {role}")
    input_sha256 = {role: sha256_file(path) for role, path in input_paths.items()}
    read_counterfactual_prior_map(
        args.matched_hard_prior_map,
        expected_matching="offline_hard_v1",
        expected_split_manifest_sha256=input_sha256["split_manifest"],
        expected_cache_manifest_sha256=input_sha256["cache_manifest"],
        expected_cache_entry_block=4,
    )
    parents = _load_by_seed(args.v2_config)
    a10 = _load_by_seed(args.a10_config)
    f01 = _load_by_seed(args.f01_config)
    f02 = _load_by_seed(args.f02_config)
    tila8 = _load_by_seed(args.tila8_config)
    a10_receipt_evidence = json.loads(
        args.a10_reuse_evidence.read_text(encoding="utf-8")
    )
    configs = build_phase20_configs(parents, args.source)
    reuse_audit = build_reuse_audit(
        parents,
        a10_configs=a10,
        a10_receipt_evidence=a10_receipt_evidence,
        expected_input_sha256=input_sha256,
        tila8_configs=tila8,
        f01_configs=f01,
        f02_configs=f02,
    )
    queues = allocate_phase20_jobs(configs, active_lanes=args.active_lane)
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
        "status": "PASS_PHASE20_INPUTS_FROZEN",
        "input_sha256": input_sha256,
        "cleaned_split_platform_root_required": True,
        "external_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "input_manifest.json", input_manifest)
    _write_new_json(staging / "reuse_audit.json", reuse_audit)
    all_jobs = [job for queue in queues.values() for job in queue]
    registry = {
        "schema": "prta-cxr.phase20-job-registry.v1",
        "status": "PASS_PHASE20_NONEXTERNAL_REGISTRY_FROZEN",
        "training_cell_count": len(configs),
        "job_count": len(all_jobs),
        "jobs": all_jobs,
    }
    _write_new_json(staging / "job_registry.json", registry)
    queue_hashes = {}
    loads = {}
    training_counts = {}
    for lane, queue in queues.items():
        path = staging / "queue" / f"{lane}.json"
        _write_new_json(path, queue)
        queue_hashes[path.name] = sha256_file(path)
        loads[lane] = sum(int(job["estimated_seconds"]) for job in queue)
        training_counts[lane] = sum(
            str(job["job_id"]).startswith("train-") for job in queue
        )
    receipt = {
        "schema": "prta-cxr.phase20-program-preparation.v1",
        "status": "PASS_PHASE20_SLIM_S1_PROGRAM_FROZEN",
        "created_at": _now(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "protocol": PHASE20_PROTOCOL,
        "final_mainline": FINAL_MAINLINE,
        "method_lock": {
            "prototype_alignment": 0.0,
            "direction_margin": 0.0,
            "state": 0.025,
            "opposite_direction_cost": 0.05,
            "matched_hard_cmcp": 0.01,
            "selection_reopened": False,
        },
        "seeds": list(SEEDS),
        "source_names": list(args.source),
        "active_lanes": list(args.active_lane),
        "reserved_lanes": [lane for lane in LANES if lane not in args.active_lane],
        "training_cell_count": len(configs),
        "job_count": len(all_jobs),
        "axis_counts": {
            axis: sum(config["phase20_axis"] == axis for config in configs.values())
            for axis in sorted(
                {str(value["phase20_axis"]) for value in configs.values()}
            )
        },
        "config_hashes": config_hashes,
        "parent_config_file_sha256": {
            str(seed): sha256_file(path)
            for seed, path in zip(SEEDS, args.v2_config, strict=True)
        },
        "reuse_config_file_sha256": {
            label: {
                str(seed): sha256_file(path)
                for seed, path in zip(SEEDS, paths, strict=True)
            }
            for label, paths in {
                "IF-A10": args.a10_config,
                "IF-F01": args.f01_config,
                "IF-F02": args.f02_config,
                "TILA8": args.tila8_config,
            }.items()
        },
        "a10_reuse_evidence_sha256": sha256_file(args.a10_reuse_evidence),
        "input_manifest_sha256": sha256_file(staging / "input_manifest.json"),
        "reuse_audit_sha256": sha256_file(staging / "reuse_audit.json"),
        "registry_sha256": sha256_file(staging / "job_registry.json"),
        "queue_hashes": queue_hashes,
        "lane_load_estimated_seconds": loads,
        "lane_training_cell_count": training_counts,
        "estimated_imbalance_seconds": max(loads.values()) - min(loads.values()),
        "external_evaluation_included": False,
        "clinician_manual_work_included": False,
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "preparation_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
