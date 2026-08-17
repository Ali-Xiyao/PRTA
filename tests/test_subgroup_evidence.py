import numpy as np

from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.subgroup_evidence import (
    AXES,
    aggregate_subgroups,
    class_rarity_map,
    evaluate_seed_subgroups,
)


def _rows():
    rows = []
    for index in range(25):
        target = index % 5
        logits = np.full(5, -1.0)
        logits[target] = 2.0
        probabilities = np.exp(logits - logits.max())
        probabilities /= probabilities.sum()
        rows.append(
            {
                "patient_id": f"patient-{index // 2}",
                "observation_id": f"sample-{index}",
                "target": PROGRESSION_LABELS[target],
                "prediction": PROGRESSION_LABELS[target],
                "logits": logits.tolist(),
                "probabilities": probabilities.tolist(),
                "finding": f"finding-{index % 2}",
                "source": f"source-{index % 2}",
                "prior_view": "PA",
                "current_view": "PA" if index % 2 else "AP",
                "interval_days": float(index),
                "calendar_interval_available": True,
            }
        )
    return rows


def test_class_rarity_uses_frozen_train_prevalence():
    split_rows = []
    for label in PROGRESSION_LABELS:
        count = 2 if label == "Resolved" else 25
        split_rows.extend(
            {"split": "train", "progression_label": label} for _ in range(count)
        )
    rarity = class_rarity_map(split_rows)
    assert rarity["Resolved"] == "rare_lt_5pct"
    assert rarity["Stable"] == "common_ge_5pct"


def test_subgroups_cover_frozen_axes_and_aggregate_seeds():
    rarity = {label: "common_ge_5pct" for label in PROGRESSION_LABELS}
    report = evaluate_seed_subgroups(_rows(), rarity)
    assert set(report) == set(AXES)
    assert report["view_relation"]["matched"]["accuracy"] == 1.0
    aggregate = aggregate_subgroups([report, report, report])
    assert aggregate["finding"]["finding-0"]["metrics"]["accuracy"]["sd"] == 0.0
