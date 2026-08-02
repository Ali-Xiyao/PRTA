from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from prta_cxr.artifacts import (
    replace_json_atomic,
    write_json_atomic,
    write_jsonl_atomic,
)
from prta_cxr.contracts import sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.evaluation.calibration import fit_temperature
from prta_cxr.evaluation.inference import logits_and_targets, predict_loader
from prta_cxr.protocol_freeze import validate_protocol_freeze
from prta_cxr.run_registry import read_run_registry
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules


def _evaluation_specs(
    freeze: dict[str, Any], registry: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    queue = json.loads(Path(freeze["input_paths"]["formal_queue"]).read_text("utf-8"))
    ids = [
        str(row["experiment_id"])
        for row in queue
        if str(row["experiment_id"]).startswith(("B401", "B402", "B403", "A5"))
    ]
    specs = []
    for experiment_id in ids:
        if experiment_id not in registry:
            raise ValueError(f"formal training run missing: {experiment_id}")
        specs.append(
            {
                "evaluation_id": experiment_id,
                "source_experiment_id": experiment_id,
                "method": experiment_id.split("-S", 1)[0],
                "seed": int(experiment_id.rsplit("S", 1)[1]),
            }
        )
    for alias, source in freeze["prta_aliases"].items():
        if not str(alias).startswith("B404-"):
            continue
        specs.append(
            {
                "evaluation_id": str(alias),
                "source_experiment_id": str(source),
                "method": "B404",
                "seed": int(str(alias).rsplit("S", 1)[1]),
            }
        )
    specs.sort(key=lambda value: value["evaluation_id"])
    return specs


def _load_model(
    spec: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    blocks,
    final_norm,
    device: torch.device,
    freeze: dict[str, Any],
):
    row = registry[spec["source_experiment_id"]]
    if row["status"] != "PASS_TRAINING_FINISHED":
        raise ValueError(f"training run incomplete: {spec['source_experiment_id']}")
    if row["config_hash"] != freeze["formal_config_hashes"][spec["evaluation_id"]]:
        raise ValueError(f"frozen evaluation config changed: {spec['evaluation_id']}")
    checkpoint_path = Path(str(row["checkpoint_path"]))
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported formal checkpoint")
    expected = checkpoint["input_hashes"]
    frozen_hashes = freeze["input_hashes"]
    if expected["split_manifest"] != frozen_hashes["train_dev_manifest"]:
        raise ValueError("checkpoint Train/Dev manifest differs from protocol")
    if expected["weights"] != frozen_hashes["weights"]:
        raise ValueError("checkpoint weights differ from protocol")
    if expected["text_cache"] != frozen_hashes["main_text_cache"]:
        raise ValueError("checkpoint text cache differs from protocol")
    if expected["cache_manifest"] != frozen_hashes["main_cache_manifest"]:
        raise ValueError("checkpoint image cache differs from protocol")
    model = build_train_model(blocks, final_norm, checkpoint["config"])
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    return model


def _loader(
    rows: list[dict[str, Any]],
    *,
    cache: Block8CacheIndex,
    text_cache: Path,
    split: str,
    batch_size: int,
    workers: int,
    prior_intervention: str = "true",
    wrong_finding_query: bool = False,
    label_key: str = "progression_label",
) -> DataLoader:
    dataset = PRTAFeatureDataset(
        rows,
        cache=cache,
        text_cache_path=text_cache,
        split=split,
        prior_intervention=prior_intervention,
        wrong_finding_query=wrong_finding_query,
        label_key=label_key,
    )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
    )


