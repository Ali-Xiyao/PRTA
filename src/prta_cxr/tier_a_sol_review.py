from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.contracts import (
    PROGRESSION_LABELS,
    SAMPLE_FIELDS,
    canonical_sha256,
    sha256_file,
    validate_sample,
)
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.independent_silver import AI_LABELS, load_independent_ai_output

EXPECTED_TIER_A_ROWS = 3866
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"
TRAIN_ROWS = 91065
DEV_ROWS = 16666
TRAIN_AFTER_UNCLEAR_EXCLUSION = 90771
TRAIN_DEV_AFTER_UNCLEAR_EXCLUSION = 107437
SOL_AUTHORITY_SOURCE = "human_authorized_sol_blind_tier_a_v1"
_SAMPLE_ID_PATTERN = re.compile(rb'"sample_id"\s*:\s*"([^"\\]+)"')


def _require_unsealed_input(path: Path) -> None:
    value = str(path.resolve()).lower().replace("-", "_")
    forbidden = ("internal_test", "gold")
    if any(token in value for token in forbidden):
        raise RuntimeError("Internal-test/Gold inputs are forbidden for Tier-A review")


def _require_private_path(path: Path) -> None:
    value = str(path.resolve()).lower().replace("/", "\\")
    if "\\prta-cxr\\" in value and "\\poststop_audits\\" not in value:
        raise RuntimeError("row-level Tier-A review artifacts must stay outside Git")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError(f"expected object at {path}:{line_number}")
            rows.append(value)
    return rows


