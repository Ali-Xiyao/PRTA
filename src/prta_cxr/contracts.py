from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROGRESSION_LABELS = ("Stable", "Improved", "Worse", "New", "Resolved")
INVERSION = {
    "Stable": "Stable",
    "Improved": "Worse",
    "Worse": "Improved",
    "New": "Resolved",
    "Resolved": "New",
}

SAMPLE_FIELDS = frozenset(
    {
        "sample_id",
        "patient_id_hash",
        "source",
        "prior_study_id",
        "current_study_id",
        "prior_image_path",
        "current_image_path",
        "prior_report",
        "current_report",
        "prior_datetime",
        "current_datetime",
        "interval_days",
        "interval_basis",
        "calendar_interval_available",
        "interval_semantics",
        "prior_view",
        "current_view",
        "finding",
        "progression_label",
        "label_source",
        "label_tier",
    }
)

LUNA_FIELDS = frozenset(
    {
        "sample_id",
        "finding",
        "verified_label",
        "decision",
        "prior_evidence",
        "current_evidence",
        "comparison_evidence",
        "comparison_matches_selected_prior",
        "finding_match",
        "negation_conflict",
        "uncertainty_conflict",
        "temporal_conflict",
        "reason_code",
    }
)


class ContractError(ValueError):
    """Raised when an artifact violates a fail-closed repository contract."""


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_exact_fields(row: Mapping[str, Any], expected: frozenset[str]) -> None:
    actual = set(row)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ContractError(f"field mismatch; missing={missing}, extra={extra}")


def _nonempty_string(row: Mapping[str, Any], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} must be a non-empty string")
    return value.strip()


def validate_sample(row: Mapping[str, Any]) -> dict[str, Any]:
    _require_exact_fields(row, SAMPLE_FIELDS)
    result = dict(row)
    for key in SAMPLE_FIELDS - {"interval_days", "calendar_interval_available"}:
        _nonempty_string(result, key)
    if result["progression_label"] not in PROGRESSION_LABELS:
        raise ContractError("unknown progression_label")
    if result["label_tier"] not in {"Tier-A", "Tier-B", "Reject", "Silver"}:
        raise ContractError(
            "label_tier must be Tier-A, Tier-B, Reject, or Silver"
        )
    interval = result["interval_days"]
    if not isinstance(interval, (int, float)) or interval < 0:
        raise ContractError("interval_days must be non-negative")
    if result["interval_basis"] not in {"calendar", "within_patient_ordinal"}:
        raise ContractError("unsupported interval_basis")
    calendar_available = result["calendar_interval_available"]
    if type(calendar_available) is not bool:
        raise ContractError("calendar_interval_available must be boolean")
    if calendar_available != (result["interval_basis"] == "calendar"):
        raise ContractError("calendar interval flag contradicts interval_basis")
    if result["prior_datetime"] >= result["current_datetime"]:
        raise ContractError("prior_datetime must precede current_datetime")
    return result


def validate_luna_record(row: Mapping[str, Any]) -> dict[str, Any]:
    _require_exact_fields(row, LUNA_FIELDS)
    result = dict(row)
    for key in (
        "sample_id",
        "finding",
        "verified_label",
        "decision",
        "reason_code",
    ):
        _nonempty_string(result, key)
    if result["verified_label"] not in PROGRESSION_LABELS:
        raise ContractError("unknown verified_label")
    if result["decision"] not in {"accept", "tier_b", "reject"}:
        raise ContractError("unknown Luna decision")
    boolean_fields = LUNA_FIELDS - {
        "sample_id",
        "finding",
        "verified_label",
        "decision",
        "prior_evidence",
        "current_evidence",
        "comparison_evidence",
        "reason_code",
    }
    for key in boolean_fields:
        if type(result[key]) is not bool:
            raise ContractError(f"{key} must be boolean")
    return result


def validate_luna_batch(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated = [validate_luna_record(row) for row in rows]
    identifiers = [row["sample_id"] for row in validated]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("duplicate sample_id in Luna batch")
    return validated
