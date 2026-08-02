from prta_cxr.evaluation.progression import hierarchical_patient_bootstrap
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


def test_hierarchical_bootstrap_reports_empirical_p_value():
    rows = []
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    for system in ("better", "worse"):
        for seed in (17, 29):
            for patient in ("p1", "p2"):
                for index, target in enumerate(labels):
                    rows.append(
                        {
                            "system": system,
                            "training_seed": seed,
                            "derangement_id": 0,
                            "patient_id": patient,
                            "observation_id": f"{patient}-{index}",
                            "target": target,
                            "prediction": (
                                target
                                if system == "better"
                                else labels[(index + 1) % 5]
                            ),
                            "weight": 0.2,
                        }
                    )
    result = hierarchical_patient_bootstrap(
        rows,
        labels=labels,
        systems=("better", "worse"),
        seeds=(17, 29),
        derangements=(0,),
        contrasts={"gain": ("better", "worse")},
        replicates=20,
        minimum_valid_fraction=0.0,
    )
    assert 0 <= result["contrasts"]["gain"]["empirical_two_sided_p"] <= 1
