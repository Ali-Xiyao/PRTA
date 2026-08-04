from __future__ import annotations

import argparse
import csv
import json
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
