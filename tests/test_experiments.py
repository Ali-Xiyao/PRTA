from __future__ import annotations

import json

from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.experiments import (
    config_from_spec,
    initial_development_specs,
    materialize_classification_counts,
    nested_train_fraction,
)
from prta_cxr.queue_runner import dependencies_satisfied
from prta_cxr.receipts import RUN_RECEIPT_FIELDS
from prta_cxr.run_registry import read_run_registry, upsert_run_registry


def _rows():
    rows = []
    for patient in range(20):
        rows.append(
            {
                "sample_id": f"train-{patient}",
                "patient_id_hash": f"patient-{patient}",
                "source": "source-a" if patient % 2 else "source-b",
                "progression_label": PROGRESSION_LABELS[patient % 5],
                "split": "train",
            }
        )
    for patient in range(5):
        rows.append(
            {
                "sample_id": f"dev-{patient}",
                "patient_id_hash": f"dev-patient-{patient}",
                "source": "source-a",
                "progression_label": PROGRESSION_LABELS[patient],
                "split": "dev",
            }
        )
    return rows


def test_nested_train_fractions_are_patient_level_and_nested():
    rows = _rows()
    half, half_audit = nested_train_fraction(rows, fraction=0.5)
    full, full_audit = nested_train_fraction(rows, fraction=1.0)
    half_ids = {row["patient_id_hash"] for row in half if row["split"] == "train"}
    full_ids = {row["patient_id_hash"] for row in full if row["split"] == "train"}
    assert half_ids < full_ids
    assert half_audit["train_patients"] == 10
    assert full_audit["train_patients"] == 20
    assert half_audit["patient_disjoint_from_dev"] is True


def test_development_specs_materialize_effective_loss_counts():
    base = {
        "schema": "prta-cxr.training.v1",
        "seed": 17,
        "model": {},
        "optimization": {"epochs": 1},
        "loss_weights": {},
    }
    specs = initial_development_specs()
    assert [spec["experiment_id"] for spec in specs[:5]] == [
        "D201",
        "D202",
        "D203",
        "D204",
        "D205",
    ]
    config = config_from_spec(base, specs[-1])
    effective = materialize_classification_counts(config, _rows())
    assert effective["model"]["native_head"] == "H2"
    assert effective["classification_loss"]["class_counts"] == [4] * 5


def test_run_registry_atomically_upserts_by_experiment(tmp_path):
    path = tmp_path / "registry.jsonl"
    row = {key: "" for key in RUN_RECEIPT_FIELDS}
    row["experiment_id"] = "D201"
    row["seed"] = 17
    row["status"] = "RUNNING"
    upsert_run_registry(path, row)
    row["status"] = "PASS_TRAINING_FINISHED"
    upsert_run_registry(path, row)
    values = read_run_registry(path)
    assert len(values) == 1
    assert values[0]["status"] == "PASS_TRAINING_FINISHED"
    assert json.loads(path.read_text(encoding="utf-8")) == values[0]


def test_head_screening_waits_for_full_fraction_run():
    rows = [
        {"experiment_id": "D205", "status": "RUNNING"},
        {"experiment_id": "M301-H1", "status": "PLANNED"},
    ]
    assert dependencies_satisfied(rows[1], rows) is False
    rows[0]["status"] = "PASS_TRAINING_FINISHED"
    assert dependencies_satisfied(rows[1], rows) is True
