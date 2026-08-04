import json

import pytest

from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.independent_silver import externalize_independent_batch
from prta_cxr.protected_quality_review import (
    _cohen_kappa,
    _write_batches,
    shard_ranges,
    validate_quality_output,
)


def _write_output(path, items):
    path.write_text(json.dumps({"items": items}), encoding="utf-8")


def test_quality_output_accepts_only_controlled_label_and_flags(tmp_path):
    path = tmp_path / "output.json"
    rows = [
        {
            "sample_id": "s00000_00",
            "ai_label": "Unclear",
            "quality_flags": [
                "REPORT_INSUFFICIENT",
                "FINDING_NOT_JUDGEABLE",
            ],
        }
    ]
    _write_output(path, rows)
    assert validate_quality_output(path) == rows

    _write_output(path, [rows[0] | {"reason": "not allowed"}])
    with pytest.raises(RuntimeError, match="field mismatch"):
        validate_quality_output(path)

    _write_output(path, [rows[0] | {"quality_flags": ["UNKNOWN"]}])
    with pytest.raises(RuntimeError, match="unknown flag"):
        validate_quality_output(path)


def test_quality_output_rejects_duplicate_ids_and_flags(tmp_path):
    path = tmp_path / "output.json"
    row = {
        "sample_id": "s00000_00",
        "ai_label": "Stable",
        "quality_flags": [],
    }
    _write_output(path, [row, row])
    with pytest.raises(RuntimeError, match="duplicate sample IDs"):
        validate_quality_output(path)

    duplicate_flags = row | {
        "quality_flags": ["PAIRING_ABNORMAL", "PAIRING_ABNORMAL"]
    }
    _write_output(path, [duplicate_flags])
    with pytest.raises(RuntimeError, match="unique list"):
        validate_quality_output(path)


def test_gold_batch_keeps_gold_local_and_externalizes_only_blind_fields(
    tmp_path,
):
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    prompt.write_text("blind prompt", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")
    sample = synthetic_samples()[0]
    sample["label_tier"] = "Gold"
    root = tmp_path / "poststop_audits" / "protected_quality"

    candidate, batch_dir, receipt = _write_batches(
        [sample],
        cohort="gold",
        root=root,
        batch_size=20,
        prompt=prompt,
        schema=schema,
    )

    stored = json.loads(candidate.read_text(encoding="utf-8"))
    assert stored["label_tier"] == "Gold"
    batch = json.loads((batch_dir / "batch_00000.json").read_text())
    external = externalize_independent_batch(batch)
    assert set(external["items"][0]) == {
        "sample_id",
        "finding",
        "prior_report",
        "current_report",
    }
    assert sample["sample_id"] not in json.dumps(external)
    assert "progression_label" not in json.dumps(external)
    assert "label_tier" not in json.dumps(external)
    assert "patient_id_hash" not in json.dumps(external)
    assert receipt["labels_in_external_payload"] is False


def test_quality_schema_is_closed_and_matches_controlled_flags():
    schema = json.loads(
        open(
            "schemas/protected_label_quality_review_batch_v2.schema.json",
            encoding="utf-8",
        ).read()
    )
    item = schema["properties"]["items"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["properties"]) == {
        "sample_id",
        "ai_label",
        "quality_flags",
    }
    assert set(item["properties"]["quality_flags"]["items"]["enum"]) == {
        "REPORT_INSUFFICIENT",
        "PAIRING_ABNORMAL",
        "FINDING_NOT_JUDGEABLE",
        "TEMPORAL_DIRECTION_AMBIGUOUS",
        "NEGATION_OR_UNCERTAINTY_CONFLICT",
    }


def test_shard_ranges_cover_every_batch_once():
    ranges = shard_ranges(834, 14)
    covered = [
        batch
        for start, count in ranges
        for batch in range(start, start + count)
    ]
    assert covered == list(range(834))
    assert len(ranges) == 14


def test_cohen_kappa_ignores_unclear_rows():
    rows = [
        {"current_label": "Stable", "sol_label": "Stable", "exact_current": True},
        {"current_label": "Worse", "sol_label": "Worse", "exact_current": True},
        {"current_label": "New", "sol_label": "Unclear", "exact_current": False},
    ]
    assert _cohen_kappa(rows) == 1.0
