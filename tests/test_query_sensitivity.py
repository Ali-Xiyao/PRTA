import copy
import json

import numpy as np
import torch

from prta_cxr.attention_flow import patch_attention_flow
from prta_cxr.query_sensitivity import (
    _batch_patch_attention_flow,
    attention_flow_distribution,
    build_s3_public_release,
    compute_jsd_units,
    freeze_query_sensitivity_cohort,
    jensen_shannon_divergence,
    patient_clustered_median_ci,
    summarize_jsd_units,
)


def _manifest_rows():
    rows = []
    for pair in range(110):
        for finding, label in (("Edema", "Improved"), ("Opacity", "Stable")):
            rows.append(
                {
                    "split": "dev",
                    "sample_id": f"pair-{pair}-{finding}",
                    "source": "mimic",
                    "patient_id_hash": f"patient-{pair // 2}",
                    "prior_image_path": f"prior-{pair}.jpg",
                    "current_image_path": f"current-{pair}.jpg",
                    "finding": finding,
                    "progression_label": label,
                }
            )
    return rows


def _predictions(seed):
    return [
        {
            "observation_id": row["sample_id"],
            "patient_id": row["patient_id_hash"],
            "finding": row["finding"],
            "target": row["progression_label"],
            "prediction": row["progression_label"],
            "training_seed": seed,
        }
        for row in _manifest_rows()
    ]


def test_s3_cohort_freezes_before_view_and_prefers_distinct_states():
    blocks = [(seed, _predictions(seed)) for seed in (17, 28, 43)]
    first = freeze_query_sensitivity_cohort(_manifest_rows(), blocks)
    second = freeze_query_sensitivity_cohort(
        copy.deepcopy(_manifest_rows()), copy.deepcopy(blocks)
    )
    assert first == second
    assert first["eligible_pair_count"] == 110
    assert first["eligible_row_count"] == 220
    assert first["images_opened"] is False
    assert first["attention_opened"] is False
    assert first["qualitative_selection"]["distinct_progression_states"] == 2


def test_flow_distribution_and_jsd_contract():
    first = np.arange(1, 197, dtype=np.float64)
    second = first[::-1].copy()
    joint = attention_flow_distribution(first, second)
    alternative = attention_flow_distribution(second, second)
    assert joint.shape == (392,)
    assert np.isclose(joint.sum(), 1.0)
    assert jensen_shannon_divergence(joint, joint) == 0.0
    assert 0.0 < jensen_shannon_divergence(joint, alternative) <= 1.0


def test_jsd_units_cover_query_and_seed_comparisons():
    records = []
    for seed in (17, 28, 43):
        for finding_index, finding in enumerate(("Edema", "Opacity")):
            values = np.ones(196)
            values[(seed + finding_index) % 196] = 4.0
            records.append(
                {
                    "pair_hash": "pair",
                    "patient_id_hash": "patient",
                    "seed": seed,
                    "finding": finding,
                    "r_current": values,
                    "r_prior": values[::-1],
                }
            )
    units = compute_jsd_units(records)
    assert sum(unit["kind"] == "between_query" for unit in units) == 3
    assert sum(unit["kind"] == "between_seed" for unit in units) == 6
    summary = summarize_jsd_units(units, replicates=50)
    assert set(summary) >= {
        "between_query",
        "between_seed",
        "query_sensitive_routing_supported",
    }


def test_patient_clustered_bootstrap_resamples_whole_patients():
    units = [
        {"patient_id_hash": "a", "jsd_joint": 0.1},
        {"patient_id_hash": "a", "jsd_joint": 0.2},
        {"patient_id_hash": "b", "jsd_joint": 0.8},
    ]
    result = patient_clustered_median_ci(
        units, value_key="jsd_joint", replicates=100, rng_seed=7
    )
    assert result["unit_count"] == 3
    assert result["patient_cluster_count"] == 2
    assert result["median"] == 0.2


def test_batched_flow_matches_single_sample_implementation():
    rng = np.random.default_rng(43)
    align = rng.random((2, 12, 197, 197)).astype(np.float32)
    align /= align.sum(axis=-1, keepdims=True)
    transition = rng.random((2, 12, 20, 197)).astype(np.float32)
    transition /= transition.sum(axis=-1, keepdims=True)
    current, prior = _batch_patch_attention_flow(
        torch.from_numpy(align), torch.from_numpy(transition)
    )
    for index in range(2):
        expected = patch_attention_flow(align[index], transition[index])
        assert np.allclose(current[index], expected["r_current"], atol=1e-7)
        assert np.allclose(prior[index], expected["r_prior"], atol=1e-7)


def test_s3_public_release_excludes_private_units_and_pixels():
    aggregate = {
        "status": "PASS_S3_AGGREGATE_GIT_SAFE",
        "source_commit": "source",
        "checkpoint_sha256": {"S17": "a", "S28": "b", "S43": "c"},
        "cohort_receipt_sha256": "cohort",
        "cohort": {"pair_count": 2, "row_count": 4, "patient_cluster_count": 2},
        "jsd": {"logarithm_base": 2},
        "bootstrap": {"replicates": 10_000},
        "statistics": {"query_sensitive_routing_supported": True},
        "qualitative_queries": [
            {"finding": "Edema", "reference_progression": "New"}
        ],
        "qualitative_selection_rule": "pre-view",
    }
    private = {"status": "PASS_S3_JSD_AND_CLUSTERED_BOOTSTRAP"}
    render = {
        "status": "PASS_PRIVATE_S3_RENDERED_PUBLIC_RELEASE_BLOCKED",
        "public_git_redistribution_permitted": False,
        "renderer_commit": "render",
        "analysis_manifest_sha256": "analysis",
        "figure_sha256": "figure",
        "crop": "crop",
        "interpolation": "bilinear",
        "overlay_alpha": 0.4,
        "colormap": "magma",
        "shared_p99_clip": 0.1,
    }
    release = build_s3_public_release(aggregate, private, render)
    payload = json.dumps(release)
    assert release["public_git_redistribution_permitted"] is False
    assert '"patient_id_hash"' not in payload
    assert '"sample_id"' not in payload
    assert "supp_figure_s3_query_sensitivity.png" in payload
