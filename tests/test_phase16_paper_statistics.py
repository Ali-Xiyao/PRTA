from prta_cxr.phase16_paper_statistics import _pareto_rows, holm_adjust


def test_holm_adjust_is_monotone_in_ranked_order():
    adjusted = holm_adjust({"a": 0.01, "b": 0.02, "c": 0.2})
    assert adjusted == {"a": 0.03, "b": 0.04, "c": 0.2}


def test_holm_adjust_caps_at_one():
    adjusted = holm_adjust({"a": 0.8, "b": 0.9})
    assert adjusted == {"a": 1.0, "b": 1.0}


def test_pareto_uses_current_only_fallback_not_true_v2_branch():
    point_metrics = {
        system: {
            f"seed{seed}": {
                "macro_f1": macro_f1,
                "opposite_direction_error_rate": oder,
            }
            for seed in (17, 28, 43)
        }
        for system, macro_f1, oder in (
            ("V2", 0.55, 0.003),
            ("IF-F01", 0.54, 0.005),
            ("IF-F02", 0.56, 0.004),
        )
    }
    routing = {
        "three_seed_summary": {
            "true": {
                "invalid_to_current_only": {
                    "metrics": {
                        "macro_f1": {"mean": 0.55, "sample_sd": 0.01},
                        "opposite_direction_error_rate": {
                            "mean": 0.003,
                            "sample_sd": 0.001,
                        },
                    }
                }
            },
            "matched_hard": {
                "invalid_to_current_only": {
                    "metrics": {
                        "macro_f1": {"mean": 0.41, "sample_sd": 0.01},
                        "opposite_direction_error_rate": {
                            "mean": 0.035,
                            "sample_sd": 0.001,
                        },
                    }
                }
            },
        }
    }
    rows = _pareto_rows(point_metrics, routing)
    current = next(row for row in rows if row["system"] == "B401")
    assert current["macro_f1"]["mean"] == 0.41
    assert current["dominated_by"] == ["IF-F01", "IF-F02", "V2"]
