from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from prta_cxr.contracts import sha256_file


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_phase20_public_summary(final_path: Path) -> dict[str, Any]:
    value = _read_json(final_path)
    required = {
        "status": "PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE",
        "expected_job_count": 88,
        "unique_pass_count": 88,
        "training_cell_count": 63,
        "transformed_map_count": 19,
        "source_held_evaluation_count": 6,
        "selection_performed": False,
        "winner_selected": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise ValueError(f"Phase20-A public-summary gate failed: {key}")
    training = dict(value.get("training_three_seed_summary", {}))
    source_held = dict(value.get("source_held_three_seed_summary", {}))
    if len(training) != 21 or len(source_held) != 2:
        raise ValueError("Phase20-A three-Seed group count drift")
    return {
        "schema": "prta-cxr.phase20-a-public-three-seed-summary.v1",
        "status": "PASS_PHASE20_A_PUBLIC_THREE_SEED_SUMMARY",
        "source_finalizer_sha256": sha256_file(final_path),
        "source_commit": value["source_commit"],
        "counts": {
            "jobs": 88,
            "training_cells": 63,
            "transformed_maps": 19,
            "source_held_evaluations": 6,
            "training_three_seed_groups": 21,
            "source_held_three_seed_groups": 2,
        },
        "training_three_seed_summary": training,
        "source_held_three_seed_summary": source_held,
        "selection_performed": False,
        "winner_selected": False,
        "external_evaluation_included": False,
        "protected_outcome_read_count": 0,
    }


def _mean_sd(metrics: Mapping[str, Any], name: str) -> str:
    value = dict(metrics[name])
    return f"{float(value['mean']):.6f} ± {float(value['sample_sd']):.6f}"


def render_phase20_public_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Phase20-A 88-job 正式收口与三 Seed 汇总",
        "",
        "> 状态：`PASS_PHASE20_A_PUBLIC_THREE_SEED_SUMMARY`。本页只包含聚合 Dev",
        "> 指标，不包含 checkpoint、患者级预测、影像、报告、原始日志或私有路径。",
        (
            "> 本轮未进行选模或 winner 重选，也未读取 external、Internal-test、"
            "Gold 或医生数据。"
        ),
        "",
        "## 完整性核验",
        "",
        "| 项目 | 结果 |",
        "|---|---:|",
        "| 唯一 terminal PASS | 88 / 88 |",
        "| 训练单元 | 63 |",
        "| 变换 map | 19 |",
        "| source-held evaluation | 6 |",
        "| 完整训练三 Seed组 | 21 / 21 |",
        "| 完整 source-held 三 Seed组 | 2 / 2 |",
        f"| 全局 finalizer SHA-256 | `{summary['source_finalizer_sha256']}` |",
        "",
        "## 训练三 Seed mean ± sample SD",
        "",
        (
            "| 实验 | Macro-F1 ↑ | Balanced accuracy ↑ | Min recall ↑ | "
            "ODER ↓ | NLL ↓ | Brier ↓ |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for experiment, row in dict(summary["training_three_seed_summary"]).items():
        metrics = dict(row["metrics"])
        lines.append(
            f"| `{experiment}` | {_mean_sd(metrics, 'macro_f1')} | "
            f"{_mean_sd(metrics, 'balanced_accuracy')} | "
            f"{_mean_sd(metrics, 'min_class_recall')} | "
            f"{_mean_sd(metrics, 'opposite_direction_error_rate')} | "
            f"{_mean_sd(metrics, 'nll')} | {_mean_sd(metrics, 'brier')} |"
        )
    lines.extend(
        [
            "",
            "## 双向 source-held 跨来源泛化",
            "",
            (
                "下表是目标域 ordinary patient-observation 指标；完整 "
                "patient-balanced 与逐类"
            ),
            "F1/Recall 的 mean ± sample SD 保存在配套 JSON。该实验属于跨来源域泛化，",
            "不称为独立外部临床验证。",
            "",
            (
                "| 训练组 | 目标来源 | 样本 / 患者 | Macro-F1 ↑ | "
                "Balanced accuracy ↑ | Min recall ↑ | ODER ↓ |"
            ),
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for experiment, row in dict(summary["source_held_three_seed_summary"]).items():
        metrics = dict(dict(dict(row["scopes"])["ordinary"])["metrics"])
        lines.append(
            f"| `{experiment}` | `{row['target_source']}` | "
            f"{row['rows']} / {row['patients']} | {_mean_sd(metrics, 'macro_f1')} | "
            f"{_mean_sd(metrics, 'balanced_accuracy')} | "
            f"{_mean_sd(metrics, 'min_class_recall')} | "
            f"{_mean_sd(metrics, 'opposite_direction_error_rate')} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- `Slim-S1` 主线继续冻结；本 finalizer 只对账与汇总，不按结果改方法。",
            "- 21 组均固定 Seeds 17/28/43，报告 mean ± sample SD，不报告 best seed。",
            (
                "- comparator 24-cell 与后续 B1/B2 有独立 finalizer，"
                "本页不提前混入其结果。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def phase20_training_report_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the Git-safe Phase20-A summary"
    )
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = build_phase20_public_summary(args.final.resolve())
    _write_new(
        args.json_output,
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    _write_new(args.markdown_output, render_phase20_public_markdown(summary))
    return 0
