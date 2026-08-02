from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import torch

from prta_cxr.artifacts import replace_json_atomic
from prta_cxr.cli_figures import figures_main
from prta_cxr.cli_tables import paper_tables_main
from prta_cxr.cli_trust import trust_audits_main
from prta_cxr.cli_vlm import vlm_additional_main
from prta_cxr.development_selection import prepare_next_development_stage
from prta_cxr.formal_matrix import (
    prepare_dev_baseline_queue,
    prepare_formal_matrix,
    write_development_gate,
)
from prta_cxr.formal_outcome_session import run_formal_outcome_session
from prta_cxr.protocol_freeze import (
    freeze_formal_protocol,
    validate_protocol_freeze,
)
from prta_cxr.queue_runner import run_training_queue


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _state(output: Path, status: str, **values: Any) -> None:
    replace_json_atomic(
        output / "program_state.json",
        {"schema": "prta-cxr.formal-program-keeper.v1", "status": status, **values},
    )


def _wait_initial_queue(
    initial_queue: Path, output: Path, poll_seconds: int
) -> dict[str, Any]:
    state_path = initial_queue.with_name("scheduler_state.json")
    receipt_path = initial_queue.with_name("scheduler_receipt.json")
    while not receipt_path.is_file():
        state = _read(state_path) if state_path.is_file() else {"status": "UNKNOWN"}
        if str(state.get("status", "")).startswith("HOLD_"):
            raise RuntimeError(f"initial development queue is on HOLD: {state}")
        _state(
            output,
            "WAITING_INITIAL_DEVELOPMENT_QUEUE",
            initial_queue_state=state,
        )
        time.sleep(poll_seconds)
    receipt = _read(receipt_path)
    if receipt.get("status") != "PASS_TRAINING_QUEUE_FINISHED":
        raise ValueError("initial development queue receipt is not PASS")
    return receipt


def _run_queue(
    *,
    queue: Path,
    split_manifest: Path,
    cache_root: Path,
    weights: Path,
    quality_audit: Path,
    run_registry: Path,
    runs_root: Path,
    devices: tuple[str, ...],
    poll_seconds: int,
) -> dict[str, Any]:
    result = run_training_queue(
        queue_path=queue,
        split_manifest=split_manifest,
        cache_root=cache_root,
        weights=weights,
        quality_audit=quality_audit,
        run_registry=run_registry,
        runs_root=runs_root,
        devices=devices,
        poll_seconds=poll_seconds,
    )
    if result.get("status") != "PASS_TRAINING_QUEUE_FINISHED":
        raise RuntimeError(f"training queue failed: {result}")
    return result


def _selection_stage(
    *,
    stage: str,
    root: Path,
    registry: Path,
    previous: Path | None,
    queue_kwargs: dict[str, Any],
) -> Path:
    receipt = root / "selection_receipt.json"
    if not receipt.is_file():
        prepare_next_development_stage(
            stage=stage,
            registry_path=registry,
            previous_selection=previous,
            output=root,
        )
    value = _read(receipt)
    if value.get("stage") != stage:
        raise ValueError(f"existing selection receipt stage differs: {root}")
    _run_queue(queue=root / "run_queue.json", **queue_kwargs)
    return receipt


