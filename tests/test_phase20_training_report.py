import json

import pytest

from prta_cxr.phase20_training_report import build_phase20_public_summary


def test_phase20_public_summary_is_aggregate_only(tmp_path):
    final = tmp_path / "final.json"
    value = {
        "status": "PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE",
        "source_commit": "a" * 40,
        "expected_job_count": 88,
        "unique_pass_count": 88,
        "training_cell_count": 63,
        "transformed_map_count": 19,
        "source_held_evaluation_count": 6,
        "training_three_seed_summary": {f"group-{i}": {} for i in range(21)},
        "source_held_three_seed_summary": {f"source-{i}": {} for i in range(2)},
        "selection_performed": False,
        "winner_selected": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
        "training": [{"checkpoint_path": "private"}],
    }
    final.write_text(json.dumps(value), encoding="utf-8")
    result = build_phase20_public_summary(final)
    assert result["counts"]["jobs"] == 88
    assert "training" not in result
    value["protected_outcome_read_count"] = 1
    final.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="protected_outcome_read_count"):
        build_phase20_public_summary(final)
