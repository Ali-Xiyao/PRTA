from copy import deepcopy

import pytest

from prta_cxr.contracts import canonical_sha256
from prta_cxr.phase20_program import (
    LANES,
    SEEDS,
    allocate_phase20_jobs,
    build_phase20_configs,
    build_reuse_audit,
    normalized_s0_semantics,
    validate_phase20_configs,
)


def _parent(seed):
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": f"W045-V2-S{seed}",
        "seed": seed,
        "prta_v2_variant": "V2",
        "development_axis": "prta_v2_tail8_h0_v1",
        "model": {
            "family": "prta",
            "adapter_scope": "tail8",
            "adapter_rank": 32,
            "native_head": "H0",
            "components": {
                "finding_conditioning": True,
                "cross_time_alignment": True,
                "matched_hard_cmcp": True,
            },
        },
        "optimization": {"epochs": 20},
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.0,
            "branch_decorrelation": 0.0,
            "direction_margin": 0.01,
            "opposite_direction_cost": 0.05,
            "state": 0.025,
            "inversion": 0.0,
            "cmcp": 0.01,
            "prototype_alignment": 0.01,
        },
        "cmcp": {"matching": "offline_hard_v1", "margin": 0.2},
        "data": {
            "train_fraction": 1.0,
            "fraction_salt": "prta-cxr-luna-primary-scaling-v1",
        },
    }


def _parents():
    return {seed: _parent(seed) for seed in SEEDS}


def _sources():
    return ("MIMIC-CXR", "CheXpert Plus")


def _input_hashes():
    return {
        "split_manifest": "1" * 64,
        "cleaned_split_freeze": "2" * 64,
        "cache_manifest": "3" * 64,
        "text_cache": "4" * 64,
        "matched_hard_prior_map": "5" * 64,
        "weights": "6" * 64,
        "label_quality_audit": "7" * 64,
    }


def _a10(parent):
    value = deepcopy(parent)
    value["experiment_id"] = f"IF-A10-S{parent['seed']}"
    value["development_axis"] = "ifusion_final_evidence_v1"
    value["ifusion_variant"] = "IF-A10"
    value["model"]["components"]["unaligned_prior_mode"] = "conditioned"
    value["model"]["components"]["temporal_relation_residual"] = True
    value["loss_weights"]["direction_margin"] = 0.0
    return value


def _fusion(parent, *, tag, family):
    value = deepcopy(parent)
    value["experiment_id"] = f"IF-{tag}-S{parent['seed']}"
    value["development_axis"] = "ifusion_final_evidence_v1"
    value["ifusion_variant"] = f"IF-{tag}"
    value["model"]["family"] = family
    value["model"]["components"] = {}
    value["cmcp"]["matching"] = "disabled"
    for name in (
        "alignment",
        "state",
        "inversion",
        "cmcp",
        "prototype_alignment",
        "branch_decorrelation",
    ):
        value["loss_weights"][name] = 0.0
    return value


def _tila(parent):
    value = deepcopy(parent)
    value["experiment_id"] = f"W047-TILA8-S{parent['seed']}"
    value["model"]["family"] = "tila"
    value["model"]["components"] = {
        "finding_conditioning": True,
        "cross_time_alignment": True,
        "dual_branch": True,
    }
    value["loss_weights"] = {
        "classification": 1.0,
        "alignment": 0.0,
        "state": 0.0,
        "inversion": 0.0,
        "cmcp": 0.0,
    }
    value.pop("cmcp")
    return value


def _a10_evidence(parents):
    return {
        "schema": "prta-cxr.phase20-a10-reuse-evidence.v1",
        "status": "PASS_PHASE20_A10_ALL_SEED_RECEIPT_AUDIT",
        "historical_source_commit": "a" * 40,
        "source_compatibility_audit": "default-path-additive-only",
        "seeds": [
            {
                "seed": seed,
                "training_status": "PASS_TRAINING_FINISHED",
                "formal_experiment": True,
                "internal_test_opened": False,
                "protected_outcomes_opened": False,
                "config_sha256": canonical_sha256(_a10(parents[seed])),
                "input_hashes": _input_hashes(),
                "training_receipt_file_sha256": str(seed) * 32,
            }
            for seed in SEEDS
        ],
    }


