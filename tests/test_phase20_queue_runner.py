import json
import sys

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_queue_runner import (
    dependency_decision,
    render_command,
    validate_platform_inputs,
)


def test_phase20_dependency_decision():
    assert dependency_decision([]) == "RUN"
    assert dependency_decision(["PASS"]) == "RUN"
    assert dependency_decision(["PASS", "PENDING"]) == "WAIT"
    assert dependency_decision(["FAILED"]) == "SKIP"
    assert dependency_decision(["SKIPPED"]) == "SKIP"


def test_phase20_render_command_resolves_platform_inputs(tmp_path):
    inputs = {
        "split_manifest": tmp_path / "split.jsonl",
        "cleaned_split_freeze": tmp_path / "freeze.json",
    }
    rendered = render_command(
        [
            "{python}",
            "{source}/scripts/07_train.py",
            "{runtime_root}/configs/a.json",
            "{output_root}/runs/a",
            "{split_manifest}",
            "{cleaned_split_freeze}",
            "{device}",
        ],
        source=tmp_path / "source",
        runtime_root=tmp_path / "runtime",
        output_root=tmp_path / "output",
        device="cuda:1",
        inputs=inputs,
    )
    assert rendered[0] == sys.executable
    assert rendered[-1] == "cuda:1"
    assert rendered[4] == str(inputs["split_manifest"])
    assert rendered[5] == str(inputs["cleaned_split_freeze"])
    with pytest.raises(ValueError, match="unresolved"):
        render_command(
            ["{missing}"],
            source=tmp_path,
            runtime_root=tmp_path,
            output_root=tmp_path,
            device="cpu",
            inputs={},
        )


def test_phase20_platform_inputs_are_hash_gated(tmp_path):
    direct = {}
    for name in (
        "split_manifest",
        "cleaned_split_freeze",
        "text_cache",
        "matched_hard_prior_map",
        "weights",
        "label_quality_audit",
    ):
        path = tmp_path / name
        path.write_text(json.dumps({"name": name}) + "\n", encoding="utf-8")
        direct[name] = path
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    cache_manifest = cache_root / "cache_manifest.json"
    cache_manifest.write_text("{}\n", encoding="utf-8")
    cleaned_root = tmp_path / "cleaned"
    cleaned_root.mkdir()
    inputs = {
        **{name: str(path) for name, path in direct.items()},
        "cache_root": str(cache_root),
        "cleaned_split_platform_root": str(cleaned_root),
    }
    roles = {
        **{name: path for name, path in direct.items()},
        "cache_manifest": cache_manifest,
    }
    manifest = {
        "schema": "prta-cxr.phase20-input-manifest.v1",
        "input_sha256": {name: sha256_file(path) for name, path in roles.items()},
    }
    resolved = validate_platform_inputs(inputs, manifest)
    assert resolved["cache_root"] == cache_root.resolve()
    direct["weights"].write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="weights"):
        validate_platform_inputs(inputs, manifest)


def test_phase20_platform_inputs_allow_hash_bound_posttraining_artifacts(tmp_path):
    direct = {}
    for name in (
        "split_manifest",
        "cleaned_split_freeze",
        "text_cache",
        "matched_hard_prior_map",
        "weights",
        "label_quality_audit",
    ):
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        direct[name] = path
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    cache_manifest = cache_root / "cache_manifest.json"
    cache_manifest.write_text("{}", encoding="utf-8")
    cleaned_root = tmp_path / "cleaned"
    cleaned_root.mkdir()
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"checkpoint")
    inputs = {
        **{name: str(path) for name, path in direct.items()},
        "cache_root": str(cache_root),
        "cleaned_split_platform_root": str(cleaned_root),
        "b2_s0_checkpoint_17": str(checkpoint),
    }
    manifest = {
        "schema": "prta-cxr.phase20-input-manifest.v1",
        "input_sha256": {
            **{name: sha256_file(path) for name, path in direct.items()},
            "cache_manifest": sha256_file(cache_manifest),
            "b2_s0_checkpoint_17": sha256_file(checkpoint),
        },
    }
    result = validate_platform_inputs(inputs, manifest)
    assert result["b2_s0_checkpoint_17"] == checkpoint.resolve()
