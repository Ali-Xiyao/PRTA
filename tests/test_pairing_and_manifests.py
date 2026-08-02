import pytest

from prta_cxr.contracts import ContractError
from prta_cxr.data.manifests import audit_patient_disjoint_splits
from prta_cxr.data.pairing import build_adjacent_pairs


def study(
    patient: str,
    study_id: str,
    timestamp: str,
    view: str = "PA",
    time_basis: str = "calendar",
) -> dict:
    return {
        "patient_id_hash": patient,
        "source": "fixture",
        "study_id": study_id,
        "image_path": f"images/{study_id}.jpg",
        "report": f"report {study_id}",
        "datetime": timestamp,
        "time_basis": time_basis,
        "view": view,
    }


def test_pairing_is_adjacent_patient_local_and_time_ordered():
    rows = [
        study("p1", "s3", "2025-01-03T00:00:00"),
        study("p2", "x1", "2025-01-01T00:00:00"),
        study("p1", "s1", "2025-01-01T00:00:00"),
        study("p1", "s2", "2025-01-02T00:00:00"),
    ]
    pairs = build_adjacent_pairs(rows)
    assert [(row["prior_study_id"], row["current_study_id"]) for row in pairs] == [
        ("s1", "s2"),
        ("s2", "s3"),
    ]
    assert all(row["patient_id_hash"] == "p1" for row in pairs)
    assert all(row["calendar_interval_available"] for row in pairs)


def test_pairing_preserves_ordinal_time_without_claiming_calendar_days():
    rows = [
        study(
            "p1",
            "s1",
            "2000-01-01T00:00:00",
            time_basis="within_patient_ordinal",
        ),
        study(
            "p1",
            "s3",
            "2000-01-03T00:00:00",
            time_basis="within_patient_ordinal",
        ),
    ]
    pair = build_adjacent_pairs(rows)[0]
    assert pair["interval_days"] == 2
    assert pair["interval_basis"] == "within_patient_ordinal"
    assert pair["calendar_interval_available"] is False
    assert pair["interval_semantics"].endswith("not_calendar_days")


def test_patient_leakage_audit_passes_and_fails_closed():
    report = audit_patient_disjoint_splits(
        [
            {"sample_id": "a", "patient_id_hash": "p1", "split": "train"},
            {"sample_id": "b", "patient_id_hash": "p2", "split": "dev"},
        ]
    )
    assert report["patient_overlap"] == 0
    with pytest.raises(ContractError, match="leakage"):
        audit_patient_disjoint_splits(
            [
                {"patient_id_hash": "p1", "split": "train"},
                {"patient_id_hash": "p1", "split": "test"},
            ]
        )
