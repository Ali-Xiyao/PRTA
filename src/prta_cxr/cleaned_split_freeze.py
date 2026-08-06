from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from prta_cxr.artifacts import (
    replace_json_atomic,
    write_json_atomic,
    write_jsonl_atomic,
)
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file

ACTIVE_COUNTS = {
    "train": 89_406,
    "dev": 13_420,
    "internal_test": 13_588,
    "gold": 250,
}
EXCLUDED_COUNTS = {
    "train": 9_004,
    "dev": 2_219,
    "internal_test": 369,
    "gold": 75,
}
RETAINED_COUNTS = {
    split: ACTIVE_COUNTS[split] - EXCLUDED_COUNTS[split]
    for split in ACTIVE_COUNTS
}
BAND_COUNTS = {"Top 3%": 3_500, "3-5%": 2_334, "5-10%": 5_833}

FREEZE_SCHEMA = "prta-cxr.cleaned-split-freeze.v1"
FREEZE_STATUS = "PASS_CLEANED_SPLIT_FROZEN"
DATASET_VERSION = "prta_cxr_physician_cleaned_v1"
PHYSICIAN_REVIEW_STATUS = "PHYSICIAN_CONFIRMED_EXCLUDE"
PHYSICIAN_DECISION = "DO_NOT_USE"
FUTURE_ACTION = "EXCLUDED_FROM_ALL_FUTURE_TRAIN_DEV_TEST_GOLD"


class CleanedSplitContractError(ValueError):
    pass


def _raw_line_sha256(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def _verified_hashes(
    paths: Mapping[str, str], hashes: Mapping[str, str], *, kind: str
) -> None:
    if set(paths) != set(hashes):
        raise CleanedSplitContractError(f"{kind} path/hash keys differ")
    for key, value in paths.items():
        path = Path(value)
        if not path.is_file():
            raise FileNotFoundError(f"{kind} file missing: {key}={path}")
        if sha256_file(path) != str(hashes[key]):
            raise CleanedSplitContractError(f"{kind} hash changed: {key}")


def _profile_jsonl(
    path: Path,
    *,
    allowed_splits: set[str],
    implicit_split: str | None = None,
) -> dict[str, Any]:
    ids: set[str] = set()
    id_split: dict[str, str] = {}
    line_hashes: dict[str, str] = {}
    patients: dict[str, set[str]] = {split: set() for split in allowed_splits}
    split_counts: Counter[str] = Counter()
    label_counts: dict[str, Counter[str]] = {
        split: Counter() for split in allowed_splits
    }
    source_counts: dict[str, Counter[str]] = {
        split: Counter() for split in allowed_splits
    }
    finding_counts: dict[str, Counter[str]] = {
        split: Counter() for split in allowed_splits
    }
    with Path(path).open("rb") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line.decode("utf-8"))
            sample_id = str(row.get("sample_id", "")).strip()
            if not sample_id or sample_id in ids:
                raise CleanedSplitContractError(
                    f"missing/duplicate sample_id at {path}:{line_number}"
                )
            split = str(row.get("split", implicit_split or "")).strip()
            if split not in allowed_splits:
                raise CleanedSplitContractError(
                    f"unexpected split {split!r} at {path}:{line_number}"
                )
            label_key = "human_label" if split == "gold" else "progression_label"
            label = str(row.get(label_key, "")).strip()
            if label not in PROGRESSION_LABELS:
                raise CleanedSplitContractError(
                    f"invalid label {label!r} at {path}:{line_number}"
                )
            patient = str(row.get("patient_id_hash", "")).strip()
            if not patient:
                raise CleanedSplitContractError(
                    f"missing patient hash at {path}:{line_number}"
                )
            ids.add(sample_id)
            id_split[sample_id] = split
            line_hashes[sample_id] = _raw_line_sha256(line)
            patients[split].add(patient)
            split_counts[split] += 1
            label_counts[split][label] += 1
            source_counts[split][str(row.get("source", ""))] += 1
            finding_counts[split][str(row.get("finding", ""))] += 1
    return {
        "ids": ids,
        "id_split": id_split,
        "line_hashes": line_hashes,
        "patients": patients,
        "split_counts": dict(split_counts),
        "label_counts": {
            split: dict(sorted(values.items()))
            for split, values in label_counts.items()
        },
        "source_counts": {
            split: dict(sorted(values.items()))
            for split, values in source_counts.items()
        },
        "finding_counts": {
            split: dict(sorted(values.items()))
            for split, values in finding_counts.items()
        },
    }


