from __future__ import annotations

from copy import deepcopy
from typing import Any

SEEDS = (17, 28, 43)
VARIANTS = ("V0", "V1", "V2", "V3", "V4", "V5")


def _base_config(parent: dict[str, Any], *, seed: int) -> dict[str, Any]:
    config = deepcopy(parent)
    config["experiment_id"] = f"W045-V0-S{seed}"
    config["seed"] = seed
    config["development_axis"] = "prta_v2_tail8_h0_v1"
    config["prta_v2_variant"] = "V0"
    config["cache_entry_block"] = 4
    model = config["model"]
    model["family"] = "prta"
    model["native_head"] = "H0"
    model["adapter_scope"] = "tail8"
    model["components"] = {
        "finding_conditioning": True,
        "cross_time_alignment": True,
        "dual_branch": True,
        "branch_mode": "legacy",
        "matched_hard_cmcp": False,
        "learned_relation_residual_scale": False,
        "relation_residual_initial_scale": 1e-3,
        "prior_reliability_gate": False,
        "selective_state_anchor": False,
        "selective_state_beta": 1.0,
    }
    weights = config["loss_weights"]
    weights.update(
        {
            "alignment": 0.0,
            "prototype_alignment": 0.0,
            "cmcp": 0.0,
            "branch_decorrelation": 0.0,
        }
    )
    config["prototype_alignment"] = {"temperature": 0.07}
    config["cmcp"] = {"margin": 0.2, "matching": "offline_hard_v1"}
    return config


def build_prta_v2_configs(parent: dict[str, Any]) -> list[dict[str, Any]]:
    configs = []
    for seed in SEEDS:
        for variant_index, variant in enumerate(VARIANTS):
            config = _base_config(parent, seed=seed)
            config["experiment_id"] = f"W045-{variant}-S{seed}"
            config["prta_v2_variant"] = variant
            weights = config["loss_weights"]
            components = config["model"]["components"]
            if variant_index >= 1:
                weights["prototype_alignment"] = 0.01
            if variant_index >= 2:
                weights["cmcp"] = 0.01
                components["matched_hard_cmcp"] = True
            if variant_index >= 3:
                components["learned_relation_residual_scale"] = True
            if variant_index >= 4:
                components["prior_reliability_gate"] = True
            if variant_index >= 5:
                components["selective_state_anchor"] = True
            configs.append(config)
    validate_prta_v2_configs(configs)
    return configs


def validate_prta_v2_configs(configs: list[dict[str, Any]]) -> None:
    expected_ids = {
        f"W045-{variant}-S{seed}" for seed in SEEDS for variant in VARIANTS
    }
    actual_ids = {str(config.get("experiment_id")) for config in configs}
    if len(configs) != len(expected_ids) or actual_ids != expected_ids:
        raise ValueError("Wave045 must contain the exact 18-cell matrix")
    for config in configs:
        variant = str(config["prta_v2_variant"])
        index = VARIANTS.index(variant)
        model = config["model"]
        components = model["components"]
        weights = config["loss_weights"]
        if model["native_head"] != "H0" or model["adapter_scope"] != "tail8":
            raise ValueError("Wave045 requires the frozen Tail8/H0 mainline")
        if int(config["cache_entry_block"]) != 4:
            raise ValueError("Wave045 Tail8 requires the Block-4 cache")
        if float(weights["alignment"]) != 0.0:
            raise ValueError("Wave045 disables batch InfoNCE alignment")
        if (float(weights["prototype_alignment"]) > 0) != (index >= 1):
            raise ValueError("Wave045 prototype-alignment progression drift")
        if (float(weights["cmcp"]) > 0) != (index >= 2):
            raise ValueError("Wave045 CMCP progression drift")
        checks = (
            ("matched_hard_cmcp", 2),
            ("learned_relation_residual_scale", 3),
            ("prior_reliability_gate", 4),
            ("selective_state_anchor", 5),
        )
        for name, threshold in checks:
            if bool(components[name]) != (index >= threshold):
                raise ValueError(f"Wave045 component progression drift: {name}")
