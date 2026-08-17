from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.hard_cmcp import build_matched_hard_prior_entries
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key
from prta_cxr.data.training_dataset import read_jsonl
from prta_cxr.experiments import (
    filter_train_dev_sources,
    inject_train_label_noise,
    nested_train_fraction,
)


def transform_rows_for_config(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = dict(config.get("data", {}))
    selected, source_audit = filter_train_dev_sources(
        rows,
        train_sources=data.get("train_sources"),
        dev_sources=data.get("dev_sources"),
    )
    selected, fraction_audit = nested_train_fraction(
        selected,
        fraction=float(data.get("train_fraction", 1.0)),
        salt=str(data.get("fraction_salt", "prta-cxr-luna-primary-scaling-v1")),
    )
    noise = dict(data.get("label_noise", {}))
    noise_audit = None
    if float(noise.get("rate", 0.0)):
        selected, noise_audit = inject_train_label_noise(
            selected,
            rate=float(noise["rate"]),
            family=str(noise.get("family", "symmetric")),
            salt=str(noise.get("salt", "prta-cxr-label-noise-v1")),
        )
    audit = {
        "schema": "prta-cxr.phase16-map-transform-audit.v1",
        "source_filter": source_audit,
        "fraction": fraction_audit,
        "label_noise": noise_audit,
    }
    return selected, audit


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable map: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def build_phase16_map_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a transformed Phase16 hard-CMCP map"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--feature-batch-size", type=int, default=128)
    parser.add_argument("--match-chunk-size", type=int, default=512)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    rows, transform_audit = transform_rows_for_config(
        read_jsonl(args.split_manifest), config
    )
    cache = Block8CacheIndex(args.cache_root)
    embeddings: dict[str, torch.Tensor] = {}
    for start in range(0, len(rows), args.feature_batch_size):
        batch = rows[start : start + args.feature_batch_size]
        keys = [
            image_cache_key(row["source"], row["current_image_path"]) for row in batch
        ]
        pooled = cache.get_many(keys).float().mean(dim=1)
        for row, embedding in zip(batch, pooled, strict=True):
            embeddings[str(row["sample_id"])] = embedding
    entries, matching_audit = build_matched_hard_prior_entries(
        rows,
        embeddings,
        chunk_size=args.match_chunk_size,
        device=args.device,
    )
    transformed_roster = sorted(str(row["sample_id"]) for row in rows)
    transformed_ids = set(transformed_roster)
    target_ids = [str(entry["target_sample_id"]) for entry in entries]
    candidate_ids = [str(entry["counterfactual_sample_id"]) for entry in entries]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("Phase16 map contains duplicate targets")
    if set(target_ids) != transformed_ids:
        raise ValueError("Phase16 map target roster is incomplete")
    if not set(candidate_ids).issubset(transformed_ids):
        raise ValueError("Phase16 map candidate is outside transformed roster")
    payload = {
        "schema": "prta-cxr.matched-hard-prior-map.v1",
        "status": "PASS_PHASE16_TRANSFORMED_MATCHED_HARD_MAP",
        "split_manifest_sha256": sha256_file(args.split_manifest),
        "cache_manifest_sha256": sha256_file(args.cache_root / "cache_manifest.json"),
        "cache_entry_block": cache.cache_entry_block,
        "config_sha256": sha256_file(args.config),
        "transform_audit": transform_audit,
        "transform_audit_sha256": canonical_sha256(transform_audit),
        "transformed_roster_sha256": canonical_sha256(transformed_roster),
        "target_roster_sha256": canonical_sha256(sorted(target_ids)),
        "candidate_roster_sha256": canonical_sha256(sorted(candidate_ids)),
        "target_roster_complete": True,
        "candidate_roster_subset": True,
        "matching": {
            "required_different_patient": True,
            "required_different_label": True,
            "required_same_finding": True,
            "preferred_same_source": True,
            "preferred_same_current_view": True,
            "hardness": "maximum current-token mean cosine within best tier",
        },
        "audit": matching_audit,
        "entries": entries,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(args.output, payload)
    print(json.dumps({"output": str(args.output), "audit": matching_audit}, indent=2))
    return 0
