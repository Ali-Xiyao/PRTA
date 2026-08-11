from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from statistics import fmean
from typing import Any

SEEDS = (17, 28, 43)
VARIANTS = ("transition_only", "repaired_dual")
BRANCH_DECORRELATION_WEIGHT = 0.01
PRACTICAL_MACRO_F1_MARGIN = 0.002


def _validate_parent(parent: Mapping[str, Any]) -> None:
    model = dict(parent.get("model", {}))
    components = dict(model.get("components", {}))
    weights = dict(parent.get("loss_weights", {}))
    if model.get("family") != "prta":
        raise ValueError("dual-branch repair parent must be PRTA")
    if model.get("native_head") != "H0":
        raise ValueError("dual-branch repair parent must use native_head=H0")
    if not bool(components.get("finding_conditioning", False)):
        raise ValueError("dual-branch repair requires finding conditioning")
    if not bool(components.get("cross_time_alignment", False)):
        raise ValueError("dual-branch repair requires cross-time alignment")
    if not bool(components.get("dual_branch", False)):
        raise ValueError("dual-branch repair parent must retain dual_branch=true")
    if float(weights.get("classification", 0.0)) != 1.0:
        raise ValueError("dual-branch repair requires classification weight 1")
    if float(weights.get("state", -1.0)) != 0.025:
        raise ValueError("dual-branch repair parent state weight drift")


def build_dual_branch_repair_configs(
    parent: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Freeze a paired three-seed mechanism gate without outcome adaptation."""
    _validate_parent(parent)
    configs: list[dict[str, Any]] = []
    for seed in SEEDS:
        for variant in VARIANTS:
            config = deepcopy(dict(parent))
            config["experiment_id"] = (
                f"W042-DUAL-{variant.replace('_', '-').upper()}-S{seed}"
            )
            config["development_axis"] = "dual_branch_repair_v1"
            config["repair_variant"] = variant
            config["seed"] = seed
            model = dict(config["model"])
            model["adapter_scope"] = "tail8"
            components = dict(model["components"])
            weights = dict(config["loss_weights"])
            if variant == "transition_only":
                model["native_head"] = "H0"
                components["dual_branch"] = False
                components["branch_mode"] = "transition_only"
                components["bounded_state_anchor"] = False
                weights["state"] = 0.0
                weights["branch_decorrelation"] = 0.0
            else:
                model["native_head"] = "H4"
                components["dual_branch"] = True
                components["branch_mode"] = "repaired_dual"
                components["bounded_state_anchor"] = True
                weights["branch_decorrelation"] = BRANCH_DECORRELATION_WEIGHT
            model["components"] = components
            config["model"] = model
            config["loss_weights"] = weights
            configs.append(config)
    return configs


def evaluate_dual_branch_gate(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply the frozen contribution rule after every paired seed is terminal."""
    expected = {(variant, seed) for seed in SEEDS for variant in VARIANTS}
    indexed: dict[tuple[str, int], float] = {}
    for row in rows:
        key = (str(row["repair_variant"]), int(row["seed"]))
        if key in indexed:
            raise ValueError(f"duplicate dual-branch repair result: {key}")
        indexed[key] = float(row["macro_f1"])
    if set(indexed) != expected:
        raise ValueError("dual-branch repair results are incomplete or unexpected")

    control = [indexed[("transition_only", seed)] for seed in SEEDS]
    repaired = [indexed[("repaired_dual", seed)] for seed in SEEDS]
    deltas = [right - left for left, right in zip(control, repaired, strict=True)]
    mean_delta = fmean(deltas)
    wins = sum(delta > 0 for delta in deltas)
    passed = mean_delta >= PRACTICAL_MACRO_F1_MARGIN and wins >= 2
    return {
        "status": (
            "PASS_DUAL_BRANCH_REPAIR_CONTRIBUTES"
            if passed
            else "HOLD_DUAL_BRANCH_REPAIR_NO_STABLE_CONTRIBUTION"
        ),
        "selection_performed": False,
        "seeds": list(SEEDS),
        "transition_only_mean_macro_f1": fmean(control),
        "repaired_dual_mean_macro_f1": fmean(repaired),
        "paired_macro_f1_deltas": deltas,
        "mean_macro_f1_delta": mean_delta,
        "repaired_seed_wins": wins,
        "required_mean_macro_f1_delta": PRACTICAL_MACRO_F1_MARGIN,
        "required_seed_wins": 2,
    }
