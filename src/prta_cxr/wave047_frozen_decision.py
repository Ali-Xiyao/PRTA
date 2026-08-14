from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file


class FrozenDecisionError(RuntimeError):
    """Raised when a frozen Wave047 closeout input is not auditable."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FrozenDecisionError(f"expected JSON object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FrozenDecisionError(message)


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _zero_protected(record: Mapping[str, Any], *, label: str) -> None:
    _require(
        record.get("internal_test_opened") is False, f"{label} opened Internal-test"
    )
    _require(record.get("gold_opened") in (None, False), f"{label} opened Gold")
    _require(
        record.get("protected_outcome_read_count", 0) == 0,
        f"{label} has protected reads",
    )


def _metric(value: Mapping[str, Any], *, label: str) -> dict[str, float]:
    interval = value.get("interval")
    _require(isinstance(interval, dict), f"missing interval: {label}")
    return {
        "point": float(value["point"]),
        "ci95_lower": float(interval["lower"]),
        "ci95_upper": float(interval["upper"]),
        "empirical_two_sided_p": float(value["empirical_two_sided_p"]),
    }


def _diagnostic_evidence(
    *, aggregate: Mapping[str, Any], diagnostics_root: Path
) -> dict[str, Any]:
    expected = {
        (str(row["variant"]), int(row["seed"])): str(row["receipt_sha256"])
        for row in aggregate["diagnostics"]
    }
    _require(len(expected) == 9, "Wave047 diagnostic receipt count drift")
    rows: list[dict[str, Any]] = []
    for (variant, seed), expected_hash in sorted(expected.items()):
        receipt_path = (
            diagnostics_root
            / f"W047D-{variant}-S{seed}"
            / "candidate_prior_diagnostic_receipt.json"
        )
        _require(
            receipt_path.is_file(), f"missing diagnostic receipt: {variant}/{seed}"
        )
        _require(
            sha256_file(receipt_path) == expected_hash,
            f"diagnostic receipt hash drift: {variant}/{seed}",
        )
        receipt = _read_json(receipt_path)
        _require(
            receipt.get("status")
            == "PASS_WAVE047_CANDIDATE_TRAIN_DEV_PRIOR_DIAGNOSTIC",
            f"diagnostic non-PASS: {variant}/{seed}",
        )
        _zero_protected(receipt, label=f"diagnostic {variant}/{seed}")
        interventions = receipt.get("interventions")
        _require(
            isinstance(interventions, dict), f"missing interventions: {variant}/{seed}"
        )
        for intervention in ("matched_hard", "null", "reversed"):
            comparison = interventions[intervention]["comparison_to_true"]
            rows.append(
                {
                    "variant": variant,
                    "seed": seed,
                    "intervention": intervention,
                    "true_minus_intervention_macro_f1": float(
                        comparison["true_minus_intervention_macro_f1"]
                    ),
                    "oder_increase_vs_true": float(
                        comparison["opposite_direction_error_rate_delta"]
                    ),
                    "prediction_flip_rate": float(comparison["prediction_flip_rate"]),
                }
            )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["variant"], row["intervention"])].append(row)
    summary = {
        f"{variant}_{intervention}": {
            "n": len(group),
            "true_minus_intervention_macro_f1_mean": mean(
                row["true_minus_intervention_macro_f1"] for row in group
            ),
            "oder_increase_vs_true_mean": mean(
                row["oder_increase_vs_true"] for row in group
            ),
            "prediction_flip_rate_mean": mean(
                row["prediction_flip_rate"] for row in group
            ),
        }
        for (variant, intervention), group in sorted(grouped.items())
    }
    v2_directional = [
        row
        for row in rows
        if row["variant"] == "V2"
        and row["intervention"] in {"matched_hard", "reversed"}
    ]
    _require(len(v2_directional) == 6, "V2 adverse-prior diagnostic count drift")
    _require(
        all(
            row["true_minus_intervention_macro_f1"] > 0
            and row["oder_increase_vs_true"] > 0
            for row in v2_directional
        ),
        "V2 adverse-prior diagnostics have a contradictory direction",
    )
    return {
        "receipt_hashes_verified": len(expected),
        "per_variant_intervention": summary,
        "v2_adverse_prior_directionality_passed": True,
        "interpretation": (
            "Matched-hard and reversed PRIOR lower V2 Macro-F1 and raise ODER in "
            "every seed, as they do for the reference variants. This is an "
            "intervention-response consistency check, not a claim that the "
            "indirectly supervised PRIOR mechanism is causally proven reliable."
        ),
    }


def apply_wave047_frozen_decision_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the preregistered Wave047 V2/V1/V0 Train/Dev decision rule"
    )
    parser.add_argument("--closeout-receipt", type=Path, required=True)
    parser.add_argument("--candidate-aggregate", type=Path, required=True)
    parser.add_argument("--diagnostics-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output_root.exists():
        parser.error("--output-root must be a new immutable directory")

    closeout = _read_json(args.closeout_receipt)
    _require(
        closeout.get("status")
        == "PASS_WAVE046_WAVE047_CLOSEOUT_AGGREGATED_NO_SELECTION",
        "closeout receipt is not PASS",
    )
    _zero_protected(closeout, label="Wave046/Wave047 closeout")
    aggregate = _read_json(args.candidate_aggregate)
    _require(
        aggregate.get("status")
        == "PASS_WAVE047_CANDIDATE_CONFIRMATION_AGGREGATED_NO_SELECTION",
        "candidate aggregate is not PASS",
    )
    _zero_protected(aggregate, label="Wave047 candidate aggregate")
    _require(
        closeout.get("wave047_aggregate_sha256")
        == sha256_file(args.candidate_aggregate),
        "candidate aggregate hash drift from closeout receipt",
    )

    contrast = aggregate["bootstrap"]["result"]["contrasts"]["V2_minus_V0"]
    scopes = contrast["scopes"]
    seed_metrics = {
        f"seed{seed}": _metric(
            scopes[f"seed{seed}"]["macro_f1"], label=f"V2-V0 Macro-F1 seed {seed}"
        )
        for seed in (17, 28, 43)
    }
    positive_seed_count = sum(metric["point"] > 0 for metric in seed_metrics.values())
    mean_scope = scopes["mean_across_seeds"]
    macro_f1 = _metric(mean_scope["macro_f1"], label="V2-V0 Macro-F1 mean")
    balanced_accuracy = _metric(
        mean_scope["balanced_accuracy"], label="V2-V0 balanced accuracy mean"
    )
    oder = _metric(mean_scope["opposite_direction_error_rate"], label="V2-V0 ODER mean")
    class_f1 = {
        label.removeprefix("f1:"): _metric(value, label=f"V2-V0 {label}")
        for label, value in mean_scope.items()
        if label.startswith("f1:")
    }
    _require(len(class_f1) == 5, "V2-V0 class F1 count drift")

    gates = {
        "positive_macro_f1_in_at_least_two_of_three_seeds": positive_seed_count >= 2,
        "paired_bootstrap_has_no_clear_macro_f1_harm": macro_f1["ci95_upper"] >= 0,
        "paired_bootstrap_has_no_clear_balanced_accuracy_harm": (
            balanced_accuracy["ci95_upper"] >= 0
        ),
        "oder_has_no_clear_worsening": oder["ci95_lower"] <= 0,
        "f1_gain_spans_at_least_two_classes": sum(
            value["point"] > 0 for value in class_f1.values()
        )
        >= 2,
    }
    _require(all(gates.values()), "V2 did not pass the frozen confirmation gates")
    diagnostics = _diagnostic_evidence(
        aggregate=aggregate, diagnostics_root=args.diagnostics_root
    )
    gates["prior_diagnostics_have_no_contradictory_v2_response"] = True

    decision = {
        "schema": "prta-cxr.wave047-frozen-v2-decision.v1",
        "status": "PASS_WAVE047_V2_FROZEN_BY_PREREGISTERED_TRAIN_DEV_RULE",
        "created_at": datetime.now(UTC).isoformat(),
        "inputs": {
            "closeout_receipt_sha256": sha256_file(args.closeout_receipt),
            "candidate_aggregate_sha256": sha256_file(args.candidate_aggregate),
            "bootstrap_result_sha256": aggregate["bootstrap"]["result_sha256"],
        },
        "frozen_method_identity": {
            "main_method": "V2",
            "main_method_status": (
                "FROZEN_MAIN_METHOD_TRAIN_DEV_CONFIRMED_"
                "PENDING_INDEPENDENT_UNTOUCHED_TEST"
            ),
            "fallback": "V1",
            "core_reference": "V0",
            "rejected_variants": ["V3", "V4", "V5"],
            "h4_status": "APPENDIX_ONLY_NOT_COMBINED_WITH_V2",
        },
        "preregistered_rule_evidence": {
            "v2_minus_v0_macro_f1_by_seed": seed_metrics,
            "v2_minus_v0_mean_macro_f1": macro_f1,
            "v2_minus_v0_mean_balanced_accuracy": balanced_accuracy,
            "v2_minus_v0_mean_oder": oder,
            "v2_minus_v0_class_f1": class_f1,
            "diagnostics": diagnostics,
            "gates": gates,
        },
        "interpretation": (
            "V2 satisfies the frozen Train/Dev confirmation rule: positive Macro-F1 "
            "in two of three seeds, no clear paired-bootstrap harm, broad positive "
            "class-F1 point estimates, no clear ODER worsening, and no contradictory "
            "response to adverse PRIOR interventions. This is a predefined identity "
            "freeze, not post-hoc outcome selection or protected evaluation."
        ),
        "selection_performed": False,
        "winner_selected": False,
        "pre_registered_decision_rule_applied": True,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(args.output_root / "wave047_frozen_decision.json", decision)
    receipt = {
        "schema": "prta-cxr.wave047-frozen-v2-decision-receipt.v1",
        "status": "PASS_WAVE047_V2_FROZEN_BY_PREREGISTERED_TRAIN_DEV_RULE",
        "created_at": datetime.now(UTC).isoformat(),
        "decision_sha256": sha256_file(
            args.output_root / "wave047_frozen_decision.json"
        ),
        "main_method": "V2",
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(args.output_root / "completion_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
