from pathlib import Path

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.phase15_assets import build_phase15_registries
from prta_cxr.phase15_queue import SEEDS, SYSTEMS, validate_job_registry


def _plan(tmp_path: Path):
    assets = []
    for system in SYSTEMS:
        for seed in SEEDS:
            root = tmp_path / system / str(seed)
            root.mkdir(parents=True)
            checkpoint = root / "best.pt"
            receipt = root / "training_receipt.json"
            checkpoint.write_bytes(f"{system}-{seed}".encode())
            receipt.write_text("{}", encoding="utf-8")
            assets.append(
                {
                    "system": system,
                    "seed": seed,
                    "local_checkpoint": str(checkpoint),
                    "remote_checkpoint": f"/runtime/assets/{system}/S{seed}/best.pt",
                    "local_training_receipt": str(receipt),
                    "remote_training_receipt": (
                        f"/runtime/assets/{system}/S{seed}/training_receipt.json"
                    ),
                }
            )
    return {
        "schema": "prta-cxr.phase15-asset-plan.v1",
        "shared_inputs": {
            "split_manifest": "/runtime/split.jsonl",
            "cleaned_split_freeze": "/runtime/freeze.json",
            "matched_hard_prior_map": "/runtime/map.json",
            "weights": "/runtime/weights.pt",
            "label_quality_audit": "/runtime/audit.json",
        },
        "cache_inputs": {
            system: {
                "cache_root": f"/runtime/cache/{system}",
                "text_cache": f"/runtime/cache/{system}/text.pt",
            }
            for system in SYSTEMS
        },
        "estimated_seconds": {
            "probability": {system: 60 for system in SYSTEMS},
            "efficiency": {system: 90 for system in SYSTEMS},
        },
        "assets": assets,
    }


def test_build_phase15_registries_binds_hashes_and_complete_matrix(tmp_path):
    plan = _plan(tmp_path)
    registries = build_phase15_registries(plan)
    jobs = validate_job_registry(registries["job_registry"])
    assert len(jobs) == 16
    assert registries["asset_registry"]["transfer_file_count"] == 24
    first = registries["transfer_manifest"]["files"][0]
    assert first["sha256"] == sha256_file(Path(first["local_path"]))


def test_server_resident_asset_requires_bound_hash_and_size(tmp_path):
    plan = _plan(tmp_path)
    asset = plan["assets"][0]
    asset["local_checkpoint"] = None
    asset["checkpoint_sha256"] = "a" * 64
    asset["checkpoint_bytes"] = 123
    registries = build_phase15_registries(plan)
    assert registries["asset_registry"]["server_resident_file_count"] == 1

    asset["checkpoint_sha256"] = ""
    with pytest.raises(ValueError, match="requires a SHA-256"):
        build_phase15_registries(plan)
