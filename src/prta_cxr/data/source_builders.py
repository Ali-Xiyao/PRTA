from __future__ import annotations

import json
import os
import re
import shutil
from collections import Counter
from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_jsonl_atomic
from prta_cxr.contracts import ContractError, canonical_sha256, sha256_file
from prta_cxr.data.assembly import hashed_patient_id


def _pandas():
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError(
            "source preparation requires the optional 'data' dependencies"
        ) from error
    return pd


def _numeric_patient(value: object) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())
    if not digits:
        raise ContractError("patient identifier has no numeric component")
    return str(int(digits))


def _legacy_patient_hash(namespace: str, value: object) -> tuple[str, bool]:
    text = str(value).strip()
    digits = "".join(character for character in text if character.isdigit())
    if digits:
        return hashed_patient_id(namespace, str(int(digits))), False
    if not text:
        raise ContractError("legacy patient identifier is empty")
    return hashed_patient_id(namespace, text), True


def _mimic_image_path(
    root: Path, subject_id: object, study_id: object, dicom_id: object
) -> Path:
    subject = _numeric_patient(subject_id)
    return (
        root
        / f"p{subject[:2]}"
        / f"p{subject}"
        / f"s{int(study_id)}"
        / f"{dicom_id}.jpg"
    )


def _mimic_report_path(
    root: Path, subject_id: object, study_id: object
) -> Path:
    subject = _numeric_patient(subject_id)
    return root / f"p{subject[:2]}" / f"p{subject}" / f"s{int(study_id)}.txt"


def _mimic_datetime(date_value: object, time_value: object) -> str:
    date_text = str(int(float(date_value))).zfill(8)
    if str(time_value).strip().lower() in {"", "nan", "none", "<na>"}:
        time_number = 0
    else:
        time_number = int(float(time_value))
    time_text = str(time_number).zfill(6)[-6:]
    try:
        value = datetime.strptime(date_text + time_text, "%Y%m%d%H%M%S")
    except ValueError:
        value = datetime.strptime(date_text, "%Y%m%d")
    return value.isoformat()


