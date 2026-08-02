import json
from pathlib import Path

import pytest

from prta_cxr.authorization import FormalExecutionBlocked
from prta_cxr.cli_independent_silver import (
    _require_execution_enabled,
    prepare_independent_batches_main,
    synthetic_ai_rows,
)
from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.contracts import ContractError, validate_sample
from prta_cxr.independent_silver import (
    externalize_independent_batch,
    load_independent_ai_output,
    merge_independent_silver,
    prepare_independent_ai_batches,
    validate_independent_ai_batch,
)


def _authority_files(tmp_path):
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    prompt.write_text("prompt", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")
    return prompt, schema


def test_rule_blind_batches_expose_only_reports_finding_and_alias(tmp_path):
    prompt, schema = _authority_files(tmp_path)
    samples = synthetic_samples()
    batches, receipt = prepare_independent_ai_batches(
        samples, batch_size=2, prompt_path=prompt, schema_path=schema
    )
    external = externalize_independent_batch(batches[0])
    assert "sample_id_map" not in external
    assert set(external["items"][0]) == {
        "sample_id",
        "finding",
        "prior_report",
        "current_report",
    }
    assert external["items"][0]["sample_id"] == "s00000_00"
    assert samples[0]["sample_id"] not in json.dumps(external)
    assert receipt["rule_label_in_external_payload"] is False
    assert receipt["patient_identifiers_in_external_payload"] is False


def test_rule_blind_batch_rejects_tampered_external_item(tmp_path):
    prompt, schema = _authority_files(tmp_path)
    batches, _ = prepare_independent_ai_batches(
        synthetic_samples(), batch_size=2, prompt_path=prompt, schema_path=schema
    )
    batches[0]["items"][0]["current_report"] = "tampered"
    with pytest.raises(ContractError, match="hash mismatch"):
        externalize_independent_batch(batches[0])


def test_independent_output_is_two_fields_only_and_fail_closed(tmp_path):
    samples = synthetic_samples()
    rows = synthetic_ai_rows(samples)
    path = tmp_path / "output.json"
    path.write_text(json.dumps({"items": rows}), encoding="utf-8")
    assert load_independent_ai_output(path) == rows
    with pytest.raises(ContractError, match="field mismatch"):
        validate_independent_ai_batch([rows[0] | {"reason": "not allowed"}])
    with pytest.raises(ContractError, match="unknown"):
        validate_independent_ai_batch(
            [{"sample_id": "sample", "ai_label": "Probably Stable"}]
        )


def test_intersection_accepts_exact_and_excludes_mismatch_and_unclear():
    samples = synthetic_samples()
    ai_rows = synthetic_ai_rows(samples)
    ai_rows[1]["ai_label"] = "Worse"
    ai_rows[2]["ai_label"] = "Unclear"
    accepted, excluded, audit = merge_independent_silver(samples, ai_rows)
    assert len(accepted) == 3
    assert len(excluded) == 2
    assert {row["silver_status"] for row in excluded} == {
        "excluded_mismatch",
        "excluded_unclear",
    }
    assert all(row["label_tier"] == "Silver" for row in accepted)
    assert all(validate_sample(row) for row in accepted)
    assert audit["overall"] == {
        "rows": 5,
        "accepted_exact_agreement": 3,
        "excluded_mismatch": 1,
        "excluded_unclear": 1,
        "agreement_rate": 0.6,
    }
    assert audit["agreement_is_ground_truth"] is False
    assert audit["human_accuracy_audit"]["completed"] is False
    assert audit["formal_training_authorized"] is False


def test_intersection_requires_exact_complete_id_set():
    samples = synthetic_samples()
    with pytest.raises(ContractError, match="IDs mismatch"):
        merge_independent_silver(samples, synthetic_ai_rows(samples)[:-1])


def test_full_batch_preparation_preflight(capsys):
    assert prepare_independent_batches_main(["--mode", "preflight"]) == 0
    assert "PASS_INDEPENDENT_BATCH_PREPARATION_PREFLIGHT" in capsys.readouterr().out


def test_completed_pilot_and_full_execution_are_both_held():
    config = Path("configs/labeling/independent_silver_v1.json")
    with pytest.raises(FormalExecutionBlocked, match="pilot execution"):
        _require_execution_enabled(config, scope="pilot", row_count=150)
    with pytest.raises(FormalExecutionBlocked, match="full execution"):
        _require_execution_enabled(config, scope="full", row_count=148798)


def test_completed_sol_review_is_held_against_rerun():
    config = Path("configs/labeling/sol_blind_review_v1.json")
    with pytest.raises(FormalExecutionBlocked, match="pilot execution"):
        _require_execution_enabled(config, scope="pilot", row_count=150)


def test_completed_luna_primary_full_execution_is_held_against_rerun():
    config = Path("configs/labeling/luna_primary_full_v1.json")
    with pytest.raises(FormalExecutionBlocked, match="full execution"):
        _require_execution_enabled(config, scope="full", row_count=148798)