def build_tier_a_candidates(
    detail_rows: Sequence[Mapping[str, Any]],
    *,
    expected_rows: int = EXPECTED_TIER_A_ROWS,
) -> list[dict[str, Any]]:
    selected = [row for row in detail_rows if row.get("risk_tier") == "Tier A"]
    if len(selected) != expected_rows:
        raise RuntimeError(
            "Tier A row count mismatch: "
            f"expected={expected_rows}, actual={len(selected)}"
        )
    if {str(row.get("split", "")).lower() for row in selected} != {"train"}:
        raise RuntimeError("Tier A blind review is restricted to Train")
    candidates = [
        validate_sample({field: row[field] for field in SAMPLE_FIELDS})
        for row in selected
    ]
    candidates.sort(key=lambda row: row["sample_id"])
    identifiers = [row["sample_id"] for row in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("duplicate Tier A sample_id")
    return candidates


def _count_by(
    rows: Sequence[Mapping[str, Any]], keys: Sequence[str]
) -> dict[str, int]:
    counts = Counter("|".join(str(row[key]) for key in keys) for row in rows)
    return dict(sorted(counts.items()))


def prepare_tier_a_sol_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the private Train Tier-A GPT-5.6 Sol blind-review roster"
    )
    parser.add_argument("--case-details", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path, required=True)
    parser.add_argument("--config-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--expected-rows", type=int, default=EXPECTED_TIER_A_ROWS)
    args = parser.parse_args(argv)
    _require_unsealed_input(args.case_details)
    for output in (
        args.candidate_output,
        args.config_output,
        args.receipt_output,
    ):
        _require_private_path(output)
    details = _read_jsonl(args.case_details)
    candidates = build_tier_a_candidates(details, expected_rows=args.expected_rows)
    manifest_hash = canonical_sha256(candidates)
    write_jsonl_atomic(args.candidate_output, candidates)
    config = {
        "schema": "prta-cxr.independent-silver-labeling.v1",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "batch_size": 20,
        "prompt": "prompts/independent_silver_label_v1.md",
        "output_schema": "schemas/independent_silver_label_batch.schema.json",
        "fail_closed": True,
        "authorization_date": "2026-08-04",
        "authorized_scope": "train_tier_a_3866_sol_blind_review_only",
        "pilot_execution_enabled": False,
        "pilot_rows_max": 0,
        "full_execution_enabled": True,
        "full_candidate_rows": len(candidates),
        "candidate_manifest_sha256": manifest_hash,
        "rule_label_externalized": False,
        "luna_label_externalized": False,
        "tracin_fields_externalized": False,
        "patient_identifiers_externalized": False,
        "agreement_is_accuracy": False,
        "training_or_mutation_authorized": False,
    }
    write_json_atomic(args.config_output, config)
    receipt = {
        "schema": "prta-cxr.tier-a-sol-blind-preparation-receipt.v1",
        "status": "PASS_TIER_A_SOL_BLIND_ROSTER",
        "rows": len(candidates),
        "split": "train",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "case_details_sha256": sha256_file(args.case_details),
        "candidate_manifest_sha256": manifest_hash,
        "candidate_file_sha256": sha256_file(args.candidate_output),
        "counts_by_source_label": _count_by(
            candidates, ("source", "progression_label")
        ),
        "external_item_fields": [
            "sample_id",
            "finding",
            "prior_report",
            "current_report",
        ],
        "external_sample_id_is_batch_alias": True,
        "luna_label_externalized": False,
        "tracin_fields_externalized": False,
        "sealed_splits_opened": False,
    }
    write_json_atomic(args.receipt_output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def load_sol_outputs(output_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    paths = sorted(output_dir.glob("batch_*.json"))
    if not paths:
        raise RuntimeError("no Sol batch outputs found")
    for path in paths:
        rows.extend(load_independent_ai_output(path))
    identifiers = [row["sample_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("duplicate sample_id across Sol outputs")
    return rows


def load_train_id_allowlist(path: Path) -> set[str]:
    identifiers: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"sample_id", "split"}
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            raise RuntimeError("Train score CSV is missing sample_id/split")
        for row in reader:
            if row["split"].strip().lower() != "train":
                raise RuntimeError("Train allowlist contains a non-Train row")
            identifiers.append(row["sample_id"].strip())
    if len(identifiers) != TRAIN_ROWS or len(set(identifiers)) != TRAIN_ROWS:
        raise RuntimeError("Train allowlist count/uniqueness mismatch")
    return set(identifiers)


def _output_temporary(path: Path) -> Path:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.with_name(f".{path.name}.tmp.{os.getpid()}")


def apply_sol_authority_stream(
    *,
    source_manifest: Path,
    train_ids: set[str],
    candidates: Sequence[Mapping[str, Any]],
    sol_rows: Sequence[Mapping[str, str]],
    train_output: Path,
    train_dev_output: Path,
    expected_train_rows: int = TRAIN_ROWS,
    expected_dev_rows: int = DEV_ROWS,
    expected_tier_a_rows: int = EXPECTED_TIER_A_ROWS,
    expected_decisive_rows: int = 3572,
    expected_unclear_rows: int = 294,
    expected_changed_labels: int = 570,
    expected_same_labels: int = 3002,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    candidate_by_id = {row["sample_id"]: validate_sample(row) for row in candidates}
    sol_by_id = {row["sample_id"]: row["ai_label"] for row in sol_rows}
    if len(candidate_by_id) != expected_tier_a_rows:
        raise RuntimeError("Tier A candidate count mismatch")
    if set(candidate_by_id) != set(sol_by_id):
        raise RuntimeError("Sol/candidate ID mismatch")
    if not set(candidate_by_id) <= train_ids:
        raise RuntimeError("Tier A candidate is outside the Train allowlist")

    train_temporary = _output_temporary(train_output)
    combined_temporary = _output_temporary(train_dev_output)
    provenance: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen_train: set[str] = set()
    seen_candidates: set[str] = set()
    dev_raw_hash = hashlib.sha256()
    source_rows = 0
    dev_rows = 0
    train_output_rows = 0
    combined_output_rows = 0
    changed_labels = 0
    same_labels = 0
    try:
        with (
            source_manifest.open("rb") as source,
            train_temporary.open("wb") as train_handle,
            combined_temporary.open("wb") as combined_handle,
        ):
            for raw_line in source:
                if not raw_line.strip():
                    continue
                source_rows += 1
                match = _SAMPLE_ID_PATTERN.search(raw_line)
                if match is None:
                    raise RuntimeError("source manifest line has no simple sample_id")
                sample_id = match.group(1).decode("utf-8")
                if sample_id not in train_ids:
                    dev_rows += 1
                    dev_raw_hash.update(raw_line)
                    combined_handle.write(raw_line)
                    combined_output_rows += 1
                    continue

                if sample_id in seen_train:
                    raise RuntimeError("duplicate Train sample_id in source manifest")
                seen_train.add(sample_id)
                if sample_id not in candidate_by_id:
                    train_handle.write(raw_line)
                    combined_handle.write(raw_line)
                    train_output_rows += 1
                    combined_output_rows += 1
                    continue

                row = json.loads(raw_line)
                if row.get("split") != "train":
                    raise RuntimeError("allowlisted sample is not marked Train")
                sample = validate_sample(
                    {field: row[field] for field in SAMPLE_FIELDS}
                )
                candidate = candidate_by_id[sample_id]
                if sample["progression_label"] != candidate["progression_label"]:
                    raise RuntimeError(
                        "source Luna label differs from frozen candidate"
                    )
                if sample["finding"] != candidate["finding"]:
                    raise RuntimeError("source finding differs from frozen candidate")
                seen_candidates.add(sample_id)
                sol_label = sol_by_id[sample_id]
                base = {
                    "sample_id": sample_id,
                    "source": sample["source"],
                    "finding": sample["finding"],
                    "luna_label": sample["progression_label"],
                    "sol_label": sol_label,
                    "previous_label_source": sample["label_source"],
                }
                if sol_label == "Unclear":
                    exclusions.append(base | {"action": "exclude_sol_unclear"})
                    continue

                updated = dict(row)
                updated["progression_label"] = sol_label
                updated["label_source"] = SOL_AUTHORITY_SOURCE
                validate_sample({field: updated[field] for field in SAMPLE_FIELDS})
                for key, value in row.items():
                    if key not in {"progression_label", "label_source"}:
                        if updated[key] != value:
                            raise RuntimeError("non-label field changed")
                label_changed = sol_label != sample["progression_label"]
                changed_labels += int(label_changed)
                same_labels += int(not label_changed)
                provenance.append(
                    base
                    | {
                        "action": (
                            "replace_label"
                            if label_changed
                            else "rebind_authority_same_label"
                        ),
                        "label_value_changed": label_changed,
                        "new_label_source": SOL_AUTHORITY_SOURCE,
                    }
                )
                encoded = (
                    json.dumps(updated, sort_keys=True, ensure_ascii=False) + "\n"
                ).encode("utf-8")
                train_handle.write(encoded)
                combined_handle.write(encoded)
                train_output_rows += 1
                combined_output_rows += 1

        if seen_train != train_ids:
            raise RuntimeError("source manifest does not conserve Train IDs")
        if seen_candidates != set(candidate_by_id):
            raise RuntimeError("not every Tier A candidate was visited")
        if dev_rows != expected_dev_rows:
            raise RuntimeError("unexpected non-Train row count")
        if (
            len(provenance) != expected_decisive_rows
            or len(exclusions) != expected_unclear_rows
        ):
            raise RuntimeError("Sol decisive/Unclear counts changed")
        if (
            changed_labels != expected_changed_labels
            or same_labels != expected_same_labels
        ):
            raise RuntimeError("Sol/Luna agreement counts changed")
        if train_output_rows != expected_train_rows - expected_unclear_rows:
            raise RuntimeError("new Train row count mismatch")
        if combined_output_rows != (
            expected_train_rows + expected_dev_rows - expected_unclear_rows
        ):
            raise RuntimeError("new Train/Dev row count mismatch")
        train_temporary.replace(train_output)
        combined_temporary.replace(train_dev_output)
    finally:
        for temporary in (train_temporary, combined_temporary):
            if temporary.exists():
                temporary.unlink()

    audit = {
        "source_rows": source_rows,
        "source_train_rows": len(seen_train),
        "dev_rows_copied_byte_exact": dev_rows,
        "dev_raw_sha256": dev_raw_hash.hexdigest(),
        "tier_a_rows": len(candidate_by_id),
        "sol_authoritative_rows": len(provenance),
        "label_value_changed_rows": changed_labels,
        "authority_rebound_same_label_rows": same_labels,
        "excluded_sol_unclear_rows": len(exclusions),
        "unchanged_non_tier_a_train_rows": len(train_ids) - len(candidate_by_id),
        "train_output_rows": train_output_rows,
        "train_dev_output_rows": combined_output_rows,
    }
    return provenance, exclusions, audit


def compare_luna_sol(
    candidates: Sequence[Mapping[str, Any]],
    sol_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidate_by_id = {row["sample_id"]: row for row in candidates}
    sol_by_id = {row["sample_id"]: row for row in sol_rows}
    if set(candidate_by_id) != set(sol_by_id):
        missing = sorted(set(candidate_by_id) - set(sol_by_id))
        extra = sorted(set(sol_by_id) - set(candidate_by_id))
        raise RuntimeError(
            f"Sol output ID mismatch; missing={len(missing)}, extra={len(extra)}"
        )
    comparisons: list[dict[str, Any]] = []
    for sample_id in sorted(candidate_by_id):
        candidate = candidate_by_id[sample_id]
        luna_label = candidate["progression_label"]
        sol_label = sol_by_id[sample_id]["ai_label"]
        comparisons.append(
            {
                "sample_id": sample_id,
                "source": candidate["source"],
                "finding": candidate["finding"],
                "luna_label": luna_label,
                "sol_label": sol_label,
                "sol_unclear": sol_label == "Unclear",
                "exact_agreement": sol_label == luna_label,
                "opposite_direction_disagreement": (luna_label, sol_label)
                in {
                    ("Improved", "Worse"),
                    ("Worse", "Improved"),
                    ("New", "Resolved"),
                    ("Resolved", "New"),
                },
            }
        )

    def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        unclear = sum(bool(row["sol_unclear"]) for row in rows)
        exact = sum(bool(row["exact_agreement"]) for row in rows)
        decisive = total - unclear
        decisive_rows = [row for row in rows if not row["sol_unclear"]]
        luna_counts = Counter(row["luna_label"] for row in decisive_rows)
        sol_counts = Counter(row["sol_label"] for row in decisive_rows)
        expected_agreement = (
            sum(
                luna_counts[label] * sol_counts[label]
                for label in PROGRESSION_LABELS
            )
            / (decisive * decisive)
            if decisive
            else None
        )
        observed_agreement = exact / decisive if decisive else None
        kappa = (
            (observed_agreement - expected_agreement) / (1 - expected_agreement)
            if decisive and expected_agreement is not None and expected_agreement < 1
            else None
        )
        return {
            "rows": total,
            "exact_agreement_all": exact,
            "exact_agreement_rate_all": exact / total if total else None,
            "sol_unclear": unclear,
            "sol_unclear_rate": unclear / total if total else None,
            "decisive_rows": decisive,
            "exact_agreement_rate_decisive": exact / decisive if decisive else None,
            "cohen_kappa_decisive_five_class": kappa,
            "decisive_disagreements": decisive - exact,
            "opposite_direction_disagreements": sum(
                bool(row["opposite_direction_disagreement"]) for row in rows
            ),
        }

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        "source": defaultdict(list),
        "luna_label": defaultdict(list),
        "finding": defaultdict(list),
        "source_luna_label": defaultdict(list),
    }
    for row in comparisons:
        grouped["source"][row["source"]].append(row)
        grouped["luna_label"][row["luna_label"]].append(row)
        grouped["finding"][row["finding"]].append(row)
        grouped["source_luna_label"][
            f'{row["source"]}|{row["luna_label"]}'
        ].append(row)
    confusion = {
        luna: {sol: 0 for sol in AI_LABELS}
        for luna in PROGRESSION_LABELS
    }
    for row in comparisons:
        confusion[row["luna_label"]][row["sol_label"]] += 1
    summary = {
        "schema": "prta-cxr.tier-a-sol-luna-comparison.v1",
        "claim_boundary": (
            "Sol-Luna disagreement is a review signal, not proof that either label is "
            "clinically correct; human adjudication remains required."
        ),
        "overall": summarize(comparisons),
        "by_source": {
            key: summarize(value) for key, value in sorted(grouped["source"].items())
        },
        "by_luna_label": {
            key: summarize(value)
            for key, value in sorted(grouped["luna_label"].items())
        },
        "by_finding": {
            key: summarize(value) for key, value in sorted(grouped["finding"].items())
        },
        "by_source_luna_label": {
            key: summarize(value)
            for key, value in sorted(grouped["source_luna_label"].items())
        },
        "confusion_luna_rows_sol_columns": confusion,
    }
    return comparisons, summary


def render_internal_report(summary: Mapping[str, Any]) -> str:
    overall = summary["overall"]
    lines = [
        "# PRTA-CXR Tier A GPT-5.6 Sol 全量盲审内部结果",
        "",
        "> 本报告为私有数据质量审计。Sol–Luna 一致或不一致都不等价于医学真值；",
        "> 不一致样本必须经过人工判读后才能认定标签错误。",
        "",
        "## 总体结果",
        "",
        f"- 样本：{overall['rows']:,} 条 Train Tier A。",
        "- Sol 配置：`gpt-5.6-sol`，`medium`，全程盲于 Luna 标签和 TracIn 字段。",
        f"- 全体精确一致：{overall['exact_agreement_all']:,}/"
        f"{overall['rows']:,}（{overall['exact_agreement_rate_all']:.2%}）。",
        f"- Sol Unclear：{overall['sol_unclear']:,}（"
        f"{overall['sol_unclear_rate']:.2%}）。",
        f"- 排除 Unclear 后五类一致：{overall['exact_agreement_all']:,}/"
        f"{overall['decisive_rows']:,}（"
        f"{overall['exact_agreement_rate_decisive']:.2%}）。",
        f"- 五类 Cohen's κ："
        f"{overall['cohen_kappa_decisive_five_class']:.4f}。",
        f"- 明确分歧：{overall['decisive_disagreements']:,}；"
        f"方向相反分歧：{overall['opposite_direction_disagreements']:,}。",
        "",
        "## 按来源",
        "",
        "| 来源 | 行数 | Sol Unclear | 五类一致率 | Cohen's κ | 明确分歧 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for source, values in summary["by_source"].items():
        lines.append(
            f"| {source} | {values['rows']:,} | {values['sol_unclear']:,} | "
            f"{values['exact_agreement_rate_decisive']:.2%} | "
            f"{values['cohen_kappa_decisive_five_class']:.4f} | "
            f"{values['decisive_disagreements']:,} |"
        )
    lines.extend(
        [
            "",
            "## 按 Luna 标签",
            "",
            "| Luna 标签 | 行数 | Sol Unclear | 五类一致率 | 明确分歧 | 方向相反 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for label, values in summary["by_luna_label"].items():
        lines.append(
            f"| {label} | {values['rows']:,} | {values['sol_unclear']:,} | "
            f"{values['exact_agreement_rate_decisive']:.2%} | "
            f"{values['decisive_disagreements']:,} | "
            f"{values['opposite_direction_disagreements']:,} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 本轮五类一致率低于旧 150 条 pilot，说明 Tier A 中确实富集了"
            "需要复核的样本。",
            "- 两个来源的五类一致率非常接近，因此问题不像是单一数据源独有。",
            "- `New`、`Resolved`、`Worse` 的一致率相对较低；方向相反的 "
            "39 条应优先人工复核。",
            "- 这仍不能证明 Luna 错标：Tier A 同时富集困难报告、"
            "比较语义不充分和模型易错样本，Sol 也可能误判。",
            "- 本审计没有改标签、删样本、调整划分、训练或读取 Internal-test/Gold。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    _require_private_path(path)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    materialized = [dict(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(materialized[0]))
        writer.writeheader()
        writer.writerows(materialized)


def _write_text(path: Path, value: str) -> None:
    _require_private_path(path)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def compare_tier_a_sol_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare complete private Tier-A Sol labels with frozen Luna labels"
    )
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--sol-output-dir", type=Path, required=True)
    parser.add_argument("--comparison-csv", type=Path, required=True)
    parser.add_argument("--comparison-jsonl", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    args = parser.parse_args(argv)
    for output in (
        args.comparison_csv,
        args.comparison_jsonl,
        args.summary_output,
        args.report_output,
        args.receipt_output,
    ):
        _require_private_path(output)
    candidates = [validate_sample(row) for row in read_jsonl(args.candidates)]
    sol_rows = load_sol_outputs(args.sol_output_dir)
    comparisons, summary = compare_luna_sol(candidates, sol_rows)
    _write_csv(args.comparison_csv, comparisons)
    write_jsonl_atomic(args.comparison_jsonl, comparisons)
    write_json_atomic(args.summary_output, summary)
    _write_text(args.report_output, render_internal_report(summary))
    receipt = {
        "schema": "prta-cxr.tier-a-sol-luna-comparison-receipt.v1",
        "status": "PASS_COMPLETE_TIER_A_SOL_LUNA_COMPARISON",
        "rows": len(comparisons),
        "candidate_file_sha256": sha256_file(args.candidates),
        "comparison_csv_sha256": sha256_file(args.comparison_csv),
        "comparison_jsonl_sha256": sha256_file(args.comparison_jsonl),
        "summary_sha256": sha256_file(args.summary_output),
        "report_sha256": sha256_file(args.report_output),
        "agreement_is_accuracy": False,
        "training_or_data_mutation_performed": False,
        "sealed_splits_opened": False,
    }
    write_json_atomic(args.receipt_output, receipt)
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _collective_sol_hash(output_dir: Path) -> str:
    files = sorted(output_dir.glob("batch_*.json"))
    return canonical_sha256(
        [{"name": path.name, "sha256": sha256_file(path)} for path in files]
    )


def _hash_bypassed_rows(path: Path, train_ids: set[str]) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            match = _SAMPLE_ID_PATTERN.search(raw_line)
            if match is None:
                raise RuntimeError("output line has no simple sample_id")
            sample_id = match.group(1).decode("utf-8")
            if sample_id not in train_ids:
                count += 1
                digest.update(raw_line)
    return count, digest.hexdigest()


def apply_tier_a_sol_labels_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a Sol-authoritative versioned Train label manifest"
    )
    parser.add_argument("--train-dev-manifest", type=Path, required=True)
    parser.add_argument("--train-ids-csv", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--sol-output-dir", type=Path, required=True)
    parser.add_argument("--train-output", type=Path, required=True)
    parser.add_argument("--train-dev-output", type=Path, required=True)
    parser.add_argument("--provenance-output", type=Path, required=True)
    parser.add_argument("--exclusions-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    args = parser.parse_args(argv)

    for input_path in (
        args.train_dev_manifest,
        args.train_ids_csv,
        args.candidates,
        args.sol_output_dir,
    ):
        _require_unsealed_input(input_path)
    for output_path in (
        args.train_output,
        args.train_dev_output,
        args.provenance_output,
        args.exclusions_output,
        args.receipt_output,
    ):
        _require_private_path(output_path)

    input_hashes_before = {
        "train_dev_manifest": sha256_file(args.train_dev_manifest),
        "train_ids_csv": sha256_file(args.train_ids_csv),
        "candidates": sha256_file(args.candidates),
        "sol_outputs_collective": _collective_sol_hash(args.sol_output_dir),
    }
    train_ids = load_train_id_allowlist(args.train_ids_csv)
    candidates = [validate_sample(row) for row in read_jsonl(args.candidates)]
    sol_rows = load_sol_outputs(args.sol_output_dir)
    provenance, exclusions, audit = apply_sol_authority_stream(
        source_manifest=args.train_dev_manifest,
        train_ids=train_ids,
        candidates=candidates,
        sol_rows=sol_rows,
        train_output=args.train_output,
        train_dev_output=args.train_dev_output,
    )
    write_jsonl_atomic(args.provenance_output, provenance)
    write_jsonl_atomic(args.exclusions_output, exclusions)

    bypassed_count, bypassed_hash = _hash_bypassed_rows(
        args.train_dev_output, train_ids
    )
    if bypassed_count != audit["dev_rows_copied_byte_exact"]:
        raise RuntimeError("independent Dev row count verification failed")
    if bypassed_hash != audit["dev_raw_sha256"]:
        raise RuntimeError("Dev raw rows changed in the new combined manifest")
    input_hashes_after = {
        "train_dev_manifest": sha256_file(args.train_dev_manifest),
        "train_ids_csv": sha256_file(args.train_ids_csv),
        "candidates": sha256_file(args.candidates),
        "sol_outputs_collective": _collective_sol_hash(args.sol_output_dir),
    }
    if input_hashes_after != input_hashes_before:
        raise RuntimeError("an input changed during Sol-authority materialization")

    receipt = {
        "schema": "prta-cxr.tier-a-sol-authoritative-label-receipt.v1",
        "status": "PASS_SOL_AUTHORITATIVE_TRAIN_LABEL_VERSION",
        "decision_authority": "user_attested_human_review_2026-08-04",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "input_hashes": input_hashes_before,
        "audit": audit,
        "transition_counts": _count_by(
            provenance, ("luna_label", "sol_label")
        ),
        "authority_counts_by_source": _count_by(provenance, ("source",)),
        "exclusion_counts_by_source": _count_by(exclusions, ("source",)),
        "output_hashes": {
            "train_manifest": sha256_file(args.train_output),
            "train_dev_manifest": sha256_file(args.train_dev_output),
            "provenance": sha256_file(args.provenance_output),
            "exclusions": sha256_file(args.exclusions_output),
        },
        "old_artifacts_mutated": False,
        "dev_rows_modified": 0,
        "internal_test_or_gold_opened": False,
        "training_started": False,
    }
    write_json_atomic(args.receipt_output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _partition_manifest(
    path: Path, train_allowlist: set[str]
) -> tuple[dict[str, dict[str, Any]], int, str, str]:
    train_rows: dict[str, dict[str, Any]] = {}
    train_digest = hashlib.sha256()
    other_digest = hashlib.sha256()
    other_rows = 0
    with path.open("rb") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            match = _SAMPLE_ID_PATTERN.search(raw_line)
            if match is None:
                raise RuntimeError("manifest line has no simple sample_id")
            sample_id = match.group(1).decode("utf-8")
            if sample_id not in train_allowlist:
                other_rows += 1
                other_digest.update(raw_line)
                continue
            if sample_id in train_rows:
                raise RuntimeError("duplicate Train ID during independent audit")
            value = json.loads(raw_line)
            if value.get("split") != "train":
                raise RuntimeError("Train allowlist row has a non-Train split")
            train_rows[sample_id] = value
            train_digest.update(raw_line)
    return (
        train_rows,
        other_rows,
        train_digest.hexdigest(),
        other_digest.hexdigest(),
    )


def audit_tier_a_sol_labels_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently audit the Sol-authoritative Train label version"
    )
    parser.add_argument("--source-train-dev", type=Path, required=True)
    parser.add_argument("--new-train", type=Path, required=True)
    parser.add_argument("--new-train-dev", type=Path, required=True)
    parser.add_argument("--train-ids-csv", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args(argv)
    for path in (
        args.source_train_dev,
        args.new_train,
        args.new_train_dev,
        args.train_ids_csv,
        args.provenance,
        args.exclusions,
        args.receipt,
    ):
        _require_unsealed_input(path)
    _require_private_path(args.audit_output)

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    train_ids = load_train_id_allowlist(args.train_ids_csv)
    provenance = _read_jsonl(args.provenance)
    exclusions = _read_jsonl(args.exclusions)
    provenance_by_id = {row["sample_id"]: row for row in provenance}
    exclusion_by_id = {row["sample_id"]: row for row in exclusions}
    if len(provenance_by_id) != 3572 or len(exclusion_by_id) != 294:
        raise RuntimeError("provenance/exclusion uniqueness mismatch")
    if set(provenance_by_id) & set(exclusion_by_id):
        raise RuntimeError("a sample is both retained and excluded")

    old_train, old_dev_count, _, old_dev_hash = _partition_manifest(
        args.source_train_dev, train_ids
    )
    new_train, new_train_other_count, new_train_raw_hash, _ = _partition_manifest(
        args.new_train, train_ids
    )
    combined_train, new_dev_count, combined_train_raw_hash, new_dev_hash = (
        _partition_manifest(args.new_train_dev, train_ids)
    )
    if len(old_train) != TRAIN_ROWS or len(new_train) != TRAIN_AFTER_UNCLEAR_EXCLUSION:
        raise RuntimeError("independent Train row count mismatch")
    if new_train_other_count != 0:
        raise RuntimeError("Train-only output contains a non-Train row")
    if old_dev_count != DEV_ROWS or new_dev_count != DEV_ROWS:
        raise RuntimeError("independent Dev row count mismatch")
    if old_dev_hash != new_dev_hash:
        raise RuntimeError("Dev bytes differ between source and new combined manifest")
    if new_train_raw_hash != combined_train_raw_hash:
        raise RuntimeError("Train-only and combined Train bytes differ")
    if set(combined_train) != set(new_train):
        raise RuntimeError("combined and Train-only ID sets differ")
    if set(new_train) != set(old_train) - set(exclusion_by_id):
        raise RuntimeError("new Train IDs do not equal old IDs minus exclusions")

    changed = 0
    rebound = 0
    unchanged = 0
    old_distribution: Counter[str] = Counter()
    new_distribution: Counter[str] = Counter()
    for sample_id, old in old_train.items():
        old_distribution[old["progression_label"]] += 1
        if sample_id in exclusion_by_id:
            if exclusion_by_id[sample_id]["sol_label"] != "Unclear":
                raise RuntimeError("excluded row is not Sol Unclear")
            continue
        new = new_train[sample_id]
        new_distribution[new["progression_label"]] += 1
        for key, value in old.items():
            if key not in {"progression_label", "label_source"}:
                if new.get(key) != value:
                    raise RuntimeError("non-label/provenance field changed")
        if sample_id in provenance_by_id:
            evidence = provenance_by_id[sample_id]
            if new["progression_label"] != evidence["sol_label"]:
                raise RuntimeError("new label differs from Sol provenance")
            if new["label_source"] != SOL_AUTHORITY_SOURCE:
                raise RuntimeError("new label source is not Sol-authoritative")
            if evidence["label_value_changed"]:
                changed += 1
            else:
                rebound += 1
        else:
            if new != old:
                raise RuntimeError("non-Tier-A Train row changed")
            unchanged += 1
    if (changed, rebound, unchanged) != (570, 3002, 87199):
        raise RuntimeError("independent action counts changed")

    expected_hashes = receipt["output_hashes"]
    actual_hashes = {
        "train_manifest": sha256_file(args.new_train),
        "train_dev_manifest": sha256_file(args.new_train_dev),
        "provenance": sha256_file(args.provenance),
        "exclusions": sha256_file(args.exclusions),
    }
    if actual_hashes != expected_hashes:
        raise RuntimeError("output hashes differ from the materialization receipt")
    audit = {
        "schema": "prta-cxr.tier-a-sol-authoritative-independent-audit.v1",
        "status": "PASS_SOL_AUTHORITATIVE_INDEPENDENT_AUDIT",
        "source_train_rows": len(old_train),
        "new_train_rows": len(new_train),
        "new_train_dev_rows": len(new_train) + new_dev_count,
        "sol_authoritative_rows": len(provenance_by_id),
        "label_value_changed_rows": changed,
        "authority_rebound_same_label_rows": rebound,
        "excluded_sol_unclear_rows": len(exclusion_by_id),
        "unchanged_non_tier_a_train_rows": unchanged,
        "dev_rows_byte_identical": new_dev_count,
        "dev_raw_sha256": new_dev_hash,
        "train_bytes_equal_between_outputs": True,
        "old_label_distribution": dict(sorted(old_distribution.items())),
        "new_label_distribution": dict(sorted(new_distribution.items())),
        "verified_output_hashes": actual_hashes,
        "internal_test_or_gold_opened": False,
        "training_started": False,
    }
    write_json_atomic(args.audit_output, audit)
    print(json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False))
    return 0
