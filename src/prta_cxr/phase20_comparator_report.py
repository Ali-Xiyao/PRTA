from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_comparator_finalize import (
    COMPARISON_PROTOCOL,
    _method_summary,
)
from prta_cxr.phase20_comparator_program import COMPARATOR_SPECS, COMPARATOR_STATUS
from prta_cxr.phase20_training_finalize import (
    _closed,
    _read_json,
    _write_new_json,
    validate_phase20_training_job,
)

HOST_STATUS = "PHASE20_COMPARATOR_INTERIM_HOST_SNAPSHOT_VALIDATED"
PUBLIC_STATUS = "PHASE20_COMPARATOR_INTERIM_PARTIAL_NO_SELECTION"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_running_state(
    state: Mapping[str, Any],
    job: Mapping[str, Any],
    *,
    source_commit: str,
    queue_sha256: str,
) -> None:
    job_id = str(job["job_id"])
    if (
        state.get("schema") != "prta-cxr.phase20-job-state.v1"
        or state.get("status") != "RUNNING"
        or state.get("job_id") != job_id
        or state.get("group") != job.get("group")
        or state.get("lane") != job.get("lane")
        or state.get("source_commit") != source_commit
        or state.get("queue_sha256") != queue_sha256
    ):
        raise ValueError(f"invalid comparator RUNNING state: {job_id}")
    _closed(state, label=f"comparator running state {job_id}")


def _validated_method_row(row: Mapping[str, Any], program_root: Path) -> dict[str, Any]:
    value = dict(row)
    config = _read_json(program_root / "configs" / f"{value['experiment_id']}.json")
    method = str(config["phase20_role"])
    if method not in COMPARATOR_SPECS:
        raise ValueError(f"unknown comparator method: {method}")
    if (
        config.get("official_implementation") is not False
        or config.get("official_checkpoint") is not False
        or config.get("method_provenance")
        != COMPARATOR_SPECS[method]["method_provenance"]
    ):
        raise ValueError(f"comparator provenance drift: {method}")
    return {
        **value,
        "method": method,
        "method_provenance": config["method_provenance"],
        "comparison_protocol": COMPARISON_PROTOCOL[method],
        "official_implementation": False,
        "official_checkpoint": False,
    }


