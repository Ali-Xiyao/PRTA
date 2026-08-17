import json
from pathlib import Path

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.ifusion_diagnostic_queue import (
    INTERVENTIONS,
    validate_diagnostic_output,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _build_output(tmp_path: Path) -> tuple[Path, Path, Path]:
    output = tmp_path / "output"
    output.mkdir()
    checkpoint = tmp_path / "best.pt"
    checkpoint.write_bytes(b"checkpoint")
    training_receipt = tmp_path / "training_receipt.json"
    _write_json(training_receipt, {"best_dev_macro_f1": 0.75})
    blocks = {}
    interventions = {}
    for intervention in INTERVENTIONS:
        path = output / f"{intervention}.predictions.jsonl"
        path.write_text('{"patient_id":"p1"}\n', encoding="utf-8")
        blocks[intervention] = {
            "path": path.name,
            "rows": 1,
            "sha256": sha256_file(path),
        }
        interventions[intervention] = {"metrics": {"ordinary": {"macro_f1": 0.75}}}
    _write_json(
        output / "ifusion_dev_diagnostic_receipt.json",
        {
            "schema": "prta-cxr.ifusion-dev-diagnostic.v1",
            "status": "PASS_IFUSION_TRAIN_DEV_PRIOR_DIAGNOSTIC",
            "evidence_status": "PENDING_PAIRED_BOOTSTRAP",
            "experiment_id": "IF-A01-S17",
            "variant": "IF-A01",
            "seed": 17,
            "checkpoint_only": True,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
            "checkpoint_sha256": sha256_file(checkpoint),
            "training_receipt_sha256": sha256_file(training_receipt),
            "prediction_blocks": blocks,
            "interventions": interventions,
        },
    )
    return output, checkpoint, training_receipt


def test_validate_diagnostic_output_accepts_hash_bound_exact_metric(tmp_path):
    output, checkpoint, training_receipt = _build_output(tmp_path)
    result = validate_diagnostic_output(
        output,
        run_id="IF-A01-S17",
        checkpoint=checkpoint,
        training_receipt_path=training_receipt,
    )
    assert result["metric_delta"] == 0.0
    assert result["zero_protected_reads"] is True
    assert set(result["prediction_blocks"]) == set(INTERVENTIONS)


def test_validate_diagnostic_output_rejects_prediction_hash_drift(tmp_path):
    output, checkpoint, training_receipt = _build_output(tmp_path)
    (output / "true.predictions.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="prediction hash drift"):
        validate_diagnostic_output(
            output,
            run_id="IF-A01-S17",
            checkpoint=checkpoint,
            training_receipt_path=training_receipt,
        )


def test_validate_diagnostic_output_rejects_metric_drift(tmp_path):
    output, checkpoint, training_receipt = _build_output(tmp_path)
    _write_json(training_receipt, {"best_dev_macro_f1": 0.74})
    receipt_path = output / "ifusion_dev_diagnostic_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["training_receipt_sha256"] = sha256_file(training_receipt)
    _write_json(receipt_path, receipt)
    with pytest.raises(ValueError, match="true-PRIOR metric drift"):
        validate_diagnostic_output(
            output,
            run_id="IF-A01-S17",
            checkpoint=checkpoint,
            training_receipt_path=training_receipt,
        )