def run_formal_program(
    *,
    output: Path,
    initial_queue: Path,
    split_manifest: Path,
    sealed_internal_test: Path,
    gold_manifest: Path,
    cache_root: Path,
    gold_cache_root: Path,
    weights: Path,
    quality_audit: Path,
    run_registry: Path,
    development_runs_root: Path,
    formal_runs_root: Path,
    protocol_config: Path,
    trust_config: Path,
    case_selection_config: Path,
    vlm_config: Path,
    vlm_model_config: Path,
    vlm_model_index: Path,
    devices: tuple[str, ...],
    outcome_device: torch.device,
    poll_seconds: int,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    completed = output / "program_receipt.json"
    if completed.is_file():
        value = _read(completed)
        if value.get("status") != "PASS_FORMAL_PROGRAM_FINISHED":
            raise ValueError("existing formal program receipt is not complete")
        return value
    _wait_initial_queue(initial_queue, output, poll_seconds)
    queue_kwargs = {
        "split_manifest": split_manifest,
        "cache_root": cache_root,
        "weights": weights,
        "quality_audit": quality_audit,
        "run_registry": run_registry,
        "runs_root": development_runs_root,
        "devices": devices,
        "poll_seconds": poll_seconds,
    }
    _state(output, "RUNNING_LOSS_STAGE")
    loss = _selection_stage(
        stage="loss",
        root=output / "loss",
        registry=run_registry,
        previous=None,
        queue_kwargs=queue_kwargs,
    )
    _state(output, "RUNNING_ADAPTER_STAGE")
    adapter = _selection_stage(
        stage="adapter",
        root=output / "adapter",
        registry=run_registry,
        previous=loss,
        queue_kwargs=queue_kwargs,
    )
    _state(output, "RUNNING_CONFIRM_STAGE")
    confirm = _selection_stage(
        stage="confirm",
        root=output / "confirm",
        registry=run_registry,
        previous=adapter,
        queue_kwargs=queue_kwargs,
    )
    baseline_root = output / "dev_baselines"
    if not (baseline_root / "preparation_receipt.json").is_file():
        prepare_dev_baseline_queue(
            registry_path=run_registry,
            confirm_selection=confirm,
            output=baseline_root,
        )
    _state(output, "RUNNING_DEV_BASELINES")
    _run_queue(queue=baseline_root / "run_queue.json", **queue_kwargs)
    gate_path = output / "development_gate.json"
    if not gate_path.is_file():
        write_development_gate(
            registry_path=run_registry,
            confirm_selection=confirm,
            output=gate_path,
        )
    gate = _read(gate_path)
    if gate.get("decision") != "GO":
        result = {
            "schema": "prta-cxr.formal-program-keeper.v1",
            "status": f"{gate['decision']}_FORMAL_PROGRAM_AT_DEVELOPMENT_GATE",
            "development_gate": gate,
            "formal_outcomes_opened": False,
        }
        replace_json_atomic(output / "program_state.json", result)
        return result
    matrix_root = output / "formal_matrix"
    matrix_receipt = matrix_root / "formal_matrix_receipt.json"
    if not matrix_receipt.is_file():
        prepare_formal_matrix(
            registry_path=run_registry,
            confirm_selection=confirm,
            gate_receipt=gate_path,
            output=matrix_root,
        )
    _state(output, "RUNNING_FORMAL_TRAINING_MATRIX")
    formal_queue_kwargs = {
        **queue_kwargs,
        "runs_root": formal_runs_root,
    }
    _run_queue(queue=matrix_root / "run_queue.json", **formal_queue_kwargs)
    freeze_path = output / "protocol_freeze.json"
    if freeze_path.is_file():
        freeze = validate_protocol_freeze(
            _read(freeze_path), receipt_path=freeze_path
        )
    else:
        freeze_formal_protocol(
            repo_root=Path(__file__).resolve().parents[2],
            gate_receipt=gate_path,
            formal_matrix_receipt=matrix_receipt,
            formal_queue=matrix_root / "run_queue.json",
            run_registry=run_registry,
            train_dev_manifest=split_manifest,
            sealed_internal_test_manifest=sealed_internal_test,
            gold_manifest=gold_manifest,
            main_cache_manifest=cache_root / "cache_manifest.json",
            gold_cache_manifest=gold_cache_root / "cache_manifest.json",
            weights=weights,
            main_text_cache=cache_root / "text_cache.pt",
            gold_text_cache=gold_cache_root / "text_cache.pt",
            quality_audit=quality_audit,
            protocol_config=protocol_config,
            trust_config=trust_config,
            case_selection_config=case_selection_config,
            vlm_config=vlm_config,
            vlm_model_config=vlm_model_config,
            vlm_model_index=vlm_model_index,
            output=freeze_path,
        )
        freeze = validate_protocol_freeze(
            _read(freeze_path), receipt_path=freeze_path
        )
    _state(output, "RUNNING_ONE_TIME_FORMAL_OUTCOME_SESSION")
    outcome_root = output / "formal_outcome"
    outcome = run_formal_outcome_session(
        protocol_path=freeze_path,
        output_root=outcome_root,
        device=outcome_device,
        batch_size=32,
        workers=2,
        resume=outcome_root.exists(),
    )
    trust_root = output / "trust"
    trust_root.mkdir(exist_ok=True)
    trust_path = trust_root / "trust_audit.json"
    if not trust_path.is_file():
        trust_audits_main(
            [
                "--mode",
                "formal",
                "--formal",
                "--predictions-root",
                str(outcome_root / "predictions"),
                "--protocol-freeze",
                str(freeze_path),
                "--output",
                str(trust_path),
            ]
        )
    figures_root = output / "figures"
    if not (figures_root / "figure_manifest.json").is_file():
        figures_main(
            [
                "--mode",
                "formal",
                "--formal",
                "--protocol-freeze",
                str(freeze_path),
                "--outcome-session",
                str(outcome_root / "session_receipt.json"),
                "--predictions-root",
                str(outcome_root / "predictions"),
                "--trust-audit",
                str(trust_path),
                "--development-root",
                str(development_runs_root),
                "--quality-audit",
                str(quality_audit),
                "--case-selection",
                str(case_selection_config),
                "--output",
                str(figures_root),
            ]
        )
    vlm_root = output / "vlm_additional"
    vlm_args = [
        "--mode",
        "formal",
        "--formal",
        "--protocol-freeze",
        str(freeze_path),
        "--outcome-session",
        str(outcome_root / "session_receipt.json"),
        "--output",
        str(vlm_root),
        "--device",
        str(outcome_device),
    ]
    if vlm_root.exists():
        vlm_args.append("--resume")
    vlm_additional_main(vlm_args)
    paper_root = output / "paper_results"
    if not (paper_root / "finalization_receipt.json").is_file():
        paper_tables_main(
            [
                "--mode",
                "formal",
                "--formal",
                "--protocol-freeze",
                str(freeze_path),
                "--outcome-session",
                str(outcome_root / "session_receipt.json"),
                "--trust-audit",
                str(trust_path),
                "--figure-manifest",
                str(figures_root / "figure_manifest.json"),
                "--vlm-result",
                str(vlm_root / "result.json"),
                "--output",
                str(paper_root),
            ]
        )
    result = {
        "schema": "prta-cxr.formal-program-keeper.v1",
        "status": "PASS_FORMAL_PROGRAM_FINISHED",
        "development_gate": gate["decision"],
        "protocol_freeze_sha256": freeze["receipt_file_sha256"],
        "formal_outcome_status": outcome["status"],
        "paper_finalization": str(
            (paper_root / "finalization_receipt.json").resolve()
        ),
    }
    replace_json_atomic(completed, result)
    replace_json_atomic(output / "program_state.json", result)
    return result
