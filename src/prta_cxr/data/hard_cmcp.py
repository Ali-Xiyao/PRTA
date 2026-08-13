from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F

from prta_cxr.contracts import ContractError


def read_matched_hard_prior_map(path: Path) -> dict[str, str]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema") != "prta-cxr.matched-hard-prior-map.v1":
        raise ContractError("unsupported matched-hard prior map schema")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise ContractError("matched-hard prior map entries are missing")
    result: dict[str, str] = {}
    for raw in entries:
        if not isinstance(raw, dict):
            raise ContractError("matched-hard prior entry must be an object")
        target = str(raw.get("target_sample_id", ""))
        candidate = str(raw.get("counterfactual_sample_id", ""))
        if not target or not candidate:
            raise ContractError("matched-hard prior entry identifiers are missing")
        if target in result:
            raise ContractError(f"duplicate matched-hard target: {target}")
        result[target] = candidate
    return result


def build_matched_hard_prior_entries(
    rows: Sequence[Mapping[str, Any]],
    current_embeddings: Mapping[str, torch.Tensor],
    *,
    label_key: str = "progression_label",
    chunk_size: int = 512,
    device: torch.device | str = "cpu",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Match every Train/Dev row to the hardest valid prior candidate.

    Matching is exact within each split/finding group. Different-patient and
    different-label constraints are mandatory. Same-source and same-view
    candidates are preferred lexicographically before cosine hardness.
    """
    if chunk_size <= 0:
        raise ValueError("chunk size must be positive")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        split = str(row.get("split", ""))
        if split not in {"train", "dev"}:
            continue
        required = {
            "sample_id",
            "patient_id_hash",
            "source",
            "finding",
            "prior_image_path",
            "current_image_path",
            label_key,
        }
        missing = required - set(row)
        if missing:
            raise ContractError(
                f"hard-CMCP row fields missing: {sorted(missing)}"
            )
        groups[(split, str(row["finding"]))].append(row)

    selected_device = torch.device(device)
    entries: list[dict[str, Any]] = []
    group_audit: dict[str, Any] = {}
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda row: str(row["sample_id"]))
        missing_embeddings = [
            str(row["sample_id"])
            for row in group
            if str(row["sample_id"]) not in current_embeddings
        ]
        if missing_embeddings:
            raise ContractError(
                "current embeddings missing for hard-CMCP rows: "
                f"{missing_embeddings[:3]}"
            )
        matrix = F.normalize(
            torch.stack(
                [
                    torch.as_tensor(
                        current_embeddings[str(row["sample_id"])],
                        dtype=torch.float32,
                    )
                    for row in group
                ]
            ).to(selected_device),
            dim=-1,
        )
        patients = [str(row["patient_id_hash"]) for row in group]
        labels = [str(row[label_key]) for row in group]
        sources = [str(row["source"]) for row in group]
        views = [str(row.get("current_view", "unknown")) for row in group]

        def codes(values: list[str]) -> torch.Tensor:
            vocabulary = {
                value: index
                for index, value in enumerate(sorted(set(values)))
            }
            return torch.tensor(
                [vocabulary[value] for value in values],
                dtype=torch.long,
                device=selected_device,
            )

        patient_codes = codes(patients)
        label_codes = codes(labels)
        source_codes = codes(sources)
        view_codes = codes(views)
        matched = 0
        for start in range(0, len(group), chunk_size):
            end = min(start + chunk_size, len(group))
            similarities = matrix[start:end] @ matrix.transpose(0, 1)
            query_patients = patient_codes[start:end].unsqueeze(1)
            query_labels = label_codes[start:end].unsqueeze(1)
            valid = (query_patients != patient_codes.unsqueeze(0)) & (
                query_labels != label_codes.unsqueeze(0)
            )
            valid_rows = valid.any(dim=1)
            if not bool(valid_rows.all()):
                failed = int((~valid_rows).nonzero()[0].item()) + start
                raise ContractError(
                    "no different-patient/different-label hard-CMCP candidate "
                    f"for {group[failed]['sample_id']}"
                )
            same_source = (
                source_codes[start:end].unsqueeze(1)
                == source_codes.unsqueeze(0)
            )
            same_view = view_codes[start:end].unsqueeze(1) == view_codes.unsqueeze(0)
            # A tier gap greater than the full cosine range makes the metadata
            # preference lexicographic; cosine selects the hard example only
            # within the best available tier.
            tier = same_source.to(torch.float32) * 3.0
            tier = tier + (same_source & same_view).to(torch.float32) * 3.0
            scores = (similarities + tier).masked_fill(~valid, float("-inf"))
            candidate_indices = scores.argmax(dim=1)
            cosine_values = similarities.gather(
                1, candidate_indices.unsqueeze(1)
            ).squeeze(1)
            for offset, target in enumerate(group[start:end]):
                target_index = start + offset
                candidate_index = int(candidate_indices[offset].item())
                candidate = group[candidate_index]
                entries.append(
                    {
                        "target_sample_id": str(target["sample_id"]),
                        "counterfactual_sample_id": str(candidate["sample_id"]),
                        "split": key[0],
                        "finding": key[1],
                        "target_label": labels[target_index],
                        "counterfactual_label": labels[candidate_index],
                        "same_source": sources[candidate_index]
                        == sources[target_index],
                        "same_current_view": views[candidate_index]
                        == views[target_index],
                        "current_cosine_similarity": float(
                            cosine_values[offset].item()
                        ),
                    }
                )
                matched += 1
        group_audit["|".join(key)] = {"rows": len(group), "matched": matched}
    entries.sort(key=lambda row: str(row["target_sample_id"]))
    return entries, {
        "eligible_rows": sum(len(group) for group in groups.values()),
        "matched_rows": len(entries),
        "coverage": 1.0 if entries else 0.0,
        "groups": group_audit,
    }
