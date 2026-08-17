from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import replace_json_atomic, write_json_atomic
from prta_cxr.authorization import (
    FORMAL_ENV_NAME,
    FORMAL_ENV_VALUE,
    require_formal_authorization,
)
from prta_cxr.contracts import sha256_file
from prta_cxr.provenance import resolve_source_commit

INTERVENTIONS = ("true", "matched_hard", "null", "reversed")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _relative_file(root: Path, value: str, *, role: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{role} must be a safe runtime-relative path")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{role} escapes runtime root") from error
    if not path.is_file():
        raise FileNotFoundError(f"missing {role}: {path}")
    return path


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as stream:
        return sum(1 for _ in stream)


def validate_diagnostic_output(
    output: Path,
    *,
    run_id: str,
    checkpoint: Path,
    training_receipt_path: Path,
) -> dict[str, Any]:
    receipt_path = output / "ifusion_dev_diagnostic_receipt.json"
    receipt = _read_json(receipt_path)
    training_receipt = _read_json(training_receipt_path)
    if receipt.get("schema") != "prta-cxr.ifusion-dev-diagnostic.v1":
        raise ValueError(f"unsupported diagnostic schema: {run_id}")
    if receipt.get("status") != "PASS_IFUSION_TRAIN_DEV_PRIOR_DIAGNOSTIC":
        raise ValueError(f"diagnostic is not terminal PASS: {run_id}")
    if receipt.get("evidence_status") != "PENDING_PAIRED_BOOTSTRAP":
        raise ValueError(f"unexpected diagnostic evidence state: {run_id}")
    if receipt.get("experiment_id") != run_id:
        raise ValueError(f"diagnostic experiment identity drift: {run_id}")
    if receipt.get("checkpoint_only") is not True:
        raise ValueError(f"diagnostic is not checkpoint-only: {run_id}")
    if receipt.get("internal_test_opened") is not False:
        raise ValueError(f"diagnostic opened Internal-test: {run_id}")
    if receipt.get("gold_opened") is not False:
        raise ValueError(f"diagnostic opened gold: {run_id}")
    if receipt.get("protected_outcome_read_count") != 0:
        raise ValueError(f"diagnostic protected-read drift: {run_id}")
    if receipt.get("checkpoint_sha256") != sha256_file(checkpoint):
        raise ValueError(f"diagnostic checkpoint hash drift: {run_id}")
    if receipt.get("training_receipt_sha256") != sha256_file(training_receipt_path):
        raise ValueError(f"diagnostic training-receipt hash drift: {run_id}")

    blocks = receipt.get("prediction_blocks")
    if not isinstance(blocks, Mapping) or set(blocks) != set(INTERVENTIONS):
        raise ValueError(f"diagnostic intervention block drift: {run_id}")
    block_summary: dict[str, Any] = {}
    for intervention in INTERVENTIONS:
        record = blocks[intervention]
        if not isinstance(record, Mapping):
            raise ValueError(
                f"invalid prediction block record: {run_id}/{intervention}"
            )
        relative = Path(str(record.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe prediction block path: {run_id}/{intervention}")
        path = output / relative
        observed_rows = _line_count(path)
        if observed_rows != int(record.get("rows", -1)):
            raise ValueError(f"prediction row-count drift: {run_id}/{intervention}")
        observed_sha256 = sha256_file(path)
        if observed_sha256 != record.get("sha256"):
            raise ValueError(f"prediction hash drift: {run_id}/{intervention}")
        block_summary[intervention] = {
            "rows": observed_rows,
            "sha256": observed_sha256,
        }

    interventions = receipt.get("interventions")
    if not isinstance(interventions, Mapping) or set(interventions) != set(
        INTERVENTIONS
    ):
        raise ValueError(f"diagnostic intervention metric drift: {run_id}")
    true_macro_f1 = float(interventions["true"]["metrics"]["ordinary"]["macro_f1"])
    training_macro_f1 = float(training_receipt["best_dev_macro_f1"])
    metric_delta = true_macro_f1 - training_macro_f1
    if abs(metric_delta) > 1e-12:
        raise ValueError(
            f"diagnostic true-PRIOR metric drift: {run_id} ({metric_delta})"
        )
    return {
        "run_id": run_id,
        "seed": int(receipt["seed"]),
        "variant": str(receipt["variant"]),
        "receipt_sha256": sha256_file(receipt_path),
        "true_macro_f1": true_macro_f1,
        "training_best_dev_macro_f1": training_macro_f1,
        "metric_delta": metric_delta,
        "prediction_blocks": block_summary,
        "zero_protected_reads": True,
    }


def _diagnostic_command(
    args: argparse.Namespace,
    *,
    checkpoint: Path,
    training_receipt: Path,
    output: Path,
) -> list[str]:
    command = [
        sys.executable,
        str(args.source / "scripts/45_evaluate_prta_v2_mechanisms.py"),
        "--checkpoint",
        str(checkpoint),
        "--training-receipt",
        str(training_receipt),
        "--split-manifest",
        str(args.split_manifest),
        "--cleaned-split-freeze",
        str(args.cleaned_split_freeze),
        "--cache-root",
        str(args.cache_root),
        "--text-cache",
        str(args.text_cache),
        "--matched-hard-prior-map",
        str(args.matched_hard_prior_map),
        "--weights",
        str(args.weights),
        "--label-quality-audit",
        str(args.label_quality_audit),
        "--output",
        str(output),
        "--device",
        str(args.device),
        "--batch-size",
        str(args.batch_size),
        "--diagnostic-scope",
        "ifusion_final",
        "--formal",
    ]
    if args.cleaned_split_platform_root is not None:
        command.extend(
            ["--cleaned-split-platform-root", str(args.cleaned_split_platform_root)]
        )
    if args.random_counterfactual_prior_map is not None:
        command.extend(
            [
                "--random-counterfactual-prior-map",
                str(args.random_counterfactual_prior_map),
            ]
        )
    return command


def run_ifusion_diagnostic_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one frozen Information Fusion diagnostic GPU lane"
    )
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--matched-hard-prior-map", type=Path, required=True)
    parser.add_argument("--random-counterfactual-prior-map", type=Path)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--visible-device-index", type=int)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")

    args.source = args.source.resolve()
    args.runtime_root = args.runtime_root.resolve()
    args.output_root = args.output_root.resolve()
    queue = _read_json(args.queue)
    if queue.get("schema") != "prta-cxr.ifusion-diagnostic-queue.v1":
        raise ValueError("unsupported Information Fusion diagnostic queue schema")
    if queue.get("status") != "PASS_IFUSION_DIAGNOSTIC_QUEUE_FROZEN":
        raise ValueError("Information Fusion diagnostic queue is not frozen")
    if queue.get("lane") != args.lane:
        raise ValueError("Information Fusion diagnostic lane identity drift")
    rows = queue.get("runs")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Information Fusion diagnostic queue is empty")
    run_ids = [str(row["run_id"]) for row in rows]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("duplicate run ID in Information Fusion diagnostic queue")

    lane_root = args.output_root / args.lane
    if lane_root.exists():
        raise FileExistsError(f"diagnostic lane output already exists: {lane_root}")
    (lane_root / "logs").mkdir(parents=True)
    progress_path = lane_root / "progress.json"
    failure_path = lane_root / "failure.json"
    completion_path = lane_root / "completion.json"
    source_commit = resolve_source_commit(args.source)
    progress: dict[str, Any] = {
        "schema": "prta-cxr.ifusion-diagnostic-lane-progress.v1",
        "status": "RUNNING",
        "created_at": _now(),
        "updated_at": _now(),
        "lane": args.lane,
        "source_commit": source_commit,
        "queue_sha256": sha256_file(args.queue),
        "current_run_id": None,
        "completed": [],
        "remaining": len(rows),
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(progress_path, progress)

    environment = os.environ.copy()
    environment.update(
        {
            FORMAL_ENV_NAME: FORMAL_ENV_VALUE,
            "PRTA_CXR_SOURCE_COMMIT": source_commit,
            "PYTHONUNBUFFERED": "1",
        }
    )
    if args.visible_device_index is not None:
        environment["CUDA_VISIBLE_DEVICES"] = str(args.visible_device_index)

    completed: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        run_id = str(row["run_id"])
        checkpoint = _relative_file(
            args.runtime_root, str(row["checkpoint"]), role=f"checkpoint/{run_id}"
        )
        training_receipt = _relative_file(
            args.runtime_root,
            str(row["training_receipt"]),
            role=f"training_receipt/{run_id}",
        )
        output = lane_root / "runs" / run_id
        log = lane_root / "logs" / f"{run_id}.log"
        if output.exists() or log.exists():
            raise FileExistsError(f"immutable diagnostic output exists: {run_id}")
        progress.update(
            {
                "updated_at": _now(),
                "current_run_id": run_id,
                "current_queue_index": index,
                "completed": completed,
                "remaining": len(rows) - index,
            }
        )
        replace_json_atomic(progress_path, progress)
        command = _diagnostic_command(
            args,
            checkpoint=checkpoint,
            training_receipt=training_receipt,
            output=output,
        )
        try:
            with log.open("xb") as stream:
                returncode = subprocess.run(
                    command,
                    cwd=args.source,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    check=False,
                ).returncode
            if returncode:
                raise RuntimeError(
                    f"diagnostic child failed: {run_id} (exit {returncode})"
                )
            completed.append(
                validate_diagnostic_output(
                    output,
                    run_id=run_id,
                    checkpoint=checkpoint,
                    training_receipt_path=training_receipt,
                )
            )
        except Exception as error:
            failure = {
                "schema": "prta-cxr.ifusion-diagnostic-lane-failure.v1",
                "status": "IFUSION_DIAGNOSTIC_LANE_FAILED_HOLD",
                "created_at": _now(),
                "lane": args.lane,
                "run_id": run_id,
                "error_type": type(error).__name__,
                "error": str(error),
                "completed": completed,
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            }
            write_json_atomic(failure_path, failure)
            replace_json_atomic(progress_path, {**failure, "updated_at": _now()})
            raise

    completion = {
        "schema": "prta-cxr.ifusion-diagnostic-lane-completion.v1",
        "status": "PASS_IFUSION_DIAGNOSTIC_LANE_COMPLETE",
        "created_at": _now(),
        "lane": args.lane,
        "source_commit": source_commit,
        "queue_sha256": sha256_file(args.queue),
        "completed": completed,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(completion_path, completion)
    replace_json_atomic(
        progress_path,
        {**completion, "updated_at": _now(), "current_run_id": None, "remaining": 0},
    )
    print(json.dumps(completion, indent=2, sort_keys=True))
    return 0
