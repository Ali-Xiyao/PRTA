from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file


class CloseoutError(RuntimeError):
    """Raised when a terminal Train/Dev closeout artifact drifts."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CloseoutError(f"expected JSON object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CloseoutError(message)


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _zero_protected(receipt: Mapping[str, Any], *, label: str) -> None:
    _require(
        receipt.get("internal_test_opened") is False, f"{label} opened Internal-test"
    )
    _require(receipt.get("gold_opened") in (None, False), f"{label} opened Gold")
    count = receipt.get(
        "protected_outcome_read_count",
        0 if receipt.get("protected_outcomes_opened") is False else -1,
    )
    _require(count == 0, f"{label} has protected reads")


def _mean_sd(values: Sequence[float]) -> dict[str, float | int]:
    return {
        "mean": float(mean(values)),
        "sample_sd": float(stdev(values)) if len(values) > 1 else 0.0,
        "n": len(values),
    }


def _duration_seconds(receipt: Mapping[str, Any]) -> float | None:
    start = receipt.get("start_time")
    end = receipt.get("end_time")
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    return float(
        (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    )


def _best_ordinary_metrics(receipt: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    history = receipt.get("history")
    best_epoch = receipt.get("best_epoch")
    _require(isinstance(history, list) and history, f"{label} lacks terminal history")
    rows = [row for row in history if row.get("epoch") == best_epoch]
    _require(len(rows) == 1, f"{label} has ambiguous best epoch")
    ordinary = rows[0].get("ordinary")
    _require(isinstance(ordinary, dict), f"{label} lacks ordinary Dev metrics")
    for metric in ("macro_f1", "balanced_accuracy", "opposite_direction_error_rate"):
        _require(metric in ordinary, f"{label} missing {metric}")
    for metric in ("per_class_recall", "per_class_f1"):
        values = ordinary.get(metric)
        _require(isinstance(values, dict), f"{label} missing {metric}")
        _require(set(values) == set(PROGRESSION_LABELS), f"{label} class set drift")
    return ordinary


def _verify_terminal_run(
    *,
    experiment_id: str,
    seed: int,
    hardware: str,
    config_path: Path,
    receipt_path: Path,
    checkpoint_path: Path,
) -> dict[str, Any]:
    config = _read_json(config_path)
    receipt = _read_json(receipt_path)
    _require(
        config.get("experiment_id") == experiment_id,
        f"config ID drift: {experiment_id}",
    )
    _require(int(config.get("seed", -1)) == seed, f"config seed drift: {experiment_id}")
    _require(
        receipt.get("status") == "PASS_TRAINING_FINISHED", f"non-PASS: {experiment_id}"
    )
    _zero_protected(receipt, label=experiment_id)
    _require(
        receipt.get("config_sha256") == canonical_sha256(config),
        f"effective config hash drift: {experiment_id}",
    )
    _require(checkpoint_path.is_file(), f"missing checkpoint: {experiment_id}")
    metrics = _best_ordinary_metrics(receipt, label=experiment_id)
    return {
        "experiment_id": experiment_id,
        "seed": seed,
        "hardware": hardware,
        "config_file_sha256": sha256_file(config_path),
        "effective_config_sha256": canonical_sha256(config),
        "receipt_sha256": sha256_file(receipt_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "completed_epochs": int(receipt["completed_epochs"]),
        "duration_seconds": _duration_seconds(receipt),
        "peak_gpu_memory_status": "NOT_RECORDED_BY_FROZEN_RUNNER",
        "metrics": metrics,
        "input_sha256": receipt.get("input_hashes", {}),
        "zero_protected_reads": True,
    }


def _summarize_runs(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    _require(rows, "cannot summarize zero runs")
    scalar = ("macro_f1", "balanced_accuracy", "opposite_direction_error_rate")
    summary = {
        "scalar_metrics": {
            metric: _mean_sd([float(row["metrics"][metric]) for row in rows])
            for metric in scalar
        },
        "per_class_recall": {
            label: _mean_sd(
                [float(row["metrics"]["per_class_recall"][label]) for row in rows]
            )
            for label in PROGRESSION_LABELS
        },
        "per_class_f1": {
            label: _mean_sd(
                [float(row["metrics"]["per_class_f1"][label]) for row in rows]
            )
            for label in PROGRESSION_LABELS
        },
        "completed_epochs": _mean_sd([float(row["completed_epochs"]) for row in rows]),
        "duration_seconds": _mean_sd(
            [
                float(row["duration_seconds"])
                for row in rows
                if row["duration_seconds"] is not None
            ]
        ),
        "peak_gpu_memory_status": "NOT_RECORDED_BY_FROZEN_RUNNER",
    }
    return summary


def _verify_baselines(*, baseline_root: Path, server_evidence: Path) -> dict[str, Any]:
    preparation_path = baseline_root / "preparation_receipt.json"
    preparation = _read_json(preparation_path)
    _require(
        preparation.get("status") == "PASS_FORMAL_NATIVE_BASELINE_COMPLETION_PREPARED",
        "Wave046 preparation is not PASS",
    )
    _zero_protected(preparation, label="Wave046 preparation")
    reused = {str(row["experiment_id"]): row for row in preparation["reused_runs"]}
    specs = [
        (
            "B401",
            "W046-B401-S17",
            17,
            "A800-80GB",
            server_evidence / "W046-B401-S17" / "config.json",
            server_evidence / "W046-B401-S17" / "training_receipt.json",
            server_evidence / "W046-B401-S17" / "best.pt",
        ),
        (
            "B401",
            "W046-B401-S28",
            28,
            "RTX3090",
            baseline_root / "configs" / "W046-B401-S28.json",
            baseline_root / "runs" / "W046-B401-S28" / "training_receipt.json",
            baseline_root / "runs" / "W046-B401-S28" / "best.pt",
        ),
        (
            "B401",
            "W046-B401-S43",
            43,
            "RTX3090",
            baseline_root / "configs" / "W046-B401-S43.json",
            baseline_root / "runs" / "W046-B401-S43" / "training_receipt.json",
            baseline_root / "runs" / "W046-B401-S43" / "best.pt",
        ),
        (
            "B402",
            "CLN1-B402-S17",
            17,
            "REUSED_LOCAL",
            Path(str(reused["CLN1-B402-S17"]["config_path"])),
            Path(str(reused["CLN1-B402-S17"]["receipt_path"])),
            Path(str(reused["CLN1-B402-S17"]["checkpoint_path"])),
        ),
        (
            "B402",
            "W046-B402-S28",
            28,
            "RTX3090",
            baseline_root / "configs" / "W046-B402-S28.json",
            baseline_root / "runs" / "W046-B402-S28" / "training_receipt.json",
            baseline_root / "runs" / "W046-B402-S28" / "best.pt",
        ),
        (
            "B402",
            "W046-B402-S43",
            43,
            "RTX3090",
            baseline_root / "configs" / "W046-B402-S43.json",
            baseline_root / "runs" / "W046-B402-S43" / "training_receipt.json",
            baseline_root / "runs" / "W046-B402-S43" / "best.pt",
        ),
        (
            "B403",
            "CLN1-B403-S17",
            17,
            "REUSED_LOCAL",
            Path(str(reused["CLN1-B403-S17"]["config_path"])),
            Path(str(reused["CLN1-B403-S17"]["receipt_path"])),
            Path(str(reused["CLN1-B403-S17"]["checkpoint_path"])),
        ),
        (
            "B403",
            "B403-S28",
            28,
            "REUSED_LOCAL",
            Path(str(reused["B403-S28"]["config_path"])),
            Path(str(reused["B403-S28"]["receipt_path"])),
            Path(str(reused["B403-S28"]["checkpoint_path"])),
        ),
        (
            "B403",
            "B403-S43",
            43,
            "REUSED_LOCAL",
            Path(str(reused["B403-S43"]["config_path"])),
            Path(str(reused["B403-S43"]["receipt_path"])),
            Path(str(reused["B403-S43"]["checkpoint_path"])),
        ),
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for family, run_id, seed, hardware, config, receipt, checkpoint in specs:
        grouped[family].append(
            _verify_terminal_run(
                experiment_id=run_id,
                seed=seed,
                hardware=hardware,
                config_path=config,
                receipt_path=receipt,
                checkpoint_path=checkpoint,
            )
        )
    return {
        "schema": "prta-cxr.wave046-native-baseline-aggregate.v1",
        "status": "PASS_WAVE046_NATIVE_BASELINES_AGGREGATED_NO_SELECTION",
        "preparation_sha256": sha256_file(preparation_path),
        "families": {
            family: {"runs": rows, "summary": _summarize_runs(rows)}
            for family, rows in sorted(grouped.items())
        },
        "no_outcome_selection": True,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def _verify_diagnostics(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = _read_json(manifest_path)
    _require(
        manifest.get("status") == "PASS_WAVE047_CANDIDATE_DIAGNOSTICS_FROZEN",
        "candidate diagnostic manifest is not PASS",
    )
    _zero_protected(manifest, label="candidate diagnostic manifest")
    verified = []
    for item in manifest["diagnostic_receipts"]:
        receipt_path = Path(str(item["receipt_path"]))
        _require(
            sha256_file(receipt_path) == item["receipt_sha256"],
            "diagnostic receipt hash drift",
        )
        receipt = _read_json(receipt_path)
        _require(
            receipt.get("status")
            == "PASS_WAVE047_CANDIDATE_TRAIN_DEV_PRIOR_DIAGNOSTIC",
            "candidate diagnostic non-PASS",
        )
        _zero_protected(receipt, label=str(item["receipt_path"]))
        blocks = {}
        for intervention, block in receipt["prediction_blocks"].items():
            block_path = receipt_path.parent / str(block["path"])
            _require(
                sha256_file(block_path) == block["sha256"],
                "diagnostic prediction hash drift",
            )
            blocks[intervention] = str(block["sha256"])
        verified.append(
            {
                "variant": item["variant"],
                "seed": item["seed"],
                "receipt_sha256": item["receipt_sha256"],
                "prediction_block_sha256": dict(sorted(blocks.items())),
            }
        )
    _require(len(verified) == 9, "candidate diagnostic receipt count drift")
    return sorted(verified, key=lambda row: (row["variant"], row["seed"]))


def _verify_candidate(
    *,
    candidate_root: Path,
    bootstrap_root: Path,
    amendment_path: Path,
    server_evidence: Path,
) -> dict[str, Any]:
    preparation_path = candidate_root / "preparation_receipt.json"
    preparation = _read_json(preparation_path)
    _require(
        preparation.get("status") == "PASS_WAVE047_CANDIDATE_CONFIRMATION_FROZEN",
        "Wave047 preparation is not PASS",
    )
    _zero_protected(preparation, label="Wave047 preparation")
    diagnostics = _verify_diagnostics(bootstrap_root / "diagnostic_manifest.json")
    bootstrap_receipt_path = bootstrap_root / "bootstrap" / "completion_receipt.json"
    bootstrap_result_path = (
        bootstrap_root / "bootstrap" / "paired_patient_bootstrap.json"
    )
    bootstrap_receipt = _read_json(bootstrap_receipt_path)
    _require(
        bootstrap_receipt.get("status") == "PASS_WAVE047_CANDIDATE_BOOTSTRAP_COMPLETE",
        "candidate bootstrap is not PASS",
    )
    _zero_protected(bootstrap_receipt, label="candidate bootstrap")
    _require(
        bootstrap_receipt.get("result_sha256") == sha256_file(bootstrap_result_path),
        "candidate bootstrap result hash drift",
    )
    amendment = _read_json(amendment_path)
    _require(
        amendment.get("status") == "PASS_WAVE047_FOUR_GPU_RESOURCE_AMENDMENT_FROZEN",
        "Wave047 resource amendment is not PASS",
    )
    _zero_protected(amendment, label="Wave047 resource amendment")
    tila_specs = [
        (
            17,
            "RTX3090",
            amendment["queue_rows"]["local_gpu0"][0]["config_path"],
            candidate_root.parent
            / "wave047_four_gpu_resource_amendment_v2"
            / "local_gpu0"
            / "runs"
            / "W047-TILA8-S17"
            / "training_receipt.json",
            candidate_root.parent
            / "wave047_four_gpu_resource_amendment_v2"
            / "local_gpu0"
            / "runs"
            / "W047-TILA8-S17"
            / "best.pt",
        ),
        (
            28,
            "RTX3090",
            amendment["queue_rows"]["local_gpu1"][0]["config_path"],
            candidate_root.parent
            / "wave047_four_gpu_resource_amendment_v2"
            / "local_gpu1"
            / "runs"
            / "W047-TILA8-S28"
            / "training_receipt.json",
            candidate_root.parent
            / "wave047_four_gpu_resource_amendment_v2"
            / "local_gpu1"
            / "runs"
            / "W047-TILA8-S28"
            / "best.pt",
        ),
        (
            43,
            "A800-80GB",
            server_evidence / "W047-TILA8-S43" / "config.json",
            server_evidence / "W047-TILA8-S43" / "training_receipt.json",
            server_evidence / "W047-TILA8-S43" / "best.pt",
        ),
    ]
    tila_runs = [
        _verify_terminal_run(
            experiment_id=f"W047-TILA8-S{seed}",
            seed=seed,
            hardware=hardware,
            config_path=Path(str(config)),
            receipt_path=receipt,
            checkpoint_path=checkpoint,
        )
        for seed, hardware, config, receipt, checkpoint in tila_specs
    ]
    return {
        "schema": "prta-cxr.wave047-candidate-confirmation-aggregate.v1",
        "status": "PASS_WAVE047_CANDIDATE_CONFIRMATION_AGGREGATED_NO_SELECTION",
        "preparation_sha256": sha256_file(preparation_path),
        "resource_amendment_sha256": sha256_file(amendment_path),
        "diagnostics": diagnostics,
        "bootstrap": {
            "receipt_sha256": sha256_file(bootstrap_receipt_path),
            "result_sha256": sha256_file(bootstrap_result_path),
            "result": _read_json(bootstrap_result_path),
        },
        "tail8_tila": {"runs": tila_runs, "summary": _summarize_runs(tila_runs)},
        "candidate_status": "PENDING_FROZEN_DECISION_RULE",
        "no_outcome_selection": True,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def finalize_wave046_wave047_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Finalize Wave046/Wave047 Train/Dev closeout"
    )
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--baseline-server-evidence", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--bootstrap-root", type=Path, required=True)
    parser.add_argument("--resource-amendment", type=Path, required=True)
    parser.add_argument("--tila-server-evidence", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output_root.exists():
        parser.error("--output-root must be a new immutable directory")
    baseline = _verify_baselines(
        baseline_root=args.baseline_root,
        server_evidence=args.baseline_server_evidence,
    )
    candidate = _verify_candidate(
        candidate_root=args.candidate_root,
        bootstrap_root=args.bootstrap_root,
        amendment_path=args.resource_amendment,
        server_evidence=args.tila_server_evidence,
    )
    _write_new_json(
        args.output_root / "wave046_native_baseline_aggregate.json", baseline
    )
    _write_new_json(
        args.output_root / "wave047_candidate_confirmation_aggregate.json", candidate
    )
    receipt = {
        "schema": "prta-cxr.wave046-wave047-closeout-receipt.v1",
        "status": "PASS_WAVE046_WAVE047_CLOSEOUT_AGGREGATED_NO_SELECTION",
        "created_at": datetime.now(UTC).isoformat(),
        "wave046_aggregate_sha256": sha256_file(
            args.output_root / "wave046_native_baseline_aggregate.json"
        ),
        "wave047_aggregate_sha256": sha256_file(
            args.output_root / "wave047_candidate_confirmation_aggregate.json"
        ),
        "candidate_status": "PENDING_FROZEN_DECISION_RULE",
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(args.output_root / "completion_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
