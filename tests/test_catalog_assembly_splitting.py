import json

import pytest

from prta_cxr.contracts import ContractError
from prta_cxr.data.assembly import (
    build_full_candidate_pairs,
    hashed_patient_id,
    normalize_studies,
)
from prta_cxr.data.catalog import SourceSpec, load_source_catalog
from prta_cxr.data.exclusions import load_exclusion_registry
from prta_cxr.data.splitting import patient_stratified_split


def source(*, status: str = "debug_only_legacy", allowed: bool = True) -> SourceSpec:
    return SourceSpec(
        source_id="fixture",
        patient_namespace="fixture",
        manifest_env="PRTA_FIXTURE_UNUSED",
        status=status,
        allowed_official_splits=("train",),
        longitudinal_reports=True,
        license_verified=allowed,
        deidentified=allowed,
        processing_allowed=allowed,
    )


def study(
    patient: str,
    visit: int,
    *,
    view: str = "PA",
    time_basis: str = "calendar",
) -> dict:
    return {
        "patient_id": patient,
        "study_id": f"{patient}-study-{visit}",
        "image_id": f"{patient}-image-{visit}",
        "image_path": f"images/{patient}-{visit}.png",
        "report": f"report {visit}",
        "study_datetime": f"2025-01-{visit + 1:02d}T00:00:00",
        "time_basis": time_basis,
        "view": view,
        "official_split": "train",
    }


def test_catalog_requires_governance_but_reactivates_debug_only(tmp_path):
    catalog = {
        "schema": "prta-cxr.source-catalog.v1",
        "policy": "full-authorized-repartition-v1",
        "debug_only_isolation_retired": True,
        "default_split_fractions": {
            "train": 0.8,
            "dev": 0.1,
            "internal_test": 0.1,
        },
        "sources": [
            {
                "source_id": "old_debug",
                "patient_namespace": "fixture",
                "manifest_env": "PRTA_FIXTURE_UNUSED",
                "status": "debug_only_legacy",
                "allowed_official_splits": ["train"],
                "longitudinal_reports": True,
                "license_verified": True,
                "deidentified": True,
                "processing_allowed": True,
            }
        ],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    loaded = load_source_catalog(path)
    audit = loaded.audit()
    assert audit["eligible_source_count"] == 1
    assert audit["sources"][0]["debug_only_reactivated"] is True
    assert source(status="revealed_test").eligible_for_repartition is False
    assert source(allowed=False).eligible_for_repartition is False


def test_normalization_hashes_patients_excludes_and_selects_one_frontal():
    blocked = hashed_patient_id("fixture", "blocked")
    rows = [
        study("kept", 0, view="AP"),
        study("kept", 0, view="PA") | {"image_id": "preferred-pa"},
        study("kept", 1),
        study("blocked", 0),
        study("blocked", 1),
    ]
    normalized, audit = normalize_studies(
        source(), rows, excluded_patient_hashes=frozenset({blocked})
    )
    assert len(normalized) == 2
    assert normalized[0]["image_id"] == "preferred-pa"
    assert audit["diagnostics"]["protected_patient"] == 2
    assert audit["raw_patient_ids_persisted"] is False
    assert audit["time_bases"] == {"calendar": 2}
    assert all("patient_id" not in row for row in normalized)
    pairs, pair_audit = build_full_candidate_pairs({"fixture": normalized})
    assert len(pairs) == 1
    assert pair_audit["debug_only_isolation_inherited"] is False


def test_normalization_deduplicates_ambiguous_patient_timepoints():
    rows = [
        study("kept", 0, view="AP"),
        study("kept", 1, view="PA")
        | {
            "study_datetime": "2025-01-01T00:00:00",
            "image_id": "preferred-pa-at-same-time",
        },
        study("kept", 2, view="PA"),
    ]
    normalized, audit = normalize_studies(source(), rows)
    assert len(normalized) == 2
    assert normalized[0]["image_id"] == "preferred-pa-at-same-time"
    assert audit["diagnostics"]["duplicate_patient_time"] == 1
    pairs, _ = build_full_candidate_pairs({"fixture": normalized})
    assert len(pairs) == 1
    assert pairs[0]["interval_days"] > 0


def test_exclusion_registry_accepts_hashes_only(tmp_path):
    patient = hashed_patient_id("fixture", "p1")
    path = tmp_path / "exclusions.json"
    path.write_text(
        json.dumps(
            {
                "schema": "prta-cxr.patient-exclusions.v1",
                "categories": [
                    {
                        "category": "revealed_historical_test",
                        "patient_id_hashes": [patient],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    excluded, audit = load_exclusion_registry(path)
    assert excluded == frozenset({patient})
    assert audit["outcome_fields_read"] == []
    path.write_text(
        json.dumps(
            {
                "schema": "prta-cxr.patient-exclusions.v1",
                "categories": [
                    {
                        "category": "revealed_historical_test",
                        "patient_id_hashes": ["raw-patient-id"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="SHA-256"):
        load_exclusion_registry(path)


def test_new_split_is_patient_disjoint_and_does_not_inherit_old_partition():
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    rows = []
    for patient in range(30):
        for sample in range(2):
            rows.append(
                {
                    "sample_id": f"sample-{patient}-{sample}",
                    "patient_id_hash": f"hash-{patient}",
                    "source": "fixture",
                    "finding": "Effusion" if patient % 2 else "Edema",
                    "progression_label": labels[(patient + sample) % len(labels)],
                    "old_debug_partition": "tiny_debug_only",
                }
            )
    split_rows, audit = patient_stratified_split(
        rows,
        fractions={"train": 0.8, "dev": 0.1, "internal_test": 0.1},
    )
    patient_splits = {}
    for row in split_rows:
        patient_splits.setdefault(row["patient_id_hash"], set()).add(row["split"])
    assert all(len(values) == 1 for values in patient_splits.values())
    assert audit["patient_overlap"] == 0
    assert audit["debug_roster_inherited"] is False
    assert set(audit["splits"]) == {"train", "dev", "internal_test"}
