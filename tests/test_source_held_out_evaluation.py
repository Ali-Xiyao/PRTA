import pytest

from prta_cxr.contracts import canonical_sha256
from prta_cxr.source_held_out_evaluation import (
    target_source_rows,
    validate_source_filter_receipt,
    validate_source_holdout_sources,
)


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


def test_source_holdout_rejects_target_leakage_and_binds_filter_audit():
    config = {"data": {"train_sources": ["train"], "dev_sources": ["train"]}}
    assert validate_source_holdout_sources(config, target_source="target") == (
        ["train"],
        ["train"],
    )
    leaking = {"data": {"train_sources": ["train", "target"], "dev_sources": ["train"]}}
    with pytest.raises(ValueError, match="leaked.*Train"):
        validate_source_holdout_sources(leaking, target_source="target")
    audit = {"train_sources": ["train"], "dev_sources": ["train"]}
    receipt = {"fraction_audit": {"source_filter": audit}}
    hashes = {"source_filter_audit": canonical_sha256(audit)}
    validate_source_filter_receipt(receipt, hashes, expected_source_audit=audit)
    with pytest.raises(ValueError, match="receipt source-filter"):
        validate_source_filter_receipt(
            {"fraction_audit": {"source_filter": {}}},
            hashes,
            expected_source_audit=audit,
        )
