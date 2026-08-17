from prta_cxr.phase16_program import build_phase16_configs, build_phase16_jobs


def _base():
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "W045-V2-S28",
        "seed": 28,
        "prta_v2_variant": "V2",
        "data": {"train_fraction": 1.0, "fraction_salt": "f"},
        "model": {
            "family": "prta",
            "adapter_scope": "tail8",
            "heads": 12,
            "components": {},
        },
        "optimization": {"epochs": 20},
        "loss_weights": {"classification": 1.0, "cmcp": 0.01},
    }


def _inputs():
    value = {
        name: f"/x/{name}"
        for name in (
            "split_manifest",
            "cleaned_split_freeze",
            "cleaned_split_platform_root",
            "cache_root",
            "text_cache",
            "weights",
            "label_quality_audit",
            "matched_hard_prior_map",
            "model_root",
        )
    }
    value["v2"] = {
        str(seed): {
            "checkpoint": f"/x/S{seed}/best.pt",
            "training_receipt": f"/x/S{seed}/training.json",
            "baseline_probability_receipt": f"/x/S{seed}/probability.json",
        }
        for seed in (17, 28, 43)
    }
    return value


def test_phase16_full_config_matrix_and_jobs():
    configs = build_phase16_configs(_base(), ("chexpert_plus", "mimic_cxr_jpg"))
    assert len(configs) == 51
    assert (
        sum(config["phase16_axis"] == "data_scaling" for config in configs.values())
        == 12
    )
    assert (
        sum(config["phase16_axis"] == "source_held_out" for config in configs.values())
        == 12
    )
    assert (
        sum(config["phase16_axis"] == "label_noise" for config in configs.values())
        == 18
    )
    assert (
        sum(
            config["phase16_axis"] == "internal_longitudinal_comparator"
            for config in configs.values()
        )
        == 9
    )
    jobs = build_phase16_jobs(configs, inputs=_inputs(), remote_program_root="/program")
    assert len(jobs) == 87
    assert len({job["job_id"] for job in jobs}) == len(jobs)
    assert sum(job["job_id"].startswith("map-") for job in jobs) == 10
    assert sum(job["job_id"].startswith("train-") for job in jobs) == 51
    assert sum(job["job_id"].startswith("evaluate-P16-SOURCE") for job in jobs) == 12
    assert sum(job["job_id"].startswith("modality-stress-v2-S") for job in jobs) == 3
    source_configs = [
        config
        for config in configs.values()
        if config["phase16_axis"] == "source_held_out"
    ]
    roll_configs = [
        config
        for config in source_configs
        if config["source_held_out_role"] == "exploratory"
    ]
    assert all(
        config["cmcp"]["matching"] == "in_batch_roll_v1"
        and config["model"]["components"]["matched_hard_cmcp"] is False
        for config in roll_configs
    )
    v1_configs = [
        config
        for config in source_configs
        if config["source_held_out_role"] == "confirmatory"
    ]
    assert len(v1_configs) == 6
    assert all(
        config["prta_v2_variant"] == "V1"
        and config["loss_weights"]["prototype_alignment"] == 0.01
        and config["loss_weights"]["cmcp"] == 0.0
        and config["model"]["components"]["matched_hard_cmcp"] is False
        for config in v1_configs
    )
    source_jobs = [job for job in jobs if job["job_id"].startswith("train-P16-SOURCE")]
    assert all(not job["dependencies"] for job in source_jobs)
    assert all(
        "--counterfactual-prior-map" not in job["command"] for job in source_jobs
    )
    comparators = [
        config
        for config in configs.values()
        if config["phase16_axis"] == "internal_longitudinal_comparator"
    ]
    assert all(
        config["method_provenance"] == "architecture_inspired_internal_reimplementation"
        and config["official_implementation"] is False
        and "Official" not in config["method_label"]
        for config in comparators
    )
    modality_cache = next(
        job for job in jobs if job["job_id"] == "modality-text-cache-v2"
    )
    assert "--model-root" in modality_cache["command"]
    assert "--text-cache" not in modality_cache["command"]
