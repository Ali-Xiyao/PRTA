from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path

import torch

from prta_cxr.data.hard_cmcp import build_matched_hard_prior_entries
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key
from prta_cxr.data.training_dataset import read_jsonl


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a Train/Dev-only matched-hard CMCP prior map"
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--feature-batch-size", type=int, default=128)
    parser.add_argument("--match-chunk-size", type=int, default=512)
    args = parser.parse_args(argv)
    if args.feature_batch_size <= 0:
        parser.error("--feature-batch-size must be positive")

    rows = [
        row
        for row in read_jsonl(args.split_manifest)
        if str(row.get("split")) in {"train", "dev"}
    ]
    cache = Block8CacheIndex(args.cache_root)
    embeddings: dict[str, torch.Tensor] = {}
    for start in range(0, len(rows), args.feature_batch_size):
        batch = rows[start : start + args.feature_batch_size]
        keys = [
            image_cache_key(row["source"], row["current_image_path"])
            for row in batch
        ]
        pooled = cache.get_many(keys).float().mean(dim=1)
        for row, embedding in zip(batch, pooled, strict=True):
            embeddings[str(row["sample_id"])] = embedding

    entries, audit = build_matched_hard_prior_entries(
        rows,
        embeddings,
        chunk_size=args.match_chunk_size,
        device=args.device,
    )
    _write_new_json(
        args.output,
        {
            "schema": "prta-cxr.matched-hard-prior-map.v1",
            "status": "PASS_TRAIN_DEV_MATCHED_HARD_PRIOR_MAP",
            "split_manifest_sha256": _sha256(args.split_manifest),
            "cache_manifest_sha256": _sha256(
                args.cache_root / "cache_manifest.json"
            ),
            "cache_entry_block": cache.cache_entry_block,
            "matching": {
                "required_different_patient": True,
                "required_different_label": True,
                "required_same_finding": True,
                "preferred_same_source": True,
                "preferred_same_current_view": True,
                "hardness": "maximum current-token mean cosine within best tier",
            },
            "audit": audit,
            "entries": entries,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
    )
    print(json.dumps({"output": str(args.output), "audit": audit}, indent=2))
    return 0
