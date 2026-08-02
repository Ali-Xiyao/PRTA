import json

import pytest

from prta_cxr.contracts import PROGRESSION_LABELS, ContractError
from prta_cxr.quality_gate import load_completed_human_silver_audit


def _receipt():
    sources = ["mimic_cxr", "chexpert_plus"]
    return {
        "schema": "prta-cxr.human-silver-accuracy-audit.v1",
        "status": "PASS_HUMAN_SILVER_ACCURACY_AUDIT",
        "completed": True,
        "reviewed_rows": 250,
        "stratification": "source_x_five_label",
        "sources": sources,
        "labels": list(PROGRESSION_LABELS),
        "silver_accuracy": 0.92,
        "accuracy_by_source": {source: 0.92 for source in sources},
        "accuracy_by_label": {label: 0.92 for label in PROGRESSION_LABELS},
        "strata_counts": {
            f"{source}|{label}": 25
            for source in sources
            for label in PROGRESSION_LABELS
        },
        "review_manifest_sha256": "a" * 64,
    }


def test_completed_human_silver_audit_passes(tmp_path):
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(_receipt()), encoding="utf-8")
    assert load_completed_human_silver_audit(path)["reviewed_rows"] == 250


@pytest.mark.parametrize(
    ("update", "match"),
    (
        ({"completed": False}, "not complete"),
        ({"reviewed_rows": 199}, "200-300"),
        ({"stratification": "overall"}, "stratification"),
        ({"labels": ["Stable"]}, "five labels"),
        ({"strata_counts": {}}, "strata"),
    ),
)
def test_incomplete_or_unstratified_human_audit_fails(tmp_path, update, match):
    value = _receipt() | update
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ContractError, match=match):
        load_completed_human_silver_audit(path)