def _load_exclusions(
    path: Path,
    *,
    expected_counts: Mapping[str, int],
    expected_bands: Mapping[str, int],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    id_split: dict[str, str] = {}
    split_counts: Counter[str] = Counter()
    band_counts: Counter[str] = Counter()
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            sample_id = str(row.get("sample_id", "")).strip()
            split = str(row.get("split", "")).strip()
            if not sample_id or sample_id in ids:
                raise CleanedSplitContractError(
                    f"missing/duplicate exclusion ID at {path}:{line_number}"
                )
            if split not in expected_counts:
                raise CleanedSplitContractError(
                    f"unexpected exclusion split {split!r}"
                )
            if row.get("review_status") != "SUSPICIOUS_PENDING_REVIEW":
                raise CleanedSplitContractError(
                    "source exclusion roster is not the frozen Top-10% roster"
                )
            if row.get("diagnostic_action") != (
                "EXCLUDED_FROM_TOP10_POSTHOC_DIAGNOSTIC"
            ):
                raise CleanedSplitContractError(
                    "source exclusion action differs from diagnostic receipt"
                )
            ids.add(sample_id)
            id_split[sample_id] = split
            split_counts[split] += 1
            band_counts[str(row.get("priority_band", ""))] += 1
            rows.append(row)
    if dict(split_counts) != dict(expected_counts):
        raise CleanedSplitContractError(
            f"physician exclusion counts differ: {dict(split_counts)}"
        )
    if dict(band_counts) != dict(expected_bands):
        raise CleanedSplitContractError(
            f"physician exclusion band counts differ: {dict(band_counts)}"
        )
    return rows, id_split


def _assert_exact_complement(
    *,
    original_ids: set[str],
    retained_ids: set[str],
    excluded_ids: set[str],
) -> None:
    if retained_ids & excluded_ids:
        raise CleanedSplitContractError("retained and excluded IDs overlap")
    if original_ids != retained_ids | excluded_ids:
        missing = len(original_ids - retained_ids - excluded_ids)
        unexpected = len((retained_ids | excluded_ids) - original_ids)
        raise CleanedSplitContractError(
            "source is not the exact retained/excluded union; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _assert_pairwise_patient_disjoint(
    patients: Mapping[str, set[str]],
) -> dict[str, int]:
    overlaps: dict[str, int] = {}
    splits = sorted(patients)
    for index, left in enumerate(splits):
        for right in splits[index + 1 :]:
            key = f"{left}__{right}"
            overlaps[key] = len(patients[left] & patients[right])
    if any(overlaps.values()):
        raise CleanedSplitContractError(
            f"patient leakage exists in cleaned split: {overlaps}"
        )
    return overlaps


def _write_private_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "sample_id",
        "split",
        "rank_global",
        "priority_band",
        "candidate_score",
        "candidate_reasons",
        "review_status",
        "physician_review_scope",
        "physician_decision",
        "cleaned_split_action",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in fields} for row in rows
        )