def build_interim_host_snapshot(
    program_root: Path,
    state_roots: Mapping[str, Path],
    artifact_roots: Mapping[str, Path],
    *,
    host: str,
) -> dict[str, Any]:
    if host not in {"server", "local"}:
        raise ValueError("interim comparator host must be server or local")
    if set(state_roots) != set(artifact_roots) or not state_roots:
        raise ValueError("comparator state/artifact root labels must match")
    preparation_path = program_root / "preparation_receipt.json"
    registry_path = program_root / "job_registry.json"
    input_manifest_path = program_root / "input_manifest.json"
    preparation = _read_json(preparation_path)
    registry = _read_json(registry_path)
    input_manifest = _read_json(input_manifest_path)
    _closed(preparation, label="comparator preparation")
    _closed(input_manifest, label="comparator inputs")
    if (
        preparation.get("status") != COMPARATOR_STATUS
        or preparation.get("registry_sha256") != sha256_file(registry_path)
        or preparation.get("input_manifest_sha256") != sha256_file(input_manifest_path)
        or int(preparation.get("training_cell_count", -1)) != 24
    ):
        raise ValueError("frozen comparator program identity drift")
    expected = {
        str(job["job_id"]): dict(job)
        for job in registry.get("jobs", [])
        if str(job.get("host")) == host
    }
    if not expected:
        raise ValueError("interim comparator host selection is empty")
    attempts: dict[str, list[tuple[dict[str, Any], str, str]]] = defaultdict(list)
    for label, root in state_roots.items():
        if not root.is_dir():
            raise ValueError(f"comparator state root unavailable: {label}")
        for path in sorted(root.glob("*.json")):
            value = _read_json(path)
            job_id = str(value.get("job_id", ""))
            if (
                value.get("schema") == "prta-cxr.phase20-job-state.v1"
                and job_id in expected
            ):
                attempts[job_id].append((value, label, sha256_file(path)))

    cells: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    frozen_inputs = dict(input_manifest["input_sha256"])
    for job_id, job in expected.items():
        values = attempts.get(job_id, [])
        if len(values) > 1:
            raise ValueError(f"duplicate comparator state attempts: {job_id}")
        if not values:
            statuses.append(
                {
                    "job_id": job_id,
                    "method": str(job["method"]),
                    "seed": int(job["seed"]),
                    "lane": str(job["lane"]),
                    "status": "PENDING",
                }
            )
            continue
        state, label, state_sha256 = values[0]
        status = str(state.get("status", ""))
        queue_sha256 = str(preparation["queue_hashes"][f"{job['lane']}.json"])
        if status == "PASS":
            row = validate_phase20_training_job(
                job,
                state,
                program_root=program_root,
                program_source_commit=str(preparation["source_commit"]),
                queue_sha256=queue_sha256,
                frozen_inputs=frozen_inputs,
            )
            cells.append(_validated_method_row(row, program_root))
        elif status == "RUNNING":
            _validate_running_state(
                state,
                job,
                source_commit=str(preparation["source_commit"]),
                queue_sha256=queue_sha256,
            )
        elif status not in {"FAILED", "SKIPPED"}:
            raise ValueError(f"unsupported comparator state status: {job_id}/{status}")
        statuses.append(
            {
                "job_id": job_id,
                "method": str(job["method"]),
                "seed": int(job["seed"]),
                "lane": str(job["lane"]),
                "status": status,
                "state_sha256": state_sha256,
                "artifact_root_label": label,
            }
        )
    counts = {
        status: sum(row["status"] == status for row in statuses)
        for status in ("PASS", "RUNNING", "PENDING", "FAILED", "SKIPPED")
    }
    if counts["PASS"] != len(cells):
        raise ValueError("interim comparator PASS cell count drift")
    return {
        "schema": "prta-cxr.phase20-comparator-interim-host.v1",
        "status": HOST_STATUS,
        "created_at": _now(),
        "host": host,
        "program_preparation_sha256": sha256_file(preparation_path),
        "source_commit": preparation["source_commit"],
        "expected_cell_count": len(expected),
        "counts": counts,
        "job_status": sorted(statuses, key=lambda row: str(row["job_id"])),
        "cells": sorted(cells, key=lambda row: str(row["job_id"])),
        "selection_performed": False,
        "winner_selected": False,
        "official_implementation_included": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def _public_cell(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "job_id",
            "experiment_id",
            "method",
            "seed",
            "hardware_class",
            "best_epoch",
            "completed_epochs",
            "duration_seconds",
            "metrics",
            "ordinary",
            "parameter_audit",
            "method_provenance",
            "comparison_protocol",
            "official_implementation",
            "official_checkpoint",
            "checkpoint_sha256",
            "training_receipt_sha256",
        )
    }


