from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

SEEDS = (17, 28, 43)

# The no-state and no-dual rows are supplied by the already-terminal Wave042
# paired mechanism gate. Every entry here must be trained under the repaired
# parent in the new Wave043 queue.
NEW_VARIANTS = (
    "full",
    "no_finding",
    "no_cross_time_alignment",
    "no_direction_margin",
    "no_opposite_direction_cost",
    "classification_only",
    "scope_no_tail",
    "scope_tail2",
    "scope_tail4",
    "scope_tail6",
    "scope_tail10",
)

SCOPE_CACHE_ENTRY_BLOCK = {
    "no_tail": 8,
    "tail2": 8,
    "tail4": 8,
    "tail6": 4,
    "tail8": 4,
    "tail10": 2,
}


def _validate_legacy_parent(parent: Mapping[str, Any]) -> None:
    model = dict(parent.get("model", {}))
    components = dict(model.get("components", {}))
    weights = dict(parent.get("loss_weights", {}))
    if model.get("family") != "prta":
        raise ValueError("repaired ablation parent must be PRTA")
    if model.get("native_head") != "H0":
        raise ValueError("repaired ablation source parent must use native_head=H0")
    if model.get("adapter_scope") != "tail8":
        raise ValueError("repaired ablation source parent must use tail8")
    for name in ("finding_conditioning", "cross_time_alignment", "dual_branch"):
        if not bool(components.get(name, False)):
            raise ValueError(f"repaired ablation source parent requires {name}=true")
    if float(weights.get("classification", 0.0)) != 1.0:
        raise ValueError("repaired ablation requires classification weight 1")
    if float(weights.get("state", -1.0)) != 0.025:
        raise ValueError("repaired ablation parent state weight drift")


def build_repaired_parent(parent: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the frozen legacy parent into the accepted repaired method."""
    _validate_legacy_parent(parent)
    config = deepcopy(dict(parent))
    model = dict(config["model"])
    components = dict(model["components"])
    weights = dict(config["loss_weights"])
    model["native_head"] = "H4"
    model["adapter_scope"] = "tail8"
    components["dual_branch"] = True
    components["branch_mode"] = "repaired_dual"
    components["bounded_state_anchor"] = True
    model["components"] = components
    weights["branch_decorrelation"] = 0.0
    config["model"] = model
    config["loss_weights"] = weights
    return config


def cache_entry_block(config: Mapping[str, Any]) -> int:
    scope = str(dict(config["model"])["adapter_scope"])
    try:
        return SCOPE_CACHE_ENTRY_BLOCK[scope]
    except KeyError as error:
        raise ValueError(f"unsupported repaired scope: {scope}") from error


def build_repaired_ablation_configs(
    parent: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Freeze all new repaired-method Train/Dev cells without outcome use."""
    base = build_repaired_parent(parent)
    configs: list[dict[str, Any]] = []
    for seed in SEEDS:
        for variant in NEW_VARIANTS:
            config = deepcopy(base)
            slug = variant.replace("_", "-").upper()
            config["experiment_id"] = f"W043-{slug}-S{seed}"
            config["development_axis"] = "repaired_full_ablation_v1"
            config["ablation_variant"] = variant
            config["seed"] = seed
            model = dict(config["model"])
            components = dict(model["components"])
            weights = dict(config["loss_weights"])
            if variant == "no_finding":
                components["finding_conditioning"] = False
            elif variant == "no_cross_time_alignment":
                components["cross_time_alignment"] = False
            elif variant == "no_direction_margin":
                weights["direction_margin"] = 0.0
            elif variant == "no_opposite_direction_cost":
                weights["opposite_direction_cost"] = 0.0
            elif variant == "classification_only":
                for name in (
                    "alignment",
                    "branch_decorrelation",
                    "cmcp",
                    "direction_margin",
                    "inversion",
                    "opposite_direction_cost",
                    "state",
                ):
                    weights[name] = 0.0
            elif variant.startswith("scope_"):
                model["adapter_scope"] = variant.removeprefix("scope_")
            elif variant != "full":
                raise AssertionError(f"unhandled repaired ablation variant: {variant}")
            model["components"] = components
            config["model"] = model
            config["loss_weights"] = weights
            config["cache_entry_block"] = cache_entry_block(config)
            configs.append(config)
    return configs
