import copy
import json

import numpy as np

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.evidence_cells import (
    _load_true_probability_receipt,
    aggregate_calibration_bins,
    aggregate_finding_progression_cells,
)


def _calibration_block(scale: float):
    fixed = [
        {
            "lower": 0.0,
            "upper": 0.5,
            "count": 2,
            "accuracy": 0.5,
            "confidence": 0.4 * scale,
        },
        {
            "lower": 0.5,
            "upper": 1.0,
            "count": 3,
            "accuracy": 1.0,
            "confidence": 0.8 * scale,
        },
    ]
    adaptive = [
        {
            "count": 2,
            "accuracy": 0.5,
            "confidence": 0.4 * scale,
            "minimum_confidence": 0.3,
            "maximum_confidence": 0.5,
        },
        {
            "count": 3,
            "accuracy": 1.0,
            "confidence": 0.8 * scale,
            "minimum_confidence": 0.6,
            "maximum_confidence": 0.9,
        },
    ]
    classwise = []
    for class_index in range(5):
        bins = [
            {
                "lower": item["lower"],
                "upper": item["upper"],
                "count": item["count"],
                "frequency": item["accuracy"],
                "probability": item["confidence"],
            }
            for item in fixed
        ]
        classwise.append({"class_index": class_index, "ece": 0.1, "bins": bins})
    return {
        "calibration": {
            "reliability": fixed,
            "adaptive_reliability": adaptive,
            "classwise_reliability": classwise,
        }
    }


def _calibration_report():
    seed_reports = []
    for seed, scale in zip((17, 28, 43), (0.9, 1.0, 1.1), strict=True):
        seed_reports.append(
            {
                "seed": seed,
                "rows": 5,
                "uncalibrated": _calibration_block(scale),
                "cross_fitted_calibrated": _calibration_block(1.0),
            }
        )
    return {
        "schema": "prta-cxr.phase20-s1-dev-calibration-evidence.v1",
        "status": "PASS_PHASE20_S1_DEV_CALIBRATION_COMPLETE",
        "system": "Slim-S1",
        "seeds": [17, 28, 43],
        "seed_reports": seed_reports,
        "protected_outcome_read_count": 0,
        "internal_test_opened": False,
        "selection_performed": False,
    }


def _rows(*, seed: int):
    rows = []
    for index in range(30):
        target = index % 5
        logits = np.full(5, -1.0)
        predicted = target if seed != 43 or index % 3 else (target + 1) % 5
        logits[predicted] = 2.0
        probabilities = np.exp(logits - logits.max())
        probabilities /= probabilities.sum()
        rows.append(
            {
                "patient_id": f"patient-{index}",
                "observation_id": f"sample-{index}",
                "target": PROGRESSION_LABELS[target],
                "prediction": PROGRESSION_LABELS[predicted],
                "logits": logits.tolist(),
                "probabilities": probabilities.tolist(),
                "finding": "Edema" if index < 25 else "Rare Finding",
            }
        )
    return rows


def test_calibration_bins_preserve_three_seed_values():
    result = aggregate_calibration_bins(_calibration_report())
    fixed = result["uncalibrated"]["fixed_width"]
    assert len(fixed) == 2
    assert fixed[0]["count_per_seed"] == [2, 2, 2]
    assert fixed[0]["accuracy"]["mean"] == 0.5
    assert len(result["cross_fitted_calibrated"]["classwise_fixed_width"]) == 5


def test_joint_cells_suppress_small_patient_groups():
    result = aggregate_finding_progression_cells(
        [(seed, _rows(seed=seed)) for seed in (17, 28, 43)],
        minimum_rows=5,
        minimum_patients=5,
    )
    assert result["expected_cells"] == 10
    edema_stable = next(
        cell
        for cell in result["cells"]
        if cell["finding"] == "Edema"
        and cell["progression_label"] == "Stable"
    )
    assert not edema_stable["suppressed"]
    assert edema_stable["recall"]["values"] == [1.0, 1.0, 3 / 5]
    rare = [cell for cell in result["cells"] if cell["finding"] == "Rare Finding"]
    assert all(cell["suppressed"] for cell in rare)
    assert all(cell["recall"] is None for cell in rare)


def test_joint_cells_reject_cohort_drift():
    blocks = [(seed, _rows(seed=seed)) for seed in (17, 28, 43)]
    changed = copy.deepcopy(blocks[1][1])
    changed[0]["finding"] = "Other"
    blocks[1] = (28, changed)
    try:
        aggregate_finding_progression_cells(blocks)
    except ValueError as error:
        assert "cohort identity drift" in str(error)
    else:
        raise AssertionError("cohort drift was not rejected")


def test_true_only_loader_does_not_require_other_interventions(tmp_path):
    predictions = tmp_path / "true.predictions.jsonl"
    predictions.write_text(
        "\n".join(json.dumps(row) for row in _rows(seed=17)) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema": "prta-cxr.phase20-s1-dev-probability-diagnostic.v1",
        "status": "PASS_PHASE20_S1_DEV_PROBABILITY_EXPORT",
        "variant": "Slim-S1",
        "probability_export": True,
        "seed": 17,
        "internal_test_opened": False,
        "gold_opened": False,
        "selection_performed": False,
        "protected_outcome_read_count": 0,
        "evaluation_interventions": ["true", "matched_hard", "null", "reversed"],
        "prediction_blocks": {
            "true": {
                "path": predictions.name,
                "rows": 30,
                "sha256": sha256_file(predictions),
            },
            "matched_hard": {"path": "not-downloaded.jsonl"},
        },
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    loaded_receipt, rows = _load_true_probability_receipt(receipt_path)
    assert loaded_receipt["seed"] == 17
    assert len(rows) == 30
