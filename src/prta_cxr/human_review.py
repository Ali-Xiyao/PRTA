from __future__ import annotations

import posixpath
import re
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from prta_cxr.contracts import (
    PROGRESSION_LABELS,
    ContractError,
    canonical_sha256,
    validate_sample,
)

HUMAN_REVIEW_LABELS = (*PROGRESSION_LABELS, "Unclear", "Unusable")
HUMAN_REVIEW_HEADERS = (
    "case_no",
    "review_id",
    "source",
    "finding",
    "PRIOR_REPORT",
    "CURRENT_REPORT",
    "human_label",
    "unusable_reason",
    "reviewer_id",
    "review_date",
    "notes_optional",
    "row_status",
)
SENIOR_LUNA_REVIEW_HEADERS = (
    "序号",
    "review_id",
    "数据源",
    "目标病灶",
    "PRIOR_REPORT",
    "CURRENT_REPORT",
    "Luna标签",
    "资深医生标签",
    "不可用原因",
    "审核人",
    "审核日期",
    "备注（可选）",
    "填写状态",
)
SENIOR_LUNA_COMPACT_HEADERS = SENIOR_LUNA_REVIEW_HEADERS[:8]
SENIOR_COMPACT_REVIEW_MODE = "luna_assisted_senior_panel_compact_v2"

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
_CELL_REFERENCE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")


