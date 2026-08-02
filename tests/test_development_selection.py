from prta_cxr.development_selection import select_dev_candidate


def _receipt(f1, gap):
    return {
        "best_dev_macro_f1": f1,
        "dev_prior_audit": {"true_minus_wrong_prior_gap": gap},
    }


def test_head_requires_15pp_and_nonworse_prior_gap():
    receipts = {
        "H0": _receipt(0.50, 0.04),
        "H1": _receipt(0.52, 0.039),
        "H2": _receipt(0.516, 0.041),
    }
    result = select_dev_candidate(
        "H0", ["H1", "H2"], receipts, minimum_f1_gain=0.015
    )
    assert result["chosen_experiment_id"] == "H2"
    assert result["qualified_experiment_ids"] == ["H2"]


def test_selection_keeps_baseline_when_gain_is_too_small():
    receipts = {"base": _receipt(0.50, 0.04), "candidate": _receipt(0.51, 0.05)}
    result = select_dev_candidate(
        "base", ["candidate"], receipts, minimum_f1_gain=0.015
    )
    assert result["chosen_experiment_id"] == "base"
