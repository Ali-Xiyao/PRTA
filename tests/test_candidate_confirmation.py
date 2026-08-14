import pytest

from prta_cxr.candidate_confirmation import paired_patient_bootstrap
from prta_cxr.contracts import PROGRESSION_LABELS


def _rows():
    rows = []
    for system in ("V0", "V1", "V2"):
        for seed in (17, 28, 43):
            for patient in range(25):
                target = PROGRESSION_LABELS[patient % len(PROGRESSION_LABELS)]
                prediction = target
                if system == "V0" and patient % 11 == 0:
                    prediction = PROGRESSION_LABELS[
                        (patient + 1) % len(PROGRESSION_LABELS)
                    ]
                if system == "V1" and patient % 13 == 0:
                    prediction = PROGRESSION_LABELS[
                        (patient + 1) % len(PROGRESSION_LABELS)
                    ]
                if system == "V2" and patient % 17 == 0:
                    prediction = PROGRESSION_LABELS[
                        (patient + 1) % len(PROGRESSION_LABELS)
                    ]
                rows.append(
                    {
                        "system": system,
                        "training_seed": seed,
                        "cohort": "dev",
                        "prior_intervention": "true",
                        "patient_id": f"patient-{patient}",
                        "observation_id": f"observation-{patient}",
                        "target": target,
                        "prediction": prediction,
                    }
                )
    return rows


def test_candidate_bootstrap_is_paired_and_reports_required_metrics():
    result = paired_patient_bootstrap(_rows(), replicates=40, rng_seed=7)
    assert result["patients"] == 25
    assert result["observations"] == 25
    contrast = result["contrasts"]["V2_minus_V0"]
    metrics = contrast["scopes"]["mean_across_seeds"]
    assert "macro_f1" in metrics
    assert "balanced_accuracy" in metrics
    assert "opposite_direction_error_rate" in metrics
    assert "recall:Stable" in metrics
    assert "f1:New" in metrics
    assert contrast["exclusive_counts"]["seed17"]["left_only_correct"] > 0
    assert result["bootstrap"]["paired_systems"] is True


def test_candidate_bootstrap_rejects_non_dev_or_incomplete_matrix():
    rows = _rows()
    rows[0]["cohort"] = "internal_test"
    with pytest.raises(ValueError, match="Dev predictions only"):
        paired_patient_bootstrap(rows, replicates=4)
    with pytest.raises(ValueError, match="not fully crossed"):
        paired_patient_bootstrap(_rows()[:-25], replicates=4)
