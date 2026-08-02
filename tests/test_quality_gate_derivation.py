from prta_cxr.contracts import canonical_sha256
from prta_cxr.quality_gate import derive_completed_human_silver_audit


def test_derive_completed_human_silver_audit():
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    comparisons = []
    for source in ("mimic", "chexpert"):
        for label in labels:
            for index in range(25):
                comparisons.append(
                    {
                        "source": source,
                        "luna_label": label,
                        "luna_human_exact": index != 0,
                    }
                )
    audit = {
        "status": "PASS_SENIOR_LUNA_ASSISTED_REVIEW_COMPLETE_GOLD_FROZEN",
        "comparison_sha256": canonical_sha256(comparisons),
        "review_mode": "luna_assisted_senior_panel_compact_v2",
    }
    result = derive_completed_human_silver_audit(audit, comparisons)
    assert result["silver_accuracy"] == 0.96
    assert result["training_gate_passed"] is True
    assert len(result["strata_counts"]) == 10
