import json

import pytest

from prta_cxr.cli_labeling import (
    luna_command,
    synthetic_luna_rows,
    synthetic_samples,
)
from prta_cxr.contracts import ContractError
from prta_cxr.label_batches import load_luna_output, prepare_luna_batches
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
        "prior_view": "PA",
        "current_view": "PA",
    }
    samples, audit = candidate_samples([pair])
    assert len(samples) == 1
    assert samples[0]["progression_label"] == "Improved"
    assert samples[0]["label_tier"] == "Tier-B"
    assert audit["candidate_samples"] == 1


def test_luna_batches_remove_patient_identity_and_pin_authority(tmp_path):
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    prompt.write_text("prompt", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")
    batches, receipt = prepare_luna_batches(
        synthetic_samples(),
        batch_size=2,
        prompt_path=prompt,
        schema_path=schema,
    )
    assert len(batches) == 3
    assert receipt["patient_identifiers_in_batches"] is False
    serialized = json.dumps(batches)
    assert "patient_id" not in serialized
    assert "synthetic-hash" not in serialized


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
    assert command[:3] == ["codex", "exec", "-m"]
    assert "--sandbox" in command
    assert command[-1] == "-"