def merge_interim_host_snapshots(
    program_root: Path, snapshots: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if len(snapshots) != 2 or {str(value.get("host")) for value in snapshots} != {
        "server",
        "local",
    }:
        raise ValueError("interim merge requires one server and one local snapshot")
    preparation_path = program_root / "preparation_receipt.json"
    registry_path = program_root / "job_registry.json"
    preparation = _read_json(preparation_path)
    registry = _read_json(registry_path)
    expected_jobs = {str(job["job_id"]) for job in registry.get("jobs", [])}
    preparation_sha = sha256_file(preparation_path)
    statuses: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    for snapshot in snapshots:
        _closed(snapshot, label=f"interim comparator snapshot {snapshot.get('host')}")
        if (
            snapshot.get("status") != HOST_STATUS
            or snapshot.get("program_preparation_sha256") != preparation_sha
            or snapshot.get("source_commit") != preparation.get("source_commit")
        ):
            raise ValueError("interim comparator host identity drift")
        statuses.extend(dict(row) for row in snapshot.get("job_status", []))
        cells.extend(dict(row) for row in snapshot.get("cells", []))
    observed_jobs = [str(row["job_id"]) for row in statuses]
    if (
        len(observed_jobs) != len(set(observed_jobs))
        or set(observed_jobs) != expected_jobs
    ):
        raise ValueError("interim comparator snapshots have duplicate or missing jobs")
    pass_jobs = {str(row["job_id"]) for row in statuses if row["status"] == "PASS"}
    if {str(row["job_id"]) for row in cells} != pass_jobs:
        raise ValueError("interim comparator cell/status drift")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cells:
        grouped[str(row["method"])].append(row)
    method_results: dict[str, Any] = {}
    for method in COMPARATOR_SPECS:
        values = sorted(grouped.get(method, []), key=lambda row: int(row["seed"]))
        available = [int(row["seed"]) for row in values]
        pending = [seed for seed in (17, 28, 43) if seed not in available]
        method_results[method] = {
            "status": "COMPLETE_THREE_SEED" if not pending else "PENDING_THREE_SEED",
            "available_seeds": available,
            "pending_seeds": pending,
            "method_provenance": COMPARATOR_SPECS[method]["method_provenance"],
            "comparison_protocol": COMPARISON_PROTOCOL[method],
            "official_implementation": False,
            "official_checkpoint": False,
            "three_seed_summary": _method_summary(values) if not pending else None,
            "by_seed": {str(row["seed"]): _public_cell(row) for row in values},
        }
    counts = {
        status: sum(row["status"] == status for row in statuses)
        for status in ("PASS", "RUNNING", "PENDING", "FAILED", "SKIPPED")
    }
    return {
        "schema": "prta-cxr.phase20-comparator-interim-public.v1",
        "status": PUBLIC_STATUS,
        "snapshot_at": _now(),
        "program_preparation_sha256": preparation_sha,
        "source_commit": preparation["source_commit"],
        "expected_cell_count": 24,
        "counts": counts,
        "complete_three_seed_method_count": sum(
            value["status"] == "COMPLETE_THREE_SEED"
            for value in method_results.values()
        ),
        "methods": method_results,
        "terminal_pass_cells": sorted(
            (_public_cell(row) for row in cells), key=lambda row: str(row["job_id"])
        ),
        "incomplete_cells": sorted(
            (
                {
                    key: row[key]
                    for key in ("job_id", "method", "seed", "lane", "status")
                }
                for row in statuses
                if row["status"] != "PASS"
            ),
            key=lambda row: str(row["job_id"]),
        ),
        "finalizer_status": "PENDING_24_OF_24",
        "selection_performed": False,
        "winner_selected": False,
        "official_implementation_included": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def _mean_sd(method: Mapping[str, Any], metric: str) -> str:
    summary = method.get("three_seed_summary")
    if not isinstance(summary, Mapping):
        return "待汇总"
    value = dict(summary["scalar_metrics"])[metric]
    return f"{float(value['mean']):.4f} ± {float(value['sample_sd']):.4f}"


def render_interim_markdown(summary: Mapping[str, Any]) -> str:
    counts = dict(summary["counts"])
    lines = [
        "# Phase20 comparator 阶段性结果（仅 terminal PASS）",
        "",
        "> 本页是写作快照，不是 24/24 正式 finalizer。只收录已通过完整",
        "> checkpoint/receipt/config/input/hash 核验的 terminal PASS 单元；未齐三",
        "> Seed 的方法统一标为“待跑/待汇总”，不做 winner 选择。",
        "",
        "## 快照完整性",
        "",
        "| 项目 | 数量 |",
        "|---|---:|",
        f"| 冻结 comparator 单元 | {summary['expected_cell_count']} |",
        f"| terminal PASS | {counts['PASS']} |",
        f"| RUNNING | {counts['RUNNING']} |",
        f"| PENDING | {counts['PENDING']} |",
        f"| FAILED / SKIPPED | {counts['FAILED']} / {counts['SKIPPED']} |",
        (
            "| 已齐三 Seed 方法 | "
            f"{summary['complete_three_seed_method_count']} / {len(COMPARATOR_SPECS)} |"
        ),
        "| 正式 comparator finalizer | 待 24/24 |",
        "",
        "## 方法级三 Seed阶段表",
        "",
        "| 方法 | Seed 状态 | Macro-F1 ↑ | Balanced accuracy ↑ | ODER ↓ | 结论状态 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for method, value in dict(summary["methods"]).items():
        available = "/".join(map(str, value["available_seeds"])) or "无"
        pending = "/".join(map(str, value["pending_seeds"])) or "无"
        status = (
            "可写三 Seed描述性结果" if not value["pending_seeds"] else "待跑/待汇总"
        )
        lines.append(
            f"| `{method}` | 已有 {available}；缺 {pending} | "
            f"{_mean_sd(value, 'macro_f1')} | "
            f"{_mean_sd(value, 'balanced_accuracy')} | "
            f"{_mean_sd(value, 'opposite_direction_error_rate')} | {status} |"
        )
    lines.extend(
        [
            "",
            "## 已完成单元逐 Seed结果",
            "",
            (
                "| 方法 | Seed | Macro-F1 | Balanced accuracy | Min recall | "
                "ODER | Best epoch |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary["terminal_pass_cells"]:
        metrics = dict(row["metrics"])
        lines.append(
            f"| `{row['method']}` | {row['seed']} | {float(metrics['macro_f1']):.4f} | "
            f"{float(metrics['balanced_accuracy']):.4f} | "
            f"{float(metrics['min_class_recall']):.4f} | "
            f"{float(metrics['opposite_direction_error_rate']):.4f} | "
            f"{row['best_epoch']} |"
        )
    lines.extend(
        [
            "",
            "## 未完成单元",
            "",
            "| 方法 | Seed | 当前状态 | 论文表处理 |",
            "|---|---:|---|---|",
        ]
    )
    for row in summary["incomplete_cells"]:
        label = "待跑" if row["status"] == "PENDING" else "运行中，待汇总"
        if row["status"] in {"FAILED", "SKIPPED"}:
            label = "异常，禁止填数"
        lines.append(
            f"| `{row['method']}` | {row['seed']} | `{row['status']}` | {label} |"
        )
    lines.extend(
        [
            "",
            "## 写作边界",
            "",
            (
                "- 本快照只允许描述已齐三 Seed 方法的观察性 Dev 结果，"
                "不做显著性或最终排名结论。"
            ),
            (
                "- 未齐三 Seed 的方法在主表中保留行，但指标单元格写“待汇总”，"
                "不得用单 Seed 代替。"
            ),
            (
                "- 所有比较器均为内部、架构启发或论文式复现，"
                "不声称官方实现或官方 checkpoint。"
            ),
            (
                "- 正式结论仍以 24/24 comparator finalizer 和后续 B1/B2 "
                "evidence finalizer 为准。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def phase20_comparator_report_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a Git-safe interim Phase20 comparator snapshot"
    )
    parser.add_argument("--comparator-program", type=Path, required=True)
    parser.add_argument("--state-root", action="append")
    parser.add_argument("--artifact-root", action="append")
    parser.add_argument("--host", choices=("server", "local"))
    parser.add_argument("--snapshot", type=Path, action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)

    def parse(values: Sequence[str] | None, option: str) -> dict[str, Path]:
        result = {}
        for raw in values or []:
            if "=" not in raw:
                parser.error(f"{option} must use LABEL=PATH")
            label, path = raw.split("=", 1)
            if not label or label in result:
                parser.error(f"{option} labels must be unique")
            result[label] = Path(path)
        return result

    program = args.comparator_program.resolve()
    if args.snapshot:
        if len(args.snapshot) != 2 or not args.json_output or not args.markdown_output:
            parser.error(
                "snapshot merge requires two snapshots and JSON/Markdown outputs"
            )
        snapshots = [_read_json(path) for path in args.snapshot]
        result = merge_interim_host_snapshots(program, snapshots)
        _write_new_json(args.json_output, result)
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(
            render_interim_markdown(result), encoding="utf-8"
        )
        return 0
    if (
        not args.host
        or not args.output
        or not args.state_root
        or not args.artifact_root
    ):
        parser.error("host snapshot requires host/state/artifact/output")
    result = build_interim_host_snapshot(
        program,
        parse(args.state_root, "--state-root"),
        parse(args.artifact_root, "--artifact-root"),
        host=args.host,
    )
    _write_new_json(args.output, result)
    return 0
