from prta_cxr.evaluation.reporting import (
    benjamini_hochberg,
    intervention_comparison,
    prediction_summary,
)


def _rows(predictions):
    labels = ["Stable", "Improved", "Worse", "New", "Resolved"]
    rows = []
    for index, (target, prediction) in enumerate(zip(labels, predictions, strict=True)):
        probabilities = [0.025] * 5
        probabilities[labels.index(prediction)] = 0.9
        rows.append(
            {
                "patient_id": f"p-{index}",
                "observation_id": f"s-{index}",
                "target": target,
                "prediction": prediction,
                "probabilities": probabilities,
            }
        )
    return rows


def test_prediction_and_intervention_summaries():
    reference = _rows(["Stable", "Improved", "Worse", "New", "Resolved"])
    changed = _rows(["Improved", "Improved", "Worse", "New", "Resolved"])
    assert prediction_summary(reference)["classification"]["ordinary"]["macro_f1"] == 1
    comparison = intervention_comparison(reference, changed)
    assert comparison["flip_rate"] == 0.2
    assert comparison["correct_to_wrong_rate"] == 0.2


def test_benjamini_hochberg_is_monotone_and_bounded():
    adjusted = benjamini_hochberg({"a": 0.01, "b": 0.04, "c": 0.2})
    assert 0 <= adjusted["a"] <= adjusted["b"] <= adjusted["c"] <= 1
