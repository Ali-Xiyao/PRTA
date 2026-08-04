from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.tier_a_sol_review import (
    build_tier_a_candidates,
    compare_luna_sol,
)


def _details():
    rows = []
    for index, sample in enumerate(synthetic_samples()):
        rows.append(sample | {"risk_tier": "Tier A", "split": "train"})
        rows[-1]["sample_id"] = f"tier-a-{index}"
    return rows


def test_tier_a_candidates_are_exact_train_only_and_sorted():
    rows = list(reversed(_details()))
    candidates = build_tier_a_candidates(rows, expected_rows=5)
    assert [row["sample_id"] for row in candidates] == sorted(
        row["sample_id"] for row in rows
    )


def test_sol_luna_comparison_preserves_unclear_and_disagreement_boundary():
    candidates = build_tier_a_candidates(_details(), expected_rows=5)
    sol_rows = [
        {"sample_id": row["sample_id"], "ai_label": row["progression_label"]}
        for row in candidates
    ]
    sol_rows[0]["ai_label"] = "Unclear"
    sol_rows[1]["ai_label"] = "Worse"
    comparisons, summary = compare_luna_sol(candidates, sol_rows)
    assert len(comparisons) == 5
    assert summary["overall"]["sol_unclear"] == 1
    assert summary["overall"]["decisive_rows"] == 4
    assert summary["overall"]["cohen_kappa_decisive_five_class"] is not None
    assert summary["claim_boundary"].startswith("Sol-Luna disagreement")
