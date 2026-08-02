import pytest

from prta_cxr.cli_independent_silver import synthetic_ai_rows
from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.contracts import ContractError
from prta_cxr.sol_review import compare_rule_luna_sol


def test_three_way_sol_review_reports_blind_agreement_and_disagreements():
    samples = synthetic_samples()
    luna = synthetic_ai_rows(samples)
    sol = synthetic_ai_rows(samples)
    luna[1]["ai_label"] = "Worse"
    luna[2]["ai_label"] = "Unclear"
    sol[1]["ai_label"] = "Worse"
    sol[3]["ai_label"] = "Stable"
    sol[4]["ai_label"] = "Unclear"

    comparisons, audit = compare_rule_luna_sol(samples, luna, sol)

    assert len(comparisons) == 5
    assert audit["overall"]["six_class_exact"] == 2
    assert audit["overall"]["six_class_agreement"] == 0.4
    assert audit["overall"]["both_decisive_rows"] == 3
    assert audit["overall"]["five_class_exact"] == 2
    assert audit["rule_luna_mismatch"]["rows"] == 1
    assert audit["rule_luna_mismatch"]["resolution_counts"] == {
        "sol_supports_luna": 1,
        "sol_supports_rule": 0,
        "sol_selects_third_label": 0,
        "sol_unclear": 0,
    }
    assert audit["rule_luna_exact"] == {
        "rows": 3,
        "sol_confirms": 1,
        "sol_differs": 1,
        "sol_unclear": 1,
    }
    assert audit["decisive_disagreements"] == {
        "rows": 1,
        "direct_opposite_direction_pairs": 0,
    }
    assert audit["luna_unclear"] == {
        "rows": 1,
        "sol_distribution": {"Worse": 1},
    }
    assert audit["three_way_patterns"] == {
        "all_three_same": 1,
        "at_least_one_unclear": 2,
        "luna_sol_same_rule_differs": 1,
        "rule_luna_same_sol_differs": 1,
    }
    assert audit["agreement_is_luna_accuracy"] is False
    assert audit["formal_training_authorized"] is False


def test_three_way_sol_review_requires_exact_id_sets():
    samples = synthetic_samples()
    rows = synthetic_ai_rows(samples)
    with pytest.raises(ContractError, match="must match exactly"):
        compare_rule_luna_sol(samples, rows, rows[:-1])
