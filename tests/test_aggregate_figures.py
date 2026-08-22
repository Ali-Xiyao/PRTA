import copy

import numpy as np

from prta_cxr.aggregate_figures import joint_recall_matrix, reliability_plot_series


def _report():
    bins = [
        {
            "bin_index": 0,
            "count_mean": 10.0,
            "accuracy": {"mean": 0.7, "sd": 0.1},
            "confidence": {"mean": 0.6, "sd": 0.02},
        },
        {
            "bin_index": 1,
            "count_mean": 0.0,
            "accuracy": {"mean": None, "sd": None},
            "confidence": {"mean": None, "sd": None},
        },
    ]
    cells = []
    labels = ["Stable", "Improved", "Worse", "New", "Resolved"]
    for index, label in enumerate(labels):
        suppressed = index == 4
        cells.append(
            {
                "finding": "Edema",
                "progression_label": label,
                "rows": 40 if not suppressed else 4,
                "suppressed": suppressed,
                "recall": None if suppressed else {"mean": 0.1 * (index + 1)},
            }
        )
    return {
        "schema": "prta-cxr.calibration-joint-cells.v1",
        "status": "PASS_CALIBRATION_JOINT_CELLS_COMPLETE",
        "seeds": [17, 28, 43],
        "privacy": {
            "aggregate_only": True,
            "patient_identifiers_published": False,
            "patient_level_predictions_published": False,
        },
        "calibration_bins": {
            "uncalibrated": {"fixed_width": bins},
            "cross_fitted_calibrated": {"fixed_width": copy.deepcopy(bins)},
        },
        "finding_progression": {
            "findings": ["Edema"],
            "progression_labels": labels,
            "cells": cells,
        },
    }


def test_reliability_series_omits_empty_bins():
    series = reliability_plot_series(_report())
    assert len(series["uncalibrated"]["points"]) == 1
    assert series["uncalibrated"]["points"][0]["accuracy"] == 0.7


def test_joint_matrix_leaves_suppressed_cells_blank():
    findings, labels, matrix, counts = joint_recall_matrix(_report())
    assert findings == ["Edema"]
    assert labels[-1] == "Resolved"
    assert matrix.shape == (1, 5)
    assert np.isnan(matrix[0, -1])
    assert counts[0, -1] == 4
