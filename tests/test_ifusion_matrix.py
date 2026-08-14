import json
from copy import deepcopy

from prta_cxr.contracts import sha256_file
from prta_cxr.ifusion_matrix import (
    ABLATIONS,
    FUSION_FAMILIES,
    SEEDS,
    allocate_duration_balanced,
    build_ifusion_training_configs,
    prepare_ifusion_matrix_main,
)


def _parent(seed):
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": f"W045-V2-S{seed}",
        "seed": seed,
        "development_axis": "prta_v2_tail8_h0_v1",
        "prta_v2_variant": "V2",
        "cache_entry_block": 4,
        "model": {
            "family": "prta",
            "width": 768,
            "adapter_rank": 32,
            "heads": 12,
            "state_tokens": 20,
            "transition_tokens": 20,
            "dropout": 0.1,
            "native_head": "H0",
            "adapter_scope": "tail8",
            "components": {
                "finding_conditioning": True,
                "cross_time_alignment": True,
                "dual_branch": True,
                "branch_mode": "legacy",
                "matched_hard_cmcp": True,
                "learned_relation_residual_scale": False,
                "relation_residual_initial_scale": 0.001,
                "prior_reliability_gate": False,
                "selective_state_anchor": False,
                "selective_state_beta": 1.0,
            },
        },
        "optimization": {
            "epochs": 20,
            "batch_size": 16,
            "learning_rate": 0.0001,
        },
        "data": {"train_fraction": 1.0},
        "classification_loss": {
            "name": "class_balanced_focal",
            "class_counts": [10, 9, 8, 7, 6],
        },
        "direction_margin": {"margin": 0.2},
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.0,
            "direction_margin": 0.01,
            "opposite_direction_cost": 0.05,
            "state": 0.025,
            "inversion": 0.0,
            "cmcp": 0.01,
            "prototype_alignment": 0.01,
            "branch_decorrelation": 0.0,
        },
        "prototype_alignment": {"temperature": 0.07},
        "cmcp": {"margin": 0.2, "matching": "offline_hard_v1"},
    }


def _parents():
    return {seed: _parent(seed) for seed in SEEDS}


def test_ifusion_builder_freezes_exact_33_cell_core_matrix():
    configs = build_ifusion_training_configs(_parents())
    assert len(configs) == 33
    assert {config["ifusion_variant"] for config in configs} == {
        *ABLATIONS,
        *FUSION_FAMILIES,
    }
    assert {config["seed"] for config in configs} == set(SEEDS)


def test_ifusion_ablation_semantics_match_final_plan():
    configs = {
        config["ifusion_variant"]: config
        for config in build_ifusion_training_configs(_parents())
        if config["seed"] == 17
    }
    assert not configs["IF-A01"]["model"]["components"]["finding_conditioning"]
    assert configs["IF-A02"]["model"]["components"]["unaligned_prior_mode"] == "raw"
    assert not configs["IF-A03"]["model"]["components"]["temporal_relation_residual"]
    assert configs["IF-A04"]["loss_weights"]["state"] == 0
    assert configs["IF-A05"]["loss_weights"]["direction_margin"] == 0
    assert configs["IF-A05"]["loss_weights"]["opposite_direction_cost"] == 0
    assert configs["IF-A06"]["loss_weights"]["prototype_alignment"] == 0
    assert configs["IF-A06"]["loss_weights"]["cmcp"] == 0.01
    assert configs["IF-A08"]["cmcp"]["matching"] == "offline_random_v1"
    assert configs["IF-A10"]["loss_weights"]["direction_margin"] == 0
    assert configs["IF-A10"]["loss_weights"]["opposite_direction_cost"] == 0.05
    assert configs["IF-A11"]["loss_weights"]["direction_margin"] == 0.01
    assert configs["IF-A11"]["loss_weights"]["opposite_direction_cost"] == 0


