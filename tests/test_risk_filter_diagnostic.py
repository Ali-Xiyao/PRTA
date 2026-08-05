import csv
import json
from pathlib import Path

import pytest

from prta_cxr.risk_filter_diagnostic import (
    RiskFilterContractError,
    _filter_jsonl_byte_exact,
    build_diagnostic_config,
    load_risk_candidates,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_risk_candidates_require_contiguous_global_ranks(tmp_path: Path):
    path = tmp_path / "risk.csv"
    rows = [
        {
            "sample_id": "a",
            "split": "train",
            "rank_global": "1",
            "priority_band": "Top 3%",
            "candidate_reasons": "reason",
            "active_inclusion": "True",
        },
        {
            "sample_id": "b",
            "split": "dev",
            "rank_global": "2",
            "priority_band": "3-5%",
            "candidate_reasons": "reason",
            "active_inclusion": "True",
        },
    ]
    _write_csv(path, rows)
    result = load_risk_candidates(
        path,
        expected_splits={"train": 1, "dev": 1},
        expected_bands={"Top 3%": 1, "3-5%": 1},
    )
    assert [row["sample_id"] for row in result] == ["a", "b"]
    rows[1]["rank_global"] = "3"
    _write_csv(path, rows)
    with pytest.raises(RiskFilterContractError, match="not contiguous"):
        load_risk_candidates(
            path,
            expected_splits={"train": 1, "dev": 1},
            expected_bands={"Top 3%": 1, "3-5%": 1},
        )


def test_filter_preserves_retained_jsonl_bytes_and_marks_exact_id(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    rows = [
        {
            "sample_id": "drop",
            "split": "train",
            "patient_id_hash": "p1",
            "progression_label": "Stable",
        },
        {
            "sample_id": "keep",
            "split": "train",
            "patient_id_hash": "p2",
            "progression_label": "Worse",
        },
    ]
    lines = [json.dumps(row, separators=(",", ":")) + "\n" for row in rows]
    source.write_text("".join(lines), encoding="utf-8")
    output = tmp_path / "filtered.jsonl"
    audit = _filter_jsonl_byte_exact(
        source,
        output,
        candidate_index={"drop": {"split": "train"}},
        allowed_splits={"train"},
    )
    assert output.read_text(encoding="utf-8") == lines[1]
    assert audit["removed_ids"] == {"drop"}
    assert audit["retained_ids"] == {"keep"}


def test_diagnostic_config_keeps_parent_budget_and_binds_counts():
    parent = {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "OLD",
        "seed": 29,
        "model": {"family": "prta"},
        "data": {"train_fraction": 1.0},
        "optimization": {"epochs": 20, "batch_size": 16},
        "loss_weights": {"classification": 1.0},
        "classification_loss": {"class_counts": [1, 1, 1, 1, 1]},
    }
    result = build_diagnostic_config(
        parent,
        train_label_counts={
            "Stable": 10,
            "Improved": 20,
            "Worse": 30,
            "New": 40,
            "Resolved": 50,
        },
        exclusion_sha256="a" * 64,
    )
    assert result["seed"] == 17
    assert result["optimization"] == parent["optimization"]
    assert result["classification_loss"]["class_counts"] == [10, 20, 30, 40, 50]
    assert result["diagnostic_metadata"]["outcome_adaptive_selection_bias"]
