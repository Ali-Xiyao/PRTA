import json

import pytest

from prta_cxr.case_study import build_case_study
from prta_cxr.contracts import ContractError


def _prediction(identifier, target, prediction, condition, system):
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    probabilities = [0.05] * 5
    probabilities[labels.index(prediction)] = 0.8
    return {
        "calendar_interval_available": True,
        "cohort": "dev",
        "confidence": 0.8,
        "current_view": "AP",
        "finding": "Edema",
        "interval_basis": "calendar",
        "interval_days": 2.0,
        "observation_id": identifier,
        "patient_id": f"patient-{identifier}",
        "prediction": prediction,
        "prior_intervention": condition,
        "prior_view": "AP",
        "probabilities": probabilities,
        "query_finding": "Edema",
        "source": "source-a",
        "system": system,
        "target": target,
        "temperature": 1.0,
        "training_seed": 17,
    }


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _fixture(tmp_path):
    manifest = tmp_path / "train_dev.jsonl"
    rows = []
    for identifier, target in (("a", "Stable"), ("b", "Worse")):
        rows.append(
            {
                "sample_id": identifier,
                "patient_id_hash": f"patient-{identifier}",
                "source": "source-a",
                "prior_study_id": f"p-{identifier}",
                "current_study_id": f"c-{identifier}",
                "prior_image_path": f"p-{identifier}.jpg",
                "current_image_path": f"c-{identifier}.jpg",
                "prior_report": "prior report",
                "current_report": "current report",
                "prior_datetime": "2025-01-01",
                "current_datetime": "2025-01-02",
                "prior_view": "AP",
                "current_view": "AP",
                "progression_label": target,
                "finding": "Edema",
                "split": "dev",
            }
        )
    _write_jsonl(manifest, rows)
    roots = {name: tmp_path / name for name in ("prta", "b403")}
    predictions = {
        "prta": {"a": "Stable", "b": "Improved"},
        "b403": {"a": "Improved", "b": "Worse"},
    }
    for system, root in roots.items():
        for condition in ("true", "matched_wrong", "null", "reversed"):
            output = []
            for identifier, target in (("a", "Stable"), ("b", "Worse")):
                prediction = predictions[system][identifier]
                if condition != "true":
                    prediction = "Stable"
                output.append(
                    _prediction(identifier, target, prediction, condition, system)
                )
            _write_jsonl(root / f"{condition}.predictions.jsonl", output)
    return manifest, roots


def test_case_study_is_complete_private_and_hashed(tmp_path):
    manifest, roots = _fixture(tmp_path)
    output = tmp_path / "output"
    receipt = build_case_study(
        manifest_path=manifest,
        prta_root=roots["prta"],
        b403_root=roots["b403"],
        output_root=output,
        per_target=1,
    )
    assert receipt["status"] == "PASS_EXPLORATORY_DEV_CASE_STUDY"
    assert receipt["rows"] == 2
    assert receipt["protected_outcome_read_count"] == 0
    summary = json.loads((output / "case_study_summary.json").read_text())
    assert summary["paired_counts"] == {
        "b403_only_correct": 1,
        "prta_only_correct": 1,
    }
    assert summary["prior_interventions"]["null"]["prta"][
        "true_correct_to_wrong"
    ] == 0


def test_case_study_rejects_protected_path(tmp_path):
    manifest, roots = _fixture(tmp_path)
    protected = tmp_path / "gold" / "output"
    with pytest.raises(ContractError, match="protected path"):
        build_case_study(
            manifest_path=manifest,
            prta_root=roots["prta"],
            b403_root=roots["b403"],
            output_root=protected,
        )
