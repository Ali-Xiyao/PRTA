from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.contracts import PROGRESSION_LABELS, SAMPLE_FIELDS, sha256_file

MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"
NEW_LABEL_SOURCE = "gpt-5.6-sol_blind_authoritative_all_risk_2026-08-04"
EXPECTED_SOURCE_TRAIN = 90_771
EXPECTED_NEW_REVIEW = 5_968
EXPECTED_PILOT_ONLY = 13
EXPECTED_TARGETS = 5_981
EXPECTED_DECISIVE = 4_616
EXPECTED_UNCLEAR = 1_365
EXPECTED_CHANGED = 1_093
EXPECTED_SAME = 3_523
EXPECTED_REVIEW_BASELINE_MISMATCH = 2
EXPECTED_OUTPUT_TRAIN = 89_406
EXPECTED_DEV = 13_420
EXPECTED_TRAIN_DEV = 102_826
EXPECTED_INTERNAL_TEST = 13_588
EXPECTED_GOLD = 250


def _private(path: Path) -> None:
    value = str(path.resolve()).lower().replace("/", "\\")
    if "\\prta-cxr\\" in value and "\\poststop_audits\\" not in value:
        raise RuntimeError("row-level replacement outputs must stay outside Git")


def _stream_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError(f"non-object JSONL row at {path}:{line_number}")
            yield value


