from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.contracts import SAMPLE_FIELDS, sha256_file, validate_sample
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.protected_quality_review import (
    DEFAULT_PROMPT,
    DEFAULT_SCHEMA,
    MODEL,
    REASONING_EFFORT,
    _group_summary,
    _load_completed_outputs,
    _private,
    _write_batches,
    _write_csv,
    shard_ranges,
)

COHORT = "tier_bc_missing"
EXPECTED_TIER_BC_ROWS = 13334
EXPECTED_MISSING_ROWS = 5968
EXPECTED_REVIEWED_ROWS = 7366
EXPECTED_PRIOR_ROWS = {
    "tier_a": 3866,
    "protected": 33615,
    "pilot": 150,
}
EXPECTED_TOTALS = {
    "Tier B|train": 2921,
    "Tier C|dev": 7353,
    "Tier C|train": 3060,
}
EXPECTED_MISSING = {
    "Tier B|train": 2912,
    "Tier C|train": 3056,
}


def _load_ids(path: Path, *, expected_rows: int) -> set[str]:
    identifiers = [str(row["sample_id"]) for row in read_jsonl(path)]
    if len(identifiers) != expected_rows or len(set(identifiers)) != expected_rows:
        raise RuntimeError(f"review ID count/uniqueness mismatch: {path}")
    return set(identifiers)


def _count(rows: list[dict[str, Any]]) -> dict[str, int]:
    values = Counter(f'{row["risk_tier"]}|{row["split"]}' for row in rows)
    return dict(sorted(values.items()))


