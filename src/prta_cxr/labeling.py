from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import ContractError, validate_luna_batch, validate_sample


def merge_luna_labels(
    samples: Sequence[Mapping[str, Any]],
    luna_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    validated_samples = [validate_sample(row) for row in samples]
    validated_luna = validate_luna_batch(luna_rows)
    sample_by_id = {row["sample_id"]: row for row in validated_samples}
    if len(sample_by_id) != len(validated_samples):
        raise ContractError("duplicate sample_id in candidate samples")
    luna_by_id = {row["sample_id"]: row for row in validated_luna}
    if set(luna_by_id) != set(sample_by_id):
        raise ContractError("Luna IDs must match candidate sample IDs exactly")

    merged = []
    counts = {"Tier-A": 0, "Tier-B": 0, "Reject": 0}
    for sample_id in sorted(sample_by_id):
        sample = sample_by_id[sample_id]
        luna = luna_by_id[sample_id]
        if sample["finding"] != luna["finding"]:
            raise ContractError(f"finding mismatch for {sample_id}")
        conflicts = any(
            luna[key]
            for key in (
                "negation_conflict",
                "uncertainty_conflict",
                "temporal_conflict",
            )
        )
        if luna["decision"] == "accept" and not conflicts:
            tier = "Tier-A"
        elif luna["decision"] == "tier_b" and not conflicts:
            tier = "Tier-B"
        else:
            tier = "Reject"
        output = dict(sample)
        output.update(
            {
                "progression_label": luna["verified_label"],
                "label_source": "luna_verified",
                "label_tier": tier,
                "luna": luna,
            }
        )
        counts[tier] += 1
        merged.append(output)
    return merged, counts
