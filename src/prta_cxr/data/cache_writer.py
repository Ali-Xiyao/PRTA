from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import torch

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.token_cache import image_cache_key


def _replace_json_atomic(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _normalized_inventory(
    inventory: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    normalized = [
        {
            "image_key": str(item["image_key"]),
            "source": str(item["source"]),
            "image_path": str(item["image_path"]),
        }
        for item in inventory
    ]
    keys = [item["image_key"] for item in normalized]
    if len(keys) != len(set(keys)):
        raise ValueError("image inventory keys must be unique")
    return normalized


def _validate_feature_tensor(
    features: torch.Tensor, *, expected_images: int
) -> None:
    if features.ndim != 3 or tuple(features.shape[1:]) != (197, 768):
        raise ValueError("intermediate features must have shape [N, 197, 768]")
    if features.shape[0] != expected_images:
        raise ValueError("inventory and feature counts differ")
    if not torch.isfinite(features).all():
        raise ValueError("intermediate features contain non-finite values")


def _entry_block(encoder_receipt: Mapping[str, Any]) -> int:
    value = int(encoder_receipt.get("output_block", 8))
    if value not in {2, 4, 6, 8}:
        raise ValueError("cache encoder output_block must be 2, 4, 6, or 8")
    return value


def _cache_status(entry_block: int) -> str:
    return f"PASS_PRTA_CXR_BLOCK{entry_block}_CACHE"


def _cache_schema(entry_block: int, *, build: bool = False) -> str:
    suffix = "-build" if build else ""
    return f"prta-cxr.block{entry_block}-cache{suffix}.v1"


def _streaming_identity(
    normalized: list[dict[str, str]],
    *,
    shard_size: int,
    encoder_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    entry_block = _entry_block(encoder_receipt)
    return {
        "schema": _cache_schema(entry_block, build=True),
        "status": "IN_PROGRESS",
        "cache_entry_block": entry_block,
        "cached_image_count": len(normalized),
        "token_shape": [197, 768],
        "dtype": "float16",
        "inventory_path": "image_inventory.json",
        "inventory_sha256": canonical_sha256(normalized),
        "shard_size": int(shard_size),
        "encoder": dict(encoder_receipt),
        "shards": [],
        "completed_images": 0,
    }


def _validate_recorded_streaming_shards(
    output_root: Path,
    state: dict[str, Any],
) -> None:
    total = int(state["cached_image_count"])
    shard_size = int(state["shard_size"])
    entry_block = int(state.get("cache_entry_block", 8))
    completed = 0
    for index, entry in enumerate(state["shards"]):
        expected_name = f"block{entry_block}_{index:05d}.pt"
        if entry["path"] != expected_name:
            raise ValueError("streaming cache shard order is not contiguous")
        expected_count = min(shard_size, total - completed)
        if int(entry["images"]) != expected_count:
            raise ValueError("streaming cache shard image count mismatch")
        target = output_root / expected_name
        if not target.is_file() or sha256_file(target) != entry["sha256"]:
            raise ValueError("streaming cache shard hash mismatch")
        value = torch.load(target, map_location="cpu", weights_only=True)
        _validate_feature_tensor(
            value["features"], expected_images=expected_count
        )
        completed += expected_count
    if completed != int(state["completed_images"]):
        raise ValueError("streaming cache completed-image count mismatch")


def prepare_streaming_block8_cache(
    output_root: Path,
    inventory: list[Mapping[str, str]],
    *,
    shard_size: int,
    encoder_receipt: Mapping[str, Any],
    resume: bool,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Create or validate a bounded-memory, resume-safe cache build."""
    output_root = Path(output_root)
    if shard_size <= 0:
        raise ValueError("shard_size must be positive")
    normalized = _normalized_inventory(inventory)
    expected = _streaming_identity(
        normalized,
        shard_size=shard_size,
        encoder_receipt=encoder_receipt,
    )
    inventory_path = output_root / "image_inventory.json"
    state_path = output_root / "cache_build_state.json"
    if not output_root.exists():
        output_root.mkdir(parents=True)
        write_json_atomic(inventory_path, normalized)
        _replace_json_atomic(state_path, expected)
        return normalized, expected
    if not resume:
        raise FileExistsError(f"refusing to overwrite cache root: {output_root}")
    if not inventory_path.is_file() or not state_path.is_file():
        raise ValueError("resume cache lacks inventory or build state")
    recorded_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    identity_fields = (
        "schema",
        "cache_entry_block",
        "cached_image_count",
        "token_shape",
        "dtype",
        "inventory_path",
        "inventory_sha256",
        "shard_size",
        "encoder",
    )
    for field in identity_fields:
        if state.get(field) != expected[field]:
            raise ValueError(f"resume cache identity mismatch for {field}")
    if canonical_sha256(recorded_inventory) != expected["inventory_sha256"]:
        raise ValueError("resume cache inventory content mismatch")
    _validate_recorded_streaming_shards(output_root, state)
    recorded_names = {str(entry["path"]) for entry in state["shards"]}
    entry_block = int(state.get("cache_entry_block", 8))
    disk_names = {
        path.name for path in output_root.glob(f"block{entry_block}_*.pt")
    }
    if disk_names != recorded_names:
        raise ValueError("resume cache has unregistered or missing shard files")
    return normalized, state


def write_streaming_block8_shard(
    output_root: Path,
    state: dict[str, Any],
    features: torch.Tensor,
) -> dict[str, Any]:
    output_root = Path(output_root)
    index = len(state["shards"])
    start = int(state["completed_images"])
    total = int(state["cached_image_count"])
    expected_count = min(int(state["shard_size"]), total - start)
    if expected_count <= 0:
        raise ValueError("streaming cache already contains every image")
    _validate_feature_tensor(features, expected_images=expected_count)
    entry_block = int(state.get("cache_entry_block", 8))
    name = f"block{entry_block}_{index:05d}.pt"
    target = output_root / name
    if target.exists():
        raise FileExistsError(f"refusing to overwrite cache shard: {target}")
    temporary = target.with_name(f".{target.name}.tmp.{os.getpid()}")
    try:
        torch.save(
            {"features": features.detach().cpu().to(torch.float16)}, temporary
        )
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    entry = {
        "path": name,
        "images": expected_count,
        "sha256": sha256_file(target),
    }
    state["shards"].append(entry)
    state["completed_images"] = start + expected_count
    _replace_json_atomic(output_root / "cache_build_state.json", state)
    return entry


def finalize_streaming_block8_cache(
    output_root: Path, state: dict[str, Any]
) -> dict[str, Any]:
    output_root = Path(output_root)
    if int(state["completed_images"]) != int(state["cached_image_count"]):
        raise ValueError("cannot finalize an incomplete streaming cache")
    _validate_recorded_streaming_shards(output_root, state)
    entry_block = int(state.get("cache_entry_block", 8))
    manifest = {
        "schema": _cache_schema(entry_block),
        "status": _cache_status(entry_block),
        "cache_entry_block": entry_block,
        "cached_image_count": int(state["cached_image_count"]),
        "token_shape": [197, 768],
        "dtype": "float16",
        "inventory_path": "image_inventory.json",
        "inventory_sha256": state["inventory_sha256"],
        "shards": list(state["shards"]),
        "encoder": dict(state["encoder"]),
        "contains_reports": False,
        "contains_labels": False,
        "contains_patient_identifiers": False,
        "resume_safe": True,
    }
    manifest_path = output_root / "cache_manifest.json"
    if manifest_path.exists():
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
        comparable = dict(recorded)
        comparable.pop("text_cache", None)
        comparable.pop("formal_input", None)
        comparable.pop("training_store", None)
        if comparable != manifest:
            raise ValueError("existing final cache manifest differs from build")
    else:
        write_json_atomic(manifest_path, manifest)
    state["status"] = "COMPLETE"
    _replace_json_atomic(output_root / "cache_build_state.json", state)
    return manifest


def replace_cache_manifest(output_root: Path, manifest: Mapping[str, Any]) -> None:
    _replace_json_atomic(Path(output_root) / "cache_manifest.json", dict(manifest))


def build_block8_training_store(output_root: Path) -> dict[str, Any]:
    """Build one contiguous read-only FP16 store from verified cache shards."""
    output_root = Path(output_root)
    manifest_path = output_root / "cache_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry_block = int(
        manifest.get(
            "cache_entry_block",
            dict(manifest.get("encoder", {})).get("output_block", 8),
        )
    )
    if manifest.get("status") != _cache_status(entry_block):
        raise ValueError("training store requires a complete intermediate cache")
    target = output_root / f"block{entry_block}_features.f16.bin"
    receipt_path = output_root / "training_store_receipt.json"
    expected_bytes = (
        int(manifest["cached_image_count"]) * 197 * 768 * 2
    )
    if target.exists() or receipt_path.exists():
        if not target.is_file() or not receipt_path.is_file():
            raise FileExistsError("incomplete Block-8 training store exists")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if target.stat().st_size != expected_bytes:
            raise ValueError("existing training store has the wrong byte size")
        if receipt.get("file_sha256") != sha256_file(target):
            raise ValueError("existing training store hash mismatch")
        return receipt
    temporary = target.with_name(f".{target.name}.tmp.{os.getpid()}")
    digest = hashlib.sha256()
    rows = 0
    try:
        with temporary.open("wb") as handle:
            for entry in manifest["shards"]:
                shard_path = output_root / str(entry["path"])
                if sha256_file(shard_path) != str(entry["sha256"]):
                    raise ValueError(f"cache shard hash mismatch: {shard_path}")
                value = torch.load(shard_path, map_location="cpu", weights_only=True)
                features = value["features"].contiguous().to(torch.float16)
                _validate_feature_tensor(
                    features, expected_images=int(entry["images"])
                )
                payload = features.numpy().tobytes(order="C")
                handle.write(payload)
                digest.update(payload)
                rows += int(features.shape[0])
            handle.flush()
            os.fsync(handle.fileno())
        if rows != int(manifest["cached_image_count"]):
            raise ValueError("training store row count mismatch")
        if temporary.stat().st_size != expected_bytes:
            raise ValueError("training store byte count mismatch")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    receipt = {
        "schema": f"prta-cxr.block{entry_block}-training-store.v1",
        "status": f"PASS_BLOCK{entry_block}_TRAINING_STORE",
        "cache_entry_block": entry_block,
        "path": target.name,
        "rows": rows,
        "shape": [rows, 197, 768],
        "dtype": "float16",
        "bytes": expected_bytes,
        "file_sha256": digest.hexdigest(),
        "inventory_sha256": manifest["inventory_sha256"],
        "source_cache_manifest_sha256": sha256_file(manifest_path),
    }
    write_json_atomic(receipt_path, receipt)
    manifest["training_store"] = receipt
    replace_cache_manifest(output_root, manifest)
    return receipt


def unique_image_inventory(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    inventory: dict[str, dict[str, str]] = {}
    for row in rows:
        source = str(row["source"])
        for prefix in ("prior", "current"):
            path = str(row[f"{prefix}_image_path"])
            key = image_cache_key(source, path)
            item = {"image_key": key, "source": source, "image_path": path}
            previous = inventory.setdefault(key, item)
            if previous != item:
                raise ValueError("image cache key collision")
    return [inventory[key] for key in sorted(inventory)]


def write_block8_cache(
    output_root: Path,
    inventory: list[Mapping[str, str]],
    features: torch.Tensor,
    *,
    shard_size: int = 256,
    encoder_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite cache root: {output_root}")
    if shard_size <= 0:
        raise ValueError("shard_size must be positive")
    _validate_feature_tensor(features, expected_images=len(inventory))
    receipt = dict(encoder_receipt or {})
    entry_block = _entry_block(receipt)

    output_root.mkdir(parents=True)
    normalized = _normalized_inventory(inventory)
    write_json_atomic(output_root / "image_inventory.json", normalized)
    shards = []
    for shard_index, start in enumerate(range(0, len(normalized), shard_size)):
        selected = features[start : start + shard_size].detach().cpu().to(torch.float16)
        name = f"block{entry_block}_{shard_index:05d}.pt"
        target = output_root / name
        temporary = target.with_name(f".{target.name}.tmp.{os.getpid()}")
        try:
            torch.save({"features": selected}, temporary)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        shards.append(
            {
                "path": name,
                "images": selected.shape[0],
                "sha256": sha256_file(target),
            }
        )
    manifest = {
        "schema": _cache_schema(entry_block),
        "status": _cache_status(entry_block),
        "cache_entry_block": entry_block,
        "cached_image_count": len(normalized),
        "token_shape": [197, 768],
        "dtype": "float16",
        "inventory_path": "image_inventory.json",
        "inventory_sha256": canonical_sha256(normalized),
        "shards": shards,
        "encoder": receipt,
        "contains_reports": False,
        "contains_labels": False,
        "contains_patient_identifiers": False,
    }
    write_json_atomic(output_root / "cache_manifest.json", manifest)
    return manifest


def synthetic_block8_features(count: int, *, seed: int) -> torch.Tensor:
    if count <= 0:
        raise ValueError("synthetic cache requires at least one image")
    generator = torch.Generator().manual_seed(seed)
    return torch.randn(count, 197, 768, generator=generator)
