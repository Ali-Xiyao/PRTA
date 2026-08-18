from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from prta_cxr.authorization import FORMAL_ENV_NAME, FORMAL_ENV_VALUE
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256
from prta_cxr.rexgradient_evaluation import (
    DEDUP_STATUS,
    _BKTree,
    bootstrap_external_metrics,
    build_external_program_jobs,
    deduplicate_external_main,
    derive_external_labels,
    freeze_external_protocol_main,
    validate_mapping_spec,
    validate_slim_s1_checkpoint,
)


def _spec() -> dict[str, object]:
    return {
        "schema": "prta-cxr.rexgradient-label-mapping-spec.v1",
        "protocol": "explicit-current-report-transition-cues-v1",
        "ruleset_version": "prta-cxr-report-transition-v1",
        "findings": [
            "Atelectasis",
            "Cardiomegaly",
            "Consolidation",
            "Edema",
            "Enlarged Cardiomediastinum",
            "Fracture",
            "Lung Lesion",
            "Lung Opacity",
            "Pleural Effusion",
            "Pleural Other",
            "Pneumonia",
            "Pneumothorax",
        ],
        "progression_labels": list(PROGRESSION_LABELS),
        "accepted_sections": ["IMPRESSION", "FINDINGS", "UNSECTIONED"],
        "conflicting_labels": "exclude",
        "uncertain_or_negated_change": "exclude",
        "no_explicit_transition_cue": "exclude",
        "label_tier": "External-Silver",
        "minimum_validation_support_per_class": 1,
        "test_mapping_tuning_allowed": False,
        "model_selection_allowed": False,
        "threshold_tuning_allowed": False,
        "bootstrap_replicates": 1000,
        "bootstrap_seed": 20260818,
    }


def _pair(index: int, impression: str) -> dict[str, object]:
    return {
        "schema": "prta-cxr.rexgradient-unlabeled-pair.v1",
        "sample_id": f"pair-{index}",
        "external_split": "validation",
        "patient_id_hash": f"patient-{index}",
        "prior_study_id_hash": f"prior-{index}",
        "current_study_id_hash": f"current-{index}",
        "prior_image_path": f"images/prior-{index}.png",
        "current_image_path": f"images/current-{index}.png",
        "prior_datetime": "2020-01-01T00:00:00+00:00",
        "current_datetime": "2020-01-02T00:00:00+00:00",
        "interval_days": 1,
        "prior_view": "PA",
        "current_view": "PA",
        "prior_report": {"findings": "", "impression": ""},
        "current_report": {"findings": "", "impression": impression},
    }


def _checkpoint(seed: int, weights_hash: str = "w" * 64):
    config = {
        "experiment_id": f"P20-FINAL-S1-S{seed}",
        "seed": seed,
        "final_mainline": "Slim-S1",
        "prta_v2_variant": "Slim-S1",
        "phase20_axis": "final_mainline_confirmation",
        "model": {
            "family": "prta",
            "adapter_scope": "tail8",
            "native_head": "H0",
            "adapter_rank": 32,
            "components": {
                "finding_conditioning": True,
                "cross_time_alignment": True,
                "temporal_relation_residual": True,
                "matched_hard_cmcp": True,
            },
        },
        "loss_weights": {
            "prototype_alignment": 0.0,
            "state": 0.025,
            "opposite_direction_cost": 0.05,
            "cmcp": 0.01,
            "direction_margin": 0.0,
        },
        "cmcp": {"matching": "offline_hard_v1"},
    }
    checkpoint = {
        "schema": "prta-cxr.checkpoint.v1",
        "config": config,
        "input_hashes": {"weights": weights_hash},
        "model_state": {},
    }
    receipt = {
        "schema": "prta-cxr.training-receipt.v1",
        "status": "PASS_TRAINING_FINISHED",
        "formal_experiment": True,
        "config_sha256": canonical_sha256(config),
        "input_hashes": {"weights": weights_hash},
    }
    return checkpoint, receipt


def test_mapping_derives_only_explicit_supported_labels() -> None:
    rows, audit = derive_external_labels(
        [
            _pair(1, "New pleural effusion."),
            _pair(2, "Cardiomediastinal silhouette is unchanged."),
            _pair(3, "Possible pneumonia."),
        ],
        split="validation",
        mapping_spec=_spec(),
        blocked_image_paths={"images/prior-2.png"},
    )
    assert [(row["finding"], row["progression_label"]) for row in rows] == [
        ("Pleural Effusion", "New")
    ]
    assert audit["excluded_pairs_due_to_dedup"] == 1
    assert audit["pairs_without_explicit_transition_label"] == 1


def test_mapping_and_checkpoint_contracts_fail_closed() -> None:
    spec = _spec()
    spec["model_selection_allowed"] = True
    with pytest.raises(ValueError, match="prohibit"):
        validate_mapping_spec(spec)
    checkpoint, receipt = _checkpoint(17)
    seed, _ = validate_slim_s1_checkpoint(checkpoint, receipt)
    assert seed == 17
    checkpoint["config"]["loss_weights"]["state"] = 0.0
    with pytest.raises(ValueError, match="state"):
        validate_slim_s1_checkpoint(checkpoint, receipt)


