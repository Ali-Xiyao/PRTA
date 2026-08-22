import json

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.data.selection_manifest import require_train_only_selection_manifest


def test_train_only_selection_manifest_closes_protected_surfaces(tmp_path):
    manifest = tmp_path / "train_only.jsonl"
    freeze = tmp_path / "cleaned_split_freeze.json"
    receipt_path = tmp_path / "selection_receipt.json"
    manifest.write_text('{"sample_id":"sample-1"}\n', encoding="utf-8")
    freeze.write_text('{"status":"PASS"}\n', encoding="utf-8")
    closed = {
        "current_dev_used_for_selection": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }
    receipt = {
        "schema": "prta-cxr.slim-selection-manifest.v1",
        "status": "PASS_SLIM_SELECTION_MANIFEST_FROZEN",
        "derived_manifest_sha256": sha256_file(manifest),
        "cleaned_split_freeze_sha256": sha256_file(freeze),
        "split_audit": {
            "status": "PASS_SLIM_TRAIN_ONLY_PATIENT_SPLIT",
            "patient_overlap": [],
            "source_train_rows": 1,
            "derived_rows": 1,
            "source_train_roster_sha256": "same-roster",
            "derived_roster_sha256": "same-roster",
            **closed,
        },
        **closed,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    validated = require_train_only_selection_manifest(
        manifest,
        selection_receipt_path=receipt_path,
        cleaned_split_freeze=freeze,
    )
    assert validated["status"] == "PASS_SLIM_SELECTION_MANIFEST_FROZEN"

    receipt["external_opened"] = True
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="external_opened"):
        require_train_only_selection_manifest(
            manifest,
            selection_receipt_path=receipt_path,
            cleaned_split_freeze=freeze,
        )
