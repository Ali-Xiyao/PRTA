from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import torch

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.token_cache import image_cache_key


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
    if features.ndim != 3 or tuple(features.shape[1:]) != (197, 768):
        raise ValueError("Block-8 features must have shape [N, 197, 768]")
    if len(inventory) != features.shape[0]:
        raise ValueError("inventory and feature counts differ")
    if not torch.isfinite(features).all():
        raise ValueError("Block-8 features contain non-finite values")
    keys = [str(item["image_key"]) for item in inventory]
    if len(keys) != len(set(keys)):
        raise ValueError("image inventory keys must be unique")

    output_root.mkdir(parents=True)
    normalized = [
        {
            "image_key": str(item["image_key"]),
            "source": str(item["source"]),
            "image_path": str(item["image_path"]),
        }
        for item in inventory
    ]
    write_json_atomic(output_root / "image_inventory.json", normalized)
    shards = []
    for shard_index, start in enumerate(range(0, len(normalized), shard_size)):
        selected = features[start : start + shard_size].detach().cpu().to(torch.float16)
        name = f"block8_{shard_index:05d}.pt"
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
        "schema": "prta-cxr.block8-cache.v1",
        "status": "PASS_PRTA_CXR_BLOCK8_CACHE",
        "cached_image_count": len(normalized),
        "token_shape": [197, 768],
        "dtype": "float16",
        "inventory_path": "image_inventory.json",
        "inventory_sha256": canonical_sha256(normalized),
        "shards": shards,
        "encoder": dict(encoder_receipt or {}),
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
