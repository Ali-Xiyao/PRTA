from __future__ import annotations

import json
from pathlib import Path

import pytest

from prta_cxr.cleaned_split_freeze import (
    CleanedSplitContractError,
    _assert_exact_complement,
    require_cleaned_manifest,
)
from prta_cxr.contracts import sha256_file


def test_exact_complement_accepts_disjoint_union() -> None:
    _assert_exact_complement(
        original_ids={"a", "b", "c"},
        retained_ids={"a", "b"},
        excluded_ids={"c"},
    )


def test_exact_complement_rejects_retained_excluded_overlap() -> None:
    with pytest.raises(CleanedSplitContractError, match="overlap"):
        _assert_exact_complement(
            original_ids={"a", "b"},
            retained_ids={"a"},
            excluded_ids={"a", "b"},
        )


def test_cleaned_manifest_gate_rejects_non_frozen_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = tmp_path / "frozen.jsonl"
    alternate = tmp_path / "alternate.jsonl"
    frozen.write_text('{"sample_id":"a"}\n', encoding="utf-8")
    alternate.write_bytes(frozen.read_bytes())
    receipt = {
        "schema": "prta-cxr.cleaned-split-freeze.v1",
        "status": "PASS_CLEANED_SPLIT_FROZEN",
        "physician_review_status": "PHYSICIAN_CONFIRMED_EXCLUDE",
        "physician_decision": "DO_NOT_USE",
        "physician_confirmed_exclusions": 11_667,
        "retained_counts": {
            "train": 80_402,
            "dev": 11_201,
            "internal_test": 13_219,
            "gold": 175,
        },
        "output_paths": {
            "train_dev": str(frozen),
            "internal_test": str(frozen),
            "gold": str(frozen),
        },
        "output_sha256": {
            "train_dev": sha256_file(frozen),
            "internal_test": sha256_file(frozen),
            "gold": sha256_file(frozen),
        },
        "lineage_paths": {"dummy": str(frozen)},
        "lineage_sha256": {"dummy": sha256_file(frozen)},
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(CleanedSplitContractError, match="active frozen path"):
        require_cleaned_manifest(
            alternate,
            receipt_path=receipt_path,
            role="train_dev",
        )


def test_cleaned_manifest_gate_rejects_changed_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = tmp_path / "frozen.jsonl"
    frozen.write_text('{"sample_id":"a"}\n', encoding="utf-8")
    receipt = {
        "schema": "prta-cxr.cleaned-split-freeze.v1",
        "status": "PASS_CLEANED_SPLIT_FROZEN",
        "physician_review_status": "PHYSICIAN_CONFIRMED_EXCLUDE",
        "physician_decision": "DO_NOT_USE",
        "physician_confirmed_exclusions": 11_667,
        "retained_counts": {
            "train": 80_402,
            "dev": 11_201,
            "internal_test": 13_219,
            "gold": 175,
        },
        "output_paths": {
            "train_dev": str(frozen),
            "internal_test": str(frozen),
            "gold": str(frozen),
        },
        "output_sha256": {
            "train_dev": "0" * 64,
            "internal_test": "0" * 64,
            "gold": "0" * 64,
        },
        "lineage_paths": {"dummy": str(frozen)},
        "lineage_sha256": {"dummy": sha256_file(frozen)},
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(CleanedSplitContractError, match="cleaned hash changed"):
        require_cleaned_manifest(
            frozen,
            receipt_path=receipt_path,
            role="train_dev",
        )


def test_cleaned_manifest_portable_projection_reads_only_requested_role(
    tmp_path: Path,
) -> None:
    portable_root = tmp_path / "portable"
    train_dev = portable_root / "manifests" / "train_dev_cleaned_v1.jsonl"
    train_dev.parent.mkdir(parents=True)
    train_dev.write_text('{"sample_id":"a"}\n', encoding="utf-8")
    receipt = {
        "schema": "prta-cxr.cleaned-split-freeze.v1",
        "status": "PASS_CLEANED_SPLIT_FROZEN",
        "physician_review_status": "PHYSICIAN_CONFIRMED_EXCLUDE",
        "physician_decision": "DO_NOT_USE",
        "physician_confirmed_exclusions": 11_667,
        "retained_counts": {
            "train": 80_402,
            "dev": 11_201,
            "internal_test": 13_219,
            "gold": 175,
        },
        "output_paths": {
            "aggregate_summary": r"H:\frozen\aggregate_summary.json",
            "train_dev": r"H:\frozen\manifests\train_dev_cleaned_v1.jsonl",
            "internal_test": r"H:\frozen\manifests\internal_test_cleaned_v1.jsonl",
            "gold": r"H:\frozen\manifests\gold_cleaned_v1.jsonl",
        },
        "output_sha256": {
            "train_dev": sha256_file(train_dev),
            "internal_test": "0" * 64,
            "gold": "0" * 64,
        },
        "lineage_paths": {"protected": r"H:\sealed\lineage.json"},
        "lineage_sha256": {"protected": "0" * 64},
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    value = require_cleaned_manifest(
        train_dev,
        receipt_path=receipt_path,
        role="train_dev",
        portable_root=portable_root,
    )
    assert value["output_sha256"]["train_dev"] == sha256_file(train_dev)
