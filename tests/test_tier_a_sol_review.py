import json

from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.tier_a_sol_review import (
    apply_sol_authority_stream,
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


def test_sol_authority_replaces_decisive_and_excludes_unclear(tmp_path):
    train_rows = _details()
    candidates = build_tier_a_candidates(train_rows, expected_rows=5)[:3]
    dev = synthetic_samples()[0] | {"sample_id": "dev-0", "split": "dev"}
    source = tmp_path / "train_dev.jsonl"
    source_rows = [*train_rows, dev]
    source.write_text(
        "".join(
            json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
            for row in source_rows
        ),
        encoding="utf-8",
    )
    changed = (
        "Worse" if candidates[1]["progression_label"] != "Worse" else "Improved"
    )
    sol_rows = [
        {
            "sample_id": candidates[0]["sample_id"],
            "ai_label": candidates[0]["progression_label"],
        },
        {"sample_id": candidates[1]["sample_id"], "ai_label": changed},
        {"sample_id": candidates[2]["sample_id"], "ai_label": "Unclear"},
    ]
    train_output = tmp_path / "train_v2.jsonl"
    combined_output = tmp_path / "train_dev_v2.jsonl"
    provenance, exclusions, audit = apply_sol_authority_stream(
        source_manifest=source,
        train_ids={row["sample_id"] for row in train_rows},
        candidates=candidates,
        sol_rows=sol_rows,
        train_output=train_output,
        train_dev_output=combined_output,
        expected_train_rows=5,
        expected_dev_rows=1,
        expected_tier_a_rows=3,
        expected_decisive_rows=2,
        expected_unclear_rows=1,
        expected_changed_labels=1,
        expected_same_labels=1,
    )
    assert len(provenance) == 2
    assert len(exclusions) == 1
    assert audit["train_output_rows"] == 4
    assert audit["train_dev_output_rows"] == 5
    assert audit["dev_rows_copied_byte_exact"] == 1
    assert "dev-0" in combined_output.read_text(encoding="utf-8")
    assert "dev-0" not in train_output.read_text(encoding="utf-8")