def run_formal_outcome_session(
    *,
    protocol_path: Path,
    output_root: Path,
    device: torch.device,
    batch_size: int,
    workers: int,
    resume: bool,
) -> dict[str, Any]:
    freeze_raw = json.loads(protocol_path.read_text(encoding="utf-8"))
    freeze = validate_protocol_freeze(freeze_raw, receipt_path=protocol_path)
    session_marker = protocol_path.with_name("formal_outcome_session_open.json")
    if output_root.exists() and not resume:
        raise FileExistsError(f"formal outcome output already exists: {output_root}")
    if not output_root.exists() and resume:
        raise FileNotFoundError("cannot resume a missing formal outcome output")
    output_root.mkdir(parents=True, exist_ok=resume)
    predictions_root = output_root / "predictions"
    predictions_root.mkdir(exist_ok=True)
    state_path = output_root / "session_state.json"
    registry_path = Path(freeze["run_registry_path"])
    registry = {
        str(row["experiment_id"]): row for row in read_run_registry(registry_path)
    }
    specs = _evaluation_specs(freeze, registry)
    weights = Path(freeze["input_paths"]["weights"])
    visual, _ = load_biomedclip_visual(weights)
    blocks, final_norm = tail_modules(visual)
    main_cache_root = Path(freeze["input_paths"]["main_cache_manifest"]).parent
    gold_cache_root = Path(freeze["input_paths"]["gold_cache_manifest"]).parent
    main_cache = Block8CacheIndex(main_cache_root)
    gold_cache = Block8CacheIndex(gold_cache_root)
    train_dev_rows = read_jsonl(Path(freeze["input_paths"]["train_dev_manifest"]))
    main_text = Path(freeze["input_paths"]["main_text_cache"])
    gold_text = Path(freeze["input_paths"]["gold_text_cache"])
    main_specs = [spec for spec in specs if spec["method"].startswith("B40")]
    calibration_path = output_root / "dev_calibration.json"
    temperatures: dict[str, float] = {}
    calibration_rows = {}
    for spec in main_specs:
        prediction_path = predictions_root / "dev" / (
            f"{spec['evaluation_id']}.true.predictions.jsonl"
        )
        if prediction_path.exists():
            rows = read_jsonl(prediction_path)
        else:
            model = _load_model(
                spec, registry, blocks, final_norm, device, freeze
            )
            rows = predict_loader(
                model,
                _loader(
                    train_dev_rows,
                    cache=main_cache,
                    text_cache=main_text,
                    split="dev",
                    batch_size=batch_size,
                    workers=workers,
                ),
                device=device,
                system=spec["method"],
                seed=spec["seed"],
                cohort="dev",
            )
            prediction_path.parent.mkdir(parents=True, exist_ok=True)
            write_jsonl_atomic(prediction_path, rows)
            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()
        logits, targets = logits_and_targets(rows)
        temperature = fit_temperature(logits, targets)
        temperatures[spec["evaluation_id"]] = temperature
        calibration_rows[spec["evaluation_id"]] = {
            "temperature": temperature,
            "rows": len(rows),
            "prediction_sha256": sha256_file(prediction_path),
        }
    calibration_receipt = {
        "schema": "prta-cxr.dev-calibration.v1",
        "status": "PASS_DEV_TEMPERATURES_FIT",
        "temperature_source": "dev_only",
        "systems": calibration_rows,
        "protected_outcomes_opened": False,
    }
    if calibration_path.exists():
        if json.loads(calibration_path.read_text("utf-8")) != calibration_receipt:
            raise ValueError("existing Dev calibration receipt differs")
    else:
        write_json_atomic(calibration_path, calibration_receipt)
    marker_value = {
        "schema": "prta-cxr.formal-outcome-session-open.v1",
        "status": "FORMAL_OUTCOME_SESSION_OPEN",
        "opened_at": datetime.now(UTC).isoformat(),
        "protocol_freeze_sha256": freeze["receipt_file_sha256"],
        "run_registry_sha256": sha256_file(registry_path),
        "dev_calibration_sha256": sha256_file(calibration_path),
        "output_root": str(output_root.resolve()),
    }
    if session_marker.exists():
        existing = json.loads(session_marker.read_text(encoding="utf-8"))
        comparable = dict(existing)
        comparable.pop("opened_at", None)
        candidate = dict(marker_value)
        candidate.pop("opened_at", None)
        if not resume or comparable != candidate:
            raise ValueError("formal outcome session marker already exists or differs")
    else:
        if resume:
            raise ValueError(
                "resume requested before formal outcome session was opened"
            )
        write_json_atomic(session_marker, marker_value)
    internal_rows = read_jsonl(
        Path(freeze["input_paths"]["sealed_internal_test_manifest"])
    )
    gold_rows = read_jsonl(Path(freeze["input_paths"]["gold_manifest"]))
    gold_rows = [
        {**row, "split": "gold", "human_label": str(row["human_label"])}
        for row in gold_rows
    ]
    completed = []
    for spec in specs:
        model = _load_model(spec, registry, blocks, final_norm, device, freeze)
        conditions = [("true", "true", False)]
        if spec["method"] == "B404":
            conditions.extend(
                [
                    ("current_only", "current_only", False),
                    ("null_prior", "null", False),
                    ("random_prior", "random", False),
                    ("matched_wrong_prior", "matched_wrong", False),
                    ("reversed_pair", "reversed", False),
                    ("wrong_finding_query", "true", True),
                ]
            )
        temperature = temperatures.get(spec["evaluation_id"], 1.0)
        for condition, prior_mode, wrong_query in conditions:
            path = predictions_root / "internal_test" / (
                f"{spec['evaluation_id']}.{condition}.predictions.jsonl"
            )
            if not path.exists():
                rows = predict_loader(
                    model,
                    _loader(
                        internal_rows,
                        cache=main_cache,
                        text_cache=main_text,
                        split="internal_test",
                        batch_size=batch_size,
                        workers=workers,
                        prior_intervention=prior_mode,
                        wrong_finding_query=wrong_query,
                    ),
                    device=device,
                    temperature=temperature,
                    system=spec["method"],
                    seed=spec["seed"],
                    cohort="internal_test",
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                write_jsonl_atomic(path, rows)
            completed.append(str(path.resolve()))
        if spec["method"].startswith("B40"):
            path = predictions_root / "gold" / (
                f"{spec['evaluation_id']}.true.predictions.jsonl"
            )
            if not path.exists():
                rows = predict_loader(
                    model,
                    _loader(
                        gold_rows,
                        cache=gold_cache,
                        text_cache=gold_text,
                        split="gold",
                        batch_size=batch_size,
                        workers=workers,
                        label_key="human_label",
                    ),
                    device=device,
                    temperature=temperature,
                    system=spec["method"],
                    seed=spec["seed"],
                    cohort="gold",
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                write_jsonl_atomic(path, rows)
            completed.append(str(path.resolve()))
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()
        replace_json_atomic(
            state_path,
            {
                "status": "RUNNING_FORMAL_OUTCOME_SESSION",
                "completed_prediction_files": len(completed),
                "latest_evaluation_id": spec["evaluation_id"],
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
    result = {
        "schema": "prta-cxr.formal-outcome-session.v1",
        "status": "PASS_FORMAL_OUTCOME_PREDICTIONS_FINISHED",
        "protocol_freeze_sha256": freeze["receipt_file_sha256"],
        "session_marker_sha256": sha256_file(session_marker),
        "dev_calibration_sha256": sha256_file(calibration_path),
        "prediction_files": len(completed),
        "completed_at": datetime.now(UTC).isoformat(),
        "method_or_config_changed_after_open": False,
    }
    receipt_path = output_root / "session_receipt.json"
    if not receipt_path.exists():
        write_json_atomic(receipt_path, result)
    replace_json_atomic(state_path, result)
    return result