def build_missing_tier_bc_candidates(
    detail_rows: list[dict[str, Any]],
    reviewed: dict[str, set[str]],
    *,
    expected_total: int = EXPECTED_TIER_BC_ROWS,
    expected_missing: int = EXPECTED_MISSING_ROWS,
    expected_totals: dict[str, int] | None = None,
    expected_missing_by_tier_split: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    selected = [
        row for row in detail_rows if row.get("risk_tier") in {"Tier B", "Tier C"}
    ]
    identifiers = [str(row["sample_id"]) for row in selected]
    if len(selected) != expected_total or len(set(identifiers)) != expected_total:
        raise RuntimeError("Tier-B/C candidate count/uniqueness mismatch")
    totals = _count(selected)
    if expected_totals is not None and totals != expected_totals:
        raise RuntimeError("Tier-B/C tier/split totals changed")

    union = set().union(*reviewed.values()) if reviewed else set()
    missing_rows = [row for row in selected if str(row["sample_id"]) not in union]
    missing_rows.sort(key=lambda row: str(row["sample_id"]))
    if len(missing_rows) != expected_missing:
        raise RuntimeError("Tier-B/C missing Sol-review count changed")
    missing_counts = _count(missing_rows)
    if (
        expected_missing_by_tier_split is not None
        and missing_counts != expected_missing_by_tier_split
    ):
        raise RuntimeError("Tier-B/C missing tier/split counts changed")
    if {str(row["split"]) for row in missing_rows} != {"train"}:
        raise RuntimeError("unreviewed Tier-B/C roster must be Train-only")

    candidates = [
        validate_sample({field: row[field] for field in SAMPLE_FIELDS})
        for row in missing_rows
    ]
    metadata = [
        {
            "sample_id": str(row["sample_id"]),
            "risk_tier": str(row["risk_tier"]),
        }
        for row in missing_rows
    ]
    per_namespace_hits = {
        name: sum(str(row["sample_id"]) in values for row in selected)
        for name, values in reviewed.items()
    }
    multi_namespace = sum(
        sum(str(row["sample_id"]) in values for values in reviewed.values()) > 1
        for row in selected
    )
    coverage = {
        "tier_bc_rows": len(selected),
        "already_reviewed_union": len(selected) - len(missing_rows),
        "missing_rows": len(missing_rows),
        "totals_by_tier_split": totals,
        "missing_by_tier_split": missing_counts,
        "review_hits_by_namespace": per_namespace_hits,
        "multi_namespace_rows": multi_namespace,
    }
    return candidates, metadata, coverage


def prepare_tier_bc_sol_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare exact missing Tier-B/C GPT-5.6 Sol blind review"
    )
    parser.add_argument("--case-details", type=Path, required=True)
    parser.add_argument("--tier-a-results", type=Path, required=True)
    parser.add_argument("--protected-results", type=Path, required=True)
    parser.add_argument("--pilot-results", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args(argv)
    _private(args.output_root)
    if args.output_root.exists():
        raise FileExistsError(f"refusing existing output root: {args.output_root}")
    args.output_root.mkdir(parents=True)

    inputs = {
        "case_details": sha256_file(args.case_details),
        "tier_a_results": sha256_file(args.tier_a_results),
        "protected_results": sha256_file(args.protected_results),
        "pilot_results": sha256_file(args.pilot_results),
    }
    preopen = {
        "schema": "prta-cxr.tier-bc-sol-preparation-preopen.v1",
        "status": "AUTHORIZED_TIER_BC_MISSING_SOL_REVIEW",
        "authorization_date": "2026-08-04",
        "input_hashes": inputs,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "label_mutation_authorized": False,
        "training_or_metric_computation_authorized": False,
    }
    write_json_atomic(args.output_root / "preopen_receipt.json", preopen)

    reviewed = {
        "tier_a": _load_ids(
            args.tier_a_results, expected_rows=EXPECTED_PRIOR_ROWS["tier_a"]
        ),
        "protected": _load_ids(
            args.protected_results,
            expected_rows=EXPECTED_PRIOR_ROWS["protected"],
        ),
        "pilot": _load_ids(
            args.pilot_results, expected_rows=EXPECTED_PRIOR_ROWS["pilot"]
        ),
    }
    candidates, metadata, coverage = build_missing_tier_bc_candidates(
        read_jsonl(args.case_details),
        reviewed,
        expected_totals=EXPECTED_TOTALS,
        expected_missing_by_tier_split=EXPECTED_MISSING,
    )
    if coverage["already_reviewed_union"] != EXPECTED_REVIEWED_ROWS:
        raise RuntimeError("reviewed Tier-B/C union count changed")

    candidate_path, batch_dir, batch_receipt = _write_batches(
        candidates,
        cohort=COHORT,
        root=args.output_root,
        batch_size=args.batch_size,
        prompt=args.prompt,
        schema=args.schema,
    )
    metadata_path = args.output_root / "private" / "candidate_metadata.jsonl"
    write_jsonl_atomic(metadata_path, metadata)
    config = {
        "schema": "prta-cxr.protected-quality-review-config.v1",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "authorized_scope": "missing_train_tier_bc_full_blind_quality_review",
        "execution_enabled": True,
        "cohort_rows": {COHORT: len(candidates)},
        "candidate_file_hashes": {COHORT: sha256_file(candidate_path)},
        "candidate_manifest_hashes": {
            COHORT: batch_receipt["candidate_manifest_sha256"]
        },
        "prompt_sha256": sha256_file(args.prompt),
        "schema_sha256": sha256_file(args.schema),
        "labels_externalized": False,
        "tracin_fields_externalized": False,
        "training_or_mutation_authorized": False,
    }
    config_path = args.output_root / "private" / "config.json"
    write_json_atomic(config_path, config)
    receipt = {
        "schema": "prta-cxr.tier-bc-sol-preparation.v1",
        "status": "PASS_TIER_BC_MISSING_BLIND_ROSTER",
        "input_hashes": inputs,
        "coverage": coverage,
        "candidate_rows": len(candidates),
        "batches": batch_receipt["batches"],
        "batch_size": args.batch_size,
        "candidate_sha256": sha256_file(candidate_path),
        "candidate_metadata_sha256": sha256_file(metadata_path),
        "config_sha256": sha256_file(config_path),
        "batch_dir": str(batch_dir),
        "external_item_fields": batch_receipt["external_item_fields"],
        "labels_or_risk_externalized": False,
        "training_or_mutation_performed": False,
    }
    write_json_atomic(args.output_root / "preparation_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def launch_tier_bc_sol_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Launch disjoint missing Tier-B/C Sol review shards"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=15)
    args = parser.parse_args(argv)
    _private(args.output_root)
    registry_path = args.output_root / "launch_registry.json"
    if registry_path.exists():
        raise FileExistsError(f"refusing existing launch registry: {registry_path}")
    preparation = json.loads(
        (args.output_root / "preparation_receipt.json").read_text(encoding="utf-8")
    )
    total = preparation["batches"]
    ranges = shard_ranges(total, args.workers)
    repo_root = Path(__file__).resolve().parents[2]
    runner = repo_root / "scripts" / "25_run_protected_quality_review.py"
    batch_dir = args.output_root / "private" / "batches" / COHORT
    output_dir = args.output_root / "private" / "outputs" / COHORT
    config = args.output_root / "private" / "config.json"
    logs = args.output_root / "private" / "logs"
    logs.mkdir(parents=True, exist_ok=False)
    children = []
    for index, (start, count) in enumerate(ranges):
        receipt = args.output_root / "receipts" / f"full_{index:02d}.json"
        stdout_path = logs / f"full_{index:02d}.stdout.log"
        stderr_path = logs / f"full_{index:02d}.stderr.log"
        command = [
            sys.executable,
            str(runner),
            "--cohort",
            COHORT,
            "--batch-dir",
            str(batch_dir),
            "--output-dir",
            str(output_dir),
            "--config",
            str(config),
            "--receipt-output",
            str(receipt),
            "--start-batch",
            str(start),
            "--max-batches",
            str(count),
            "--resume",
        ]
        with stdout_path.open("w", encoding="utf-8") as stdout_handle:
            with stderr_path.open("w", encoding="utf-8") as stderr_handle:
                process = subprocess.Popen(
                    command,
                    cwd=repo_root,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        children.append(
            {
                "shard": index,
                "start_batch": start,
                "max_batches": count,
                "pid": process.pid,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "receipt": str(receipt),
            }
        )
    registry = {
        "schema": "prta-cxr.tier-bc-sol-launch.v1",
        "status": "RUNNING_TIER_BC_MISSING_BLIND_REVIEW",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "candidate_rows": preparation["candidate_rows"],
        "batches": total,
        "workers": len(children),
        "children": children,
        "training_or_mutation_started": False,
    }
    write_json_atomic(registry_path, registry)
    print(json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def compare_tier_bc_sol_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare completed Tier-B/C blind review without mutation"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--case-details", type=Path, required=True)
    parser.add_argument("--tier-a-results", type=Path, required=True)
    parser.add_argument("--protected-results", type=Path, required=True)
    parser.add_argument("--pilot-results", type=Path, required=True)
    args = parser.parse_args(argv)
    _private(args.output_root)
    analysis_dir = args.output_root / "private" / "analysis"
    if analysis_dir.exists():
        raise FileExistsError(f"refusing existing analysis dir: {analysis_dir}")
    preparation = json.loads(
        (args.output_root / "preparation_receipt.json").read_text(encoding="utf-8")
    )
    current_hashes = {
        "case_details": sha256_file(args.case_details),
        "tier_a_results": sha256_file(args.tier_a_results),
        "protected_results": sha256_file(args.protected_results),
        "pilot_results": sha256_file(args.pilot_results),
    }
    if current_hashes != preparation["input_hashes"]:
        raise RuntimeError("Tier-B/C review input changed before comparison")
    candidates = read_jsonl(
        args.output_root / "private" / "candidates" / f"{COHORT}.jsonl"
    )
    metadata = {
        row["sample_id"]: row
        for row in read_jsonl(
            args.output_root / "private" / "candidate_metadata.jsonl"
        )
    }
    outputs = _load_completed_outputs(
        args.output_root / "private" / "outputs" / COHORT,
        preparation["batches"],
    )
    candidate_ids = {row["sample_id"] for row in candidates}
    if candidate_ids != set(metadata) or candidate_ids != set(outputs):
        raise RuntimeError("Tier-B/C candidate/metadata/output ID mismatch")
    results = []
    for sample in candidates:
        sample_id = sample["sample_id"]
        sol = outputs[sample_id]
        exact = sol["ai_label"] == sample["progression_label"]
        results.append(
            dict(sample)
            | {
                "risk_tier": metadata[sample_id]["risk_tier"],
                "current_label": sample["progression_label"],
                "current_label_source": sample["label_source"],
                "sol_label": sol["ai_label"],
                "sol_unclear": sol["ai_label"] == "Unclear",
                "exact_current": exact,
                "quality_flags": sol["quality_flags"],
            }
        )
    flagged = [
        row
        for row in results
        if row["sol_unclear"] or not row["exact_current"] or row["quality_flags"]
    ]
    confusion = Counter(
        (row["risk_tier"], row["current_label"], row["sol_label"])
        for row in results
    )
    summary = {
        "schema": "prta-cxr.tier-bc-sol-quality-summary.v1",
        "status": "PASS_READ_ONLY_TIER_BC_SOL_REVIEW",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "rows": len(results),
        "flagged_union_rows": len(flagged),
        "overall": _group_summary(results, tuple()),
        "by_risk_tier": _group_summary(results, ("risk_tier",)),
        "by_source": _group_summary(results, ("risk_tier", "source")),
        "by_current_label": _group_summary(
            results, ("risk_tier", "current_label")
        ),
        "by_finding": _group_summary(results, ("risk_tier", "finding")),
        "confusion": [
            {
                "risk_tier": tier,
                "current_label": current,
                "sol_label": sol,
                "rows": count,
            }
            for (tier, current, sol), count in sorted(confusion.items())
        ],
        "quality_flag_counts": dict(
            sorted(
                Counter(
                    flag for row in results for flag in row["quality_flags"]
                ).items()
            )
        ),
        "labels_modified": 0,
        "samples_deleted": 0,
        "splits_modified": 0,
        "training_started": False,
        "post_relabel_metrics_computed": False,
    }
    analysis_dir.mkdir(parents=True)
    all_jsonl = analysis_dir / "all_review_results.jsonl"
    flagged_csv = analysis_dir / "all_flagged_for_review.csv"
    summary_json = analysis_dir / "aggregate_summary.json"
    report = analysis_dir / "PRTA_CXR_TierBC_Sol内部复核.md"
    write_jsonl_atomic(all_jsonl, results)
    _write_csv(flagged_csv, flagged)
    write_json_atomic(summary_json, summary)
    overall = summary["overall"][0]
    report.write_text(
        "\n".join(
            [
                "# PRTA-CXR Tier B/C GPT-5.6 Sol 内部复核",
                "",
                "> 只读自动复核：Sol 不是医学 Gold。本任务不改标签、不删除、"
                "不调整划分、不训练、不计算改标后指标。",
                "",
                f'- 补审行数：{len(results):,}',
                f'- Sol Unclear：{overall["sol_unclear"]:,}',
                f'- 明确一致率：{overall["decisive_agreement_rate"]}',
                f'- 不一致/Unclear/质量标志并集：{len(flagged):,}',
                "",
                "逐病例结果和需关注列表仅保存在本私有目录。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if current_hashes != {
        "case_details": sha256_file(args.case_details),
        "tier_a_results": sha256_file(args.tier_a_results),
        "protected_results": sha256_file(args.protected_results),
        "pilot_results": sha256_file(args.pilot_results),
    }:
        raise RuntimeError("Tier-B/C review input changed during comparison")
    receipt = {
        "schema": "prta-cxr.tier-bc-sol-final-receipt.v1",
        "status": "PASS_READ_ONLY_TIER_BC_SOL_AUDIT",
        "input_hashes_before_after": current_hashes,
        "row_counts": {
            "reviewed_now": len(results),
            "previously_reviewed": preparation["coverage"]["already_reviewed_union"],
            "tier_bc_total": preparation["coverage"]["tier_bc_rows"],
        },
        "output_hashes": {
            path.name: sha256_file(path)
            for path in (all_jsonl, flagged_csv, summary_json, report)
        },
        "labels_modified": 0,
        "training_or_model_metric_computation_started": False,
    }
    write_json_atomic(args.output_root / "final_audit_receipt.json", receipt)
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def audit_tier_bc_sol_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently audit Tier-B/C Sol review conservation"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--case-details", type=Path, required=True)
    parser.add_argument("--tier-a-results", type=Path, required=True)
    parser.add_argument("--protected-results", type=Path, required=True)
    parser.add_argument("--pilot-results", type=Path, required=True)
    args = parser.parse_args(argv)
    _private(args.output_root)
    audit_path = args.output_root / "independent_audit.json"
    if audit_path.exists():
        raise FileExistsError(f"refusing existing audit: {audit_path}")
    preparation = json.loads(
        (args.output_root / "preparation_receipt.json").read_text(encoding="utf-8")
    )
    final = json.loads(
        (args.output_root / "final_audit_receipt.json").read_text(encoding="utf-8")
    )
    current_inputs = {
        "case_details": sha256_file(args.case_details),
        "tier_a_results": sha256_file(args.tier_a_results),
        "protected_results": sha256_file(args.protected_results),
        "pilot_results": sha256_file(args.pilot_results),
    }
    if current_inputs != preparation["input_hashes"]:
        raise RuntimeError("independent audit found input hash drift")

    candidates = read_jsonl(
        args.output_root / "private" / "candidates" / f"{COHORT}.jsonl"
    )
    metadata = {
        row["sample_id"]: row
        for row in read_jsonl(
            args.output_root / "private" / "candidate_metadata.jsonl"
        )
    }
    outputs = _load_completed_outputs(
        args.output_root / "private" / "outputs" / COHORT,
        preparation["batches"],
    )
    result_path = args.output_root / "private" / "analysis" / "all_review_results.jsonl"
    results = {row["sample_id"]: row for row in read_jsonl(result_path)}
    candidate_by_id = {row["sample_id"]: row for row in candidates}
    expected_ids = set(candidate_by_id)
    if not (
        len(candidates)
        == len(candidate_by_id)
        == len(metadata)
        == len(outputs)
        == len(results)
        == EXPECTED_MISSING_ROWS
    ):
        raise RuntimeError("independent audit found duplicate or missing rows")
    if not (
        expected_ids == set(metadata) == set(outputs) == set(results)
    ):
        raise RuntimeError("independent audit found ID mapping drift")
    for sample_id in expected_ids:
        candidate = candidate_by_id[sample_id]
        result = results[sample_id]
        sol = outputs[sample_id]
        if any(result[field] != candidate[field] for field in SAMPLE_FIELDS):
            raise RuntimeError("candidate field changed in comparison result")
        if result["risk_tier"] != metadata[sample_id]["risk_tier"]:
            raise RuntimeError("risk tier changed in comparison result")
        if (
            result["sol_label"] != sol["ai_label"]
            or result["quality_flags"] != sol["quality_flags"]
        ):
            raise RuntimeError("Sol output changed in comparison result")

    receipt_paths = sorted((args.output_root / "receipts").glob("full_*.json"))
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in receipt_paths]
    batch_receipts = [batch for receipt in receipts for batch in receipt["batches"]]
    if len(receipts) != 30 or len(batch_receipts) != preparation["batches"]:
        raise RuntimeError("independent audit found incomplete shard receipts")
    if len({row["batch_id"] for row in batch_receipts}) != preparation["batches"]:
        raise RuntimeError("independent audit found duplicate batch receipts")
    if sum(row["rows"] for row in batch_receipts) != EXPECTED_MISSING_ROWS:
        raise RuntimeError("independent audit found receipt row drift")
    if any(
        row["model"] != MODEL
        or row["reasoning_effort"] != REASONING_EFFORT
        or row["failed_attempts"] != 0
        for row in batch_receipts
    ):
        raise RuntimeError("independent audit found model/effort/failure drift")

    analysis = args.output_root / "private" / "analysis"
    actual_outputs = {
        path.name: sha256_file(path)
        for path in (
            result_path,
            analysis / "all_flagged_for_review.csv",
            analysis / "aggregate_summary.json",
            analysis / "PRTA_CXR_TierBC_Sol内部复核.md",
        )
    }
    if actual_outputs != final["output_hashes"]:
        raise RuntimeError("independent audit found final output hash drift")
    audit = {
        "schema": "prta-cxr.tier-bc-sol-independent-audit.v1",
        "status": "PASS_TIER_BC_SOL_INDEPENDENT_AUDIT",
        "candidate_rows": len(candidates),
        "output_rows": len(outputs),
        "result_rows": len(results),
        "unique_ids": len(expected_ids),
        "batches": len(batch_receipts),
        "shard_receipts": len(receipts),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "failed_attempts": sum(row["failed_attempts"] for row in batch_receipts),
        "reused_canary_outputs": sum(
            bool(row["reused_existing_output"]) for row in batch_receipts
        ),
        "input_hashes_verified": current_inputs,
        "output_hashes_verified": actual_outputs,
        "labels_modified": 0,
        "samples_deleted": 0,
        "splits_modified": 0,
        "training_or_metrics_started": False,
    }
    write_json_atomic(audit_path, audit)
    print(json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False))
    return 0
