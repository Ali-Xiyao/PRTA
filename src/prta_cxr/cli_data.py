from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.data.assembly import build_full_candidate_pairs, normalize_studies
from prta_cxr.data.catalog import SourceSpec, load_source_catalog
from prta_cxr.data.exclusions import load_exclusion_registry
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.data.splitting import patient_stratified_split

DEFAULT_CATALOG = Path("configs/data/source_catalog_v1.json")


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _synthetic_source() -> SourceSpec:
    return SourceSpec(
        source_id="synthetic_longitudinal",
        patient_namespace="synthetic",
        manifest_env="PRTA_SYNTHETIC_UNUSED",
        status="debug_only_legacy",
        allowed_official_splits=("train",),
        longitudinal_reports=True,
        license_verified=True,
        deidentified=True,
        processing_allowed=True,
    )


def synthetic_studies(patient_count: int = 12) -> list[dict[str, Any]]:
    rows = []
    for patient in range(patient_count):
        for visit in range(3):
            rows.append(
                {
                    "patient_id": f"patient-{patient}",
                    "study_id": f"study-{patient}-{visit}",
                    "image_id": f"image-{patient}-{visit}",
                    "image_path": f"synthetic/image-{patient}-{visit}.png",
                    "report": f"synthetic report {patient} {visit}",
                    "study_datetime": f"2025-01-{visit + 1:02d}T00:00:00",
                    "view": "PA" if visit % 2 == 0 else "AP",
                    "official_split": "train",
                }
            )
    return rows


def build_pairs_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the full eligible longitudinal candidate-pair pool"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "synthetic", "formal"), default="preflight"
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--exclusions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    catalog = load_source_catalog(args.catalog)
    if args.mode == "preflight":
        audit = catalog.audit()
        audit.update(
            {
                "status": "PASS_BUILD_PAIRS_PREFLIGHT",
                "real_data_opened": False,
                "formal_artifact_written": False,
            }
        )
        _print(audit)
        return 0
    if args.mode == "synthetic":
        source = _synthetic_source()
        normalized, source_audit = normalize_studies(source, synthetic_studies())
        pairs, pair_audit = build_full_candidate_pairs(
            {source.source_id: normalized}
        )
        result = {
            "status": "PASS_BUILD_PAIRS_SYNTHETIC",
            "source_audit": source_audit,
            "pair_audit": pair_audit,
            "pairs": pairs,
            "formal_artifact_written": False,
        }
        if args.output:
            write_jsonl_atomic(args.output, pairs)
        if args.audit_output:
            write_json_atomic(args.audit_output, result | {"pairs": []})
        _print(result | {"pairs": f"{len(pairs)} synthetic rows"})
        return 0

    require_formal_authorization(formal_flag=args.formal)
    if not args.output or not args.audit_output or not args.exclusions:
        parser.error("formal mode requires --output, --audit-output, and --exclusions")
    exclusions, exclusion_audit = load_exclusion_registry(args.exclusions)
    normalized_by_source = {}
    source_audits = {}
    for source in catalog.sources:
        if not source.eligible_for_repartition:
            continue
        path = source.manifest_path()
        rows = read_jsonl(path)
        normalized, audit = normalize_studies(
            source, rows, excluded_patient_hashes=exclusions
        )
        normalized_by_source[source.source_id] = normalized
        source_audits[source.source_id] = audit
    if not normalized_by_source:
        raise RuntimeError("no source is eligible and activated for repartition")
    pairs, pair_audit = build_full_candidate_pairs(normalized_by_source)
    if not pairs:
        raise RuntimeError("full candidate build produced zero pairs")
    receipt = {
        "status": "PASS_FULL_CANDIDATE_PAIR_BUILD",
        "catalog_audit": catalog.audit(),
        "exclusion_audit": exclusion_audit,
        "source_audits": source_audits,
        "pair_audit": pair_audit,
        "formal_execution": True,
        "outcome_fields_read": [],
    }
    write_jsonl_atomic(args.output, pairs)
    write_json_atomic(args.audit_output, receipt)
    _print(receipt)
    return 0


def _synthetic_labeled_rows() -> list[dict[str, Any]]:
    source = _synthetic_source()
    normalized, _ = normalize_studies(source, synthetic_studies(patient_count=30))
    pairs, _ = build_full_candidate_pairs({source.source_id: normalized})
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    findings = ("Effusion", "Edema", "Pneumothorax")
    output = []
    for index, pair in enumerate(pairs):
        output.append(
            pair
            | {
                "sample_id": f"synthetic-{index:04d}",
                "finding": findings[index % len(findings)],
                "progression_label": labels[index % len(labels)],
                "label_source": "synthetic",
                "label_tier": "Tier-A",
            }
        )
    return output


def freeze_splits_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze new patient-disjoint Train/Dev/Internal-test splits"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "synthetic", "formal"), default="preflight"
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--salt", default="prta-cxr-full-repartition-v1")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    catalog = load_source_catalog(args.catalog)
    if args.mode == "preflight":
        _print(
            {
                "status": "PASS_FREEZE_SPLITS_PREFLIGHT",
                "fractions": catalog.split_fractions,
                "debug_roster_inherited": False,
                "real_data_opened": False,
            }
        )
        return 0
    if args.mode == "formal":
        require_formal_authorization(formal_flag=args.formal)
        if not args.input or not args.output or not args.audit_output:
            parser.error("formal mode requires --input/--output/--audit-output")
        rows = read_jsonl(args.input)
    else:
        rows = _synthetic_labeled_rows()
    split_rows, audit = patient_stratified_split(
        rows, fractions=catalog.split_fractions, salt=args.salt
    )
    result = {
        "status": "PASS_FREEZE_SPLITS_SYNTHETIC"
        if args.mode == "synthetic"
        else "PASS_FREEZE_SPLITS_FORMAL",
        "audit": audit,
        "formal_execution": args.mode == "formal",
    }
    if args.output:
        write_jsonl_atomic(args.output, split_rows)
    if args.audit_output:
        write_json_atomic(args.audit_output, result)
    _print(result)
    return 0
