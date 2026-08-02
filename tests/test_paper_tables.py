from prta_cxr.reporting.paper_tables import (
    data_table,
    method_result,
    wilson_interval,
)


def _summary(value):
    return {
        "classification": {
            "patient_balanced": {
                "macro_f1": value,
                "balanced_accuracy": value,
                "accuracy": value,
                "min_class_recall": value / 2,
                "opposite_direction_error_rate": 0.01,
            }
        },
        "calibration": {
            "nll": 1.0,
            "brier": 0.5,
            "ece": 0.1,
            "mean_confidence": 0.7,
        },
        "risk_coverage": {
            "aurc": 0.2,
            "risk_at_coverage": {"0.9": 0.1, "0.8": 0.08, "0.7": 0.06},
        },
    }


def test_method_result_averages_three_seeds_and_uses_frozen_ci():
    trust = {
        "summaries": {
            f"B401|{seed}|internal_test|true": _summary(value)
            for seed, value in zip((17, 29, 43), (0.4, 0.5, 0.6), strict=True)
        },
        "bootstrap": {
            "main_methods": {
                "system_intervals": {
                    "B401": {"lower": 0.45, "upper": 0.55, "level": 0.95}
                }
            }
        },
    }
    result = method_result(trust, "B401")
    assert result["macro_f1"] == 0.5
    assert result["ci95"]["lower"] == 0.45
    assert result["risk_at_coverage"]["0.8"] == 0.08


def test_data_table_recomputes_final_source_split_counts():
    rows = [
        {
            "source": "mimic",
            "split": split,
            "patient_id_hash": patient,
        }
        for split, patient in (("train", "p1"), ("dev", "p2"), ("train", "p1"))
    ]
    result = data_table(rows)
    assert result[0]["train"] == 2
    assert result[0]["dev"] == 1
    assert result[0]["patients"] == 2
    assert result[0]["candidate_rows"] == "N/A—not frozen"


def test_wilson_interval_is_bounded_and_contains_observed_rate():
    lower, upper = wilson_interval(246, 250)
    assert 0 <= lower < 246 / 250 < upper <= 1