def test_bk_tree_and_patient_bootstrap() -> None:
    tree = _BKTree()
    tree.add(0b0000)
    tree.add(0b1111)
    assert tree.query(0b0001, 1) == [(1, 0)]
    rows = []
    for patient_index in range(10):
        for label in PROGRESSION_LABELS:
            rows.append(
                {
                    "patient_id": f"p{patient_index}",
                    "observation_id": f"p{patient_index}-{label}",
                    "target": label,
                    "prediction": label,
                }
            )
    result = bootstrap_external_metrics(rows, replicates=20, rng_seed=7)
    assert result["point"]["patient_balanced"]["macro_f1"] == 1.0
    assert result["valid_replicates"] == 20


def test_external_program_has_closed_two_lane_dependency_graph() -> None:
    queues = build_external_program_jobs()
    assert set(queues) == {"external_gpu0", "external_gpu1"}
    jobs = {job["job_id"]: job for queue in queues.values() for job in queue}
    assert len(jobs) == 13
    assert jobs["rex-label-test"]["dependencies"] == ["rex-freeze-protocol"]
    assert set(jobs["rex-finalize-test"]["dependencies"]) == {
        "rex-infer-test-s17",
        "rex-infer-test-s28",
        "rex-infer-test-s43",
    }
    assert all(
        dependency in jobs
        for job in jobs.values()
        for dependency in job["dependencies"]
    )
    gpu_loads = {
        lane: sum(
            job["estimated_seconds"]
            for job in queue
            if job["group"]
            in {
                "validation_cache",
                "sealed_test_cache",
                "validation_inference",
                "test_inference",
            }
        )
        for lane, queue in queues.items()
    }
    assert gpu_loads == {"external_gpu0": 5100, "external_gpu1": 5100}


def test_strict_dedup_conservatively_blocks_exact_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(FORMAL_ENV_NAME, FORMAL_ENV_VALUE)
    external = tmp_path / "external"
    (external / "images").mkdir(parents=True)
    (external / "manifests").mkdir()
    internal = tmp_path / "internal"
    internal.mkdir()
    pixels = np.arange(64, dtype=np.uint8).reshape(8, 8)
    Image.fromarray(pixels).save(external / "images" / "same.png")
    Image.fromarray(pixels).save(internal / "same.png")
    Image.fromarray(np.flipud(pixels)).save(external / "images" / "different.png")
    inventory = [
        {"relative_path": "images/same.png"},
        {"relative_path": "images/different.png"},
    ]
    (external / "manifests" / "image_inventory.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in inventory), encoding="utf-8"
    )
    internal_manifest = tmp_path / "internal.jsonl"
    internal_manifest.write_text(
        json.dumps(
            {
                "source": "internal",
                "prior_image_path": "same.png",
                "current_image_path": "same.png",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "dedup"
    assert (
        deduplicate_external_main(
            [
                "--external-root",
                str(external),
                "--internal-manifest",
                str(internal_manifest),
                "--internal-image-root",
                str(internal),
                "--perceptual-threshold",
                "0",
                "--output",
                str(output),
                "--formal",
            ]
        )
        == 0
    )
    receipt = json.loads((output / "dedup_receipt.json").read_text())
    assert receipt["status"] == DEDUP_STATUS
    assert "images/same.png" in receipt["blocked_external_paths"]


def test_freeze_protocol_binds_all_three_slim_seeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(FORMAL_ENV_NAME, FORMAL_ENV_VALUE)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps(_spec()), encoding="utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text(
        json.dumps(
            {
                "status": "PASS_REXGRADIENT_EXTERNAL_LABELS",
                "external_split": "validation",
                "mapping_spec_sha256": __import__(
                    "prta_cxr.contracts", fromlist=["sha256_file"]
                ).sha256_file(mapping),
                "test_outcomes_used_for_mapping": False,
                "audit": {"label_counts": {label: 1 for label in PROGRESSION_LABELS}},
            }
        ),
        encoding="utf-8",
    )
    dedup = tmp_path / "dedup.json"
    dedup.write_text(
        json.dumps({"status": DEDUP_STATUS, "unresolved_candidate_count": 0}),
        encoding="utf-8",
    )
    weights = tmp_path / "weights.bin"
    weights.write_bytes(b"weights")
    from prta_cxr.contracts import sha256_file

    checkpoints = []
    receipts = []
    for seed in (17, 28, 43):
        checkpoint, receipt = _checkpoint(seed, sha256_file(weights))
        checkpoint_path = tmp_path / f"s{seed}.pt"
        receipt_path = tmp_path / f"s{seed}.json"
        torch.save(checkpoint, checkpoint_path)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        checkpoints.append(str(checkpoint_path))
        receipts.append(str(receipt_path))
    output = tmp_path / "protocol"
    arguments = [
        "--mapping-spec",
        str(mapping),
        "--validation-label-receipt",
        str(validation),
        "--dedup-receipt",
        str(dedup),
        "--checkpoint",
        *checkpoints,
        "--training-receipt",
        *receipts,
        "--weights",
        str(weights),
        "--output",
        str(output),
        "--formal",
    ]
    assert freeze_external_protocol_main(arguments) == 0
    protocol = json.loads((output / "protocol_receipt.json").read_text())
    assert [item["seed"] for item in protocol["checkpoint_roster"]] == [17, 28, 43]
    assert protocol["model_selection_allowed"] is False
