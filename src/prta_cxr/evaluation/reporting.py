from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.evaluation.calibration import (
    calibration_metrics,
    risk_coverage_metrics,
)
from prta_cxr.evaluation.progression import (
    classification_metrics,
    metrics_from_confusion,
)


def prediction_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize empty predictions")
    probabilities = np.asarray([row["probabilities"] for row in rows], dtype=float)
    label_index = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
    targets = [label_index[str(row["target"])] for row in rows]
    return {
        "classification": classification_metrics(rows, labels=PROGRESSION_LABELS),
        "calibration": calibration_metrics(probabilities, targets, bins=15),
        "risk_coverage": risk_coverage_metrics(probabilities, targets),
    }


def intervention_comparison(
    reference: Sequence[Mapping[str, Any]],
    intervention: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reference_by_id = {str(row["observation_id"]): row for row in reference}
    intervention_by_id = {
        str(row["observation_id"]): row for row in intervention
    }
    if set(reference_by_id) != set(intervention_by_id):
        raise ValueError("intervention sample IDs do not match reference")
    flip = 0
    correct_to_wrong = 0
    wrong_to_correct = 0
    for sample_id in sorted(reference_by_id):
        left = reference_by_id[sample_id]
        right = intervention_by_id[sample_id]
        left_correct = left["prediction"] == left["target"]
        right_correct = right["prediction"] == right["target"]
        flip += left["prediction"] != right["prediction"]
        correct_to_wrong += left_correct and not right_correct
        wrong_to_correct += not left_correct and right_correct
    reference_summary = prediction_summary(reference)
    intervention_summary = prediction_summary(intervention)
    left_f1 = reference_summary["classification"]["ordinary"]["macro_f1"]
    right_f1 = intervention_summary["classification"]["ordinary"]["macro_f1"]
    count = len(reference_by_id)
    return {
        "rows": count,
        "macro_f1_delta_vs_true": right_f1 - left_f1,
        "flip_rate": flip / count,
        "correct_to_wrong_rate": correct_to_wrong / count,
        "wrong_to_correct_rate": wrong_to_correct / count,
        "reference": reference_summary,
        "intervention": intervention_summary,
    }


def _interval_bin(row: Mapping[str, Any]) -> str:
    if not bool(row.get("calendar_interval_available", False)):
        return "ordinal_or_unavailable"
    value = float(row["interval_days"])
    for bound in (7, 30, 90, 365):
        if value <= bound:
            return f"le_{bound}_days"
    return "gt_365_days"


def subgroup_summary(
    rows: Sequence[Mapping[str, Any]], key: str
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        value = _interval_bin(row) if key == "interval_bin" else str(row[key])
        grouped[value].append(row)
    label_index = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
    output = {}
    for value, selected in sorted(grouped.items()):
        confusion = np.zeros((5, 5), dtype=float)
        patients = set()
        for row in selected:
            confusion[
                label_index[str(row["target"])],
                label_index[str(row["prediction"])],
            ] += 1
            patients.add(str(row["patient_id"]))
        output[value] = {
            "rows": len(selected),
            "patients": len(patients),
            "present_labels": [
                label
                for label, support in zip(
                    PROGRESSION_LABELS, confusion.sum(axis=1), strict=True
                )
                if support > 0
            ],
            "metrics": metrics_from_confusion(
                confusion,
                labels=PROGRESSION_LABELS,
                require_all_labels=False,
            ),
        }
    return output


def benjamini_hochberg(p_values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted((float(value), key) for key, value in p_values.items())
    count = len(ordered)
    adjusted: dict[str, float] = {}
    running = 1.0
    for reverse_index, (value, key) in enumerate(reversed(ordered), start=1):
        rank = count - reverse_index + 1
        running = min(running, value * count / rank)
        adjusted[key] = min(1.0, running)
    return dict(sorted(adjusted.items()))
