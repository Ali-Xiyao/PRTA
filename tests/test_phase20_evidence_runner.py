from pathlib import Path

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_evidence_runner import (
    render_evidence_command,
    validate_evidence_platform_inputs,
)


def _file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_phase20_evidence_platform_inputs_are_hash_bound(tmp_path):
    cache_root = tmp_path / "cache"
    model_root = tmp_path / "model"
    cleaned_root = tmp_path / "cleaned"
    cleaned_root.mkdir()
    platform = {
        "split_manifest": str(_file(tmp_path / "split.jsonl")),
        "cleaned_split_freeze": str(_file(tmp_path / "freeze.json")),
        "cleaned_split_platform_root": str(cleaned_root),
        "cache_root": str(cache_root),
        "text_cache": str(_file(tmp_path / "text.pt")),
        "matched_hard_prior_map": str(_file(tmp_path / "map.json")),
        "weights": str(_file(tmp_path / "weights.bin", b"weights")),
        "label_quality_audit": str(_file(tmp_path / "quality.json")),
        "model_root": str(model_root),
    }
    file_roles = {
        "split_manifest": Path(platform["split_manifest"]),
        "cleaned_split_freeze": Path(platform["cleaned_split_freeze"]),
        "cache_manifest": _file(cache_root / "cache_manifest.json"),
        "text_cache": Path(platform["text_cache"]),
        "matched_hard_prior_map": Path(platform["matched_hard_prior_map"]),
        "weights": Path(platform["weights"]),
        "label_quality_audit": Path(platform["label_quality_audit"]),
        "model_open_clip_config": _file(model_root / "open_clip_config.json"),
        "model_tokenizer": _file(model_root / "tokenizer.json"),
        "model_config": _file(model_root / "config.json"),
        "model_weights": _file(
            model_root / "open_clip_pytorch_model.bin", b"weights"
        ),
    }
    for seed in (17, 28, 43):
        checkpoint = _file(tmp_path / f"S{seed}" / "best.pt")
        receipt = _file(tmp_path / f"S{seed}" / "training_receipt.json")
        platform[f"s1_checkpoint_{seed}"] = str(checkpoint)
        platform[f"s1_training_receipt_{seed}"] = str(receipt)
        file_roles[f"s1_checkpoint_{seed}"] = checkpoint
        file_roles[f"s1_training_receipt_{seed}"] = receipt
    manifest = {
        "input_sha256": {
            role: sha256_file(path) for role, path in file_roles.items()
        }
    }
    validated = validate_evidence_platform_inputs(platform, manifest)
    assert validated["cache_root"] == cache_root.resolve()
    assert validated["s1_checkpoint_43"].is_file()

    Path(platform["s1_checkpoint_17"]).write_bytes(b"drift")
    with pytest.raises(ValueError, match="input hash drift: s1_checkpoint_17"):
        validate_evidence_platform_inputs(platform, manifest)


def test_phase20_evidence_render_rejects_unresolved_placeholders(tmp_path):
    rendered = render_evidence_command(
        ["{python}", "{source}/script.py", "{s1_checkpoint_17}"],
        source=tmp_path / "source",
        runtime_root=tmp_path / "program",
        output_root=tmp_path / "output",
        device="cuda:0",
        inputs={"s1_checkpoint_17": tmp_path / "best.pt"},
    )
    assert rendered[1].endswith("script.py")
    with pytest.raises(ValueError, match="unresolved Phase20 evidence placeholder"):
        render_evidence_command(
            ["{missing}"],
            source=tmp_path,
            runtime_root=tmp_path,
            output_root=tmp_path,
            device="cpu",
            inputs={},
        )