def freeze_cleaned_split(
    *,
    preparation_receipt: Path,
    luna_merge_audit: Path,
    sol_train_receipt: Path,
    sol_protected_receipt: Path,
    output_root: Path,
    active_pointer: Path,
    replace_active_pointer: bool = False,
    expected_active_counts: Mapping[str, int] = ACTIVE_COUNTS,
    expected_excluded_counts: Mapping[str, int] = EXCLUDED_COUNTS,
    expected_retained_counts: Mapping[str, int] = RETAINED_COUNTS,
    expected_band_counts: Mapping[str, int] = BAND_COUNTS,
) -> dict[str, Any]:
    preparation_receipt = Path(preparation_receipt).resolve()
    output_root = Path(output_root).resolve()
    active_pointer = Path(active_pointer).resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing existing output root: {output_root}")
    if active_pointer.exists() and not replace_active_pointer:
        raise FileExistsError(f"refusing existing active pointer: {active_pointer}")
    if active_pointer.exists():
        previous_pointer = json.loads(active_pointer.read_text(encoding="utf-8"))
        if previous_pointer.get("schema") != (
            "prta-cxr.active-cleaned-split-pointer.v1"
        ) or previous_pointer.get("status") != "ACTIVE_CLEANED_SPLIT_FROZEN":
            raise CleanedSplitContractError(
                "refusing to replace an unrecognized active pointer"
            )
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise CleanedSplitContractError("private cleaned split must stay outside Git")

    prep = json.loads(preparation_receipt.read_text(encoding="utf-8"))
    if prep.get("schema") != "prta-cxr.top10-risk-exclusion-preparation.v1":
        raise CleanedSplitContractError("unsupported preparation receipt")
    if prep.get("status") != "PASS_TOP10_RISK_EXCLUSION_DIAGNOSTIC_PREPARED":
        raise CleanedSplitContractError("preparation receipt is not PASS")
    if prep.get("active_counts") != dict(expected_active_counts):
        raise CleanedSplitContractError("active counts differ from frozen authority")
    if prep.get("excluded_counts") != dict(expected_excluded_counts):
        raise CleanedSplitContractError("excluded counts differ from frozen authority")
    if prep.get("retained_counts") != dict(expected_retained_counts):
        raise CleanedSplitContractError("retained counts differ from frozen authority")
    _verified_hashes(prep["input_paths"], prep["input_sha256"], kind="input")
    _verified_hashes(prep["output_paths"], prep["output_sha256"], kind="output")

    lineage_paths = {
        "luna_primary_merge_audit": Path(luna_merge_audit).resolve(),
        "sol_train_authority_receipt": Path(sol_train_receipt).resolve(),
        "sol_protected_authority_receipt": Path(sol_protected_receipt).resolve(),
        "top10_preparation_receipt": preparation_receipt,
    }
    for key, path in lineage_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"lineage file missing: {key}={path}")

    exclusion_rows, exclusion_id_split = _load_exclusions(
        Path(prep["output_paths"]["exclusion_jsonl"]),
        expected_counts=expected_excluded_counts,
        expected_bands=expected_band_counts,
    )
    input_profiles = {
        "train_dev": _profile_jsonl(
            Path(prep["input_paths"]["train_dev_manifest"]),
            allowed_splits={"train", "dev"},
        ),
        "internal_test": _profile_jsonl(
            Path(prep["input_paths"]["internal_test_manifest"]),
            allowed_splits={"internal_test"},
        ),
        "gold": _profile_jsonl(
            Path(prep["input_paths"]["gold_manifest"]),
            allowed_splits={"gold"},
            implicit_split="gold",
        ),
    }
    retained_profiles = {
        "train_dev": _profile_jsonl(
            Path(prep["output_paths"]["train_dev"]),
            allowed_splits={"train", "dev"},
        ),
        "internal_test": _profile_jsonl(
            Path(prep["output_paths"]["internal_test"]),
            allowed_splits={"internal_test"},
        ),
        "gold": _profile_jsonl(
            Path(prep["output_paths"]["gold"]),
            allowed_splits={"gold"},
            implicit_split="gold",
        ),
    }

    original_ids: set[str] = set()
    retained_ids: set[str] = set()
    original_id_split: dict[str, str] = {}
    retained_id_split: dict[str, str] = {}
    all_patients: dict[str, set[str]] = {
        split: set() for split in expected_retained_counts
    }
    for key in input_profiles:
        current = input_profiles[key]
        retained = retained_profiles[key]
        if original_ids & current["ids"]:
            raise CleanedSplitContractError("sample IDs overlap across source files")
        if retained_ids & retained["ids"]:
            raise CleanedSplitContractError("sample IDs overlap across retained files")
        original_ids.update(current["ids"])
        retained_ids.update(retained["ids"])
        original_id_split.update(current["id_split"])
        retained_id_split.update(retained["id_split"])
        for split, values in retained["patients"].items():
            all_patients[split].update(values)
        for sample_id, line_hash in retained["line_hashes"].items():
            if current["line_hashes"].get(sample_id) != line_hash:
                raise CleanedSplitContractError(
                    f"retained source row was rewritten: {sample_id}"
                )

    excluded_ids = set(exclusion_id_split)
    _assert_exact_complement(
        original_ids=original_ids,
        retained_ids=retained_ids,
        excluded_ids=excluded_ids,
    )
    if any(
        original_id_split.get(sample_id) != split
        for sample_id, split in exclusion_id_split.items()
    ):
        raise CleanedSplitContractError("exclusion split differs from source split")
    if any(
        retained_id_split.get(sample_id) != original_id_split.get(sample_id)
        for sample_id in retained_ids
    ):
        raise CleanedSplitContractError("retained sample changed split")
    retained_split_counts = Counter(retained_id_split.values())
    if dict(retained_split_counts) != dict(expected_retained_counts):
        raise CleanedSplitContractError(
            f"retained split counts differ: {dict(retained_split_counts)}"
        )
    patient_overlaps = _assert_pairwise_patient_disjoint(all_patients)

    physician_rows = []
    for row in exclusion_rows:
        value = dict(row)
        value.update(
            {
                "review_status": PHYSICIAN_REVIEW_STATUS,
                "physician_review_scope": "ALL_11667_ROWS_REVIEWED",
                "physician_decision": PHYSICIAN_DECISION,
                "cleaned_split_action": FUTURE_ACTION,
                "automated_signal_role": "SUPPORTING_DISCOVERY_PROVENANCE_ONLY",
            }
        )
        physician_rows.append(value)

    staging = output_root.with_name(f".{output_root.name}.tmp.{os.getpid()}")
    if staging.exists():
        raise FileExistsError(f"refusing existing staging root: {staging}")
    try:
        (staging / "manifests").mkdir(parents=True)
        (staging / "quarantine").mkdir()
        final_paths = {
            "train_dev": output_root / "manifests" / "train_dev_cleaned_v1.jsonl",
            "internal_test": (
                output_root / "manifests" / "internal_test_cleaned_v1.jsonl"
            ),
            "gold": output_root / "manifests" / "gold_cleaned_v1.jsonl",
            "physician_exclusions_jsonl": (
                output_root
                / "quarantine"
                / "physician_confirmed_exclusions_v1.jsonl"
            ),
            "physician_exclusions_csv": (
                output_root
                / "quarantine"
                / "physician_confirmed_exclusions_v1.csv"
            ),
            "quarantine_readme": output_root / "quarantine" / "README_CN.md",
            "data_quality_audit": output_root / "data_quality_audit.json",
            "aggregate_summary": output_root / "aggregate_summary.json",
        }
        staging_paths = {
            key: staging / path.relative_to(output_root)
            for key, path in final_paths.items()
        }
        for key in ("train_dev", "internal_test", "gold"):
            shutil.copyfile(
                Path(prep["output_paths"][key]), staging_paths[key]
            )
        write_jsonl_atomic(
            staging_paths["physician_exclusions_jsonl"], physician_rows
        )
        _write_private_csv(staging_paths["physician_exclusions_csv"], physician_rows)
        staging_paths["quarantine_readme"].write_text(
            "# PRTA-CXR 医生确认排除病例隔离区\n\n"
            "本目录包含 11,667 条经医生全部复核后确认不应使用的病例。\n\n"
            "- 状态：`PHYSICIAN_CONFIRMED_EXCLUDE`\n"
            "- 决策：`DO_NOT_USE`\n"
            "- 禁止用途：训练、Dev、Internal-test、Gold 及任何后续模型实验\n"
            "- Luna、Sol、历史误判、NLL 与近似 TracIn 仅用于候选发现，"
            "医生确认是最终排除依据。\n"
            "- 原始影像不移动、不删除；后续程序仅允许读取冻结后的清洗清单。\n"
            "- 本目录仅用于私有审计和追溯，禁止提交公开 Git。\n",
            encoding="utf-8",
        )

        aggregate = {
            "schema": "prta-cxr.cleaned-split-aggregate.v1",
            "dataset_version": DATASET_VERSION,
            "active_counts_before_physician_exclusion": dict(expected_active_counts),
            "physician_confirmed_exclusion_counts": dict(expected_excluded_counts),
            "retained_counts": dict(expected_retained_counts),
            "retained_total": sum(expected_retained_counts.values()),
            "physician_confirmed_exclusion_total": sum(
                expected_excluded_counts.values()
            ),
            "risk_band_counts": dict(expected_band_counts),
            "retained_label_counts": {
                split: next(
                    profile["label_counts"][split]
                    for profile in retained_profiles.values()
                    if split in profile["label_counts"]
                )
                for split in expected_retained_counts
            },
            "retained_source_counts": {
                split: next(
                    profile["source_counts"][split]
                    for profile in retained_profiles.values()
                    if split in profile["source_counts"]
                )
                for split in expected_retained_counts
            },
            "retained_finding_counts": {
                split: next(
                    profile["finding_counts"][split]
                    for profile in retained_profiles.values()
                    if split in profile["finding_counts"]
                )
                for split in expected_retained_counts
            },
            "outcome_adaptive_selection_bias": True,
        }
        audit = {
            "schema": "prta-cxr.cleaned-split-data-quality-audit.v1",
            "status": "PASS_CLEANED_SPLIT_DATA_QUALITY_AUDIT",
            "exact_source_complement": True,
            "retained_rows_byte_identical_to_source": True,
            "sample_id_unique_across_four_splits": True,
            "patient_overlap_counts": patient_overlaps,
            "all_patient_overlap_counts_zero": True,
            "all_five_labels_present_in_each_split": all(
                set(aggregate["retained_label_counts"][split])
                == set(PROGRESSION_LABELS)
                for split in expected_retained_counts
            ),
            "original_artifacts_mutated": False,
            "training_started": False,
        }
        if not audit["all_five_labels_present_in_each_split"]:
            raise CleanedSplitContractError("a cleaned split lost label support")
        write_json_atomic(staging_paths["aggregate_summary"], aggregate)
        write_json_atomic(staging_paths["data_quality_audit"], audit)

        output_sha256 = {
            key: sha256_file(staging_paths[key]) for key in staging_paths
        }
        lineage_sha256 = {
            key: sha256_file(path) for key, path in lineage_paths.items()
        }
        receipt = {
            "schema": FREEZE_SCHEMA,
            "status": FREEZE_STATUS,
            "dataset_version": DATASET_VERSION,
            "frozen_at": datetime.now(UTC).isoformat(),
            "physician_review_status": PHYSICIAN_REVIEW_STATUS,
            "physician_review_scope": "ALL_11667_ROWS_REVIEWED",
            "physician_decision": PHYSICIAN_DECISION,
            "physician_confirmed_exclusions": sum(expected_excluded_counts.values()),
            "automated_signal_role": "SUPPORTING_DISCOVERY_PROVENANCE_ONLY",
            "active_counts_before_physician_exclusion": dict(expected_active_counts),
            "excluded_counts": dict(expected_excluded_counts),
            "retained_counts": dict(expected_retained_counts),
            "retained_total": sum(expected_retained_counts.values()),
            "output_paths": {
                key: str(path) for key, path in final_paths.items()
            },
            "output_sha256": output_sha256,
            "lineage_paths": {key: str(path) for key, path in lineage_paths.items()},
            "lineage_sha256": lineage_sha256,
            "source_input_paths": dict(prep["input_paths"]),
            "source_input_sha256": dict(prep["input_sha256"]),
            "source_retained_paths": dict(prep["output_paths"]),
            "source_retained_sha256": dict(prep["output_sha256"]),
            "future_use_contract": {
                "train_dev": "ONLY_FROZEN_CLEANED_MANIFEST",
                "internal_test": "ONLY_FROZEN_CLEANED_MANIFEST",
                "gold": "ONLY_FROZEN_CLEANED_MANIFEST",
                "excluded_rows_allowed": False,
                "original_manifests": "AUDIT_ONLY_NOT_FOR_FUTURE_EXPERIMENTS",
            },
            "outcome_adaptive_selection_bias": True,
            "unbiased_original_distribution_claim_allowed": False,
            "historical_formal_gate_replaced": False,
            "original_artifacts_mutated": False,
            "training_started": False,
        }
        receipt_path = staging / "cleaned_split_freeze_receipt.json"
        write_json_atomic(receipt_path, receipt)
        staging.replace(output_root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    final_receipt = output_root / "cleaned_split_freeze_receipt.json"
    pointer = {
        "schema": "prta-cxr.active-cleaned-split-pointer.v1",
        "status": "ACTIVE_CLEANED_SPLIT_FROZEN",
        "dataset_version": DATASET_VERSION,
        "freeze_receipt": str(final_receipt),
        "freeze_receipt_sha256": sha256_file(final_receipt),
        "physician_confirmed_exclusions": sum(expected_excluded_counts.values()),
        "retained_counts": dict(expected_retained_counts),
        "future_experiments_must_use_cleaned_split": True,
    }
    if replace_active_pointer:
        replace_json_atomic(active_pointer, pointer)
    else:
        write_json_atomic(active_pointer, pointer)
    return validate_cleaned_split_freeze(final_receipt)


def _validate_cleaned_split_freeze_metadata(
    receipt_path: Path,
) -> dict[str, Any]:
    receipt_path = Path(receipt_path).resolve()
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    if value.get("schema") != FREEZE_SCHEMA or value.get("status") != FREEZE_STATUS:
        raise CleanedSplitContractError("cleaned split is not formally frozen")
    if value.get("physician_review_status") != PHYSICIAN_REVIEW_STATUS:
        raise CleanedSplitContractError("physician exclusion authority is absent")
    if value.get("physician_decision") != PHYSICIAN_DECISION:
        raise CleanedSplitContractError("physician exclusion decision differs")
    if value.get("physician_confirmed_exclusions") != sum(EXCLUDED_COUNTS.values()):
        raise CleanedSplitContractError("physician exclusion total differs")
    if value.get("retained_counts") != RETAINED_COUNTS:
        raise CleanedSplitContractError("cleaned retained counts differ")
    value["receipt_path"] = str(receipt_path)
    value["receipt_sha256"] = sha256_file(receipt_path)
    return value


def validate_cleaned_split_freeze(receipt_path: Path) -> dict[str, Any]:
    value = _validate_cleaned_split_freeze_metadata(receipt_path)
    _verified_hashes(value["output_paths"], value["output_sha256"], kind="cleaned")
    _verified_hashes(value["lineage_paths"], value["lineage_sha256"], kind="lineage")
    return value


def require_cleaned_manifest(
    manifest_path: Path,
    *,
    receipt_path: Path,
    role: str,
    portable_root: Path | None = None,
) -> dict[str, Any]:
    if role not in {"train_dev", "internal_test", "gold"}:
        raise CleanedSplitContractError(f"unsupported cleaned split role: {role}")
    receipt = _validate_cleaned_split_freeze_metadata(receipt_path)
    actual = Path(manifest_path).resolve()
    if portable_root is None:
        expected = Path(receipt["output_paths"][role]).resolve()
    else:
        output_paths = receipt["output_paths"]
        frozen_root = PureWindowsPath(output_paths["aggregate_summary"]).parent
        frozen_role = PureWindowsPath(output_paths[role])
        try:
            relative = frozen_role.relative_to(frozen_root)
        except ValueError as exc:
            raise CleanedSplitContractError(
                f"formal {role} path is outside the frozen output root"
            ) from exc
        expected = (Path(portable_root).resolve() / Path(*relative.parts)).resolve()
    if actual != expected:
        raise CleanedSplitContractError(
            f"formal {role} must use active frozen path: {expected}"
        )
    if sha256_file(actual) != receipt["output_sha256"][role]:
        raise CleanedSplitContractError(f"formal {role} cleaned hash changed")
    return receipt


def freeze_cleaned_split_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the physician-confirmed PRTA-CXR cleaned split"
    )
    parser.add_argument("--preparation-receipt", type=Path, required=True)
    parser.add_argument("--luna-merge-audit", type=Path, required=True)
    parser.add_argument("--sol-train-receipt", type=Path, required=True)
    parser.add_argument("--sol-protected-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--active-pointer", type=Path, required=True)
    parser.add_argument("--confirm-all-physician-reviewed", action="store_true")
    parser.add_argument("--confirm-selection-bias", action="store_true")
    parser.add_argument("--replace-active-pointer", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_all_physician_reviewed:
        raise CleanedSplitContractError(
            "explicit --confirm-all-physician-reviewed is required"
        )
    if not args.confirm_selection_bias:
        raise CleanedSplitContractError(
            "explicit --confirm-selection-bias is required"
        )
    result = freeze_cleaned_split(
        preparation_receipt=args.preparation_receipt,
        luna_merge_audit=args.luna_merge_audit,
        sol_train_receipt=args.sol_train_receipt,
        sol_protected_receipt=args.sol_protected_receipt,
        output_root=args.output_root,
        active_pointer=args.active_pointer,
        replace_active_pointer=args.replace_active_pointer,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0