def _select_mimic_studies(metadata_path: Path, split_path: Path):
    pd = _pandas()
    metadata = pd.read_csv(
        metadata_path,
        usecols=[
            "dicom_id",
            "subject_id",
            "study_id",
            "ViewPosition",
            "StudyDate",
            "StudyTime",
        ],
        dtype={"dicom_id": str, "subject_id": str, "study_id": str},
    )
    split = pd.read_csv(
        split_path,
        dtype={"dicom_id": str, "subject_id": str, "study_id": str},
    )
    merged = metadata.merge(
        split,
        on=["dicom_id", "subject_id", "study_id"],
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != len(metadata) or len(split) != len(metadata):
        raise ContractError("MIMIC metadata/split join is incomplete")
    if int(merged.groupby("subject_id")["split"].nunique().max()) != 1:
        raise ContractError("official MIMIC splits are not patient-disjoint")
    train = merged[merged["split"].eq("train")].copy()
    train["ViewPosition"] = train["ViewPosition"].fillna("").str.upper()
    frontal = train[train["ViewPosition"].isin(("PA", "AP"))].copy()
    frontal["view_rank"] = frontal["ViewPosition"].map({"PA": 0, "AP": 1})
    selected = (
        frontal.sort_values(
            ["subject_id", "study_id", "view_rank", "dicom_id"]
        )
        .drop_duplicates(["subject_id", "study_id"])
        .drop(columns=["view_rank"])
    )
    audit = {
        "metadata_rows": len(metadata),
        "official_split_rows": len(split),
        "official_train_rows": len(train),
        "official_train_frontal_rows": len(frontal),
        "selected_frontal_studies": len(selected),
    }
    return selected, audit


def build_mimic_source_manifest(
    output_path: Path,
    *,
    metadata_path: Path,
    split_path: Path,
    image_root: Path,
    report_root: Path,
    resume_path: Path | None = None,
) -> dict[str, Any]:
    selected, audit = _select_mimic_studies(metadata_path, split_path)
    counters = Counter()
    patients: set[str] = set()
    resumed_image_ids: set[str] = set()
    if resume_path is not None:
        with Path(resume_path).open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ContractError(
                        f"MIMIC resume has invalid JSON at line {line_number}"
                    ) from error
                image_id = str(row["image_id"])
                if image_id in resumed_image_ids:
                    raise ContractError("MIMIC resume contains duplicate image IDs")
                resumed_image_ids.add(image_id)
                patients.add(str(row["patient_id"]))
        selected_ids = {str(value) for value in selected["dicom_id"]}
        if not resumed_image_ids.issubset(selected_ids):
            raise ContractError("MIMIC resume contains rows outside selected studies")
        counters["resumed_studies"] = len(resumed_image_ids)

    def rows() -> Iterator[dict[str, Any]]:
        for row in selected.itertuples(index=False):
            if str(row.dicom_id) in resumed_image_ids:
                continue
            patient = _numeric_patient(row.subject_id)
            image = _mimic_image_path(
                image_root, row.subject_id, row.study_id, row.dicom_id
            )
            report = _mimic_report_path(report_root, row.subject_id, row.study_id)
            if not image.is_file():
                counters["missing_image"] += 1
                continue
            if not report.is_file():
                counters["missing_report"] += 1
                continue
            text = report.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                counters["empty_report"] += 1
                continue
            patients.add(patient)
            counters["emitted_studies"] += 1
            yield {
                "patient_id": patient,
                "study_id": str(int(row.study_id)),
                "image_id": str(row.dicom_id),
                "image_lineage_id": f"mimic|{row.dicom_id}",
                "image_path": str(image),
                "report": text,
                "study_datetime": _mimic_datetime(
                    row.StudyDate, row.StudyTime
                ),
                "view": str(row.ViewPosition),
                "official_split": "train",
                "time_basis": "calendar",
            }

    if resume_path is None:
        write_jsonl_atomic(output_path, rows())
    else:
        if output_path.exists():
            raise FileExistsError(f"refusing to overwrite artifact: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(f".{output_path.name}.tmp.{os.getpid()}")
        try:
            with Path(resume_path).open("rb") as source, temporary.open("wb") as sink:
                source.seek(0, os.SEEK_END)
                resume_bytes = source.tell()
                resume_has_newline = True
                if resume_bytes:
                    source.seek(-1, os.SEEK_END)
                    resume_has_newline = source.read(1) == b"\n"
                source.seek(0)
                shutil.copyfileobj(source, sink, length=1024 * 1024)
                if resume_bytes and not resume_has_newline:
                    sink.write(b"\n")
                for row in rows():
                    sink.write(
                        (
                            json.dumps(
                                row,
                                sort_keys=True,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
            temporary.replace(output_path)
        finally:
            if temporary.exists():
                temporary.unlink()
    return {
        "schema": "prta-cxr.source-build-audit.v1",
        "source_id": "mimic_cxr_jpg",
        "time_basis": "calendar",
        **audit,
        "patients": len(patients),
        "resumed_studies": len(resumed_image_ids),
        "diagnostics": dict(sorted(counters.items())),
        "manifest_sha256": sha256_file(output_path),
        "raw_patient_ids_persisted_in_restricted_source_manifest": True,
        "protected_outcomes_opened": False,
    }


_CHEXPERT_STUDY = re.compile(
    r"^(?P<split>[^/]+)/(?P<patient>patient[^/]+)/(?P<study>study[^/]+)/"
)


def build_chexpert_plus_source_manifest(
    output_path: Path,
    *,
    parquet_path: Path,
    image_root: Path,
) -> dict[str, Any]:
    pd = _pandas()
    columns = [
        "path_to_image",
        "frontal_lateral",
        "ap_pa",
        "deid_patient_id",
        "patient_report_date_order",
        "report",
        "section_findings",
        "section_impression",
        "split",
    ]
    frame = pd.read_parquet(parquet_path, columns=columns)
    train = frame[frame["split"].astype(str).eq("train")].copy()
    frontal = train[
        train["frontal_lateral"].astype(str).str.lower().eq("frontal")
        & train["ap_pa"].astype(str).str.upper().isin(("PA", "AP"))
    ].copy()
    frontal["view_rank"] = (
        frontal["ap_pa"].astype(str).str.upper().map({"PA": 0, "AP": 1})
    )
    parsed = frontal["path_to_image"].astype(str).str.replace("\\", "/").str.extract(
        _CHEXPERT_STUDY
    )
    if bool(parsed.isna().any(axis=None)):
        raise ContractError("CheXpert Plus image paths violate patient/study schema")
    frontal["parsed_patient"] = parsed["patient"]
    frontal["parsed_study"] = parsed["study"]
    if not bool(
        (
            frontal["deid_patient_id"].astype(str)
            == frontal["parsed_patient"].astype(str)
        ).all()
    ):
        raise ContractError("CheXpert Plus patient column/path mismatch")
    selected = (
        frontal.sort_values(
            [
                "deid_patient_id",
                "parsed_study",
                "view_rank",
                "path_to_image",
            ]
        )
        .drop_duplicates(["deid_patient_id", "parsed_study"])
        .drop(columns=["view_rank"])
    )
    counters = Counter()
    patients: set[str] = set()

    def _report_text(row: Any) -> str:
        for field in ("report", "section_findings", "section_impression"):
            value = getattr(row, field)
            if value is not None and not pd.isna(value) and str(value).strip():
                return str(value).strip()
        return ""

    def rows() -> Iterator[dict[str, Any]]:
        base = datetime(2000, 1, 1)
        for row in selected.itertuples(index=False):
            patient = str(row.deid_patient_id)
            relative = Path(str(row.path_to_image).replace("/", os.sep))
            image = image_root / relative
            if not image.is_file():
                counters["missing_image"] += 1
                continue
            text = _report_text(row)
            if not text:
                counters["empty_report"] += 1
                continue
            order = int(row.patient_report_date_order)
            if order <= 0:
                counters["invalid_report_order"] += 1
                continue
            patients.add(patient)
            counters["emitted_studies"] += 1
            image_id = Path(str(row.path_to_image)).stem
            yield {
                "patient_id": patient,
                "study_id": str(row.parsed_study),
                "image_id": image_id,
                "image_lineage_id": f"chexpert_plus|{row.path_to_image}",
                "image_path": str(image),
                "report": text,
                "study_datetime": (base + timedelta(days=order - 1)).isoformat(),
                "view": str(row.ap_pa).upper(),
                "official_split": "train",
                "time_basis": "within_patient_ordinal",
            }

    write_jsonl_atomic(output_path, rows())
    return {
        "schema": "prta-cxr.source-build-audit.v1",
        "source_id": "chexpert_plus",
        "time_basis": "within_patient_ordinal",
        "input_rows": len(frame),
        "official_train_rows": len(train),
        "official_train_frontal_rows": len(frontal),
        "selected_frontal_studies": len(selected),
        "patients": len(patients),
        "diagnostics": dict(sorted(counters.items())),
        "manifest_sha256": sha256_file(output_path),
        "raw_patient_ids_persisted_in_restricted_source_manifest": True,
        "protected_outcomes_opened": False,
        "calendar_intervals_available": False,
    }


def _project_json_source(
    path: Path,
    *,
    patient_field: str,
    partition_field: str | None,
    excluded_partitions: set[str] | None,
    patient_namespace: str,
) -> tuple[set[str], dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ContractError("historical exclusion source must be a JSON list")
    output: set[str] = set()
    selected_rows = 0
    for row in value:
        if not isinstance(row, Mapping) or patient_field not in row:
            raise ContractError("historical row lacks the patient field")
        if partition_field is not None:
            if partition_field not in row:
                raise ContractError("historical row lacks the partition field")
            if str(row[partition_field]) not in excluded_partitions:
                continue
        selected_rows += 1
        patient = _numeric_patient(row[patient_field])
        output.add(hashed_patient_id(patient_namespace, patient))
    return output, {
        "path_sha256": sha256_file(path),
        "rows_scanned": len(value),
        "rows_selected": selected_rows,
        "patients_selected": len(output),
        "fields_accessed": [
            patient_field,
            *([] if partition_field is None else [partition_field]),
        ],
        "outcome_fields_accessed": [],
    }


def build_exclusion_registry(
    config_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if config.get("schema") != "prta-cxr.exclusion-sources.v1":
        raise ContractError("unsupported exclusion-source config schema")
    namespace = str(config["patient_namespace"])
    revealed: set[str] = set()
    source_audits = {}
    for source in config["sources"]:
        raw = os.environ.get(str(source["path_env"]), "").strip()
        if not raw:
            raise ContractError(f"missing exclusion path env {source['path_env']}")
        partitions = source["excluded_partitions"]
        selected, audit = _project_json_source(
            Path(raw),
            patient_field=str(source["patient_field"]),
            partition_field=(
                None
                if source["partition_field"] is None
                else str(source["partition_field"])
            ),
            excluded_partitions=(
                None if partitions is None else {str(value) for value in partitions}
            ),
            patient_namespace=namespace,
        )
        revealed.update(selected)
        source_audits[str(source["source_id"])] = audit

    registry_raw = os.environ.get(
        str(config["legacy_structural_registry_env"]), ""
    ).strip()
    if not registry_raw:
        raise ContractError("missing legacy structural registry environment path")
    legacy = json.loads(Path(registry_raw).read_text(encoding="utf-8"))
    if legacy.get("outcome_fields_read") != [] or legacy.get(
        "sealed_label_file_opened"
    ) is not False:
        raise ContractError("legacy structural registry lacks outcome firewall")
    legacy_sources = legacy["sources"]
    for name in ("r32_dev", "r32_sealed_vlm_test"):
        revealed.update(
            hashed_patient_id(namespace, _numeric_patient(value))
            for value in legacy_sources[name]["patient_ids"]
        )
    gold = set()
    raw_hashed_gold = 0
    for value in legacy_sources["gold_quarantine"]["patient_ids"]:
        patient_hash, used_raw = _legacy_patient_hash(namespace, value)
        gold.add(patient_hash)
        raw_hashed_gold += int(used_raw)
    payload = {
        "schema": "prta-cxr.patient-exclusions.v1",
        "categories": [
            {
                "category": "revealed_historical_test",
                "patient_id_hashes": sorted(revealed),
            },
            {
                "category": "protected_gold",
                "patient_id_hashes": sorted(gold),
            },
        ],
    }
    from prta_cxr.artifacts import write_json_atomic

    write_json_atomic(output_path, payload)
    return {
        "schema": "prta-cxr.exclusion-projection-audit.v1",
        "status": "PASS_ID_PARTITION_ONLY_PROJECTION",
        "sources": source_audits,
        "legacy_structural_registry_sha256": sha256_file(Path(registry_raw)),
        "revealed_historical_test_patients": len(revealed),
        "protected_gold_patients": len(gold),
        "nonnumeric_gold_ids_hashed_as_namespaced_raw": raw_hashed_gold,
        "union_patients": len(revealed | gold),
        "reactivated_old_train_membership": True,
        "fields_accessed": ["patient_id", "partition"],
        "outcome_fields_accessed": [],
        "registry_sha256": canonical_sha256(payload),
    }
