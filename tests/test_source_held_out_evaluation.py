import pytest

from prta_cxr.source_held_out_evaluation import target_source_rows


def test_target_source_rows_uses_only_target_dev():
    rows = [
        {"sample_id": "a", "split": "train", "source": "x"},
        {"sample_id": "b", "split": "dev", "source": "x"},
        {"sample_id": "c", "split": "dev", "source": "y"},
    ]
    assert [
        row["sample_id"] for row in target_source_rows(rows, target_source="y")
    ] == ["c"]
    with pytest.raises(ValueError, match="no Dev"):
        target_source_rows(rows, target_source="z")
