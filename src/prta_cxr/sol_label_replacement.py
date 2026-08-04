from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.contracts import (
    PROGRESSION_LABELS,
    SAMPLE_FIELDS,
    sha256_file,
    validate_sample,
)

MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"
OLD_LABEL_SOURCE = "luna_primary_report_label"
NEW_LABEL_SOURCE = "gpt-5.6-sol_blind_authoritative_2026-08-04"
EXPECTED_SOURCE_ROWS = {"dev": 16666, "internal_test": 16699, "gold": 250}
EXPECTED_RETAINED_ROWS = {"dev": 13420, "internal_test": 13588}
EXPECTED_UNCLEAR_ROWS = {"dev": 3246, "internal_test": 3111}
EXPECTED_CHANGED_ROWS = {"dev": 1347, "internal_test": 1433}
EXPECTED_SAME_ROWS = {"dev": 12073, "internal_test": 12155}
EXPECTED_TRAIN_ROWS = 90771


def _private(path: Path) -> None:
    value = str(path.resolve()).lower().replace("/", "\\")
    if "\\prta-cxr\\" in value and "\\poststop_audits\\" not in value:
        raise RuntimeError("row-level replacement outputs must stay outside Git")


def _stream_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError(f"non-object JSONL row at line {line_number}")
            yield value


def _validate_split_sample(row: dict[str, Any], expected_split: str) -> None:
    expected_fields = set(SAMPLE_FIELDS) | {"split"}
    if set(row) != expected_fields:
        raise RuntimeError("source split row field mismatch")
    if row["split"] != expected_split:
        raise RuntimeError("source row has the wrong split")
    validate_sample({field: row[field] for field in SAMPLE_FIELDS})


