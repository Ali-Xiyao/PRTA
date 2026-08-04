import json
from pathlib import Path

import pytest

from prta_cxr.cli_labeling import (
    luna_command,
    synthetic_luna_rows,
    synthetic_samples,
)
from prta_cxr.contracts import ContractError
from prta_cxr.label_batches import (
    load_luna_output,
    prepare_luna_batches,
    select_stratified_pilot,
)
from prta_cxr.label_rules import candidate_samples, extract_report_annotations
from prta_cxr.labeling import merge_luna_labels


def test_rule_extraction_accepts_direction_and_rejects_uncertainty_negation():
    accepted = extract_report_annotations(
        "IMPRESSION: Decreased right pleural effusion compared with prior."
    )
    assert [(row["finding"], row["label"]) for row in accepted] == [
        ("Pleural Effusion", "Improved")
    ]
    assert (
        extract_report_annotations(
            "IMPRESSION: Possible increased right pleural effusion."
        )
        == []
    )
    assert (
        extract_report_annotations(
            "IMPRESSION: No significant increase in right pleural effusion."
        )
        == []
    )


def test_pair_to_candidate_uses_clean_sample_contract():
    pair = {
        "pair_id": "pair-1",
        "patient_id_hash": "hash-1",
        "source": "fixture",
        "prior_study_id": "p",
        "current_study_id": "c",
        "prior_image_path": "images/p.png",
        "current_image_path": "images/c.png",
        "prior_report": "FINDINGS: Moderate pleural effusion.",
        "current_report": "IMPRESSION: Decreased pleural effusion.",
        "prior_datetime": "2025-01-01T00:00:00",
        "current_datetime": "2025-01-02T00:00:00",
        "interval_days": 1,
        "interval_basis": "within_patient_ordinal",
        "calendar_interval_available": False,
        "interval_semantics": "within_patient_ordinal_steps_not_calendar_days",
        "prior_view": "PA",
        "current_view": "PA",
    }
    samples, audit = candidate_samples([pair])
    assert len(samples) == 1
    assert samples[0]["progression_label"] == "Improved"
    assert samples[0]["label_tier"] == "Tier-B"
    assert samples[0]["calendar_interval_available"] is False
    assert audit["candidate_samples"] == 1


def test_luna_batches_remove_patient_identity_and_pin_authority(tmp_path):
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    prompt.write_text("prompt", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")
    samples = synthetic_samples()
    batches, receipt = prepare_luna_batches(
        samples,
        batch_size=2,
        prompt_path=prompt,
        schema_path=schema,
    )
    assert len(batches) == 3
    assert receipt["patient_identifiers_in_batches"] is False
    serialized = json.dumps(batches)
    assert "patient_id" not in serialized
    assert "synthetic-hash" not in serialized
    assert "elapsed_calendar_days" in serialized
    assert batches[0]["items"][0]["sample_id"] == "s00000_00"
    assert batches[0]["sample_id_map"]["s00000_00"] == samples[0]["sample_id"]


def test_luna_output_and_merge_fail_closed(tmp_path):
    samples = synthetic_samples()
    rows = synthetic_luna_rows(samples)
    path = tmp_path / "output.json"
    path.write_text(json.dumps({"items": rows}), encoding="utf-8")
    loaded = load_luna_output(path)
    merged, counts = merge_luna_labels(samples, loaded)
    assert len(merged) == 5
    assert counts["Tier-A"] == 5
    path.write_text(json.dumps({"items": rows + [rows[0]]}), encoding="utf-8")
    with pytest.raises(ContractError, match="duplicate"):
        load_luna_output(path)


def test_luna_command_is_argument_list_not_shell(tmp_path):
    command = luna_command(
        model="gpt-5.6-luna",
        schema=tmp_path / "schema.json",
        output=tmp_path / "output.json",
    )
    assert Path(command[0]).name in {"codex", "codex.cmd"}
    assert command[1:3] == ["exec", "-m"]
    assert "--sandbox" in command
    assert command[-1] == "-"


def test_luna_command_pins_reasoning_effort(tmp_path):
    command = luna_command(
        model="gpt-5.6-sol",
        schema=tmp_path / "schema.json",
        output=tmp_path / "output.json",
        reasoning_effort="medium",
    )
    assert "-c" in command
    assert 'model_reasoning_effort="medium"' in command


def test_stratified_pilot_is_deterministic_unique_patient_and_balanced():
    samples = []
    for patient in range(30):
        row = synthetic_samples()[patient % 5].copy()
        row["sample_id"] = f"sample-{patient}"
        row["patient_id_hash"] = f"patient-{patient}"
        row["source"] = "source-a" if patient % 2 else "source-b"
        row["finding"] = "Edema" if patient % 3 else "Pleural Effusion"
        samples.append(row)
    left, audit = select_stratified_pilot(samples, pilot_size=20, salt="fixed")
    right, _ = select_stratified_pilot(samples, pilot_size=20, salt="fixed")
    assert left == right
    assert len({row["patient_id_hash"] for row in left}) == 20
    assert set(audit["sources"]) == {"source-a", "source-b"}
    assert set(audit["labels"]) == {
        "Improved",
        "New",
        "Resolved",
        "Stable",
        "Worse",
    }
