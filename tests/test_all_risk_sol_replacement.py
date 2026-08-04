import json
from pathlib import Path

from prta_cxr.all_risk_sol_replacement import (
    NEW_LABEL_SOURCE,
    apply_all_risk_train_stream,
    build_all_risk_targets,
)
from prta_cxr.cli_labeling import synthetic_samples


def _train_row(index: int) -> dict:
    row = dict(synthetic_samples()[index])
    row["sample_id"] = f"train-{index}"
    row["split"] = "train"
    row["label_source"] = "luna_primary_report_label"
    return row


def test_all_risk_target_union_and_stream_replacement(tmp_path: Path):
    rows = [_train_row(index) for index in range(4)]
    changed = "Worse" if rows[0]["progression_label"] != "Worse" else "New"
    new_review = [
        {
            **rows[0],
            "risk_tier": "Tier B",
            "current_label": rows[0]["progression_label"],
            "sol_label": changed,
            "quality_flags": [],
        },
        {
            **rows[1],
            "risk_tier": "Tier C",
            "current_label": rows[1]["progression_label"],
            "sol_label": "Unclear",
            "quality_flags": ["REPORT_INSUFFICIENT"],
        },
    ]
    pilot = [
        {
            "sample_id": rows[2]["sample_id"],
            "luna_label": rows[2]["progression_label"],
            "sol_label": rows[2]["progression_label"],
        }
    ]
    details = [{**rows[2], "risk_tier": "Tier B"}]
    targets = build_all_risk_targets(
        new_review_rows=new_review,
        pilot_rows=pilot,
        case_detail_rows=details,
        expected_new=2,
        expected_pilot_only=1,
    )
    source = tmp_path / "source.jsonl"
    with source.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    output = tmp_path / "output.jsonl"
    provenance, exclusions, audit = apply_all_risk_train_stream(
        source_train=source,
        targets=targets,
        train_output=output,
        expected_source_rows=4,
        expected_targets=3,
        expected_decisive=2,
        expected_unclear=1,
        expected_changed=1,
        expected_same=1,
        expected_review_baseline_mismatch=0,
    )
    output_rows = [json.loads(line) for line in output.read_text("utf-8").splitlines()]
    output_by_id = {row["sample_id"]: row for row in output_rows}
    assert set(output_by_id) == {"train-0", "train-2", "train-3"}
    assert output_by_id["train-0"]["progression_label"] == changed
    assert output_by_id["train-0"]["label_source"] == NEW_LABEL_SOURCE
    assert output_by_id["train-2"]["label_source"] == NEW_LABEL_SOURCE
    assert output_by_id["train-3"] == rows[3]
    assert len(provenance) == 2
    assert exclusions[0]["sample_id"] == "train-1"
    assert audit["non_target_rows_copied_byte_exact"] == 1


def test_git_safe_all_risk_config_binds_final_counts():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "configs" / "labeling" / "sol_authoritative_all_risk_v1.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["status"] == "ACTIVE_SOL_AUTHORITATIVE_ALL_RISK_NOT_TRAINED"
    assert config["row_counts"] == {
        "train": 89406,
        "dev": 13420,
        "train_dev": 102826,
        "internal_test": 13588,
        "gold_physician_consensus": 250,
    }
    assert config["action_counts"]["target_rows"] == 5981
    assert config["action_counts"]["excluded_sol_unclear"] == 1365
    assert config["action_counts"]["label_value_changed"] == 1093
    assert config["artifact_sha256"]["train"] == (
        "3aa67f2a09f0907ca35ea410b78a18e5feb7d8871d311154da71ee49ade3889a"
    )
    assert config["artifact_sha256"]["train_dev"] == (
        "a39e03e64ac43faed9348d3f8aabe79eede8bf2e398bff7cb2b795673ca1aa41"
    )
    assert config["training_execution_enabled"] is False
    assert config["model_metrics_computed"] is False