def _count_jsonl(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(bool(line.strip()) for line in handle)


def _temporary(path: Path) -> Path:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.with_name(f".{path.name}.tmp.{os.getpid()}")


def _validate_train_row(row: Mapping[str, Any]) -> None:
    if row.get("split") != "train":
        raise RuntimeError("active Train manifest contains a non-Train row")
    missing = set(SAMPLE_FIELDS) - set(row)
    if missing:
        raise RuntimeError(f"Train row is missing sample fields: {sorted(missing)}")
    if row.get("progression_label") not in PROGRESSION_LABELS:
        raise RuntimeError("Train row has an invalid progression label")


def build_all_risk_targets(
    *,
    new_review_rows: Iterable[Mapping[str, Any]],
    pilot_rows: Iterable[Mapping[str, Any]],
    case_detail_rows: Iterable[Mapping[str, Any]],
    expected_new: int = EXPECTED_NEW_REVIEW,
    expected_pilot_only: int = EXPECTED_PILOT_ONLY,
) -> dict[str, dict[str, Any]]:
    new: dict[str, dict[str, Any]] = {}
    for row in new_review_rows:
        sample_id = str(row.get("sample_id", ""))
        if not sample_id or sample_id in new:
            raise RuntimeError("new Tier-B/C review contains an empty/duplicate ID")
        if row.get("split", "train") != "train" or row.get("risk_tier") not in {
            "Tier B",
            "Tier C",
        }:
            raise RuntimeError("new review target is outside Train Tier-B/C")
        sol_label = row.get("sol_label")
        if sol_label not in {*PROGRESSION_LABELS, "Unclear"}:
            raise RuntimeError("new review contains an invalid Sol label")
        new[sample_id] = {
            "sample_id": sample_id,
            "risk_tier": row["risk_tier"],
            "current_label": row.get("current_label"),
            "sol_label": sol_label,
            "quality_flags": list(row.get("quality_flags", [])),
            "review_source": "tier_bc_full_blind_review",
        }
    if len(new) != expected_new:
        raise RuntimeError("new Tier-B/C review count changed")

    pilot_by_id: dict[str, Mapping[str, Any]] = {}
    for row in pilot_rows:
        sample_id = str(row.get("sample_id", ""))
        if not sample_id or sample_id in pilot_by_id:
            raise RuntimeError("pilot review contains an empty/duplicate ID")
        pilot_by_id[sample_id] = row

    pilot_targets: dict[str, dict[str, Any]] = {}
    detail_hits: set[str] = set()
    for row in case_detail_rows:
        sample_id = str(row.get("sample_id", ""))
        if sample_id not in pilot_by_id:
            continue
        if sample_id in detail_hits:
            raise RuntimeError("case details contain a duplicate pilot ID")
        detail_hits.add(sample_id)
        if (
            row.get("split") != "train"
            or row.get("risk_tier") not in {"Tier B", "Tier C"}
            or sample_id in new
        ):
            continue
        pilot = pilot_by_id[sample_id]
        sol_label = pilot.get("sol_label")
        if sol_label not in {*PROGRESSION_LABELS, "Unclear"}:
            raise RuntimeError("pilot review contains an invalid Sol label")
        pilot_targets[sample_id] = {
            "sample_id": sample_id,
            "risk_tier": row["risk_tier"],
            "current_label": pilot.get("luna_label"),
            "sol_label": sol_label,
            "quality_flags": [],
            "review_source": "pilot_blind_review_previously_non_authoritative",
        }
    if len(pilot_targets) != expected_pilot_only:
        raise RuntimeError("pilot-only Train Tier-B/C target count changed")
    if set(new) & set(pilot_targets):
        raise RuntimeError("new and pilot-only target sets overlap")
    return new | pilot_targets


def apply_all_risk_train_stream(
    *,
    source_train: Path,
    targets: Mapping[str, Mapping[str, Any]],
    train_output: Path,
    expected_source_rows: int = EXPECTED_SOURCE_TRAIN,
    expected_targets: int = EXPECTED_TARGETS,
    expected_decisive: int = EXPECTED_DECISIVE,
    expected_unclear: int = EXPECTED_UNCLEAR,
    expected_changed: int = EXPECTED_CHANGED,
    expected_same: int = EXPECTED_SAME,
    expected_review_baseline_mismatch: int = EXPECTED_REVIEW_BASELINE_MISMATCH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if len(targets) != expected_targets:
        raise RuntimeError("combined replacement target count changed")
    temporary = _temporary(train_output)
    seen: set[str] = set()
    seen_targets: set[str] = set()
    provenance: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    source_rows = 0
    output_rows = 0
    changed = 0
    same = 0
    review_baseline_mismatch = 0
    unchanged_bytes = hashlib.sha256()
    try:
        with source_train.open("rb") as source, temporary.open("wb") as output:
            for raw_line in source:
                if not raw_line.strip():
                    continue
                source_rows += 1
                row = json.loads(raw_line)
                _validate_train_row(row)
                sample_id = str(row["sample_id"])
                if sample_id in seen:
                    raise RuntimeError("active Train contains a duplicate sample ID")
                seen.add(sample_id)
                target = targets.get(sample_id)
                if target is None:
                    output.write(raw_line)
                    unchanged_bytes.update(raw_line)
                    output_rows += 1
                    continue
                seen_targets.add(sample_id)
                if target["current_label"] != row["progression_label"]:
                    if target["review_source"] != (
                        "pilot_blind_review_previously_non_authoritative"
                    ):
                        raise RuntimeError(
                            "frozen full-review label differs from active Train"
                        )
                    review_baseline_mismatch += 1
                base = {
                    "sample_id": sample_id,
                    "source": row["source"],
                    "finding": row["finding"],
                    "risk_tier": target["risk_tier"],
                    "luna_label": row["progression_label"],
                    "review_current_label": target["current_label"],
                    "sol_label": target["sol_label"],
                    "previous_label_source": row["label_source"],
                    "review_source": target["review_source"],
                }
                if target["sol_label"] == "Unclear":
                    exclusions.append(
                        base
                        | {
                            "quality_flags": target["quality_flags"],
                            "action": "exclude_sol_unclear",
                        }
                    )
                    continue
                updated = dict(row)
                updated["progression_label"] = target["sol_label"]
                updated["label_source"] = NEW_LABEL_SOURCE
                _validate_train_row(updated)
                for key, value in row.items():
                    if key not in {"progression_label", "label_source"}:
                        if updated[key] != value:
                            raise RuntimeError("non-label field changed")
                value_changed = target["sol_label"] != row["progression_label"]
                changed += int(value_changed)
                same += int(not value_changed)
                provenance.append(
                    base
                    | {
                        "label_value_changed": value_changed,
                        "new_label_source": NEW_LABEL_SOURCE,
                        "action": (
                            "replace_label_value"
                            if value_changed
                            else "rebind_same_label_to_sol"
                        ),
                    }
                )
                encoded = (
                    json.dumps(updated, sort_keys=True, ensure_ascii=False) + "\n"
                ).encode("utf-8")
                output.write(
                    encoded
                )
                output_rows += 1
        if source_rows != expected_source_rows or len(seen) != expected_source_rows:
            raise RuntimeError("active Train count/uniqueness changed")
        if seen_targets != set(targets):
            raise RuntimeError("not every replacement target was found in Train")
        if (len(provenance), len(exclusions), changed, same) != (
            expected_decisive,
            expected_unclear,
            expected_changed,
            expected_same,
        ):
            raise RuntimeError("replacement action counts changed")
        if review_baseline_mismatch != expected_review_baseline_mismatch:
            raise RuntimeError("pilot review/current Train mismatch count changed")
        if output_rows != expected_source_rows - expected_unclear:
            raise RuntimeError("new Train row count mismatch")
        temporary.replace(train_output)
    finally:
        if temporary.exists():
            temporary.unlink()
    audit = {
        "source_train_rows": source_rows,
        "target_rows": len(targets),
        "sol_authoritative_rows": len(provenance),
        "excluded_sol_unclear_rows": len(exclusions),
        "label_value_changed_rows": changed,
        "authority_rebound_same_label_rows": same,
        "review_current_label_mismatch_rows": review_baseline_mismatch,
        "non_target_rows_copied_byte_exact": source_rows - len(targets),
        "non_target_raw_sha256": unchanged_bytes.hexdigest(),
        "train_output_rows": output_rows,
        "new_label_distribution": dict(
            sorted(Counter(row["sol_label"] for row in provenance).items())
        ),
    }
    return provenance, exclusions, audit


def _copy_exact(source: Path, target: Path) -> None:
    temporary = _temporary(target)
    try:
        with source.open("rb") as read_handle, temporary.open("wb") as write_handle:
            shutil.copyfileobj(read_handle, write_handle, length=1024 * 1024)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _combine(train: Path, dev: Path, output: Path) -> None:
    temporary = _temporary(output)
    try:
        with temporary.open("wb") as target:
            for source_path in (train, dev):
                with source_path.open("rb") as source:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def materialize_all_risk_sol_replacement_main(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Create the all-risk Sol-authoritative active label version"
    )
    parser.add_argument("--source-sol-train", type=Path, required=True)
    parser.add_argument("--source-sol-dev", type=Path, required=True)
    parser.add_argument("--source-sol-internal-test", type=Path, required=True)
    parser.add_argument("--source-active-pointer", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--tier-bc-review", type=Path, required=True)
    parser.add_argument("--tier-bc-audit", type=Path, required=True)
    parser.add_argument("--pilot-results", type=Path, required=True)
    parser.add_argument("--case-details", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume-preopen", action="store_true")
    args = parser.parse_args(argv)
    _private(args.output_root)
    if args.output_root.exists():
        children = {path.name for path in args.output_root.iterdir()}
        private_path = args.output_root / "private"
        resumable_children = children in (
            {"preopen_receipt.json"},
            {"preopen_receipt.json", "private"},
        )
        private_is_empty = not private_path.exists() or not any(private_path.iterdir())
        if not args.resume_preopen or not resumable_children or not private_is_empty:
            raise FileExistsError(f"refusing existing output root: {args.output_root}")
    else:
        args.output_root.mkdir(parents=True)

    input_paths = {
        "source_sol_train": args.source_sol_train,
        "source_sol_dev": args.source_sol_dev,
        "source_sol_internal_test": args.source_sol_internal_test,
        "source_active_pointer": args.source_active_pointer,
        "gold_physician_consensus": args.gold,
        "tier_bc_review": args.tier_bc_review,
        "tier_bc_independent_audit": args.tier_bc_audit,
        "pilot_results": args.pilot_results,
        "tracin_case_details": args.case_details,
    }
    inputs_before = {name: sha256_file(path) for name, path in input_paths.items()}
    preopen_path = args.output_root / "preopen_receipt.json"
    preopen = {
            "schema": "prta-cxr.all-risk-sol-replacement-preopen.v1",
            "status": "AUTHORIZED_ALL_RISK_SOL_REPLACEMENT_NOT_MATERIALIZED",
            "decision_authority": "explicit_user_request_2026-08-04",
            "replacement_scope": "train_tier_b_and_c",
            "unclear_policy": "exclude_not_coerce",
            "dev_internal_gold_policy": "copy_byte_exact_unchanged",
            "input_hashes": inputs_before,
            "training_authorized": False,
            "metric_computation_authorized": False,
        }
    if preopen_path.exists():
        existing_preopen = json.loads(preopen_path.read_text(encoding="utf-8"))
        if existing_preopen != preopen:
            raise RuntimeError("resume preopen receipt differs from current inputs")
    else:
        write_json_atomic(preopen_path, preopen)
    targets = build_all_risk_targets(
        new_review_rows=_stream_jsonl(args.tier_bc_review),
        pilot_rows=_stream_jsonl(args.pilot_results),
        case_detail_rows=_stream_jsonl(args.case_details),
    )
    private = args.output_root / "private"
    train_path = private / "train_sol_authoritative_all_risk_v1.jsonl"
    dev_path = private / "dev_sol_authoritative_v1.jsonl"
    internal_path = private / "internal_test_sol_authoritative_v1.jsonl"
    combined_path = private / "train_dev_sol_authoritative_all_risk_v1.jsonl"
    provenance_path = private / "sol_all_risk_authority_provenance.jsonl"
    exclusions_path = private / "sol_all_risk_unclear_exclusions.jsonl"
    provenance, exclusions, audit = apply_all_risk_train_stream(
        source_train=args.source_sol_train,
        targets=targets,
        train_output=train_path,
    )
    _copy_exact(args.source_sol_dev, dev_path)
    _copy_exact(args.source_sol_internal_test, internal_path)
    _combine(train_path, dev_path, combined_path)
    write_jsonl_atomic(provenance_path, provenance)
    write_jsonl_atomic(exclusions_path, exclusions)

    inputs_after = {name: sha256_file(path) for name, path in input_paths.items()}
    if inputs_after != inputs_before:
        raise RuntimeError("an input changed during all-risk replacement")
    counts = {
        "train": _count_jsonl(train_path),
        "dev": _count_jsonl(dev_path),
        "train_dev": _count_jsonl(combined_path),
        "internal_test": _count_jsonl(internal_path),
        "gold_physician_consensus": _count_jsonl(args.gold),
    }
    expected_counts = {
        "train": EXPECTED_OUTPUT_TRAIN,
        "dev": EXPECTED_DEV,
        "train_dev": EXPECTED_TRAIN_DEV,
        "internal_test": EXPECTED_INTERNAL_TEST,
        "gold_physician_consensus": EXPECTED_GOLD,
    }
    if counts != expected_counts:
        raise RuntimeError("all-risk active row counts changed")
    if sha256_file(dev_path) != inputs_before["source_sol_dev"]:
        raise RuntimeError("Dev bytes changed")
    if sha256_file(internal_path) != inputs_before["source_sol_internal_test"]:
        raise RuntimeError("Internal-test bytes changed")
    output_hashes = {
        "train": sha256_file(train_path),
        "dev": sha256_file(dev_path),
        "train_dev": sha256_file(combined_path),
        "internal_test": sha256_file(internal_path),
        "provenance": sha256_file(provenance_path),
        "exclusions": sha256_file(exclusions_path),
    }
    receipt = {
        "schema": "prta-cxr.all-risk-sol-replacement-receipt.v1",
        "status": "PASS_SOL_AUTHORITATIVE_ALL_RISK_VERSION",
        "decision_authority": "explicit_user_request_2026-08-04",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "input_hashes": inputs_before,
        "audit": audit,
        "row_counts": counts,
        "output_hashes": output_hashes,
        "old_artifacts_mutated": False,
        "dev_labels_modified": 0,
        "internal_test_labels_modified": 0,
        "gold_physician_labels_modified": 0,
        "training_started": False,
        "model_metrics_computed": False,
    }
    write_json_atomic(args.output_root / "receipt.json", receipt)
    active = {
        "schema": "prta-cxr.active-label-version.v1",
        "status": "ACTIVE_SOL_AUTHORITATIVE_ALL_RISK_NOT_TRAINED",
        "activated_at": "2026-08-04",
        "train_manifest": str(train_path),
        "train_dev_manifest": str(combined_path),
        "dev_manifest": str(dev_path),
        "sealed_internal_test_manifest": str(internal_path),
        "gold_manifest": str(args.gold),
        "artifact_sha256": output_hashes
        | {"gold_physician_consensus": inputs_before["gold_physician_consensus"]},
        "unclear_policy": "excluded",
        "training_started": False,
    }
    write_json_atomic(args.output_root / "active_label_version.json", active)
    print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _load_targets_from_args(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    return build_all_risk_targets(
        new_review_rows=_stream_jsonl(args.tier_bc_review),
        pilot_rows=_stream_jsonl(args.pilot_results),
        case_detail_rows=_stream_jsonl(args.case_details),
    )


def audit_all_risk_sol_replacement_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently audit the all-risk Sol active label version"
    )
    parser.add_argument("--source-sol-train", type=Path, required=True)
    parser.add_argument("--source-sol-dev", type=Path, required=True)
    parser.add_argument("--source-sol-internal-test", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--tier-bc-review", type=Path, required=True)
    parser.add_argument("--pilot-results", type=Path, required=True)
    parser.add_argument("--case-details", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    _private(args.output_root)
    receipt = json.loads((args.output_root / "receipt.json").read_text("utf-8"))
    targets = _load_targets_from_args(args)
    source_by_id = {
        row["sample_id"]: row for row in _stream_jsonl(args.source_sol_train)
    }
    output_path = (
        args.output_root / "private" / "train_sol_authoritative_all_risk_v1.jsonl"
    )
    output_by_id = {row["sample_id"]: row for row in _stream_jsonl(output_path)}
    unclear_ids = {
        sample_id for sample_id, row in targets.items() if row["sol_label"] == "Unclear"
    }
    if set(output_by_id) != set(source_by_id) - unclear_ids:
        raise RuntimeError("new Train IDs differ from source minus Sol Unclear")
    changed = 0
    same = 0
    review_baseline_mismatch = 0
    for sample_id, output in output_by_id.items():
        source = source_by_id[sample_id]
        target = targets.get(sample_id)
        for field, value in source.items():
            if field not in {"progression_label", "label_source"}:
                if output[field] != value:
                    raise RuntimeError("independent audit found non-label drift")
        if target is None:
            if output != source:
                raise RuntimeError("non-target Train row changed")
            continue
        if target["current_label"] != source["progression_label"]:
            review_baseline_mismatch += 1
        if output["progression_label"] != target["sol_label"]:
            raise RuntimeError("target output label differs from Sol")
        if output["label_source"] != NEW_LABEL_SOURCE:
            raise RuntimeError("target output label source is not Sol")
        value_changed = output["progression_label"] != source["progression_label"]
        changed += int(value_changed)
        same += int(not value_changed)
    if (changed, same, len(unclear_ids)) != (
        EXPECTED_CHANGED,
        EXPECTED_SAME,
        EXPECTED_UNCLEAR,
    ):
        raise RuntimeError("independent audit action counts changed")
    if review_baseline_mismatch != EXPECTED_REVIEW_BASELINE_MISMATCH:
        raise RuntimeError("independent audit found pilot baseline mismatch drift")

    private = args.output_root / "private"
    actual_hashes = {
        "train": sha256_file(output_path),
        "dev": sha256_file(private / "dev_sol_authoritative_v1.jsonl"),
        "train_dev": sha256_file(
            private / "train_dev_sol_authoritative_all_risk_v1.jsonl"
        ),
        "internal_test": sha256_file(
            private / "internal_test_sol_authoritative_v1.jsonl"
        ),
        "provenance": sha256_file(
            private / "sol_all_risk_authority_provenance.jsonl"
        ),
        "exclusions": sha256_file(
            private / "sol_all_risk_unclear_exclusions.jsonl"
        ),
    }
    if actual_hashes != receipt["output_hashes"]:
        raise RuntimeError("replacement outputs differ from receipt")
    if actual_hashes["dev"] != sha256_file(args.source_sol_dev):
        raise RuntimeError("independent audit found Dev drift")
    if actual_hashes["internal_test"] != sha256_file(args.source_sol_internal_test):
        raise RuntimeError("independent audit found Internal-test drift")
    if sha256_file(args.gold) != receipt["input_hashes"]["gold_physician_consensus"]:
        raise RuntimeError("independent audit found physician Gold drift")

    train_digest = hashlib.sha256()
    combined_dev = []
    combined_path = private / "train_dev_sol_authoritative_all_risk_v1.jsonl"
    with combined_path.open("rb") as handle:
        for index, raw_line in enumerate(handle):
            if index < EXPECTED_OUTPUT_TRAIN:
                train_digest.update(raw_line)
            else:
                combined_dev.append(raw_line)
    if train_digest.hexdigest() != actual_hashes["train"]:
        raise RuntimeError("combined Train bytes differ from standalone Train")
    with (private / "dev_sol_authoritative_v1.jsonl").open("rb") as handle:
        if combined_dev != list(handle):
            raise RuntimeError("combined Dev bytes differ from standalone Dev")
    audit = {
        "schema": "prta-cxr.all-risk-sol-replacement-independent-audit.v1",
        "status": "PASS_ALL_RISK_SOL_REPLACEMENT_INDEPENDENT_AUDIT",
        "target_rows": len(targets),
        "decisive_rows": changed + same,
        "excluded_sol_unclear_rows": len(unclear_ids),
        "label_value_changed_rows": changed,
        "authority_rebound_same_label_rows": same,
        "review_current_label_mismatch_rows": review_baseline_mismatch,
        "train_rows": len(output_by_id),
        "dev_bytes_equal_previous_active": True,
        "internal_test_bytes_equal_previous_active": True,
        "gold_physician_labels_modified": 0,
        "verified_output_hashes": actual_hashes,
        "training_started": False,
        "model_metrics_computed": False,
    }
    write_json_atomic(args.output_root / "independent_audit.json", audit)
    print(json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False))
    return 0
