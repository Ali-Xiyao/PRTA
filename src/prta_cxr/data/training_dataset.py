from __future__ import annotations

import hashlib
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
        prior_intervention: str = "true",
        wrong_finding_query: bool = False,
        label_key: str = "progression_label",
    ) -> None:
        self.rows = [dict(row) for row in rows if row.get("split") == split]
        if not self.rows:
            raise ContractError(f"split contains no rows: {split}")
        self.cache = cache
        if prior_intervention not in {
            "true",
            "current_only",
            "null",
            "random",
            "matched_wrong",
            "reversed",
        }:
            raise ContractError("unsupported dataset prior intervention")
        self.prior_intervention = prior_intervention
        self.wrong_finding_query = bool(wrong_finding_query)
        self.label_key = str(label_key)
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
                "patient_id_hash",
            }
            required.add(self.label_key)
            missing = required - set(row)
            if missing:
                raise ContractError(f"training row fields missing: {sorted(missing)}")
            if row["finding"] not in self.finding_embeddings:
                raise ContractError(f"missing finding text embedding: {row['finding']}")
            transition_key = f"{row['finding']}|{row[self.label_key]}"
            if (
                row["sample_id"] not in self.transition_embeddings
                and transition_key not in self.transition_prototypes
            ):
                raise ContractError(
                    f"missing transition text embedding: {row['sample_id']}"
                )
            if row[self.label_key] not in self.label_index:
                raise ContractError("training row has an unknown progression label")
        self.wrong_prior_indices = (
            self._wrong_prior_indices(
                matched=self.prior_intervention == "matched_wrong"
            )
            if self.prior_intervention in {"matched_wrong", "random"}
            else list(range(len(self.rows)))
        )
        self.finding_derangement = {
            finding: sorted(self.finding_embeddings)[
                (index + 1) % len(self.finding_embeddings)
            ]
            for index, finding in enumerate(sorted(self.finding_embeddings))
        }

    @staticmethod
    def _interval_bin(row: dict[str, Any]) -> str:
        if not bool(row.get("calendar_interval_available", False)):
            return "ordinal"
        value = float(row.get("interval_days", 0.0))
        for bound in (7, 30, 90, 365):
            if value <= bound:
                return f"le_{bound}"
        return "gt_365"

    def _wrong_prior_indices(self, *, matched: bool) -> list[int]:
        groups: dict[tuple[str, ...], list[int]] = {}
        for index, row in enumerate(self.rows):
            matched_keys = (
                (
                    str(row["source"]),
                    str(row["finding"]),
                    str(row.get("current_view", "unknown")),
                    self._interval_bin(row),
                ),
                (str(row["source"]), str(row["finding"])),
                (str(row["finding"]),),
                ("all",),
            )
            keys = matched_keys if matched else (("all",),)
            for key in keys:
                groups.setdefault(key, []).append(index)
        result = []
        for row in self.rows:
            matched_keys = (
                (
                    str(row["source"]),
                    str(row["finding"]),
                    str(row.get("current_view", "unknown")),
                    self._interval_bin(row),
                ),
                (str(row["source"]), str(row["finding"])),
                (str(row["finding"]),),
                ("all",),
            )
            keys = matched_keys if matched else (("all",),)
            candidates = []
            for key in keys:
                candidates = [
                    candidate
                    for candidate in groups[key]
                    if str(self.rows[candidate]["patient_id_hash"])
                    != str(row["patient_id_hash"])
                ]
                if candidates:
                    break
            if not candidates:
                raise ContractError("cannot construct a different-patient wrong prior")
            candidates.sort(key=lambda value: str(self.rows[value]["sample_id"]))
            digest = hashlib.sha256(str(row["sample_id"]).encode()).digest()
            selected = int.from_bytes(digest[:8], "big") % len(candidates)
            result.append(candidates[selected])
        return result

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        prior_source = str(row["source"])
        prior_path = str(row["prior_image_path"])
        current_source = str(row["source"])
        current_path = str(row["current_image_path"])
        if self.prior_intervention in {"matched_wrong", "random"}:
            prior_row = self.rows[self.wrong_prior_indices[index]]
            prior_source = str(prior_row["source"])
            prior_path = str(prior_row["prior_image_path"])
        elif self.prior_intervention == "reversed":
            prior_path, current_path = current_path, prior_path
        elif self.prior_intervention in {"current_only", "null"}:
            prior_path = current_path
        keys = [
            image_cache_key(prior_source, prior_path),
            image_cache_key(current_source, current_path),
        ]
        features = self.cache.get_many(keys).float()
        if self.prior_intervention == "null":
            features[0].zero_()
        query_finding = (
            self.finding_derangement[str(row["finding"])]
            if self.wrong_finding_query
            else str(row["finding"])
        )
        finding = torch.as_tensor(
            self.finding_embeddings[query_finding], dtype=torch.float32
        )
        transition_value = self.transition_embeddings.get(row["sample_id"])
        if transition_value is None:
            transition_value = self.transition_prototypes[
                f"{row['finding']}|{row[self.label_key]}"
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
            "target": self.label_index[str(row[self.label_key])],
            "source": str(row["source"]),
            "finding": str(row["finding"]),
            "prior_view": str(row.get("prior_view", "unknown")),
            "current_view": str(row.get("current_view", "unknown")),
            "interval_days": float(row.get("interval_days", -1.0)),
            "interval_basis": str(row.get("interval_basis", "unknown")),
            "calendar_interval_available": bool(
                row.get("calendar_interval_available", False)
            ),
            "prior_intervention": self.prior_intervention,
            "query_finding": query_finding,
            "matched_wrong_sample_id": str(
                self.rows[self.wrong_prior_indices[index]]["sample_id"]
            ),
        }
