import copy

import numpy as np

from prta_cxr.query_sensitivity import (
    attention_flow_distribution,
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
