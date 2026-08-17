import json

import pytest

from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.slim_export import export_slim_results
from prta_cxr.slim_matrix import SEEDS, SLIM_ARMS


def _result():
    return {
        "schema": "prta-cxr.slim-matrix-final.v1",
        "status": "PASS_SLIM_MATRIX_SELECTED",
        "selected_arm": "Slim-S3",
        "selection_disposition": "SELECTED_SIMPLEST_WITHIN_FROZEN_TOLERANCES",
        "selection_performed": True,
        "winner_selected": True,
        "arm_summaries": {
            arm: {
                "seeds": {str(seed): {"macro_f1": 0.5} for seed in SEEDS},
                "per_class_recall": {
                    label: {"mean": 0.5, "sd": 0.01} for label in PROGRESSION_LABELS
                },
            }
            for arm in SLIM_ARMS
        },
        "current_dev_used_for_selection": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }


def test_export_writes_aggregate_table_and_narrative(tmp_path):
    final = tmp_path / "final.json"
    final.write_text(json.dumps(_result()), encoding="utf-8")
    markdown = tmp_path / "final.md"
    markdown.write_text("# Safe aggregate\n", encoding="utf-8")
    result = export_slim_results(
        final_json=final,
        final_markdown=markdown,
        repo_root=tmp_path,
    )
    assert result["status"] == "PASS_SLIM_RESULTS_EXPORTED"
    assert result["selected_arm"] == "Slim-S3"
    assert (tmp_path / "paper/data/12_PRTA-CXR-Slim最小矩阵结果.json").is_file()
    narrative = (tmp_path / "paper/09_PRTA-CXR-Slim最终叙事_CN.md").read_text(
        encoding="utf-8"
    )
    assert "不保留这两个可选辅助目标" in narrative


def test_export_rejects_protected_or_path_bearing_result(tmp_path):
    value = _result()
    value["checkpoint_path"] = "/ipfs/private.pt"
    final = tmp_path / "final.json"
    final.write_text(json.dumps(value), encoding="utf-8")
    markdown = tmp_path / "final.md"
    markdown.write_text("# Safe aggregate\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden key"):
        export_slim_results(
            final_json=final,
            final_markdown=markdown,
            repo_root=tmp_path,
        )
