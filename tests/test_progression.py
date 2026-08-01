import pytest

from prta_cxr.evaluation.progression import (
    build_pair_and_entity_manifests,
    deterministic_patient_folds,
    progression_rows_from_predictions,
)


def record(index: int, label: str) -> dict:
    return {
        "sample_id": f"s{index}",
        "patient_id_hash": f"p{index}",
        "prior_study_id": f"prior-{index}",
        "current_study_id": f"current-{index}",
        "finding": "effusion",
        "progression_label": label,
    }


def test_patient_folds_and_manifests_use_clean_fields():
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    rows = [record(index, labels[index % 5]) for index in range(10)]
    assignment = deterministic_patient_folds(rows, labels=labels, fold_count=2)
    assert set(assignment) == {f"p{index}" for index in range(10)}
    pairs, entities = build_pair_and_entity_manifests(rows)
    assert len(pairs) == len(entities) == 10
    assert entities[0]["sample_id"].startswith("s")


def test_prediction_binding_fails_closed():
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    rows = [record(0, "Stable")]
    bound = progression_rows_from_predictions(rows, {"s0": "Stable"}, labels=labels)
    assert bound[0]["patient_id"] == "p0"
    with pytest.raises(ValueError, match="exactly"):
        progression_rows_from_predictions(rows, {}, labels=labels)
