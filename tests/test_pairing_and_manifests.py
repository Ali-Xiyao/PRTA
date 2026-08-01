import pytest

from prta_cxr.contracts import ContractError
from prta_cxr.data.manifests import audit_patient_disjoint_splits
from prta_cxr.data.pairing import build_adjacent_pairs


def study(patient: str, study_id: str, timestamp: str, view: str = "PA") -> dict:
    return {
        "patient_id_hash": patient,
        "source": "fixture",
        "study_id": study_id,
        "image_path": f"images/{study_id}.jpg",
        "report": f"report {study_id}",
        "datetime": timestamp,
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
