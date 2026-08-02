import json
from pathlib import Path

import pytest

from prta_cxr.contracts import (
    INVERSION,
    PROGRESSION_LABELS,
    SAMPLE_FIELDS,
    ContractError,
    validate_luna_batch,
    validate_sample,
)
from prta_cxr.labeling import merge_luna_labels


def sample() -> dict:
    return {
        "sample_id": "sample-1",
        "patient_id_hash": "patient-hash-1",
        "source": "fixture",
        "prior_study_id": "study-1",
        "current_study_id": "study-2",
        "prior_image_path": "images/prior.jpg",
        "current_image_path": "images/current.jpg",
        "prior_report": "moderate right pleural effusion",
        "current_report": "decreased to small residual right pleural effusion",
        "prior_datetime": "2025-01-01T00:00:00",
        "current_datetime": "2025-01-03T00:00:00",
        "interval_days": 2,
        "interval_basis": "calendar",
        "calendar_interval_available": True,
        "interval_semantics": "elapsed_calendar_days",
        "prior_view": "PA",
        "current_view": "PA",
        "finding": "Pleural Effusion",
        "progression_label": "Improved",
        "label_source": "rule_candidate",
        "label_tier": "Tier-B",
    }


def luna() -> dict:
    return {
        "sample_id": "sample-1",
        "finding": "Pleural Effusion",
        "verified_label": "Improved",
        "decision": "accept",
        "prior_evidence": "moderate right pleural effusion",
        "current_evidence": "small residual right pleural effusion",
        "comparison_evidence": "decreased",
        "comparison_matches_selected_prior": True,
        "finding_match": True,
        "negation_conflict": False,
        "uncertainty_conflict": False,
        "temporal_conflict": False,
        "reason_code": "explicit_direction_consistent_state",
    }


def test_five_labels_and_inversion_are_closed():
    assert set(INVERSION) == set(PROGRESSION_LABELS)
    assert all(INVERSION[INVERSION[label]] == label for label in PROGRESSION_LABELS)


def test_sample_json_schema_matches_runtime_contract():
    schema = json.loads(
        Path("schemas/sample.schema.json").read_text(encoding="utf-8")
    )
    assert set(schema["required"]) == SAMPLE_FIELDS
    assert set(schema["properties"]) == SAMPLE_FIELDS


def test_sample_and_luna_merge_to_tier_a():
    assert validate_sample(sample())["progression_label"] == "Improved"
    merged, counts = merge_luna_labels([sample()], [luna()])
    assert counts == {"Tier-A": 1, "Tier-B": 0, "Reject": 0}
    assert merged[0]["label_tier"] == "Tier-A"


def test_luna_fail_closed_on_extra_unknown_duplicate_and_conflict():
    extra = luna() | {"free_text": "not allowed"}
    with pytest.raises(ContractError):
        validate_luna_batch([extra])
    unknown = luna() | {"verified_label": "Better"}
    with pytest.raises(ContractError):
        validate_luna_batch([unknown])
    with pytest.raises(ContractError):
        validate_luna_batch([luna(), luna()])
    conflict = luna() | {"negation_conflict": True}
    assert validate_luna_batch([conflict])[0]["negation_conflict"] is True
    merged, counts = merge_luna_labels([sample()], [conflict])
    assert counts["Reject"] == 1
    assert merged[0]["label_gate"]["deterministic_reject_reason"] == (
        "accept_with_conflict"
    )


def test_merge_rejects_non_extractive_accepted_evidence():
    paraphrased = luna() | {"comparison_evidence": "the fluid got smaller"}
    merged, counts = merge_luna_labels([sample()], [paraphrased])
    assert counts == {"Tier-A": 0, "Tier-B": 0, "Reject": 1}
    assert merged[0]["label_gate"]["deterministic_reject_reason"] == (
        "non_extractive_evidence"
    )
