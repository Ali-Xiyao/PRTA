import json

import pytest

from prta_cxr.authorization import FormalExecutionBlocked
from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.cli_luna_primary import _validate_full_merge_authority
from prta_cxr.contracts import ContractError, canonical_sha256
from prta_cxr.luna_primary import (
    apply_training_patient_quarantine,
    merge_luna_primary,
    select_gold_audit_roster,
)


def _ai_rows(samples):
    return [
        {"sample_id": row["sample_id"], "ai_label": row["progression_label"]}
        for row in samples
    ]


def _large_silver_pool():
    templates = synthetic_samples()
    rows = []
    for source in ("mimic", "chexpert"):
        for patient in range(150):
            row = templates[patient % 5].copy()
            row["sample_id"] = f"{source}-{patient}"
            row["patient_id_hash"] = f"{source}-patient-{patient}"
            row["source"] = source
            row["label_source"] = "luna_primary_report_label"
            row["label_tier"] = "Silver"
            rows.append(row)
    return rows


def test_luna_label_is_primary_and_rule_mismatch_does_not_veto():
    samples = synthetic_samples()
    luna_rows = _ai_rows(samples)
    luna_rows[0]["ai_label"] = "Worse"
    accepted, discarded, audit = merge_luna_primary(samples, luna_rows)
    accepted_by_id = {row["sample_id"]: row for row in accepted}
    assert not discarded
    assert accepted_by_id[samples[0]["sample_id"]]["progression_label"] == "Worse"
    assert accepted_by_id[samples[0]["sample_id"]]["label_source"] == (
        "luna_primary_report_label"
    )
    assert audit["accepted_silver_rows"] == 5
    assert audit["rule_luna_exact_diagnostic"] == 4
    assert audit["rule_label_used_for_admission"] is False


def test_luna_unclear_is_the_only_label_level_discard():
    samples = synthetic_samples()
    luna_rows = _ai_rows(samples)
    luna_rows[2]["ai_label"] = "Unclear"
    accepted, discarded, audit = merge_luna_primary(samples, luna_rows)
    assert len(accepted) == 4
    assert discarded == [
        {
            "sample_id": samples[2]["sample_id"],
            "source": samples[2]["source"],
            "finding": samples[2]["finding"],
            "rule_label": samples[2]["progression_label"],
            "luna_label": "Unclear",
            "rule_luna_exact": False,
            "discard_reason": "luna_unclear",
        }
    ]
    assert audit["discarded_unclear_rows"] == 1


def test_luna_primary_requires_exact_complete_id_set():
    samples = synthetic_samples()
    with pytest.raises(ContractError, match="IDs mismatch"):
        merge_luna_primary(samples, _ai_rows(samples)[:-1])


def test_gold_roster_is_balanced_deterministic_and_patient_quarantined():
    rows = _large_silver_pool()
    roster, quarantine, audit = select_gold_audit_roster(rows)
    roster_again, quarantine_again, audit_again = select_gold_audit_roster(rows)
    assert roster == roster_again
    assert quarantine == quarantine_again
    assert audit == audit_again
    assert len(roster) == 250
    assert len(quarantine) == 250
    assert len({row["patient_id_hash"] for row in roster}) == 250
    assert set(audit["strata"].values()) == {25}
    assert all(row["clinician_label"] is None for row in roster)
    assert all(row["review_status"] == "PENDING_HUMAN_REVIEW" for row in roster)
    assert audit["status"] == "GOLD_PENDING_HUMAN_REVIEW"
    assert audit["gold_rows"] == 0
    assert audit["training_quarantine_required"] is True


def test_gold_roster_quarantine_removes_every_row_for_selected_patients():
    rows = _large_silver_pool()
    duplicate = rows[0].copy()
    duplicate["sample_id"] = "second-finding-same-patient"
    duplicate["finding"] = "Edema"
    rows.append(duplicate)
    _, quarantine, _ = select_gold_audit_roster(rows)
    training, held_out, audit = apply_training_patient_quarantine(
        rows, quarantine
    )
    selected_patients = {row["patient_id_hash"] for row in quarantine}
    assert not selected_patients & {
        row["patient_id_hash"] for row in training
    }
    assert all(row["patient_id_hash"] in selected_patients for row in held_out)
    assert len(training) + len(held_out) == len(rows)
    assert audit["patient_overlap"] == 0
    assert audit["quarantined_silver_rows"] >= 250


def test_full_merge_authority_rejects_incomplete_output_set(tmp_path):
    samples = synthetic_samples()
    config = {
        "admission_policy": "retain_valid_luna_five_class_discard_unclear",
        "rule_label_used_for_admission": False,
        "full_candidate_rows": len(samples),
        "candidate_manifest_sha256": canonical_sha256(samples),
        "batch_size": 2,
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(FormalExecutionBlocked, match="batch set"):
        _validate_full_merge_authority(
            config_path,
            samples,
            [tmp_path / "batch_00000.json"],
            [tmp_path / "batch_00000.json"],
        )