def test_duration_allocator_uses_all_four_lanes_and_bounds_imbalance():
    configs = build_ifusion_training_configs(_parents())
    allocation = allocate_duration_balanced(configs)
    assert set(allocation) == {
        "server3066",
        "server9929",
        "local_gpu0",
        "local_gpu1",
    }
    assert all(allocation.values())
    assert sum(map(len, allocation.values())) == 33
    loads = [
        sum(row["estimated_seconds"] for row in rows) for rows in allocation.values()
    ]
    assert max(loads) - min(loads) <= max(
        row["estimated_seconds"] for rows in allocation.values() for row in rows
    )


def test_builder_does_not_mutate_frozen_parent_configs():
    parents = _parents()
    before = deepcopy(parents)
    build_ifusion_training_configs(parents)
    assert parents == before


def test_preparer_writes_frozen_portable_matrix_and_four_queues(tmp_path):
    parent_paths = []
    for seed in SEEDS:
        path = tmp_path / f"W045-V2-S{seed}.json"
        path.write_text(json.dumps(_parent(seed)), encoding="utf-8")
        parent_paths.append(path)

    rows = [
        {
            "sample_id": f"{split}-sample-{index}",
            "patient_id_hash": f"{split}-patient-{index}",
            "finding": "Edema",
            "progression_label": label,
            "split": split,
        }
        for split in ("train", "dev")
        for index, label in enumerate(
            ("Stable", "Improved", "Worse", "New", "Resolved", "Stable")
        )
    ]
    split_path = tmp_path / "train_dev.jsonl"
    split_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    freeze = tmp_path / "cleaned_freeze.json"
    freeze.write_text("{}\n", encoding="utf-8")
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    cache_manifest = cache_root / "cache_manifest.json"
    cache_manifest.write_text("{}\n", encoding="utf-8")
    text_cache = tmp_path / "text.pt"
    weights = tmp_path / "weights.bin"
    quality = tmp_path / "quality.json"
    for path in (text_cache, weights, quality):
        path.write_bytes(b"test")

    by_group = {}
    for row in rows:
        by_group.setdefault((row["split"], row["finding"]), []).append(row)
    entries = []
    for group in by_group.values():
        for target in group:
            candidate = next(
                row
                for row in group
                if row["patient_id_hash"] != target["patient_id_hash"]
                and row["progression_label"] != target["progression_label"]
            )
            entries.append(
                {
                    "target_sample_id": target["sample_id"],
                    "counterfactual_sample_id": candidate["sample_id"],
                }
            )
    hard_map = tmp_path / "hard_map.json"
    hard_map.write_text(
        json.dumps(
            {
                "schema": "prta-cxr.matched-hard-prior-map.v1",
                "split_manifest_sha256": sha256_file(split_path),
                "cache_manifest_sha256": sha256_file(cache_manifest),
                "cache_entry_block": 4,
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "ifusion"
    arguments = ["--v2-config"]
    arguments.extend(map(str, parent_paths))
    arguments.extend(
        [
            "--split-manifest",
            str(split_path),
            "--cleaned-split-freeze",
            str(freeze),
            "--cache-root",
            str(cache_root),
            "--text-cache",
            str(text_cache),
            "--matched-hard-prior-map",
            str(hard_map),
            "--weights",
            str(weights),
            "--label-quality-audit",
            str(quality),
            "--output-root",
            str(output),
        ]
    )
    assert prepare_ifusion_matrix_main(arguments) == 0
    receipt = json.loads(
        (output / "preparation_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "PASS_IFUSION_CORE_MATRIX_FROZEN"
    assert receipt["training_cell_count"] == 33
    assert receipt["protected_outcome_read_count"] == 0
    queues = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((output / "queue").glob("*.json"))
    ]
    assert len(queues) == 4
    assert sum(map(len, queues)) == 33
    assert all(
        not str(row["config"]["path"]).startswith(str(tmp_path))
        for queue in queues
        for row in queue
    )
