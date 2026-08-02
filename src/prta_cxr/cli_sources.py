from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.data.source_builders import (
    build_chexpert_plus_source_manifest,
    build_exclusion_registry,
    build_mimic_source_manifest,
)


def prepare_sources_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build governed MIMIC and CheXpert Plus source manifests"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--mimic-metadata", type=Path)
    parser.add_argument("--mimic-split", type=Path)
    parser.add_argument("--mimic-image-root", type=Path)
    parser.add_argument("--mimic-report-root", type=Path)
    parser.add_argument("--mimic-resume", type=Path)
    parser.add_argument("--chexpert-plus-parquet", type=Path)
    parser.add_argument("--chexpert-image-root", type=Path)
    parser.add_argument(
        "--exclusion-config",
        type=Path,
        default=Path("configs/data/exclusion_sources_v1.json"),
    )
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot be combined with --formal")
        print(
            json.dumps(
                {
                    "status": "PASS_SOURCE_PREPARATION_PREFLIGHT",
                    "real_reports_opened": False,
                    "source_manifest_written": False,
                    "training_started": False,
                    "required_exclusion_path_envs": [
                        "PRTA_R24_COHORT",
                        "PRTA_R25_COHORT",
                        "PRTA_R26_COHORT",
                        "PRTA_R29_COHORT",
                        "PRTA_R30_COHORT",
                        "PRTA_R31_COHORT",
                        "PRTA_R32_STRUCTURAL_REGISTRY",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    require_formal_authorization(formal_flag=args.formal)
    required = {
        "output_root": args.output_root,
        "mimic_metadata": args.mimic_metadata,
        "mimic_split": args.mimic_split,
        "mimic_image_root": args.mimic_image_root,
        "mimic_report_root": args.mimic_report_root,
        "chexpert_plus_parquet": args.chexpert_plus_parquet,
        "chexpert_image_root": args.chexpert_image_root,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("formal source arguments missing: " + ", ".join(missing))
    for name, path in required.items():
        if name == "output_root":
            continue
        if not Path(path).exists():
            raise FileNotFoundError(path)
    if args.output_root.exists():
        raise FileExistsError(f"source output root must be fresh: {args.output_root}")
    staging = args.output_root.with_name(
        f".{args.output_root.name}.tmp.{os.getpid()}"
    )
    if staging.exists():
        raise FileExistsError(f"source staging root already exists: {staging}")
    staging.mkdir(parents=True)
    mimic_output = staging / "mimic_cxr_jpg_studies.jsonl"
    chexpert_output = staging / "chexpert_plus_studies.jsonl"
    exclusions_output = staging / "patient_exclusions.json"
    mimic_audit = build_mimic_source_manifest(
        mimic_output,
        metadata_path=args.mimic_metadata,
        split_path=args.mimic_split,
        image_root=args.mimic_image_root,
        report_root=args.mimic_report_root,
        resume_path=args.mimic_resume,
    )
    chexpert_audit = build_chexpert_plus_source_manifest(
        chexpert_output,
        parquet_path=args.chexpert_plus_parquet,
        image_root=args.chexpert_image_root,
    )
    exclusion_audit = build_exclusion_registry(
        args.exclusion_config, exclusions_output
    )
    receipt = {
        "schema": "prta-cxr.real-source-preparation.v1",
        "status": "PASS_REAL_SOURCE_MANIFESTS",
        "mimic": mimic_audit,
        "chexpert_plus": chexpert_audit,
        "exclusions": exclusion_audit,
        "input_hashes": {
            "mimic_metadata": sha256_file(args.mimic_metadata),
            "mimic_split": sha256_file(args.mimic_split),
            "chexpert_plus_parquet": sha256_file(args.chexpert_plus_parquet),
            "exclusion_config": sha256_file(args.exclusion_config),
        },
        "formal_source_preparation": True,
        "training_started": False,
        "image_cache_written": False,
        "luna_called": False,
        "internal_test_opened": False,
        "protected_outcomes_opened": False,
    }
    write_json_atomic(staging / "source_preparation_receipt.json", receipt)
    staging.replace(args.output_root)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
