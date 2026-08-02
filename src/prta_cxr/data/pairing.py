from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from prta_cxr.contracts import ContractError

REQUIRED_STUDY_FIELDS = frozenset(
    {
        "patient_id_hash",
        "source",
        "study_id",
        "image_path",
        "report",
        "datetime",
        "view",
    }
)


def _parse_datetime(value: object) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"invalid study datetime: {value!r}") from error


def build_adjacent_pairs(
    studies: Sequence[Mapping[str, Any]],
    *,
    allowed_views: frozenset[str] = frozenset({"AP", "PA"}),
) -> list[dict[str, Any]]:
    by_patient: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for study in studies:
        missing = REQUIRED_STUDY_FIELDS - set(study)
        if missing:
            raise ContractError(f"study fields missing: {sorted(missing)}")
        if str(study["view"]) not in allowed_views:
            continue
        patient = str(study["patient_id_hash"]).strip()
        if not patient:
            raise ContractError("patient_id_hash must be non-empty")
        source = str(study["source"]).strip()
        if not source:
            raise ContractError("source must be non-empty")
        time_basis = str(study.get("time_basis", "calendar")).strip()
        if time_basis not in {"calendar", "within_patient_ordinal"}:
            raise ContractError(f"unsupported time_basis: {time_basis!r}")
        by_patient[(source, patient)].append(study)

    pairs = []
    for source, patient in sorted(by_patient):
        ordered = sorted(
            by_patient[(source, patient)],
            key=lambda row: _parse_datetime(row["datetime"]),
        )
        for prior, current in zip(ordered, ordered[1:], strict=False):
            prior_time = _parse_datetime(prior["datetime"])
            current_time = _parse_datetime(current["datetime"])
            if current_time <= prior_time:
                raise ContractError("studies must have strictly increasing time")
            prior_basis = str(prior.get("time_basis", "calendar"))
            current_basis = str(current.get("time_basis", "calendar"))
            if prior_basis != current_basis:
                raise ContractError("paired studies must share one time_basis")
            interval_value = (current_time - prior_time).total_seconds() / 86400.0
            identity = "|".join(
                (
                    source,
                    patient,
                    str(prior["study_id"]),
                    str(current["study_id"]),
                )
            )
            pairs.append(
                {
                    "pair_id": hashlib.sha256(identity.encode()).hexdigest()[:24],
                    "patient_id_hash": patient,
                    "source": source,
                    "prior_image_id": str(prior.get("image_id", "")),
                    "current_image_id": str(current.get("image_id", "")),
                    "prior_study_id": str(prior["study_id"]),
                    "current_study_id": str(current["study_id"]),
                    "prior_image_path": str(prior["image_path"]),
                    "current_image_path": str(current["image_path"]),
                    "prior_report": str(prior["report"]),
                    "current_report": str(current["report"]),
                    "prior_datetime": str(prior["datetime"]),
                    "current_datetime": str(current["datetime"]),
                    "interval_days": interval_value,
                    "interval_basis": prior_basis,
                    "calendar_interval_available": prior_basis == "calendar",
                    "interval_semantics": (
                        "elapsed_calendar_days"
                        if prior_basis == "calendar"
                        else "within_patient_ordinal_steps_not_calendar_days"
                    ),
                    "prior_view": str(prior["view"]),
                    "current_view": str(current["view"]),
                }
            )
    return pairs