def _load_source_split(path: Path, split: str) -> list[dict[str, Any]]:
    rows = []
    for row in _stream_jsonl(path):
        if row.get("split") != split:
            continue
        _validate_split_sample(row, split)
        rows.append(row)
    identifiers = [row["sample_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError(f"duplicate {split} source sample ID")
    return rows


def _load_review(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {
        "dev": {},
        "internal_test": {},
        "gold": {},
    }
    for row in _stream_jsonl(path):
        cohort = row.get("cohort")
        if cohort not in output:
            raise RuntimeError("review row has an unknown cohort")
        sample_id = row.get("sample_id")
        sol_label = row.get("sol_label")
        if not isinstance(sample_id, str) or not sample_id:
            raise RuntimeError("review row has an empty sample ID")
        if sol_label not in {*PROGRESSION_LABELS, "Unclear"}:
            raise RuntimeError("review row has an invalid Sol label")
        if sample_id in output[cohort]:
            raise RuntimeError("duplicate review sample ID")
        output[cohort][sample_id] = {
            "sample_id": sample_id,
            "current_label": row.get("current_label"),
            "sol_label": sol_label,
            "quality_flags": list(row.get("quality_flags", [])),
        }
    for cohort, expected in EXPECTED_SOURCE_ROWS.items():
        if len(output[cohort]) != expected:
            raise RuntimeError(f"{cohort} review row count mismatch")
    return output


def apply_sol_labels(
    rows: list[dict[str, Any]],
    review_by_id: dict[str, dict[str, Any]],
    *,
    cohort: str,
    expected_rows: int,
    expected_retained: int,
    expected_unclear: int,
    expected_changed: int,
    expected_same: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    source_by_id = {row["sample_id"]: row for row in rows}
    if len(rows) != expected_rows or len(source_by_id) != expected_rows:
        raise RuntimeError(f"{cohort} source count or uniqueness mismatch")
    if set(source_by_id) != set(review_by_id):
        raise RuntimeError(f"{cohort} source/review ID mismatch")
    retained = []
    provenance = []
    exclusions = []
    changed = 0
    same = 0
    for source in rows:
        sample_id = source["sample_id"]
        if source["label_source"] != OLD_LABEL_SOURCE:
            raise RuntimeError(f"{cohort} contains a non-Luna source label")
        review = review_by_id[sample_id]
        if review["current_label"] != source["progression_label"]:
            raise RuntimeError(f"{cohort} review current label differs from source")
        if review["sol_label"] == "Unclear":
            exclusions.append(
                {
                    "sample_id": sample_id,
                    "cohort": cohort,
                    "source": source["source"],
                    "finding": source["finding"],
                    "luna_label": source["progression_label"],
                    "sol_label": "Unclear",
                    "quality_flags": review["quality_flags"],
                    "action": "exclude_sol_unclear",
                }
            )
            continue
        new = dict(source)
        new["progression_label"] = review["sol_label"]
        new["label_source"] = NEW_LABEL_SOURCE
        _validate_split_sample(new, source["split"])
        retained.append(new)
        value_changed = new["progression_label"] != source["progression_label"]
        changed += int(value_changed)
        same += int(not value_changed)
        provenance.append(
            {
                "sample_id": sample_id,
                "cohort": cohort,
                "source": source["source"],
                "finding": source["finding"],
                "luna_label": source["progression_label"],
                "sol_label": review["sol_label"],
                "label_value_changed": value_changed,
                "old_label_source": source["label_source"],
                "new_label_source": NEW_LABEL_SOURCE,
                "action": (
                    "replace_label_value"
                    if value_changed
                    else "rebind_same_label_to_sol"
                ),
            }
        )
    if (
        len(retained),
        len(exclusions),
        changed,
        same,
    ) != (
        expected_retained,
        expected_unclear,
        expected_changed,
        expected_same,
    ):
        raise RuntimeError(f"{cohort} replacement action counts changed")
    audit = {
        "source_rows": len(rows),
        "retained_rows": len(retained),
        "excluded_sol_unclear_rows": len(exclusions),
        "label_value_changed_rows": changed,
        "authority_rebound_same_label_rows": same,
        "old_label_distribution": dict(
            sorted(Counter(row["progression_label"] for row in rows).items())
        ),
        "new_label_distribution": dict(
            sorted(
                Counter(row["progression_label"] for row in retained).items()
            )
        ),
    }
    return retained, provenance, exclusions, audit


def _write_combined(
    path: Path,
    train_path: Path,
    dev_rows: list[dict[str, Any]],
) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("wb") as target:
            with train_path.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            for row in dev_rows:
                target.write(
                    (
                        json.dumps(row, sort_keys=True, ensure_ascii=False)
                        + "\n"
                    ).encode("utf-8")
                )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _count_jsonl(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(bool(line.strip()) for line in handle)


def materialize_sol_label_replacement_main(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Create Sol-authoritative Dev/Internal-test label surfaces"
    )
    parser.add_argument("--source-train-dev", type=Path, required=True)
    parser.add_argument("--source-internal-test", type=Path, required=True)
    parser.add_argument("--source-sol-train", type=Path, required=True)
    parser.add_argument("--review-results", type=Path, required=True)
    parser.add_argument("--review-receipt", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    _private(args.output_root)
    if args.output_root.exists():
        raise FileExistsError(f"refusing existing output root: {args.output_root}")
    args.output_root.mkdir(parents=True)
    inputs_before = {
        "source_train_dev": sha256_file(args.source_train_dev),
        "source_internal_test": sha256_file(args.source_internal_test),
        "source_sol_train": sha256_file(args.source_sol_train),
        "review_results": sha256_file(args.review_results),
        "review_receipt": sha256_file(args.review_receipt),
        "gold_physician_consensus": sha256_file(args.gold),
    }
    preopen = {
        "schema": "prta-cxr.sol-label-replacement-preopen.v1",
        "status": "AUTHORIZED_SOL_REPLACEMENT_NOT_YET_MATERIALIZED",
        "decision_authority": "explicit_user_request_2026-08-04",
        "replacement_scope": ["dev", "internal_test"],
        "unclear_policy": "exclude_not_coerce",
        "gold_policy": "physician_consensus_unchanged",
        "input_hashes": inputs_before,
        "training_authorized": False,
        "metric_computation_authorized": False,
    }
    write_json_atomic(args.output_root / "preopen_receipt.json", preopen)

    review = _load_review(args.review_results)
    dev_source = _load_source_split(args.source_train_dev, "dev")
    internal_source = _load_source_split(
        args.source_internal_test, "internal_test"
    )
    dev, dev_provenance, dev_exclusions, dev_audit = apply_sol_labels(
        dev_source,
        review["dev"],
        cohort="dev",
        expected_rows=EXPECTED_SOURCE_ROWS["dev"],
        expected_retained=EXPECTED_RETAINED_ROWS["dev"],
        expected_unclear=EXPECTED_UNCLEAR_ROWS["dev"],
        expected_changed=EXPECTED_CHANGED_ROWS["dev"],
        expected_same=EXPECTED_SAME_ROWS["dev"],
    )
    internal, int_provenance, int_exclusions, int_audit = apply_sol_labels(
        internal_source,
        review["internal_test"],
        cohort="internal_test",
        expected_rows=EXPECTED_SOURCE_ROWS["internal_test"],
        expected_retained=EXPECTED_RETAINED_ROWS["internal_test"],
        expected_unclear=EXPECTED_UNCLEAR_ROWS["internal_test"],
        expected_changed=EXPECTED_CHANGED_ROWS["internal_test"],
        expected_same=EXPECTED_SAME_ROWS["internal_test"],
    )
    private = args.output_root / "private"
    dev_path = private / "dev_sol_authoritative_v1.jsonl"
    internal_path = private / "internal_test_sol_authoritative_v1.jsonl"
    combined_path = private / "train_dev_sol_authoritative_v2.jsonl"
    provenance_path = private / "sol_authority_provenance.jsonl"
    exclusions_path = private / "sol_unclear_exclusions.jsonl"
    write_jsonl_atomic(dev_path, dev)
    write_jsonl_atomic(internal_path, internal)
    _write_combined(combined_path, args.source_sol_train, dev)
    write_jsonl_atomic(provenance_path, [*dev_provenance, *int_provenance])
    write_jsonl_atomic(exclusions_path, [*dev_exclusions, *int_exclusions])

    inputs_after = {
        "source_train_dev": sha256_file(args.source_train_dev),
        "source_internal_test": sha256_file(args.source_internal_test),
        "source_sol_train": sha256_file(args.source_sol_train),
        "review_results": sha256_file(args.review_results),
        "review_receipt": sha256_file(args.review_receipt),
        "gold_physician_consensus": sha256_file(args.gold),
    }
    if inputs_after != inputs_before:
        raise RuntimeError("an input changed during Sol label replacement")
    if _count_jsonl(args.source_sol_train) != EXPECTED_TRAIN_ROWS:
        raise RuntimeError("Sol-authoritative Train count changed")
    output_hashes = {
        "dev": sha256_file(dev_path),
        "internal_test": sha256_file(internal_path),
        "train_dev": sha256_file(combined_path),
        "provenance": sha256_file(provenance_path),
        "exclusions": sha256_file(exclusions_path),
    }
    receipt = {
        "schema": "prta-cxr.sol-label-replacement-receipt.v1",
        "status": "PASS_SOL_AUTHORITATIVE_DEV_INTERNAL_VERSION",
        "decision_authority": "explicit_user_request_2026-08-04",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "input_hashes": inputs_before,
        "audit": {"dev": dev_audit, "internal_test": int_audit},
        "row_counts": {
            "train": EXPECTED_TRAIN_ROWS,
            "dev": len(dev),
            "train_dev": EXPECTED_TRAIN_ROWS + len(dev),
            "internal_test": len(internal),
            "gold_physician_consensus": EXPECTED_SOURCE_ROWS["gold"],
        },
        "output_hashes": output_hashes,
        "old_artifacts_mutated": False,
        "gold_physician_labels_modified": 0,
        "training_started": False,
        "model_metrics_computed": False,
    }
    write_json_atomic(args.output_root / "receipt.json", receipt)
    active = {
        "schema": "prta-cxr.active-label-version.v1",
        "status": "ACTIVE_SOL_AUTHORITATIVE_NOT_TRAINED",
        "activated_at": "2026-08-04",
        "train_dev_manifest": str(combined_path),
        "sealed_internal_test_manifest": str(internal_path),
        "gold_manifest": str(args.gold),
        "train_dev_sha256": output_hashes["train_dev"],
        "internal_test_sha256": output_hashes["internal_test"],
        "gold_sha256": inputs_before["gold_physician_consensus"],
        "unclear_policy": "excluded",
        "training_started": False,
    }
    write_json_atomic(args.output_root / "active_label_version.json", active)
    print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _audit_output_rows(
    source_rows: list[dict[str, Any]],
    output_path: Path,
    review_by_id: dict[str, dict[str, Any]],
    cohort: str,
) -> dict[str, Any]:
    output_rows = list(_stream_jsonl(output_path))
    output_by_id = {row["sample_id"]: row for row in output_rows}
    unclear_ids = {
        sample_id
        for sample_id, row in review_by_id.items()
        if row["sol_label"] == "Unclear"
    }
    source_by_id = {row["sample_id"]: row for row in source_rows}
    if set(output_by_id) != set(source_by_id) - unclear_ids:
        raise RuntimeError(f"{cohort} output IDs differ from source minus Unclear")
    changed = 0
    same = 0
    for sample_id, output in output_by_id.items():
        source = source_by_id[sample_id]
        review = review_by_id[sample_id]
        _validate_split_sample(output, cohort)
        for field, value in source.items():
            if field not in {"progression_label", "label_source"}:
                if output[field] != value:
                    raise RuntimeError(f"{cohort} non-label field changed")
        if output["progression_label"] != review["sol_label"]:
            raise RuntimeError(f"{cohort} output label differs from Sol")
        if output["label_source"] != NEW_LABEL_SOURCE:
            raise RuntimeError(f"{cohort} output label source is not Sol")
        value_changed = output["progression_label"] != source["progression_label"]
        changed += int(value_changed)
        same += int(not value_changed)
    return {
        "source_rows": len(source_rows),
        "output_rows": len(output_rows),
        "excluded_unclear_rows": len(unclear_ids),
        "label_value_changed_rows": changed,
        "authority_rebound_same_label_rows": same,
    }


def audit_sol_label_replacement_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently audit Sol label replacement surfaces"
    )
    parser.add_argument("--source-train-dev", type=Path, required=True)
    parser.add_argument("--source-internal-test", type=Path, required=True)
    parser.add_argument("--source-sol-train", type=Path, required=True)
    parser.add_argument("--review-results", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    _private(args.output_root)
    receipt = json.loads(
        (args.output_root / "receipt.json").read_text(encoding="utf-8")
    )
    review = _load_review(args.review_results)
    dev_source = _load_source_split(args.source_train_dev, "dev")
    internal_source = _load_source_split(
        args.source_internal_test, "internal_test"
    )
    private = args.output_root / "private"
    dev_path = private / "dev_sol_authoritative_v1.jsonl"
    internal_path = private / "internal_test_sol_authoritative_v1.jsonl"
    combined_path = private / "train_dev_sol_authoritative_v2.jsonl"
    provenance_path = private / "sol_authority_provenance.jsonl"
    exclusions_path = private / "sol_unclear_exclusions.jsonl"
    dev_audit = _audit_output_rows(
        dev_source, dev_path, review["dev"], "dev"
    )
    internal_audit = _audit_output_rows(
        internal_source,
        internal_path,
        review["internal_test"],
        "internal_test",
    )
    train_digest = hashlib.sha256()
    combined_dev = []
    with combined_path.open("rb") as handle:
        for index, raw_line in enumerate(handle):
            if index < EXPECTED_TRAIN_ROWS:
                train_digest.update(raw_line)
            else:
                combined_dev.append(json.loads(raw_line))
    if train_digest.hexdigest() != sha256_file(args.source_sol_train):
        raise RuntimeError("combined manifest does not preserve Train bytes")
    if combined_dev != list(_stream_jsonl(dev_path)):
        raise RuntimeError("combined Dev rows differ from standalone Dev")
    actual_hashes = {
        "dev": sha256_file(dev_path),
        "internal_test": sha256_file(internal_path),
        "train_dev": sha256_file(combined_path),
        "provenance": sha256_file(provenance_path),
        "exclusions": sha256_file(exclusions_path),
    }
    if actual_hashes != receipt["output_hashes"]:
        raise RuntimeError("replacement output hashes differ from receipt")
    if sha256_file(args.gold) != receipt["input_hashes"][
        "gold_physician_consensus"
    ]:
        raise RuntimeError("physician Gold changed")
    audit = {
        "schema": "prta-cxr.sol-label-replacement-independent-audit.v1",
        "status": "PASS_SOL_LABEL_REPLACEMENT_INDEPENDENT_AUDIT",
        "dev": dev_audit,
        "internal_test": internal_audit,
        "combined_train_rows": EXPECTED_TRAIN_ROWS,
        "combined_dev_rows": len(combined_dev),
        "combined_train_bytes_equal_source": True,
        "verified_output_hashes": actual_hashes,
        "gold_physician_labels_modified": 0,
        "training_started": False,
        "model_metrics_computed": False,
    }
    write_json_atomic(args.output_root / "independent_audit.json", audit)
    print(json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False))
    return 0
