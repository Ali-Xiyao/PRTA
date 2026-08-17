import json

import pytest

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.phase16_queue import allocate_lanes, validate_registry
from prta_cxr.slim_finalize import summarize_and_select
from prta_cxr.slim_matrix import (
    SEEDS,
    SLIM_ARMS,
    build_slim_configs,
    build_slim_jobs,
    build_train_only_selection_rows,
    require_train_only_selection_manifest,
)


def _parent(seed):
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": f"W045-V2-S{seed}",
        "seed": seed,
        "prta_v2_variant": "V2",
        "model": {
            "family": "prta",
            "adapter_scope": "tail8",
            "adapter_rank": 32,
            "native_head": "H0",
            "components": {
                "finding_conditioning": True,
                "cross_time_alignment": True,
                "matched_hard_cmcp": True,
                "temporal_relation_residual": True,
            },
        },
        "optimization": {"epochs": 20},
        "loss_weights": {
            "classification": 1.0,
            "direction_margin": 0.01,
            "opposite_direction_cost": 0.05,
            "state": 0.025,
            "cmcp": 0.01,
            "prototype_alignment": 0.01,
        },
        "cmcp": {"matching": "offline_hard_v1"},
    }


def _parents():
    return {seed: _parent(seed) for seed in SEEDS}


def _rows():
    rows = []
    for patient in range(10):
        for label_index, label in enumerate(PROGRESSION_LABELS):
            rows.append(
                {
                    "sample_id": f"p{patient}-{label_index}",
                    "patient_id_hash": f"patient-{patient}",
                    "progression_label": label,
                    "source": "MIMIC-CXR",
                    "finding": "Edema",
                    "split": "train",
                }
            )
    rows.append(
        {
            "sample_id": "old-dev",
            "patient_id_hash": "old-dev-patient",
            "progression_label": PROGRESSION_LABELS[0],
            "source": "MIMIC-CXR",
            "finding": "Edema",
            "split": "dev",
        }
    )
    return rows


def test_train_only_split_excludes_old_dev_and_is_patient_disjoint():
    rows, audit = build_train_only_selection_rows(_rows())
    assert len(rows) == 50
    assert "old-dev" not in {row["sample_id"] for row in rows}
    train = {row["patient_id_hash"] for row in rows if row["split"] == "train"}
    dev = {row["patient_id_hash"] for row in rows if row["split"] == "dev"}
    assert train.isdisjoint(dev)
    assert audit["source_non_train_rows_excluded"] == 1
    assert audit["source_train_roster_sha256"] == audit["derived_roster_sha256"]


def test_selection_manifest_validator_fails_closed_on_hash_drift(tmp_path):
    manifest = tmp_path / "derived.jsonl"
    manifest.write_text("{}\n", encoding="utf-8")
    cleaned = tmp_path / "cleaned.json"
    cleaned.write_text("{}\n", encoding="utf-8")
    audit = {
        "status": "PASS_SLIM_TRAIN_ONLY_PATIENT_SPLIT",
        "patient_overlap": [],
        "source_train_rows": 1,
        "derived_rows": 1,
        "source_train_roster_sha256": "same",
        "derived_roster_sha256": "same",
        "current_dev_used_for_selection": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "external_opened": False,
        "protected_outcome_read_count": 0,
    }
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "prta-cxr.slim-selection-manifest.v1",
                "status": "PASS_SLIM_SELECTION_MANIFEST_FROZEN",
                "derived_manifest_sha256": sha256_file(manifest),
                "cleaned_split_freeze_sha256": sha256_file(cleaned),
                "split_audit": audit,
                "current_dev_used_for_selection": False,
                "internal_test_opened": False,
                "gold_opened": False,
                "external_opened": False,
                "protected_outcome_read_count": 0,
            }
        ),
        encoding="utf-8",
    )
    require_train_only_selection_manifest(
        manifest,
        selection_receipt_path=receipt,
        cleaned_split_freeze=cleaned,
    )
    manifest.write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="manifest hash drift"):
        require_train_only_selection_manifest(
            manifest,
            selection_receipt_path=receipt,
            cleaned_split_freeze=cleaned,
        )


def test_slim_matrix_is_exact_frozen_two_by_two_three_seed_design():
    configs = build_slim_configs(_parents())
    assert len(configs) == 12
    for arm, (prototype_on, state_on) in SLIM_ARMS.items():
        config = configs[f"{arm}-S17"]
        assert config["loss_weights"]["direction_margin"] == 0
        assert config["loss_weights"]["opposite_direction_cost"] == 0.05
        assert config["loss_weights"]["prototype_alignment"] == (
            0.01 if prototype_on else 0
        )
        assert config["loss_weights"]["state"] == (0.025 if state_on else 0)


def test_slim_jobs_balance_all_cells_after_one_shared_map():
    configs = build_slim_configs(_parents())
    inputs = {
        "cleaned_split_freeze": "/frozen.json",
        "cleaned_split_platform_root": "/cleaned",
        "cache_root": "/cache",
        "text_cache": "/cache/text.pt",
        "weights": "/weights.bin",
        "label_quality_audit": "/quality.json",
    }
    jobs = build_slim_jobs(configs, inputs=inputs)
    validate_registry({"schema": "prta-cxr.phase16-job-registry.v1", "jobs": jobs})
    lanes = allocate_lanes(jobs)
    assert sum(len(queue) for queue in lanes.values()) == 13
    loads = [sum(job["estimated_seconds"] for job in queue) for queue in lanes.values()]
    assert max(loads) - min(loads) <= 1200


def _cell(macro, oder, recall):
    return {
        "macro_f1": macro,
        "opposite_direction_error_rate": oder,
        "min_class_recall": recall,
        "per_class_recall": {label: recall for label in PROGRESSION_LABELS},
        "best_epoch": 7,
    }


def test_frozen_selection_rule_prefers_simplest_admissible_arm():
    values = {
        "Slim-S0": (0.5500, 0.0030, 0.480),
        "Slim-S1": (0.5495, 0.0031, 0.479),
        "Slim-S2": (0.5492, 0.0032, 0.478),
        "Slim-S3": (0.5480, 0.0033, 0.475),
    }
    cells = {arm: {seed: _cell(*values[arm]) for seed in SEEDS} for arm in SLIM_ARMS}
    result = summarize_and_select(cells)
    assert result["selected_arm"] == "Slim-S3"
    assert result["selection_disposition"] == (
        "SELECTED_SIMPLEST_WITHIN_FROZEN_TOLERANCES"
    )
