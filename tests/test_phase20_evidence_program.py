import json

import pytest
import torch

from prta_cxr.contracts import canonical_sha256
from prta_cxr.phase20_evidence_program import (
    build_phase20_evidence_jobs,
    build_phase20_phase_c_jobs,
    validate_final_s1_artifact,
)


def test_phase20_evidence_queue_is_focused_mandatory_phase_b():
    jobs = build_phase20_evidence_jobs(lane="rtx3090_0")
    by_id = {job["job_id"]: job for job in jobs}
    assert len(jobs) == 6
    assert len(by_id) == 6
    assert all(job["lane"] == "rtx3090_0" for job in jobs)
    assert set(by_id) == {
        "evidence-probability-S17",
        "evidence-probability-S28",
        "evidence-probability-S43",
        "evidence-calibration",
        "evidence-subgroups",
        "evidence-state-efficiency-S43",
    }
    assert by_id["evidence-calibration"]["dependencies"] == [
        "evidence-probability-S17",
        "evidence-probability-S28",
        "evidence-probability-S43",
    ]
    assert by_id["evidence-state-efficiency-S43"]["dependencies"] == [
        "evidence-probability-S43"
    ]
    command = by_id["evidence-probability-S17"]["command"]
    assert command[command.index("--diagnostic-scope") + 1] == "phase20_s1"
    assert "--retain-logits" in command
    assert "--true-only" not in command
    efficiency = by_id["evidence-state-efficiency-S43"]["command"]
    assert efficiency[efficiency.index("--checkpoint") + 1] == "{s1_checkpoint_43}"
    assert "131_profile_phase20_state_efficiency.py" in efficiency[1]


def test_phase20_phase_c_catalog_is_optional_and_separate():
    mandatory = build_phase20_evidence_jobs(lane="rtx3090_0")
    optional = build_phase20_phase_c_jobs(lane="rtx3090_0")
    mandatory_ids = {job["job_id"] for job in mandatory}
    optional_ids = {job["job_id"] for job in optional}
    assert len(optional) == 11
    assert not mandatory_ids & optional_ids
    assert {
        "phase-c-current-cache-blur",
        "phase-c-current-cache-contrast",
        "phase-c-current-cache-jpeg",
        "phase-c-modality-S17",
        "phase-c-modality-S28",
        "phase-c-modality-S43",
        "phase-c-state-pruned-S17",
        "phase-c-state-pruned-S28",
    } <= optional_ids
    for condition in ("blur", "contrast", "jpeg"):
        by_id = {job["job_id"]: job for job in optional}
        corruption = by_id[f"phase-c-current-cache-{condition}"]["command"]
        assert corruption[corruption.index("--raw-image-root") + 1] == (
            "{raw_image_root}"
        )


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
    checkpoint_input_hashes = {
        **input_hashes,
        "source_filter_audit": "source-filter-audit",
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
            "input_hashes": checkpoint_input_hashes,
        },
        checkpoint,
    )
    receipt = tmp_path / "training_receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "status": "PASS_TRAINING_FINISHED",
                "config_sha256": canonical_sha256(config),
                "input_hashes": checkpoint_input_hashes,
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
    assert result["input_hashes"] == checkpoint_input_hashes

    config["experiment_id"] = "P20-ABL-NOSTATE-S28"
    torch.save(
        {
            "schema": "prta-cxr.checkpoint.v1",
            "config": config,
            "input_hashes": checkpoint_input_hashes,
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
