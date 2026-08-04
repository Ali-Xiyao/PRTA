import json
from pathlib import Path

from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.tier_bc_sol_review import build_missing_tier_bc_candidates


def test_tier_bc_roster_excludes_every_prior_sol_namespace():
    base = synthetic_samples()
    details = []
    layout = [
        ("a", "Tier B", "train"),
        ("b", "Tier B", "train"),
        ("c", "Tier C", "train"),
        ("d", "Tier C", "dev"),
    ]
    for index, (sample_id, tier, split) in enumerate(layout):
        details.append(
            base[index % len(base)]
            | {"sample_id": sample_id, "risk_tier": tier, "split": split}
        )
    candidates, metadata, coverage = build_missing_tier_bc_candidates(
        details,
        {
            "tier_a": set(),
            "protected": {"d"},
            "pilot": {"b", "d"},
        },
        expected_total=4,
        expected_missing=2,
        expected_totals={
            "Tier B|train": 2,
            "Tier C|dev": 1,
            "Tier C|train": 1,
        },
        expected_missing_by_tier_split={
            "Tier B|train": 1,
            "Tier C|train": 1,
        },
    )
    assert [row["sample_id"] for row in candidates] == ["a", "c"]
    assert metadata == [
        {"sample_id": "a", "risk_tier": "Tier B"},
        {"sample_id": "c", "risk_tier": "Tier C"},
    ]
    assert coverage["already_reviewed_union"] == 2
    assert coverage["multi_namespace_rows"] == 1
    assert coverage["review_hits_by_namespace"] == {
        "tier_a": 0,
        "protected": 1,
        "pilot": 2,
    }


def test_tier_bc_roster_rejects_any_unreviewed_dev_row():
    row = synthetic_samples()[0] | {
        "sample_id": "dev-missing",
        "risk_tier": "Tier C",
        "split": "dev",
    }
    try:
        build_missing_tier_bc_candidates(
            [row],
            {"protected": set()},
            expected_total=1,
            expected_missing=1,
            expected_totals={"Tier C|dev": 1},
            expected_missing_by_tier_split={"Tier C|dev": 1},
        )
    except RuntimeError as error:
        assert "Train-only" in str(error)
    else:
        raise AssertionError("unreviewed Dev must fail closed")


def test_git_safe_tier_bc_config_binds_completed_read_only_review():
    repo_root = Path(__file__).resolve().parents[1]
    config = json.loads(
        (
            repo_root / "configs" / "labeling" / "tier_bc_sol_blind_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert config["status"] == "PASS_READ_ONLY_TIER_BC_SOL_REVIEW"
    assert config["model"] == "gpt-5.6-sol"
    assert config["reasoning_effort"] == "medium"
    assert config["coverage"] == {
        "tier_bc_total": 13334,
        "previously_reviewed_union": 7366,
        "reviewed_now": 5968,
        "tier_b_train_reviewed_now": 2912,
        "tier_c_train_reviewed_now": 3056,
        "batches": 299,
        "shard_receipts": 30,
        "failed_attempts": 0,
    }
    assert config["labels_modified"] == 0
    assert config["samples_deleted"] == 0
    assert config["splits_modified"] == 0
    assert config["training_started"] is False
    assert config["post_relabel_metrics_computed"] is False