def _column_index(reference: str) -> int:
    match = _CELL_REFERENCE.match(reference)
    if not match:
        raise ContractError(f"invalid XLSX cell reference: {reference}")
    value = 0
    for character in match.group(1):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read(path))
    return [
        "".join(node.text or "" for node in item.findall(f".//{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    ]


def _worksheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = None
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        if sheet.attrib.get("name") == sheet_name:
            relationship_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
            break
    if not relationship_id:
        raise ContractError(f"XLSX sheet not found: {sheet_name}")
    relationships = ElementTree.fromstring(
        archive.read("xl/_rels/workbook.xml.rels")
    )
    target = None
    for relation in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        if relation.attrib.get("Id") == relationship_id:
            target = relation.attrib.get("Target")
            break
    if not target:
        raise ContractError(f"XLSX relationship missing: {relationship_id}")
    if target.startswith("/"):
        resolved = target.lstrip("/")
    else:
        resolved = posixpath.normpath(posixpath.join("xl", target))
    if resolved not in archive.namelist():
        raise ContractError(f"XLSX worksheet payload missing: {resolved}")
    return resolved


def _cell_value(cell: ElementTree.Element, shared: Sequence[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.findall(f".//{{{_MAIN_NS}}}t")
        )
    value_node = cell.find(f"{{{_MAIN_NS}}}v")
    if value_node is None or value_node.text is None:
        return None
    raw = value_node.text
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (IndexError, ValueError) as error:
            raise ContractError("invalid XLSX shared string index") from error
    if cell_type in {"str", "e"}:
        return raw
    if cell_type == "b":
        return raw == "1"
    try:
        number = float(raw)
    except ValueError:
        return raw
    return int(number) if number.is_integer() else number


def _normalize_text(value: Any) -> str:
    return str(value if value is not None else "").replace("\r\n", "\n").replace(
        "\r", "\n"
    ).strip()


def _review_date(value: Any) -> str:
    if isinstance(value, (int, float)):
        parsed = datetime(1899, 12, 30) + timedelta(days=float(value))
        return parsed.date().isoformat()
    return _normalize_text(value)


def read_human_review_xlsx(
    path: Path,
    *,
    sheet_name: str | None = None,
) -> list[dict[str, Any]]:
    path = Path(path)
    try:
        archive_context = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ContractError(f"cannot open human review XLSX: {path}") from error
    with archive_context as archive:
        shared = _shared_strings(archive)
        if sheet_name is None:
            for candidate in ("资深医生复核", "人工复核"):
                try:
                    worksheet_path = _worksheet_path(archive, candidate)
                    sheet_name = candidate
                    break
                except ContractError:
                    continue
            else:
                raise ContractError(
                    "XLSX contains neither senior nor blind review sheet"
                )
        else:
            worksheet_path = _worksheet_path(archive, sheet_name)
        root = ElementTree.fromstring(
            archive.read(worksheet_path)
        )
        rows_by_number: dict[int, dict[int, Any]] = {}
        for row_node in root.findall(f".//{{{_MAIN_NS}}}row"):
            row_number = int(row_node.attrib["r"])
            values: dict[int, Any] = {}
            for cell in row_node.findall(f"{{{_MAIN_NS}}}c"):
                reference = cell.attrib.get("r", "")
                values[_column_index(reference)] = _cell_value(cell, shared)
            rows_by_number[row_number] = values

    full_header = tuple(
        _normalize_text(rows_by_number.get(1, {}).get(index))
        for index in range(len(SENIOR_LUNA_REVIEW_HEADERS))
    )
    if full_header == SENIOR_LUNA_REVIEW_HEADERS:
        review_schema = "senior_full"
    elif (
        full_header[: len(SENIOR_LUNA_COMPACT_HEADERS)]
        == SENIOR_LUNA_COMPACT_HEADERS
        and not any(full_header[len(SENIOR_LUNA_COMPACT_HEADERS) :])
    ):
        review_schema = "senior_compact"
    elif full_header[: len(HUMAN_REVIEW_HEADERS)] == HUMAN_REVIEW_HEADERS:
        review_schema = "blind"
    else:
        raise ContractError("human review XLSX headers do not match the frozen schema")
    if set(rows_by_number) - set(range(1, 252)):
        raise ContractError("human review XLSX contains rows outside 1..251")

    responses = []
    for index in range(2, 252):
        row = rows_by_number.get(index, {})
        if review_schema == "senior_full":
            responses.append(
                {
                    "case_no": row.get(0),
                    "review_id": _normalize_text(row.get(1)),
                    "source": _normalize_text(row.get(2)),
                    "finding": _normalize_text(row.get(3)),
                    "prior_report": _normalize_text(row.get(4)),
                    "current_report": _normalize_text(row.get(5)),
                    "displayed_luna_label": _normalize_text(row.get(6)),
                    "human_label": _normalize_text(row.get(7)),
                    "unusable_reason": _normalize_text(row.get(8)),
                    "reviewer_id": _normalize_text(row.get(9)),
                    "review_date": _review_date(row.get(10)),
                    "notes_optional": _normalize_text(row.get(11)),
                    "review_mode": "luna_assisted_senior_v2",
                }
            )
        elif review_schema == "senior_compact":
            responses.append(
                {
                    "case_no": row.get(0),
                    "review_id": _normalize_text(row.get(1)),
                    "source": _normalize_text(row.get(2)),
                    "finding": _normalize_text(row.get(3)),
                    "prior_report": _normalize_text(row.get(4)),
                    "current_report": _normalize_text(row.get(5)),
                    "displayed_luna_label": _normalize_text(row.get(6)),
                    "human_label": _normalize_text(row.get(7)),
                    "unusable_reason": "",
                    "reviewer_id": "",
                    "review_date": "",
                    "notes_optional": "",
                    "review_mode": SENIOR_COMPACT_REVIEW_MODE,
                }
            )
        else:
            responses.append(
                {
                    "case_no": row.get(0),
                    "review_id": _normalize_text(row.get(1)),
                    "source": _normalize_text(row.get(2)),
                    "finding": _normalize_text(row.get(3)),
                    "prior_report": _normalize_text(row.get(4)),
                    "current_report": _normalize_text(row.get(5)),
                    "human_label": _normalize_text(row.get(6)),
                    "unusable_reason": _normalize_text(row.get(7)),
                    "reviewer_id": _normalize_text(row.get(8)),
                    "review_date": _review_date(row.get(9)),
                    "notes_optional": _normalize_text(row.get(10)),
                    "review_mode": "blind_v1",
                }
            )
    return responses


def _require_string(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"human review {field} must be non-empty")
    return value.strip()


def _stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    decisive = [row for row in rows if row["human_decisive"]]
    exact = sum(bool(row["luna_human_exact"]) for row in rows)
    decisive_exact = sum(bool(row["luna_human_exact"]) for row in decisive)
    return {
        "rows": len(rows),
        "exact_rows": exact,
        "exact_rate_all_reviewed": exact / len(rows) if rows else 0.0,
        "human_decisive_rows": len(decisive),
        "decisive_exact_rows": decisive_exact,
        "exact_rate_human_decisive": (
            decisive_exact / len(decisive) if decisive else 0.0
        ),
        "human_label_counts": dict(
            sorted(Counter(str(row["human_label"]) for row in rows).items())
        ),
    }


def _validate_review_provenance(
    provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if provenance is None:
        raise ContractError("compact senior review requires provenance metadata")
    value = dict(provenance)
    expected = {
        "schema": "prta-cxr.senior-review-provenance.v1",
        "review_mode": "luna_assisted_senior_panel_consensus",
        "reviewer_count": 2,
        "clinical_experience_each": ">5 years",
        "annotation_structure": "single_consensus_column",
        "independent_annotations_available": False,
        "luna_label_visible_to_reviewers": True,
        "row_level_reviewer_ids_recorded": False,
        "row_level_review_dates_recorded": False,
        "attestation_source": "user",
        "formal_training_authorized": False,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise ContractError(
                f"senior review provenance mismatch for {field}"
            )
    _require_string(value, "reviewer_group_id")
    attestation_date = _require_string(value, "attestation_date")
    try:
        datetime.strptime(attestation_date, "%Y-%m-%d")
    except ValueError as error:
        raise ContractError(
            "provenance attestation_date must use YYYY-MM-DD"
        ) from error
    return value


def finalize_human_review(
    roster_rows: Sequence[Mapping[str, Any]],
    response_rows: Sequence[Mapping[str, Any]],
    silver_rows: Sequence[Mapping[str, Any]],
    quarantine_rows: Sequence[Mapping[str, Any]],
    training_eligible_rows: Sequence[Mapping[str, Any]],
    *,
    workbook_sha256: str,
    review_provenance: Mapping[str, Any] | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    if len(roster_rows) != 250 or len(response_rows) != 250:
        raise ContractError(
            "human review requires exactly 250 roster and response rows"
        )
    if not re.fullmatch(r"[0-9a-f]{64}", workbook_sha256):
        raise ContractError("workbook_sha256 must be lowercase SHA-256")

    roster_by_id: dict[str, dict[str, Any]] = {}
    for raw in roster_rows:
        row = dict(raw)
        review_id = _require_string(row, "review_id")
        for field in (
            "sample_id",
            "patient_id_hash",
            "source",
            "finding",
            "prior_report",
            "current_report",
            "luna_label",
            "review_status",
        ):
            _require_string(row, field)
        if row["luna_label"] not in PROGRESSION_LABELS:
            raise ContractError("roster contains unknown Luna label")
        if row["review_status"] != "PENDING_HUMAN_REVIEW":
            raise ContractError("roster review status is not pending")
        if row.get("clinician_label") is not None:
            raise ContractError("frozen roster unexpectedly contains clinician label")
        if review_id in roster_by_id:
            raise ContractError("duplicate review_id in roster")
        roster_by_id[review_id] = row

    response_by_id: dict[str, dict[str, Any]] = {}
    review_modes: set[str] = set()
    for raw in response_rows:
        row = dict(raw)
        review_id = _require_string(row, "review_id")
        label = _require_string(row, "human_label")
        review_mode = _normalize_text(row.get("review_mode")) or "blind_v1"
        allowed_modes = {
            "blind_v1",
            "luna_assisted_senior_v2",
            SENIOR_COMPACT_REVIEW_MODE,
        }
        if review_mode not in allowed_modes:
            raise ContractError(f"unknown human review mode: {review_mode}")
        if review_mode != SENIOR_COMPACT_REVIEW_MODE:
            _require_string(row, "reviewer_id")
            review_date = _require_string(row, "review_date")
            try:
                datetime.strptime(review_date, "%Y-%m-%d")
            except ValueError as error:
                raise ContractError("review_date must use YYYY-MM-DD") from error
        if label not in HUMAN_REVIEW_LABELS:
            raise ContractError(f"unknown human label: {label}")
        if label == "Unusable" and not _normalize_text(row.get("unusable_reason")):
            raise ContractError("Unusable response requires unusable_reason")
        review_modes.add(review_mode)
        if review_id in response_by_id:
            raise ContractError("duplicate review_id in human responses")
        response_by_id[review_id] = row
    if set(response_by_id) != set(roster_by_id):
        raise ContractError("human response review_id set does not match roster")
    if len(review_modes) != 1:
        raise ContractError("human responses mix incompatible review modes")
    review_mode = next(iter(review_modes))
    compact_review = review_mode == SENIOR_COMPACT_REVIEW_MODE
    provenance = (
        _validate_review_provenance(review_provenance)
        if compact_review
        else None
    )

    validated_silver = [validate_sample(row) for row in silver_rows]
    silver_by_id = {row["sample_id"]: row for row in validated_silver}
    if len(silver_by_id) != len(validated_silver):
        raise ContractError("duplicate sample_id in Silver manifest")
    training = [validate_sample(row) for row in training_eligible_rows]
    training_patients = {row["patient_id_hash"] for row in training}

    quarantine_patients = []
    for row in quarantine_rows:
        patient = _require_string(row, "patient_id_hash")
        quarantine_patients.append(patient)
    if len(quarantine_patients) != len(set(quarantine_patients)):
        raise ContractError("duplicate patient in human-review quarantine")
    roster_patients = {row["patient_id_hash"] for row in roster_by_id.values()}
    if set(quarantine_patients) != roster_patients:
        raise ContractError("quarantine patient set does not match human-review roster")
    if training_patients & roster_patients:
        raise ContractError("human-review patient leaks into training-eligible Silver")

    comparisons = []
    responses = []
    gold = []
    excluded = []
    seen_cases = set()
    for response in response_rows:
        review_id = response["review_id"].strip()
        roster = roster_by_id[review_id]
        if review_mode in {
            "luna_assisted_senior_v2",
            SENIOR_COMPACT_REVIEW_MODE,
        }:
            displayed_luna_label = _require_string(
                response, "displayed_luna_label"
            )
            if displayed_luna_label != roster["luna_label"]:
                raise ContractError(
                    f"displayed Luna label mismatch for {review_id}"
                )
        expected_case = int(response["case_no"])
        if expected_case < 1 or expected_case > 250 or expected_case in seen_cases:
            raise ContractError("invalid or duplicate case_no in human review")
        seen_cases.add(expected_case)
        for response_field, roster_field in (
            ("source", "source"),
            ("finding", "finding"),
            ("prior_report", "prior_report"),
            ("current_report", "current_report"),
        ):
            if _normalize_text(response[response_field]) != _normalize_text(
                roster[roster_field]
            ):
                raise ContractError(
                    f"blind workbook content mismatch for {review_id}: {response_field}"
                )
        sample = silver_by_id.get(roster["sample_id"])
        if sample is None:
            raise ContractError(f"review sample absent from Silver: {review_id}")
        for field in (
            "patient_id_hash",
            "source",
            "finding",
            "prior_report",
            "current_report",
        ):
            if _normalize_text(sample[field]) != _normalize_text(roster[field]):
                raise ContractError(f"roster-Silver mismatch for {review_id}: {field}")
        if sample["progression_label"] != roster["luna_label"]:
            raise ContractError(f"roster Luna label mismatch for {review_id}")

        human_label = response["human_label"].strip()
        decisive = human_label in PROGRESSION_LABELS
        exact = decisive and human_label == roster["luna_label"]
        comparison = {
            "review_id": review_id,
            "sample_id": roster["sample_id"],
            "source": roster["source"],
            "finding": roster["finding"],
            "luna_label": roster["luna_label"],
            "human_label": human_label,
            "human_decisive": decisive,
            "luna_human_exact": exact,
        }
        comparisons.append(comparison)
        responses.append(
            {
                "review_id": review_id,
                "human_label": human_label,
                "unusable_reason": _normalize_text(response.get("unusable_reason")),
                "reviewer_id": _normalize_text(response.get("reviewer_id")),
                "review_date": _normalize_text(response.get("review_date")),
                "reviewer_group_id": (
                    provenance["reviewer_group_id"] if provenance else ""
                ),
                "notes_optional": _normalize_text(response.get("notes_optional")),
            }
        )
        if decisive:
            if compact_review:
                label_source = "senior_luna_assisted_panel_consensus_v2"
                gold_status = "HUMAN_REVIEWED_LUNA_ASSISTED_PANEL_CONSENSUS"
            elif review_mode == "luna_assisted_senior_v2":
                label_source = "senior_luna_assisted_review_v2"
                gold_status = "HUMAN_REVIEWED_LUNA_ASSISTED_SINGLE_REVIEWER"
            else:
                label_source = "blind_human_review_v1"
                gold_status = "HUMAN_REVIEWED_SINGLE_REVIEWER"
            gold.append(
                sample
                | {
                    "progression_label": human_label,
                    "label_source": label_source,
                    "label_tier": "Gold",
                    "review_id": review_id,
                    "luna_label": roster["luna_label"],
                    "human_label": human_label,
                    "luna_human_exact": exact,
                    "reviewer_id": _normalize_text(response.get("reviewer_id")),
                    "review_date": _normalize_text(response.get("review_date")),
                    "reviewer_group_id": (
                        provenance["reviewer_group_id"] if provenance else ""
                    ),
                    "gold_status": gold_status,
                    "training_eligible": False,
                }
            )
        else:
            excluded.append(
                {
                    "review_id": review_id,
                    "sample_id": roster["sample_id"],
                    "patient_id_hash": roster["patient_id_hash"],
                    "source": roster["source"],
                    "finding": roster["finding"],
                    "luna_label": roster["luna_label"],
                    "human_label": human_label,
                    "unusable_reason": _normalize_text(
                        response.get("unusable_reason")
                    ),
                    "exclusion_reason": f"human_{human_label.lower()}",
                }
            )

    comparisons.sort(key=lambda row: row["review_id"])
    responses.sort(key=lambda row: row["review_id"])
    gold.sort(key=lambda row: row["review_id"])
    excluded.sort(key=lambda row: row["review_id"])
    sources = sorted({row["source"] for row in comparisons})
    by_source = {
        source: _stats([row for row in comparisons if row["source"] == source])
        for source in sources
    }
    by_luna_label = {
        label: _stats(
            [row for row in comparisons if row["luna_label"] == label]
        )
        for label in PROGRESSION_LABELS
    }
    confusion = {
        luna_label: {
            human_label: sum(
                row["luna_label"] == luna_label
                and row["human_label"] == human_label
                for row in comparisons
            )
            for human_label in HUMAN_REVIEW_LABELS
        }
        for luna_label in PROGRESSION_LABELS
    }
    held_silver = [
        row for row in validated_silver if row["patient_id_hash"] in roster_patients
    ]
    if len(training) + len(held_silver) != len(validated_silver):
        raise ContractError("training/quarantine Silver conservation failed")
    gold_patients = {row["patient_id_hash"] for row in gold}
    reviewer_ids = {row["reviewer_id"] for row in responses if row["reviewer_id"]}
    review_dates = {row["review_date"] for row in responses if row["review_date"]}
    assisted_review = review_mode in {
        "luna_assisted_senior_v2",
        SENIOR_COMPACT_REVIEW_MODE,
    }
    audit = {
        "schema": "prta-cxr.human-review-gold-freeze.v2",
        "status": (
            "PASS_SENIOR_LUNA_ASSISTED_REVIEW_COMPLETE_GOLD_FROZEN"
            if assisted_review
            else "PASS_HUMAN_REVIEW_COMPLETE_GOLD_FROZEN"
        ),
        "review_mode": review_mode,
        "independent_blind_review": not assisted_review,
        "luna_label_visible_to_reviewer": assisted_review,
        "review_rows": len(comparisons),
        "unique_review_ids": len({row["review_id"] for row in comparisons}),
        "unique_roster_patients": len(roster_patients),
        "workbook_sha256": workbook_sha256,
        "review_provenance": provenance,
        "review_provenance_sha256": (
            canonical_sha256(provenance) if provenance else None
        ),
        "responses_sha256": canonical_sha256(responses),
        "comparison_sha256": canonical_sha256(comparisons),
        "overall": _stats(comparisons),
        "by_source": by_source,
        "by_luna_label": by_luna_label,
        "worse": by_luna_label["Worse"],
        "confusion_luna_rows_human_columns": confusion,
        "gold_status": (
            "GOLD_SENIOR_LUNA_ASSISTED_PANEL_CONSENSUS_COMPLETE"
            if compact_review
            else (
                "GOLD_SENIOR_LUNA_ASSISTED_REVIEW_COMPLETE"
                if assisted_review
                else "GOLD_HUMAN_REVIEW_COMPLETE_SINGLE_REVIEWER"
            )
        ),
        "gold_rows": len(gold),
        "gold_unique_patients": len(gold_patients),
        "gold_human_label_counts": dict(
            sorted(Counter(row["human_label"] for row in gold).items())
        ),
        "excluded_rows": len(excluded),
        "excluded_human_label_counts": dict(
            sorted(Counter(row["human_label"] for row in excluded).items())
        ),
        "quarantined_patients_retained": len(roster_patients),
        "quarantined_silver_rows": len(held_silver),
        "training_eligible_silver_rows": len(training),
        "gold_training_patient_overlap": len(gold_patients & training_patients),
        "gold_manifest_sha256": canonical_sha256(gold),
        "excluded_manifest_sha256": canonical_sha256(excluded),
        "unique_reviewer_ids": len(reviewer_ids),
        "unique_review_dates": len(review_dates),
        "attested_reviewer_count": (
            provenance["reviewer_count"] if provenance else len(reviewer_ids)
        ),
        "single_human_reviewer_reference": (
            not compact_review and len(reviewer_ids) == 1
        ),
        "medical_ground_truth_claim": False,
        "formal_training_authorized": False,
        "split_cache_training_started": False,
    }
    return responses, comparisons, gold, excluded, audit
