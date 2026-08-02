from __future__ import annotations

import hashlib
import json
from collections import OrderedDict, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import torch


def image_cache_key(source: object, image_path: object) -> str:
    """Return a stable, non-identifying key for an image lineage."""
    namespace = str(source).strip()
    path = str(image_path).strip().replace("\\", "/")
    if not namespace or not path:
        raise ValueError("cache keys require non-empty source and image path")
    return hashlib.sha256(f"{namespace}|{path}".encode()).hexdigest()


class Block8CacheIndex:
    def __init__(
        self,
        cache_root: Path,
        *,
        required_status: str = "PASS_PRTA_CXR_BLOCK8_CACHE",
        maximum_loaded_shards: int = 4,
    ):
        if maximum_loaded_shards <= 0:
            raise ValueError("maximum loaded shards must be positive")
        self.cache_root = Path(cache_root)
        self.required_status = required_status
        self.maximum_loaded_shards = maximum_loaded_shards
        self.locations: dict[str, tuple[Path, int]] = {}
        self._loaded: OrderedDict[Path, dict[str, Any]] = OrderedDict()
        self._global_locations: dict[str, int] = {}
        self._training_store_path: Path | None = None
        self._training_store_shape: tuple[int, int, int] | None = None
        self._training_store: np.memmap | None = None
        self._build_index()

    def _build_index(self) -> None:
        merged = json.loads(
            (self.cache_root / "cache_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        if merged["status"] != self.required_status:
            raise ValueError("Block-8 cache does not match the required status")
        if "parts" not in merged:
            self._build_direct_index(merged)
            store = merged.get("training_store")
            if store is not None:
                path = Path(str(store["path"]))
                if not path.is_absolute():
                    path = self.cache_root / path
                shape = tuple(int(value) for value in store["shape"])
                if shape != (len(self.locations), 197, 768):
                    raise ValueError("Block-8 training store shape mismatch")
                if path.stat().st_size != int(store["bytes"]):
                    raise ValueError("Block-8 training store byte size mismatch")
                self._training_store_path = path
                self._training_store_shape = shape
            return
        for part_entry in merged["parts"]:
            part_manifest_path = Path(part_entry["manifest_path"])
            if not part_manifest_path.is_absolute():
                part_manifest_path = self.cache_root / part_manifest_path
            part_manifest = json.loads(
                part_manifest_path.read_text(encoding="utf-8")
            )
            inventory = json.loads(
                (part_manifest_path.parent / "image_inventory.json").read_text(
                    encoding="utf-8"
                )
            )
            offset = 0
            for shard_entry in part_manifest["shards"]:
                count = int(shard_entry["images"])
                current = inventory[offset : offset + count]
                if len(current) != count:
                    raise ValueError("cache shard exceeds part inventory")
                path = Path(shard_entry["path"])
                if not path.is_absolute():
                    path = part_manifest_path.parent / path
                for local_index, item in enumerate(current):
                    dicom_id = str(item["dicom_id"])
                    if dicom_id in self.locations:
                        raise ValueError(f"duplicate cached DICOM: {dicom_id}")
                    self.locations[dicom_id] = (path, local_index)
                offset += count
            if offset != len(inventory):
                raise ValueError("cache part did not consume its inventory")
        if len(self.locations) != int(merged["cached_image_count"]):
            raise ValueError("merged cache count differs from indexed DICOMs")

    def _build_direct_index(self, manifest: dict[str, Any]) -> None:
        inventory_path = self.cache_root / manifest.get(
            "inventory_path", "image_inventory.json"
        )
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        offset = 0
        for shard_entry in manifest["shards"]:
            count = int(shard_entry["images"])
            current = inventory[offset : offset + count]
            if len(current) != count:
                raise ValueError("cache shard exceeds direct inventory")
            path = Path(shard_entry["path"])
            if not path.is_absolute():
                path = self.cache_root / path
            for local_index, item in enumerate(current):
                image_key = str(item["image_key"])
                if image_key in self.locations:
                    raise ValueError(f"duplicate cached image key: {image_key}")
                self.locations[image_key] = (path, local_index)
                self._global_locations[image_key] = offset + local_index
            offset += count
        if offset != len(inventory):
            raise ValueError("direct cache did not consume its inventory")
        if len(self.locations) != int(manifest["cached_image_count"]):
            raise ValueError("cache count differs from indexed image keys")

    def __len__(self) -> int:
        return len(self.locations)

    def _load_shard(self, path: Path) -> dict[str, Any]:
        if path in self._loaded:
            value = self._loaded.pop(path)
            self._loaded[path] = value
            return value
        value = torch.load(path, map_location="cpu", weights_only=True)
        if tuple(value["features"].shape[1:]) != (197, 768):
            raise ValueError(f"unexpected Block-8 shard shape: {path}")
        self._loaded[path] = value
        while len(self._loaded) > self.maximum_loaded_shards:
            self._loaded.popitem(last=False)
        return value

    def get_many(self, image_keys: Iterable[str]) -> torch.Tensor:
        ids = [str(value) for value in image_keys]
        missing = [value for value in ids if value not in self.locations]
        if missing:
            raise KeyError(f"{len(missing)} image keys are absent; first={missing[0]}")
        if self._training_store_path is not None:
            if self._training_store is None:
                self._training_store = np.memmap(
                    self._training_store_path,
                    mode="r",
                    dtype=np.float16,
                    shape=self._training_store_shape,
                )
            indices = [self._global_locations[value] for value in ids]
            return torch.from_numpy(np.array(self._training_store[indices], copy=True))
        grouped: dict[Path, list[tuple[int, int]]] = defaultdict(list)
        for output_index, dicom_id in enumerate(ids):
            path, local_index = self.locations[dicom_id]
            grouped[path].append((output_index, local_index))
        output: list[torch.Tensor | None] = [None] * len(ids)
        for path, requests in grouped.items():
            shard = self._load_shard(path)
            features = shard["features"]
            for output_index, local_index in requests:
                output[output_index] = features[local_index]
        if any(value is None for value in output):
            raise RuntimeError("cache retrieval left an unfilled output")
        return torch.stack([value for value in output if value is not None])
