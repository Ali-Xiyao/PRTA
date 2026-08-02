from prta_cxr.formal_matrix import development_gate_decision


def _receipt(f1, min_recall, oder, gap, epoch=2):
    return {
        "best_epoch": epoch,
        "best_dev_macro_f1": f1,
        "history": [
            {
                "epoch": epoch,
                "macro_f1": f1,
                "min_class_recall": min_recall,
                "opposite_direction_error_rate": oder,
            }
        ],
        "dev_prior_audit": {"true_minus_wrong_prior_gap": gap},
    }


def test_development_gate_go_requires_all_registered_checks():
    receipts = {
        "P17": _receipt(0.57, 0.30, 0.02, 0.04),
        "P29": _receipt(0.56, 0.29, 0.021, 0.035),
        "P43": _receipt(0.55, 0.28, 0.019, 0.03),
        "B401": _receipt(0.49, 0.2, 0.04, 0.0),
        "B402": _receipt(0.52, 0.2, 0.03, 0.01),
        "B403": _receipt(0.53, 0.2, 0.025, 0.01),
    }
    result = development_gate_decision(
        prta_seed_ids=["P17", "P29", "P43"],
        baseline_ids=["B401", "B402", "B403"],
        receipts=receipts,
    )
    assert result["decision"] == "GO"
    assert all(result["checks"].values())


def test_development_gate_holds_midrange_result():
    receipts = {
        "P17": _receipt(0.50, 0.15, 0.04, 0.0),
        "P29": _receipt(0.49, 0.15, 0.04, 0.0),
        "P43": _receipt(0.48, 0.15, 0.04, 0.0),
        "B402": _receipt(0.48, 0.15, 0.04, 0.0),
        "B403": _receipt(0.47, 0.15, 0.04, 0.0),
    }
    result = development_gate_decision(
        prta_seed_ids=["P17", "P29", "P43"],
        baseline_ids=["B402", "B403"],
        receipts=receipts,
    )
    assert result["decision"] == "HOLD"
