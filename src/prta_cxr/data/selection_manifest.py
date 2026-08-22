from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prta_cxr.contracts import sha256_file


def require_train_only_selection_manifest(
    manifest_path: Path,
    *,
    selection_receipt_path: Path,
    cleaned_split_freeze: Path,
) -> dict[str, Any]:
    """Validate the immutable train-only selection surface used by PRTA-CXR."""
    receipt = json.loads(selection_receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "prta-cxr.slim-selection-manifest.v1":
        raise ValueError("unsupported train-only selection receipt schema")
    if receipt.get("status") != "PASS_SLIM_SELECTION_MANIFEST_FROZEN":
        raise ValueError("train-only selection manifest is not frozen")
    if sha256_file(manifest_path) != receipt.get("derived_manifest_sha256"):
        raise ValueError("derived manifest hash drift")
    if sha256_file(cleaned_split_freeze) != receipt.get(
        "cleaned_split_freeze_sha256"
    ):
        raise ValueError("cleaned-split authority drift")

    audit = dict(receipt.get("split_audit", {}))
    if audit.get("status") != "PASS_SLIM_TRAIN_ONLY_PATIENT_SPLIT":
        raise ValueError("train-only split audit is not PASS")
    if audit.get("patient_overlap") != []:
        raise ValueError("train-only split audit reports patient leakage")
    if audit.get("source_train_rows") != audit.get("derived_rows"):
        raise ValueError("derived train-only roster is incomplete")
    if audit.get("source_train_roster_sha256") != audit.get(
        "derived_roster_sha256"
    ):
        raise ValueError("derived train-only roster identity drift")

    protected_flags = (
        "current_dev_used_for_selection",
        "internal_test_opened",
        "gold_opened",
        "external_opened",
    )
    for surface in (audit, receipt):
        for key in protected_flags:
            if surface.get(key) is not False:
                raise ValueError(f"protected split flag is not closed: {key}")
        if surface.get("protected_outcome_read_count") != 0:
            raise ValueError("selection surface reports protected reads")
    return receipt
