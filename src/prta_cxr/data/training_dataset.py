from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset

from prta_cxr.contracts import PROGRESSION_LABELS, ContractError
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class PRTAFeatureDataset(Dataset[dict[str, Any]]):
    def __init__(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        cache: Block8CacheIndex,
        text_cache_path: Path,
        split: str,
    ) -> None:
        self.rows = [dict(row) for row in rows if row.get("split") == split]
        if not self.rows:
            raise ContractError(f"split contains no rows: {split}")
        self.cache = cache
        value = torch.load(text_cache_path, map_location="cpu", weights_only=True)
        if not isinstance(value, dict):
            raise ContractError("text cache must be a dictionary")
        self.finding_embeddings = value.get("finding_embeddings", {})
        self.transition_embeddings = value.get("transition_embeddings", {})
        self.transition_prototypes = value.get("transition_prototypes", {})
        if not isinstance(self.finding_embeddings, dict) or not isinstance(
            self.transition_embeddings, dict
        ) or not isinstance(self.transition_prototypes, dict):
            raise ContractError("text cache dictionaries are missing")
        self.label_index = {
            label: index for index, label in enumerate(PROGRESSION_LABELS)
        }
        for row in self.rows:
            required = {
                "sample_id",
                "source",
                "prior_image_path",
                "current_image_path",
                "finding",
                "progression_label",
                "patient_id_hash",
            }
            missing = required - set(row)
            if missing:
                raise ContractError(f"training row fields missing: {sorted(missing)}")
            if row["finding"] not in self.finding_embeddings:
                raise ContractError(f"missing finding text embedding: {row['finding']}")
            transition_key = f"{row['finding']}|{row['progression_label']}"
            if (
                row["sample_id"] not in self.transition_embeddings
                and transition_key not in self.transition_prototypes
            ):
                raise ContractError(
                    f"missing transition text embedding: {row['sample_id']}"
                )
            if row["progression_label"] not in self.label_index:
                raise ContractError("training row has an unknown progression label")

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        keys = [
            image_cache_key(row["source"], row["prior_image_path"]),
            image_cache_key(row["source"], row["current_image_path"]),
        ]
        features = self.cache.get_many(keys).float()
        finding = torch.as_tensor(
            self.finding_embeddings[row["finding"]], dtype=torch.float32
        )
        transition_value = self.transition_embeddings.get(row["sample_id"])
        if transition_value is None:
            transition_value = self.transition_prototypes[
                f"{row['finding']}|{row['progression_label']}"
            ]
        transition = torch.as_tensor(transition_value, dtype=torch.float32)
        if finding.shape != (512,) or transition.shape != (512,):
            raise ContractError("text embeddings must be 512-dimensional")
        return {
            "sample_id": str(row["sample_id"]),
            "patient_id_hash": str(row["patient_id_hash"]),
            "prior": features[0],
            "current": features[1],
            "finding_text": finding,
            "transition_text": transition,
            "target": self.label_index[str(row["progression_label"])],
        }
