from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from prta_cxr.contracts import ContractError, canonical_sha256
from prta_cxr.data.catalog import SourceSpec
from prta_cxr.data.pairing import build_adjacent_pairs

REQUIRED_SOURCE_STUDY_FIELDS = frozenset(
    {
        "patient_id",
        "study_id",
        "image_id",
        "image_path",
        "report",
        "study_datetime",
        "view",
        "official_split",
    }
)


def hashed_patient_id(namespace: str, patient_id: object) -> str:
    raw = str(patient_id).strip()
    if not raw:
        raise ContractError("patient_id must be non-empty")
    return hashlib.sha256(f"{namespace}|{raw}".encode()).hexdigest()


def normalize_studies(
    source: SourceSpec,
    rows: Sequence[Mapping[str, Any]],
    *,
    excluded_patient_hashes: frozenset[str] = frozenset(),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not source.eligible_for_repartition:
        raise ContractError(
            f"source {source.source_id} is not eligible: "
            f"{source.activation_reasons()}"
        )
    candidates = []
    diagnostics = Counter()
    seen_image_lineage: set[str] = set()
    for row in rows:
        missing = REQUIRED_SOURCE_STUDY_FIELDS - set(row)
        if missing:
            raise ContractError(f"source study fields missing: {sorted(missing)}")
        if str(row["official_split"]) not in source.allowed_official_splits:
            diagnostics["blocked_official_split"] += 1
            continue
        patient_hash = hashed_patient_id(
            source.patient_namespace, row["patient_id"]
        )
        if patient_hash in excluded_patient_hashes:
            diagnostics["protected_patient"] += 1
            continue
        view = str(row["view"]).upper().strip()
        if view not in {"PA", "AP"}:
            diagnostics["non_frontal"] += 1
            continue
        image_lineage = str(
            row.get("image_lineage_id")
            or f"{source.patient_namespace}|{row['image_id']}"
        )
        if image_lineage in seen_image_lineage:
            diagnostics["duplicate_image_lineage"] += 1
            continue
        seen_image_lineage.add(image_lineage)
        candidates.append(
            {
                "patient_id_hash": patient_hash,
                "source": source.source_id,
                "study_id": str(row["study_id"]),
                "image_id": str(row["image_id"]),
                "image_lineage_id": image_lineage,
                "image_path": str(row["image_path"]),
                "report": str(row["report"]),
                "datetime": str(row["study_datetime"]),
                "time_basis": str(row.get("time_basis", "calendar")),
                "view": view,
            }
        )

    view_rank = {"PA": 0, "AP": 1}
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in sorted(
        candidates,
        key=lambda item: (
            item["source"],
            item["patient_id_hash"],
            item["study_id"],
            view_rank[item["view"]],
            item["image_id"],
        ),
    ):
        key = (row["source"], row["patient_id_hash"], row["study_id"])
        if key in selected:
            diagnostics["extra_frontal_in_study"] += 1
            continue
        selected[key] = row
    timeline_selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in sorted(
        selected.values(),
        key=lambda item: (
            item["source"],
            item["patient_id_hash"],
            item["datetime"],
            view_rank[item["view"]],
            item["study_id"],
            item["image_id"],
        ),
    ):
        key = (row["source"], row["patient_id_hash"], row["datetime"])
        if key in timeline_selected:
            diagnostics["duplicate_patient_time"] += 1
            continue
        timeline_selected[key] = row
    normalized = list(timeline_selected.values())
    audit = {
        "schema": "prta-cxr.source-normalization-audit.v1",
        "source_id": source.source_id,
        "input_rows": len(rows),
        "normalized_studies": len(normalized),
        "diagnostics": dict(sorted(diagnostics.items())),
        "normalized_sha256": canonical_sha256(normalized),
        "raw_patient_ids_persisted": False,
        "time_bases": dict(
            sorted(Counter(row["time_basis"] for row in normalized).items())
        ),
    }
    return normalized, audit


def build_full_candidate_pairs(
    normalized_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pairs = []
    source_counts = {}
    lineage_seen: set[tuple[str, str]] = set()
    for source_id in sorted(normalized_by_source):
        studies = [dict(row) for row in normalized_by_source[source_id]]
        for row in studies:
            if row["source"] != source_id:
                raise ContractError("normalized source_id mismatch")
            lineage_key = (row["patient_id_hash"], row["image_lineage_id"])
            if lineage_key in lineage_seen:
                raise ContractError("cross-source duplicate image lineage")
            lineage_seen.add(lineage_key)
        current = build_adjacent_pairs(studies)
        pairs.extend(current)
        source_counts[source_id] = {
            "studies": len(studies),
            "patients": len({row["patient_id_hash"] for row in studies}),
            "pairs": len(current),
        }
    pairs.sort(
        key=lambda row: (
            row["source"],
            row["patient_id_hash"],
            row["prior_datetime"],
        )
    )
    return pairs, {
        "schema": "prta-cxr.full-candidate-pair-audit.v1",
        "debug_only_isolation_inherited": False,
        "sources": source_counts,
        "studies": sum(item["studies"] for item in source_counts.values()),
        "patients": len({row["patient_id_hash"] for row in pairs}),
        "pairs": len(pairs),
        "interval_bases": dict(
            sorted(Counter(row["interval_basis"] for row in pairs).items())
        ),
        "calendar_interval_analysis_allowed": all(
            row["calendar_interval_available"] for row in pairs
        ),
        "pair_manifest_sha256": canonical_sha256(pairs),
    }
