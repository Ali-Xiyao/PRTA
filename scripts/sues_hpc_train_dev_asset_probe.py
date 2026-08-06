#!/usr/bin/env python
"""Fail-closed engineering probe for the frozen physician-cleaned Train/Dev assets.

This script never trains, never creates an experiment queue, and refuses paths
whose names indicate protected Internal-test or Gold cohorts. Its output is
aggregate-only and safe to retain with an engineering deployment receipt.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import torch

from prta_cxr.contracts import sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key

EXPECTED = {
    "split_manifest": (
        "45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89"
    ),
    "cleaned_split_freeze": (
        "aa761c13ae74f29f7c30bc0fecb23db20eab02d79a52778dbbeddec9563cd069"
    ),
    "cache_manifest": (
        "7bec0eb448206ad01c13248f69c611a49e8669ff69a7e7fed1adbf8aaa57d7d5"
    ),
    "text_cache": "1846e3d9d7c12cdb71b37d8e12023d376a5b5b70438cfdecc3f141595c81a3fd",
    "weights": "52cc993c5c5ff962bd0c60931874bc001e7e9b41666a385530f4a036294576be",
    "training_store": (
        "050a4837dbff14f39cab75e9438c3bf7b86776583a06d12b68b1308fca44e540"
    ),
}
EXPECTED_SPLITS = {"train": 80_402, "dev": 11_201}
PROTECTED_MARKERS = ("internal_test", "internal-test", "gold")


def _required_file(path: Path, role: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    lowered = str(resolved).lower()
    if any(marker in lowered for marker in PROTECTED_MARKERS):
        raise ValueError(f"protected path rejected for {role}: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"{role} is not a file: {resolved}")
    return resolved


def _required_dir(path: Path, role: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    lowered = str(resolved).lower()
    if any(marker in lowered for marker in PROTECTED_MARKERS):
        raise ValueError(f"protected path rejected for {role}: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"{role} is not a directory: {resolved}")
    return resolved


def _require_hash(path: Path, role: str) -> str:
    actual = sha256_file(path)
    if actual != EXPECTED[role]:
        raise ValueError(
            f"{role} SHA-256 mismatch: expected {EXPECTED[role]}, got {actual}"
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    args = parser.parse_args()

    split_manifest = _required_file(args.split_manifest, "split_manifest")
    cleaned_split_freeze = _required_file(
        args.cleaned_split_freeze, "cleaned_split_freeze"
    )
    cache_root = _required_dir(args.cache_root, "cache_root")
    text_cache_path = _required_file(args.text_cache, "text_cache")
    weights = _required_file(args.weights, "weights")
    cache_manifest_path = _required_file(
        cache_root / "cache_manifest.json", "cache_manifest"
    )
    training_store_path = _required_file(
        cache_root / "block8_features.f16.bin", "training_store"
    )

    hashes = {
        "split_manifest": _require_hash(split_manifest, "split_manifest"),
        "cleaned_split_freeze": _require_hash(
            cleaned_split_freeze, "cleaned_split_freeze"
        ),
        "cache_manifest": _require_hash(cache_manifest_path, "cache_manifest"),
        "text_cache": _require_hash(text_cache_path, "text_cache"),
        "weights": _require_hash(weights, "weights"),
        "training_store": _require_hash(training_store_path, "training_store"),
    }
    cache_manifest = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
    if cache_manifest.get("contains_labels") is not False:
        raise ValueError("cache manifest must declare contains_labels=false")
    if cache_manifest.get("contains_patient_identifiers") is not False:
        raise ValueError("cache manifest must exclude patient identifiers")
    if cache_manifest.get("contains_reports") is not False:
        raise ValueError("cache manifest must exclude reports")
    store_entry = cache_manifest.get("training_store", {})
    if store_entry.get("file_sha256") != hashes["training_store"]:
        raise ValueError("cache manifest training-store hash mismatch")
    if int(store_entry.get("bytes", -1)) != training_store_path.stat().st_size:
        raise ValueError("cache manifest training-store size mismatch")
    if cache_manifest.get("encoder", {}).get("weights_sha256") != hashes["weights"]:
        raise ValueError("cache encoder weight hash mismatch")

    text_cache = torch.load(text_cache_path, map_location="cpu", weights_only=True)
    if not isinstance(text_cache, dict):
        raise ValueError("text cache must be a dictionary")

    split_counts: Counter[str] = Counter()
    probe_keys: list[str] = []
    with split_manifest.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            split = str(row.get("split"))
            if split not in EXPECTED_SPLITS:
                raise ValueError(f"unexpected split in Train/Dev manifest: {split}")
            split_counts[split] += 1
            if len(probe_keys) < 8:
                source = row["source"]
                probe_keys.extend(
                    [
                        image_cache_key(source, row["prior_image_path"]),
                        image_cache_key(source, row["current_image_path"]),
                    ]
                )
    if dict(split_counts) != EXPECTED_SPLITS:
        raise ValueError(
            "Train/Dev counts mismatch: "
            f"expected {EXPECTED_SPLITS}, got {dict(split_counts)}"
        )

    cache = Block8CacheIndex(cache_root)
    features = cache.get_many(probe_keys[:8])
    if tuple(features.shape) != (8, 197, 768):
        raise ValueError(f"unexpected cache probe shape: {tuple(features.shape)}")

    print(
        json.dumps(
            {
                "schema": "prta-cxr.sues-train-dev-asset-probe.v1",
                "status": "PASS_SUES_TRAIN_DEV_ASSET_PROBE",
                "split_counts": dict(split_counts),
                "cache_rows": len(cache),
                "cache_probe_shape": list(features.shape),
                "text_cache_entries": len(text_cache),
                "hashes": hashes,
                "protected_paths_opened": 0,
                "formal_experiment_started": False,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