def test_phase20_freezes_exact_63_cell_s1_matrix():
    configs = build_phase20_configs(_parents(), _sources())
    assert len(configs) == 63
    expected = {
        "final_mainline_confirmation": 3,
        "exact_loss_ablation": 9,
        "exact_structural_ablation": 9,
        "dmw0_fusion_comparator": 6,
        "source_held_out": 6,
        "data_scaling": 12,
        "label_noise": 18,
    }
    observed = {
        axis: sum(value["phase20_axis"] == axis for value in configs.values())
        for axis in expected
    }
    assert observed == expected

    final = configs["P20-FINAL-S1-S17"]
    assert final["loss_weights"]["prototype_alignment"] == 0
    assert final["loss_weights"]["direction_margin"] == 0
    assert final["loss_weights"]["state"] == 0.025
    assert final["loss_weights"]["opposite_direction_cost"] == 0.05
    assert final["loss_weights"]["cmcp"] == 0.01
    assert final["cmcp"]["matching"] == "offline_hard_v1"


def test_phase20_exact_ablations_change_only_frozen_axis():
    configs = build_phase20_configs(_parents(), _sources())
    final = configs["P20-FINAL-S1-S17"]
    no_state = configs["P20-ABL-NOSTATE-S17"]
    no_cmcp = configs["P20-ABL-NOCMCP-S17"]
    no_odc = configs["P20-ABL-NOODC-S17"]
    assert no_state["loss_weights"]["state"] == 0
    assert no_cmcp["loss_weights"]["cmcp"] == 0
    assert not no_cmcp["model"]["components"]["matched_hard_cmcp"]
    assert no_cmcp["cmcp"]["matching"] == "in_batch_roll_v1"
    assert no_odc["loss_weights"]["opposite_direction_cost"] == 0
    for config in (no_state, no_cmcp, no_odc):
        assert config["loss_weights"]["prototype_alignment"] == 0
        assert config["loss_weights"]["direction_margin"] == 0
        assert config["model"]["adapter_scope"] == final["model"]["adapter_scope"]


@pytest.mark.parametrize(
    ("experiment_id", "field", "bad_value", "message"),
    [
        (
            "P20-STRUCT-NOFINDING-S17",
            "finding_conditioning",
            True,
            "finding-conditioning",
        ),
        (
            "P20-STRUCT-NOALIGN-S17",
            "cross_time_alignment",
            True,
            "cross-time-alignment",
        ),
        (
            "P20-STRUCT-NORELATION-S17",
            "temporal_relation_residual",
            True,
            "temporal-relation-residual",
        ),
    ],
)
def test_phase20_structural_validator_rejects_exact_contract_drift(
    experiment_id, field, bad_value, message
):
    configs = build_phase20_configs(_parents(), _sources())
    configs[experiment_id]["model"]["components"][field] = bad_value
    with pytest.raises(ValueError, match=message):
        validate_phase20_configs(configs, sources=_sources())


def test_phase20_noalign_validator_requires_raw_prior():
    configs = build_phase20_configs(_parents(), _sources())
    configs["P20-STRUCT-NOALIGN-S28"]["model"]["components"]["unaligned_prior_mode"] = (
        "conditioned"
    )
    with pytest.raises(ValueError, match="raw PRIOR"):
        validate_phase20_configs(configs, sources=_sources())


