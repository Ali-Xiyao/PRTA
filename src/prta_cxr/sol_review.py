from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from prta_cxr.contracts import (
    PROGRESSION_LABELS,
    ContractError,
    canonical_sha256,
    validate_sample,
)
from prta_cxr.independent_silver import validate_independent_ai_batch

REVIEW_LABELS = (*PROGRESSION_LABELS, "Unclear")


def _wilson(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z**2 / (4 * total**2)
        )
        / denominator
    )
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _kappa(rows: Sequence[Mapping[str, Any]]) -> float | None:
    total = len(rows)
    if not total:
        return None
    left = Counter(str(row["luna_label"]) for row in rows)
    right = Counter(str(row["sol_label"]) for row in rows)
    observed = sum(row["luna_label"] == row["sol_label"] for row in rows) / total
    expected = sum(left[label] * right[label] for label in REVIEW_LABELS) / total**2
    if expected == 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def _agreement(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    exact = sum(row["luna_label"] == row["sol_label"] for row in rows)
    decisive = [
        row
        for row in rows
        if row["luna_label"] != "Unclear" and row["sol_label"] != "Unclear"
    ]
    decisive_exact = sum(
        row["luna_label"] == row["sol_label"] for row in decisive
    )
    return {
        "rows": total,
        "six_class_exact": exact,
        "six_class_agreement": exact / total if total else None,
        "six_class_wilson_95": _wilson(exact, total),
        "six_class_cohen_kappa": _kappa(rows),
        "both_decisive_rows": len(decisive),
        "both_decisive_coverage": len(decisive) / total if total else None,
        "five_class_exact": decisive_exact,
        "five_class_agreement": (
            decisive_exact / len(decisive) if decisive else None
        ),
        "five_class_wilson_95": _wilson(decisive_exact, len(decisive)),
        "five_class_cohen_kappa": _kappa(decisive),
    }


def compare_rule_luna_sol(
    samples: Sequence[Mapping[str, Any]],
    luna_rows: Sequence[Mapping[str, Any]],
    sol_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validated_samples = [validate_sample(row) for row in samples]
    validated_luna = validate_independent_ai_batch(luna_rows)
    validated_sol = validate_independent_ai_batch(sol_rows)
    sample_by_id = {row["sample_id"]: row for row in validated_samples}
    luna_by_id = {row["sample_id"]: row["ai_label"] for row in validated_luna}
    sol_by_id = {row["sample_id"]: row["ai_label"] for row in validated_sol}
    if len(sample_by_id) != len(validated_samples):
        raise ContractError("duplicate sample_id in Sol review candidates")
    if set(luna_by_id) != set(sample_by_id) or set(sol_by_id) != set(sample_by_id):
        raise ContractError("rule, Luna, and Sol sample IDs must match exactly")

    comparisons = []
    for sample_id in sorted(sample_by_id):
        sample = sample_by_id[sample_id]
        rule_label = sample["progression_label"]
        luna_label = luna_by_id[sample_id]
        sol_label = sol_by_id[sample_id]
        comparisons.append(
            {
                "sample_id": sample_id,
                "source": sample["source"],
                "finding": sample["finding"],
                "rule_label": rule_label,
                "luna_label": luna_label,
                "sol_label": sol_label,
                "luna_sol_exact": luna_label == sol_label,
                "rule_luna_exact": rule_label == luna_label,
                "rule_sol_exact": rule_label == sol_label,
            }
        )

    confusion = {
        luna_label: {
            sol_label: sum(
                row["luna_label"] == luna_label and row["sol_label"] == sol_label
                for row in comparisons
            )
            for sol_label in REVIEW_LABELS
        }
        for luna_label in REVIEW_LABELS
    }
    by_source = {
        source: _agreement(
            [row for row in comparisons if row["source"] == source]
        )
        for source in sorted({row["source"] for row in comparisons})
    }
    by_luna_label = {}
    for label in PROGRESSION_LABELS:
        selected = [row for row in comparisons if row["luna_label"] == label]
        exact = sum(row["sol_label"] == label for row in selected)
        decisive = [row for row in selected if row["sol_label"] != "Unclear"]
        decisive_exact = sum(row["sol_label"] == label for row in decisive)
        by_luna_label[label] = {
            "rows": len(selected),
            "sol_exact": exact,
            "agreement": exact / len(selected) if selected else None,
            "wilson_95": _wilson(exact, len(selected)),
            "sol_decisive_rows": len(decisive),
            "sol_decisive_coverage": (
                len(decisive) / len(selected) if selected else None
            ),
            "decisive_exact": decisive_exact,
            "decisive_agreement": (
                decisive_exact / len(decisive) if decisive else None
            ),
            "decisive_wilson_95": _wilson(decisive_exact, len(decisive)),
            "sol_distribution": dict(
                sorted(Counter(row["sol_label"] for row in selected).items())
            ),
        }
    by_rule_label = {
        label: _agreement(
            [row for row in comparisons if row["rule_label"] == label]
        )
        for label in PROGRESSION_LABELS
    }

    rule_luna_mismatch = [
        row
        for row in comparisons
        if row["luna_label"] != "Unclear"
        and row["rule_label"] != row["luna_label"]
    ]

    def mismatch_resolution(row: Mapping[str, Any]) -> str:
        if row["sol_label"] == "Unclear":
            return "sol_unclear"
        if row["sol_label"] == row["luna_label"]:
            return "sol_supports_luna"
        if row["sol_label"] == row["rule_label"]:
            return "sol_supports_rule"
        return "sol_selects_third_label"

    mismatch_counts = Counter(mismatch_resolution(row) for row in rule_luna_mismatch)
    mismatch_by_source = {
        source: {
            key: sum(
                mismatch_resolution(row) == key
                for row in rule_luna_mismatch
                if row["source"] == source
            )
            for key in (
                "sol_supports_luna",
                "sol_supports_rule",
                "sol_selects_third_label",
                "sol_unclear",
            )
        }
        for source in sorted({row["source"] for row in comparisons})
    }
    luna_unclear = [row for row in comparisons if row["luna_label"] == "Unclear"]
    rule_luna_exact = [
        row for row in comparisons if row["rule_label"] == row["luna_label"]
    ]
    decisive_disagreements = [
        row
        for row in comparisons
        if row["luna_label"] != "Unclear"
        and row["sol_label"] != "Unclear"
        and row["luna_label"] != row["sol_label"]
    ]
    opposite_pairs = {
        frozenset(("Improved", "Worse")),
        frozenset(("New", "Resolved")),
    }
    three_way = Counter()
    for row in comparisons:
        labels = (row["rule_label"], row["luna_label"], row["sol_label"])
        if "Unclear" in labels:
            three_way["at_least_one_unclear"] += 1
        elif labels[0] == labels[1] == labels[2]:
            three_way["all_three_same"] += 1
        elif labels[1] == labels[2]:
            three_way["luna_sol_same_rule_differs"] += 1
        elif labels[0] == labels[2]:
            three_way["rule_sol_same_luna_differs"] += 1
        elif labels[0] == labels[1]:
            three_way["rule_luna_same_sol_differs"] += 1
        else:
            three_way["all_three_different"] += 1

    luna_worse = [row for row in comparisons if row["luna_label"] == "Worse"]
    audit = {
        "schema": "prta-cxr.sol-blind-review-audit.v1",
        "status": "PASS_SOL_BLIND_REVIEW_COMPARISON",
        "rows": len(comparisons),
        "overall": _agreement(comparisons),
        "by_source": by_source,
        "by_luna_label": by_luna_label,
        "by_rule_label": by_rule_label,
        "luna_sol_confusion": confusion,
        "worse_focus": {
            "luna_worse_rows": len(luna_worse),
            "sol_agrees_worse": sum(
                row["sol_label"] == "Worse" for row in luna_worse
            ),
            "sol_distribution": dict(
                sorted(Counter(row["sol_label"] for row in luna_worse).items())
            ),
            "sol_decisive_rows": sum(
                row["sol_label"] != "Unclear" for row in luna_worse
            ),
            "decisive_agreement": (
                sum(row["sol_label"] == "Worse" for row in luna_worse)
                / sum(row["sol_label"] != "Unclear" for row in luna_worse)
                if any(row["sol_label"] != "Unclear" for row in luna_worse)
                else None
            ),
        },
        "rule_luna_mismatch": {
            "rows": len(rule_luna_mismatch),
            "resolution_counts": {
                key: mismatch_counts.get(key, 0)
                for key in (
                    "sol_supports_luna",
                    "sol_supports_rule",
                    "sol_selects_third_label",
                    "sol_unclear",
                )
            },
            "by_source": mismatch_by_source,
        },
        "rule_luna_exact": {
            "rows": len(rule_luna_exact),
            "sol_confirms": sum(
                row["sol_label"] == row["luna_label"] for row in rule_luna_exact
            ),
            "sol_differs": sum(
                row["sol_label"] not in {row["luna_label"], "Unclear"}
                for row in rule_luna_exact
            ),
            "sol_unclear": sum(
                row["sol_label"] == "Unclear" for row in rule_luna_exact
            ),
        },
        "decisive_disagreements": {
            "rows": len(decisive_disagreements),
            "direct_opposite_direction_pairs": sum(
                frozenset((row["luna_label"], row["sol_label"]))
                in opposite_pairs
                for row in decisive_disagreements
            ),
        },
        "luna_unclear": {
            "rows": len(luna_unclear),
            "sol_distribution": dict(
                sorted(Counter(row["sol_label"] for row in luna_unclear).items())
            ),
        },
        "three_way_patterns": dict(sorted(three_way.items())),
        "agreement_is_luna_accuracy": False,
        "agreement_is_medical_gold": False,
        "human_accuracy_audit_required": True,
        "human_accuracy_audit_rows_min": 200,
        "human_accuracy_audit_rows_max": 300,
        "formal_training_authorized": False,
        "paper_use_authorized": False,
        "comparison_manifest_sha256": canonical_sha256(comparisons),
    }
    return comparisons, audit
