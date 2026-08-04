import json
from pathlib import Path

from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.sol_label_replacement import (
    NEW_LABEL_SOURCE,
    OLD_LABEL_SOURCE,
    apply_sol_labels,
)


def test_decisive_sol_replaces_luna_and_unclear_is_excluded():
    rows = []
    for index, row in enumerate(synthetic_samples()[:3]):
        value = dict(row)
        value["sample_id"] = f"dev-{index}"
        value["split"] = "dev"
        value["label_source"] = OLD_LABEL_SOURCE
        rows.append(value)
    changed = "Worse" if rows[1]["progression_label"] != "Worse" else "New"
    review = {
        "dev-0": {
            "current_label": rows[0]["progression_label"],
            "sol_label": rows[0]["progression_label"],
            "quality_flags": [],
        },
        "dev-1": {
            "current_label": rows[1]["progression_label"],
            "sol_label": changed,
            "quality_flags": [],
        },
        "dev-2": {
            "current_label": rows[2]["progression_label"],
            "sol_label": "Unclear",
            "quality_flags": ["REPORT_INSUFFICIENT"],
        },
    }
    retained, provenance, exclusions, audit = apply_sol_labels(
        rows,
        review,
        cohort="dev",
        expected_rows=3,
        expected_retained=2,
        expected_unclear=1,
        expected_changed=1,
        expected_same=1,
    )
    assert [row["sample_id"] for row in retained] == ["dev-0", "dev-1"]
    assert retained[1]["progression_label"] == changed
    assert all(row["label_source"] == NEW_LABEL_SOURCE for row in retained)
    assert len(provenance) == 2
    assert exclusions == [
        {
            "sample_id": "dev-2",
            "cohort": "dev",
            "source": rows[2]["source"],
            "finding": rows[2]["finding"],
            "luna_label": rows[2]["progression_label"],
            "sol_label": "Unclear",
            "quality_flags": ["REPORT_INSUFFICIENT"],
            "action": "exclude_sol_unclear",
        }
    ]
    assert audit["label_value_changed_rows"] == 1
    assert audit["authority_rebound_same_label_rows"] == 1


def test_git_safe_active_config_binds_the_audited_label_version():
    repo_root = Path(__file__).resolve().parents[1]
    config_path = (
        repo_root / "configs" / "labeling" / "sol_authoritative_protected_v1.json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["status"] == "ACTIVE_SOL_AUTHORITATIVE_NOT_TRAINED"
    assert config["unclear_policy"] == "exclude_not_coerce"
    assert config["gold_policy"] == "physician_consensus_unchanged"
    assert config["row_counts"] == {
        "train": 90771,
        "dev": 13420,
        "train_dev": 104191,
        "internal_test": 13588,
        "gold_physician_consensus": 250,
    }
    assert config["artifact_sha256"]["train_dev"] == (
        "478e7cce0d4d25e7343ddbcc910a5b5a3e4e72e570a60fe07cea2f1078a4cd21"
    )
    assert config["artifact_sha256"]["internal_test"] == (
        "fe76a30e63430b0ce2fa1b40f194b83cb1b31938f6b89a6d1136b4b924b44305"
    )
    assert config["gold_physician_labels_modified"] == 0
    assert config["training_execution_enabled"] is False
    assert config["model_metrics_computed"] is False
