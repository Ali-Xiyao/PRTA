from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from prta_cxr.contracts import (
    PROGRESSION_LABELS,
    ContractError,
    canonical_sha256,
)


def derive_completed_human_silver_audit(
    senior_audit: Mapping[str, Any],
    comparisons: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if senior_audit.get("status") != (
        "PASS_SENIOR_LUNA_ASSISTED_REVIEW_COMPLETE_GOLD_FROZEN"
    ):
        raise ContractError("senior panel audit is not formally complete")
    if senior_audit.get("comparison_sha256") != canonical_sha256(comparisons):
        raise ContractError("senior comparison manifest hash mismatch")
    if len(comparisons) != 250:
        raise ContractError("senior quality audit must contain 250 rows")
    sources = sorted({str(row["source"]) for row in comparisons})
    labels = list(PROGRESSION_LABELS)
    strata = Counter(
        f"{row['source']}|{row['luna_label']}" for row in comparisons
    )
    exact = [bool(row["luna_human_exact"]) for row in comparisons]
    by_source = {
        source: sum(
            bool(row["luna_human_exact"])
            for row in comparisons
            if row["source"] == source
        )
        / sum(row["source"] == source for row in comparisons)
        for source in sources
    }
    by_label = {
        label: sum(
            bool(row["luna_human_exact"])
            for row in comparisons
            if row["luna_label"] == label
        )
        / sum(row["luna_label"] == label for row in comparisons)
        for label in labels
    }
    return {
        "schema": "prta-cxr.human-silver-accuracy-audit.v1",
        "status": "PASS_HUMAN_SILVER_ACCURACY_AUDIT",
        "completed": True,
        "reviewed_rows": len(comparisons),
        "stratification": "source_x_five_label",
        "sources": sources,
        "labels": labels,
        "silver_accuracy": sum(exact) / len(exact),
        "accuracy_by_source": by_source,
        "accuracy_by_label": by_label,
        "strata_counts": dict(sorted(strata.items())),
        "review_manifest_sha256": canonical_sha256(comparisons),
        "review_mode": senior_audit["review_mode"],
        "metric_interpretation": (
            "Luna-visible senior-panel confirmation rate, not blind accuracy"
        ),
        "medical_ground_truth_claim": False,
        "training_gate_passed": (
            sum(exact) / len(exact) >= 0.90
            and min(by_source.values()) >= 0.80
            and min(by_label.values()) >= 0.80
        ),
    }


def load_completed_human_silver_audit(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError("human silver audit receipt must be an object")
    required = {
        "schema",
        "status",
        "completed",
        "reviewed_rows",
        "stratification",
        "sources",
        "labels",
        "silver_accuracy",
        "accuracy_by_source",
        "accuracy_by_label",
        "strata_counts",
        "review_manifest_sha256",
    }
    missing = required - set(value)
    if missing:
        raise ContractError(f"human silver audit fields missing: {sorted(missing)}")
    if value["schema"] != "prta-cxr.human-silver-accuracy-audit.v1":
        raise ContractError("unsupported human silver audit schema")
    if (
        value["status"] != "PASS_HUMAN_SILVER_ACCURACY_AUDIT"
        or value["completed"] is not True
    ):
        raise ContractError("human silver accuracy audit is not complete")
    rows = value["reviewed_rows"]
    if not isinstance(rows, int) or not 200 <= rows <= 300:
        raise ContractError("human silver audit must contain 200-300 rows")
    if value["stratification"] != "source_x_five_label":
        raise ContractError("human silver audit stratification is invalid")
    if set(value["labels"]) != set(PROGRESSION_LABELS):
        raise ContractError("human silver audit must cover all five labels")
    if not isinstance(value["sources"], list) or len(value["sources"]) < 2:
        raise ContractError("human silver audit must cover both data sources")
    accuracy = value["silver_accuracy"]
    if not isinstance(accuracy, (int, float)) or not 0 <= accuracy <= 1:
        raise ContractError("human silver accuracy must be within [0, 1]")
    by_source = value["accuracy_by_source"]
    by_label = value["accuracy_by_label"]
    if not isinstance(by_source, dict) or set(by_source) != set(value["sources"]):
        raise ContractError("human silver source accuracies are incomplete")
    if not isinstance(by_label, dict) or set(by_label) != set(PROGRESSION_LABELS):
        raise ContractError("human silver label accuracies are incomplete")
    if any(
        not isinstance(metric, (int, float)) or not 0 <= metric <= 1
        for metric in [*by_source.values(), *by_label.values()]
    ):
        raise ContractError("human silver stratified accuracies are invalid")
    strata = value["strata_counts"]
    expected_strata = {
        f"{source}|{label}"
        for source in value["sources"]
        for label in PROGRESSION_LABELS
    }
    if not isinstance(strata, dict) or set(strata) != expected_strata:
        raise ContractError("human silver source-by-label strata are incomplete")
    if any(not isinstance(count, int) or count < 1 for count in strata.values()):
        raise ContractError("every human silver source-by-label stratum is required")
    digest = value["review_manifest_sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise ContractError("human silver review manifest hash is invalid")
    return value