def test_phase20_reuse_audit_certifies_a10_and_retrains_fusion():
    parents = _parents()
    audit = build_reuse_audit(
        parents,
        a10_configs={seed: _a10(parents[seed]) for seed in SEEDS},
        a10_receipt_evidence=_a10_evidence(parents),
        expected_input_sha256=_input_hashes(),
        tila8_configs={seed: _tila(parents[seed]) for seed in SEEDS},
        f01_configs={
            seed: _fusion(parents[seed], tag="F01", family="early_concat")
            for seed in SEEDS
        },
        f02_configs={
            seed: _fusion(parents[seed], tag="F02", family="symmetric_cross_attention")
            for seed in SEEDS
        },
    )
    decisions = audit["decisions"]
    assert decisions["full_data_s0"]["semantic_config_match_by_seed"] == {
        "17": True,
        "28": True,
        "43": True,
    }
    assert decisions["full_data_s0"]["decision"] == "REUSE_A10_AS_FULL_DATA_S0"
    assert decisions["full_data_s0"]["receipt_input_match_by_seed"] == {
        "17": True,
        "28": True,
        "43": True,
    }
    assert decisions["tila_tail8"]["decision"] == "REUSE_DMW_NOT_APPLICABLE"
    assert decisions["if_f01"]["decision"] == "RETRAIN_DMW0"
    assert decisions["if_f02"]["decision"] == "RETRAIN_DMW0"

    broken = _a10(parents[17])
    broken["loss_weights"]["state"] = 0
    with pytest.raises(ValueError, match="semantically equivalent"):
        build_reuse_audit(
            parents,
            a10_configs={
                17: broken,
                28: _a10(parents[28]),
                43: _a10(parents[43]),
            },
            a10_receipt_evidence=_a10_evidence(parents),
            expected_input_sha256=_input_hashes(),
            tila8_configs={seed: _tila(parents[seed]) for seed in SEEDS},
            f01_configs={
                seed: _fusion(parents[seed], tag="F01", family="early_concat")
                for seed in SEEDS
            },
            f02_configs={
                seed: _fusion(
                    parents[seed], tag="F02", family="symmetric_cross_attention"
                )
                for seed in SEEDS
            },
        )


def test_phase20_normalizer_materializes_relation_defaults():
    implicit = _parent(17)
    explicit = deepcopy(implicit)
    explicit["model"]["components"]["unaligned_prior_mode"] = "conditioned"
    explicit["model"]["components"]["temporal_relation_residual"] = True
    assert normalized_s0_semantics(implicit) == normalized_s0_semantics(explicit)


def test_phase20_four_lane_allocation_has_host_local_map_dependencies():
    configs = build_phase20_configs(_parents(), _sources())
    queues = allocate_phase20_jobs(configs)
    assert set(queues) == set(LANES)
    all_jobs = [job for queue in queues.values() for job in queue]
    training = [job for job in all_jobs if job["job_id"].startswith("train-")]
    assert len(training) == 63
    assert len({job["job_id"] for job in all_jobs}) == len(all_jobs)
    by_id = {job["job_id"]: job for job in all_jobs}
    for job in training:
        for dependency in job["dependencies"]:
            assert by_id[dependency]["host"] == job["host"]
    evaluations = [job for job in all_jobs if job["job_id"].startswith("evaluate-")]
    assert len(evaluations) == 6
    for job in evaluations:
        parent = by_id[job["dependencies"][0]]
        assert job["lane"] == parent["lane"]
        assert job["host"] == parent["host"]
    final_jobs = [job for job in training if "P20-FINAL-S1" in job["job_id"]]
    assert len(final_jobs) == 3
    for job in final_jobs:
        lane_queue = queues[job["lane"]]
        assert lane_queue.index(job) == 0
    loads = [
        sum(job["estimated_seconds"] for job in queue) for queue in queues.values()
    ]
    assert max(loads) - min(loads) < 20_000


def test_phase20_three_lane_allocation_reserves_second_local_gpu():
    configs = build_phase20_configs(_parents(), _sources())
    active = ("a800_3066", "a800_9929", "rtx3090_0")
    queues = allocate_phase20_jobs(configs, active_lanes=active)
    assert tuple(queues) == active
    assert "rtx3090_1" not in queues
    all_jobs = [job for queue in queues.values() for job in queue]
    training = [job for job in all_jobs if job["job_id"].startswith("train-")]
    assert len(training) == 63
    assert {job["lane"] for job in all_jobs} <= set(active)
    loads = [
        sum(job["estimated_seconds"] for job in queue) for queue in queues.values()
    ]
    assert max(loads) - min(loads) < 20_000
