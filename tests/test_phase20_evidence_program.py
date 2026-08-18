import json

import pytest
import torch

from prta_cxr.contracts import canonical_sha256
from prta_cxr.phase20_evidence_program import (
    build_phase20_evidence_jobs,
    validate_final_s1_artifact,
)


def test_phase20_evidence_queue_covers_frozen_nonexternal_s1_evidence():
    jobs = build_phase20_evidence_jobs(lane="rtx3090_0")
    by_id = {job["job_id"]: job for job in jobs}
    assert len(jobs) == 20
    assert len(by_id) == 20
    assert all(job["lane"] == "rtx3090_0" for job in jobs)
    assert {
        "evidence-probability-S17",
        "evidence-probability-S28",
        "evidence-probability-S43",
        "evidence-calibration",
        "evidence-subgroups",
        "evidence-efficiency-full",
        "evidence-efficiency-pruned",
    } <= set(by_id)
    assert by_id["evidence-calibration"]["dependencies"] == [
        "evidence-probability-S17",
        "evidence-probability-S28",
        "evidence-probability-S43",
    ]
    assert by_id["evidence-state-parity-S17"]["dependencies"] == [
        "evidence-state-pruned-S17"
    ]
    command = by_id["evidence-probability-S17"]["command"]
    assert command[command.index("--diagnostic-scope") + 1] == "phase20_s1"
    assert "--retain-logits" in command
    assert "--true-only" not in command
    pruned = by_id["evidence-state-pruned-S17"]["command"]
    assert "--true-only" in pruned
    assert "--deployment-prune-state" in pruned


def test_phase20_evidence_queue_rejects_reserved_or_unknown_lane():
    with pytest.raises(ValueError, match="unsupported Phase20 evidence lane"):
        build_phase20_evidence_jobs(lane="rtx3090_1")


def test_final_s1_artifact_validation_is_exact_and_closed(tmp_path):
    seed = 28
    input_hashes = {
        "split_manifest": "split",
        "cleaned_split_freeze": "freeze",
        "cache_manifest": "cache",
        "text_cache": "text",
        "matched_hard_prior_map": "map",
        "weights": "weights",
        "label_quality_audit": "quality",
    }
    config = {
        "experiment_id": "P20-FINAL-S1-S28",
        "seed": seed,
        "prta_v2_variant": "Slim-S1",
        "phase20_protocol": "full-train-official-dev-slim-s1-confirmation-v1",
        "phase20_axis": "final_mainline_confirmation",
    }
    checkpoint = tmp_path / "best.pt"
    torch.save(
        {
            "schema": "prta-cxr.checkpoint.v1",
            "config": config,
            "input_hashes": input_hashes,
        },
        checkpoint,
    )
    receipt = tmp_path / "training_receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "status": "PASS_TRAINING_FINISHED",
                "config_sha256": canonical_sha256(config),
                "input_hashes": input_hashes,
                "internal_test_opened": False,
                "protected_outcomes_opened": False,
            }
        ),
        encoding="utf-8",
    )
    result = validate_final_s1_artifact(
        checkpoint,
        receipt,
        seed=seed,
        expected_input_hashes=input_hashes,
    )
    assert result["experiment_id"] == "P20-FINAL-S1-S28"
    assert len(result["checkpoint_sha256"]) == 64

    config["experiment_id"] = "P20-ABL-NOSTATE-S28"
    torch.save(
        {
            "schema": "prta-cxr.checkpoint.v1",
            "config": config,
            "input_hashes": input_hashes,
        },
        checkpoint,
    )
    with pytest.raises(ValueError, match="checkpoint identity drift"):
        validate_final_s1_artifact(
            checkpoint,
            receipt,
            seed=seed,
            expected_input_hashes=input_hashes,
        )
