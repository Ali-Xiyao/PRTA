from __future__ import annotations

import json
import subprocess
import sys

from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.experiments import (
    config_from_spec,
    filter_train_dev_sources,
    initial_development_specs,
    inject_train_label_noise,
    materialize_classification_counts,
    nested_train_fraction,
)
from prta_cxr.queue_runner import dependencies_satisfied, process_alive
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


def test_source_filter_is_split_specific_and_audited():
    selected, audit = filter_train_dev_sources(
        _rows(), train_sources=["source-b"], dev_sources=["source-a"]
    )
    assert {row["source"] for row in selected if row["split"] == "train"} == {
        "source-b"
    }
    assert {row["source"] for row in selected if row["split"] == "dev"} == {"source-a"}
    assert audit["patient_disjoint"] is True


def test_label_noise_is_exact_deterministic_and_train_only():
    first, audit = inject_train_label_noise(
        _rows(), rate=0.2, family="symmetric", salt="test"
    )
    second, second_audit = inject_train_label_noise(
        _rows(), rate=0.2, family="symmetric", salt="test"
    )
    assert first == second
    assert audit == second_audit
    assert audit["changed_rows"] == 4
    assert all(
        row["progression_label"] == original["progression_label"]
        for row, original in zip(first[-5:], _rows()[-5:], strict=True)
    )
    assert all(
        row.get("clean_progression_label") != row["progression_label"]
        for row in first
        if "clean_progression_label" in row
    )


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


def test_process_alive_tracks_a_reaped_child():
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    try:
        assert process_alive(process.pid) is True
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert process_alive(process.pid) is False
