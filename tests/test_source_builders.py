import json

import pandas as pd

from prta_cxr.data.assembly import hashed_patient_id
from prta_cxr.data.exclusions import load_exclusion_registry
from prta_cxr.data.source_builders import (
    build_chexpert_plus_source_manifest,
    build_exclusion_registry,
    build_mimic_source_manifest,
)


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_mimic_source_builder_selects_train_frontal_and_reads_report(tmp_path):
    metadata = pd.DataFrame(
        [
            {
                "dicom_id": "ap",
                "subject_id": "10000001",
                "study_id": "10",
                "ViewPosition": "AP",
                "StudyDate": 20250101,
                "StudyTime": 100000,
            },
            {
                "dicom_id": "pa",
                "subject_id": "10000001",
                "study_id": "10",
                "ViewPosition": "PA",
                "StudyDate": 20250101,
                "StudyTime": 100000,
            },
            {
                "dicom_id": "later",
                "subject_id": "10000001",
                "study_id": "11",
                "ViewPosition": "PA",
                "StudyDate": 20250102,
                "StudyTime": 110000,
            },
        ]
    )
    split = metadata[["dicom_id", "subject_id", "study_id"]].copy()
    split["split"] = "train"
    metadata_path = tmp_path / "metadata.csv"
    split_path = tmp_path / "split.csv"
    metadata.to_csv(metadata_path, index=False)
    split.to_csv(split_path, index=False)
    image_root = tmp_path / "images"
    report_root = tmp_path / "reports"
    image_dir = image_root / "p10" / "p10000001"
    report_dir = report_root / "p10" / "p10000001"
    (image_dir / "s10").mkdir(parents=True)
    (image_dir / "s11").mkdir(parents=True)
    report_dir.mkdir(parents=True)
    (image_dir / "s10" / "pa.jpg").write_bytes(b"image")
    (image_dir / "s11" / "later.jpg").write_bytes(b"image")
    (report_dir / "s10.txt").write_text("first report", encoding="utf-8")
    (report_dir / "s11.txt").write_text("second report", encoding="utf-8")
    output = tmp_path / "mimic.jsonl"
    audit = build_mimic_source_manifest(
        output,
        metadata_path=metadata_path,
        split_path=split_path,
        image_root=image_root,
        report_root=report_root,
    )
    rows = _jsonl(output)
    assert [row["image_id"] for row in rows] == ["pa", "later"]
    assert all(row["time_basis"] == "calendar" for row in rows)
    assert audit["patients"] == 1
    resumed_output = tmp_path / "mimic-resumed.jsonl"
    resumed_audit = build_mimic_source_manifest(
        resumed_output,
        metadata_path=metadata_path,
        split_path=split_path,
        image_root=image_root,
        report_root=report_root,
        resume_path=output,
    )
    assert resumed_output.read_bytes() == output.read_bytes()
    assert resumed_audit["resumed_studies"] == 2


def test_chexpert_plus_builder_uses_ordinal_time_and_local_images(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "path_to_image": "train/patient1/study1/view1_frontal.jpg",
                "frontal_lateral": "Frontal",
                "ap_pa": "AP",
                "deid_patient_id": "patient1",
                "patient_report_date_order": 1,
                "report": "first report",
                "section_findings": None,
                "section_impression": None,
                "split": "train",
            },
            {
                "path_to_image": "train/patient1/study2/view1_frontal.jpg",
                "frontal_lateral": "Frontal",
                "ap_pa": "PA",
                "deid_patient_id": "patient1",
                "patient_report_date_order": 2,
                "report": "second report",
                "section_findings": None,
                "section_impression": None,
                "split": "train",
            },
        ]
    )
    parquet = tmp_path / "chexpert.parquet"
    frame.to_parquet(parquet, index=False)
    image_root = tmp_path / "images"
    for relative in frame["path_to_image"]:
        path = image_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image")
    output = tmp_path / "chexpert.jsonl"
    audit = build_chexpert_plus_source_manifest(
        output, parquet_path=parquet, image_root=image_root
    )
    rows = _jsonl(output)
    assert len(rows) == 2
    assert rows[0]["study_datetime"] < rows[1]["study_datetime"]
    assert audit["calendar_intervals_available"] is False


def test_exclusion_projection_reactivates_train_and_hashes_only(
    tmp_path, monkeypatch
):
    sources = []
    for index in range(6):
        path = tmp_path / f"source-{index}.json"
        rows = [
            {"patient_id": f"p{index}01", "partition": "train"},
            {"patient_id": f"p{index}02", "partition": "dev"},
            {"patient_id": f"p{index}03", "partition": "test"},
        ]
        path.write_text(json.dumps(rows), encoding="utf-8")
        env = f"SOURCE_{index}"
        monkeypatch.setenv(env, str(path))
        sources.append(
            {
                "source_id": f"source-{index}",
                "path_env": env,
                "patient_field": "patient_id",
                "partition_field": "partition" if index >= 3 else None,
                "excluded_partitions": ["dev", "test"] if index >= 3 else None,
            }
        )
    legacy = {
        "outcome_fields_read": [],
        "sealed_label_file_opened": False,
        "sources": {
            "r32_dev": {"patient_ids": ["p701"]},
            "r32_sealed_vlm_test": {"patient_ids": ["p702"]},
            "gold_quarantine": {"patient_ids": ["p703", "opaque-gold"]},
            "r32_train": {"patient_ids": ["p704"]},
        },
    }
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setenv("LEGACY", str(legacy_path))
    config = {
        "schema": "prta-cxr.exclusion-sources.v1",
        "patient_namespace": "mimic",
        "sources": sources,
        "legacy_structural_registry_env": "LEGACY",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    output = tmp_path / "exclusions.json"
    audit = build_exclusion_registry(config_path, output)
    excluded, _ = load_exclusion_registry(output)
    assert hashed_patient_id("mimic", "704") not in excluded
    assert hashed_patient_id("mimic", "701") in excluded
    assert audit["outcome_fields_accessed"] == []
    assert audit["nonnumeric_gold_ids_hashed_as_namespaced_raw"] == 1
