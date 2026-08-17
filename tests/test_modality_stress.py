from prta_cxr.modality_stress import compare_condition_rows


def _row(sample, probabilities):
    prediction = ("Stable", "Improved")[probabilities[1] > probabilities[0]]
    return {
        "observation_id": sample,
        "target": "Stable",
        "prediction": prediction,
        "probabilities": probabilities,
    }


def test_modality_comparison_detects_flip_and_probability_drop():
    baseline = [_row("a", [0.9, 0.1, 0, 0, 0])]
    stressed = [_row("a", [0.2, 0.8, 0, 0, 0])]
    result = compare_condition_rows(baseline, stressed)
    assert result["prediction_flip_count"] == 1
    assert result["mean_true_label_probability_drop"] > 0
    assert result["mean_js_divergence"] > 0
