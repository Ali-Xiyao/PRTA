from __future__ import annotations

import csv
import json
import os
import platform
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, Subset

from prta_cxr.artifacts import replace_json_atomic
from prta_cxr.audit.tracin import (
    EXPECTED_DEV_ROWS,
    EXPECTED_PROBES,
    EXPECTED_TRAIN_ROWS,
    SEEDS,
    AuditContractError,
    CaptumClassificationLoss,
    CaptumTupleDataset,
    LogitsOnly,
    adapter_directional_scores,
    add_prediction_summary,
    aggregate_probe_gradient,
    assert_private_output,
    audit_path,
    compute_streaming_fast_influence,
    ensure_finite_columns,
    grouped_percentiles,
    make_tracincp_fast,
    predict_dataset,
    select_dev_probes,
    tier_dev_rows,
    tier_train_rows,
    validate_open_manifest,
)
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules

SEED_RUNS = {17: "M302-CBF", 29: "M304-S29", 43: "M304-S43"}
AUDIT_SCHEMA = "prta-cxr.approximate-tracin-readonly-audit.v1"


def bind_work_contract(output: Path, snapshot: Mapping[str, str]) -> None:
    path = output / "_work" / "contract.json"
    payload = {
        "schema": "prta-cxr.approximate-tracin-work-contract.v1",
        "input_hashes": dict(snapshot),
        "protected_outcome_read_count": 0,
    }
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise AuditContractError("audit resume work contract mismatch")
        return
    replace_json_atomic(path, payload)


def _progress_callback(
    output: Path,
    lane: str,
    *,
    seed: int | None = None,
    checkpoint: str | None = None,
):
    path = output / "_work" / f"{lane}_progress.json"

    def update(component: str, current: int, total: int) -> None:
        replace_json_atomic(
            path,
            {
                "schema": "prta-cxr.approximate-tracin-progress.v1",
                "status": "RUNNING",
                "lane": lane,
                "seed": seed,
                "checkpoint": checkpoint,
                "component": component,
                "completed_batches": current,
                "total_batches": total,
                "updated_at": datetime.now(UTC).isoformat(),
                "pid": os.getpid(),
                "training_started": False,
                "protected_outcome_read_count": 0,
            },
        )

    return update


def checkpoint_paths(runs_root: Path) -> dict[int, tuple[Path, Path]]:
    result: dict[int, tuple[Path, Path]] = {}
    for seed, run_id in SEED_RUNS.items():
        root = audit_path(runs_root / run_id, role=f"seed {seed} run")
        result[seed] = (
            audit_path(root / "best.pt", role=f"seed {seed} best checkpoint"),
            audit_path(root / "last.pt", role=f"seed {seed} last checkpoint"),
        )
    return result


def _required_file(path: Path, role: str) -> Path:
    value = audit_path(path, role=role)
    if not value.is_file():
        raise AuditContractError(f"missing {role}: {value}")
    return value


def input_snapshot(
    *,
    split_manifest: Path,
    cache_root: Path,
    text_cache: Path,
    weights: Path,
    runs_root: Path,
) -> dict[str, str]:
    cache_manifest = _required_file(
        cache_root / "cache_manifest.json", "cache manifest"
    )
    inventory = _required_file(cache_root / "image_inventory.json", "cache inventory")
    training_store = _required_file(
        cache_root / "training_store_receipt.json", "training store receipt"
    )
    files: dict[str, Path] = {
        "split_manifest": _required_file(split_manifest, "Train/Dev manifest"),
        "cache_manifest": cache_manifest,
        "cache_inventory": inventory,
        "training_store_receipt": training_store,
        "text_cache": _required_file(text_cache, "text cache"),
        "weights": _required_file(weights, "BiomedCLIP weights"),
    }
    for seed, (best, last) in checkpoint_paths(runs_root).items():
        files[f"seed{seed}_best"] = _required_file(best, f"seed {seed} best")
        files[f"seed{seed}_last"] = _required_file(last, f"seed {seed} last")
    return {name: sha256_file(path) for name, path in files.items()}


def validate_checkpoint_contracts(
    paths: Mapping[int, tuple[Path, Path]], snapshot: Mapping[str, str]
) -> dict[int, dict[str, Any]]:
    configs: dict[int, dict[str, Any]] = {}
    expected_inputs: dict[str, str] | None = None
    for seed in SEEDS:
        best_path, last_path = paths[seed]
        pair: list[dict[str, Any]] = []
        for kind, path in (("best", best_path), ("last", last_path)):
            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
            if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
                raise AuditContractError(
                    f"seed {seed} {kind} checkpoint schema mismatch"
                )
            config = dict(checkpoint.get("config", {}))
            if int(config.get("seed", -1)) != seed:
                raise AuditContractError(f"seed {seed} {kind} checkpoint seed mismatch")
            if str(config.get("experiment_id")) != SEED_RUNS[seed]:
                raise AuditContractError(
                    f"seed {seed} {kind} checkpoint experiment mismatch"
                )
            inputs = dict(checkpoint.get("input_hashes", {}))
            if inputs.get("split_manifest") != snapshot["split_manifest"]:
                raise AuditContractError("checkpoint Train/Dev manifest hash mismatch")
            if inputs.get("text_cache") != snapshot["text_cache"]:
                raise AuditContractError("checkpoint text cache hash mismatch")
            if inputs.get("weights") != snapshot["weights"]:
                raise AuditContractError("checkpoint visual weights hash mismatch")
            if inputs.get("cache_manifest") != snapshot["cache_manifest"]:
                raise AuditContractError("checkpoint cache manifest hash mismatch")
            pair.append(checkpoint)
        if pair[0]["config"] != pair[1]["config"]:
            raise AuditContractError(f"seed {seed} best/last config mismatch")
        if pair[0]["input_hashes"] != pair[1]["input_hashes"]:
            raise AuditContractError(f"seed {seed} best/last input mismatch")
        if expected_inputs is None:
            expected_inputs = dict(pair[0]["input_hashes"])
        elif pair[0]["input_hashes"] != expected_inputs:
            raise AuditContractError("seeds do not share the same frozen inputs")
        configs[seed] = dict(pair[0]["config"])
        del pair
    return configs


def prepare_contract(
    *,
    split_manifest: Path,
    cache_root: Path,
    text_cache: Path,
    weights: Path,
    runs_root: Path,
    output: Path,
    repo_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[int, dict[str, Any]]]:
    split_manifest = _required_file(split_manifest, "Train/Dev manifest")
    cache_root = audit_path(cache_root, role="cache root")
    text_cache = _required_file(text_cache, "text cache")
    weights = _required_file(weights, "BiomedCLIP weights")
    runs_root = audit_path(runs_root, role="development runs root")
    assert_private_output(output, repo_root)
    rows = read_jsonl(split_manifest)
    validate_open_manifest(rows)
    snapshot = input_snapshot(
        split_manifest=split_manifest,
        cache_root=cache_root,
        text_cache=text_cache,
        weights=weights,
        runs_root=runs_root,
    )
    configs = validate_checkpoint_contracts(checkpoint_paths(runs_root), snapshot)
    return rows, snapshot, configs


def _build_model(
    *, checkpoint_path: Path, weights: Path, device: torch.device
) -> tuple[LogitsOnly, dict[str, Any]]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    config = dict(checkpoint["config"])
    visual, _ = load_biomedclip_visual(weights)
    blocks, final_norm = tail_modules(visual)
    model = build_train_model(blocks, final_norm, config)
    model.load_state_dict(checkpoint["model_state"], strict=True)
    wrapper = LogitsOnly(model).eval().to(device)
    del visual, checkpoint
    return wrapper, config


def _load_checkpoint(wrapper: LogitsOnly, path: Path, device: torch.device) -> None:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    wrapper.model.load_state_dict(checkpoint["model_state"], strict=True)
    wrapper.eval().to(device)
    del checkpoint


def _loaders(
    rows: Sequence[dict[str, Any]],
    *,
    cache_root: Path,
    text_cache: Path,
    batch_size: int,
    workers: int,
) -> tuple[PRTAFeatureDataset, PRTAFeatureDataset, DataLoader, DataLoader]:
    cache = Block8CacheIndex(cache_root)
    train = PRTAFeatureDataset(
        rows, cache=cache, text_cache_path=text_cache, split="train"
    )
    dev = PRTAFeatureDataset(rows, cache=cache, text_cache_path=text_cache, split="dev")
    train_tuple = CaptumTupleDataset(train)
    dev_tuple = CaptumTupleDataset(dev)
    pin = torch.cuda.is_available()
    train_loader = DataLoader(
        train_tuple,
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
        pin_memory=pin,
    )
    dev_loader = DataLoader(
        dev_tuple,
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
        pin_memory=pin,
    )
    return train, dev, train_loader, dev_loader


def _save_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("wb") as handle:
            np.savez_compressed(handle, **arrays)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    if not path.is_file():
        raise AuditContractError(f"required audit intermediate is missing: {path.name}")
    with np.load(path, allow_pickle=False) as value:
        return {name: value[name] for name in value.files}


def run_dev_predictions(
    rows: Sequence[dict[str, Any]],
    *,
    weights: Path,
    runs_root: Path,
    cache_root: Path,
    text_cache: Path,
    output: Path,
    device: torch.device,
    batch_size: int,
    workers: int,
    resume: bool,
) -> None:
    work = output / "_work"
    _, _, _, dev_loader = _loaders(
        rows,
        cache_root=cache_root,
        text_cache=text_cache,
        batch_size=batch_size,
        workers=workers,
    )
    paths = checkpoint_paths(runs_root)
    for seed in SEEDS:
        destination = work / f"dev_seed{seed}.npz"
        if resume and destination.is_file():
            values = _load_npz(destination)
            if len(values["prediction_index"]) != EXPECTED_DEV_ROWS:
                raise AuditContractError("resumed Dev predictions have wrong length")
            continue
        wrapper, _ = _build_model(
            checkpoint_path=paths[seed][0], weights=weights, device=device
        )
        progress = _progress_callback(output, f"dev_seed{seed}", seed=seed)
        values = predict_dataset(wrapper, dev_loader, device=device, progress=progress)
        if len(values["prediction_index"]) != EXPECTED_DEV_ROWS:
            raise AuditContractError("Dev prediction conservation failed")
        _save_npz(
            destination,
            prediction_index=values["prediction_index"],
            confidence=values["confidence"],
            nll=values["nll"],
        )
        progress("complete", len(dev_loader), len(dev_loader))
        del wrapper
        if device.type == "cuda":
            torch.cuda.empty_cache()


def select_and_save_probes(rows: Sequence[dict[str, Any]], *, output: Path) -> None:
    dev_rows = [dict(row) for row in rows if row["split"] == "dev"]
    predictions: dict[int, dict[str, np.ndarray]] = {}
    for seed in SEEDS:
        values = _load_npz(output / "_work" / f"dev_seed{seed}.npz")
        indices = values["prediction_index"]
        predictions[seed] = {
            "prediction": np.asarray(
                [PROGRESSION_LABELS[int(value)] for value in indices], dtype=str
            ),
            "confidence": values["confidence"],
            "nll": values["nll"],
        }
    add_prediction_summary(dev_rows, predictions)
    indices = select_dev_probes(dev_rows)
    if len(indices) != EXPECTED_PROBES:
        raise AuditContractError("probe count is not exactly 300")
    payload = {
        "schema": "prta-cxr.tracin-dev-probes.v1",
        "count": len(indices),
        "indices": indices,
        "sample_ids": [dev_rows[index]["sample_id"] for index in indices],
        "strata": dict(
            Counter(
                f"{dev_rows[index]['source']}|{dev_rows[index]['progression_label']}"
                for index in indices
            )
        ),
    }
    replace_json_atomic(output / "_work" / "dev_probes.json", payload)


def _probe_indices(output: Path) -> list[int]:
    path = output / "_work" / "dev_probes.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    indices = [int(item) for item in value["indices"]]
    if len(indices) != EXPECTED_PROBES or len(set(indices)) != EXPECTED_PROBES:
        raise AuditContractError("stored probe indices failed conservation")
    return indices


def run_seed_scores(
    seed: int,
    rows: Sequence[dict[str, Any]],
    *,
    weights: Path,
    runs_root: Path,
    cache_root: Path,
    text_cache: Path,
    output: Path,
    device: torch.device,
    batch_size: int,
    probe_batch_size: int,
    workers: int,
    resume: bool,
) -> None:
    if seed not in SEEDS:
        raise AuditContractError(f"unsupported seed: {seed}")
    destination = output / "_work" / f"train_seed{seed}.npz"
    if resume and destination.is_file():
        values = _load_npz(destination)
        if len(values["prediction_index"]) != EXPECTED_TRAIN_ROWS:
            raise AuditContractError("resumed Train scores have wrong length")
        return
    train, dev, train_loader, _ = _loaders(
        rows,
        cache_root=cache_root,
        text_cache=text_cache,
        batch_size=batch_size,
        workers=workers,
    )
    train_tuple = CaptumTupleDataset(train)
    dev_tuple = CaptumTupleDataset(dev)
    probe_loader = DataLoader(
        Subset(dev_tuple, _probe_indices(output)),
        batch_size=probe_batch_size,
        shuffle=False,
        num_workers=workers,
        pin_memory=device.type == "cuda",
    )
    best, last = checkpoint_paths(runs_root)[seed]
    wrapper, config = _build_model(checkpoint_path=best, weights=weights, device=device)
    loss = CaptumClassificationLoss(config.get("classification_loss", {}))
    prediction_path = output / "_work" / f"train_seed{seed}_predictions.npz"
    if resume and prediction_path.is_file():
        predictions = _load_npz(prediction_path)
        if len(predictions["prediction_index"]) != EXPECTED_TRAIN_ROWS:
            raise AuditContractError("resumed Train predictions have wrong length")
    else:
        prediction_progress = _progress_callback(
            output, f"train_seed{seed}_prediction", seed=seed
        )
        predictions = predict_dataset(
            wrapper,
            train_loader,
            device=device,
            progress=prediction_progress,
        )
        _save_npz(
            prediction_path,
            prediction_index=predictions["prediction_index"],
            confidence=predictions["confidence"],
            nll=predictions["nll"],
        )
    final_layer = wrapper.model.native_head.head[1]
    influence = make_tracincp_fast(wrapper, final_layer, train_tuple, loss)
    learning_rate = float(config["optimization"]["learning_rate"])
    fast_totals = {
        name: np.zeros(EXPECTED_TRAIN_ROWS, dtype=np.float64)
        for name in ("signed", "positive", "negative", "self_influence")
    }
    adapter_signed = np.zeros(EXPECTED_TRAIN_ROWS, dtype=np.float64)
    for checkpoint_name, checkpoint_path in (("best", best), ("last", last)):
        contribution_path = (
            output / "_work" / f"train_seed{seed}_{checkpoint_name}_contribution.npz"
        )
        if resume and contribution_path.is_file():
            saved = _load_npz(contribution_path)
            if any(len(value) != EXPECTED_TRAIN_ROWS for value in saved.values()):
                raise AuditContractError(
                    "resumed checkpoint contribution is misaligned"
                )
            for name in fast_totals:
                fast_totals[name] += saved[name]
            adapter_signed += saved["adapter_signed"]
            continue
        _load_checkpoint(wrapper, checkpoint_path, device)
        progress = _progress_callback(
            output,
            f"train_seed{seed}_{checkpoint_name}",
            seed=seed,
            checkpoint=checkpoint_name,
        )
        contribution = compute_streaming_fast_influence(
            influence,
            train_loader,
            probe_loader,
            learning_rate=learning_rate,
            device=device,
            progress=progress,
        )
        direction = aggregate_probe_gradient(
            wrapper, probe_loader, loss, device=device, progress=progress
        )
        adapter_contribution = adapter_directional_scores(
            wrapper,
            train_loader,
            loss,
            direction,
            learning_rate=learning_rate,
            device=device,
            progress=progress,
        )
        saved = {
            "signed": contribution.signed,
            "positive": contribution.positive,
            "negative": contribution.negative,
            "self_influence": contribution.self_influence,
            "adapter_signed": adapter_contribution,
        }
        _save_npz(contribution_path, **saved)
        for name in fast_totals:
            fast_totals[name] += saved[name]
        adapter_signed += saved["adapter_signed"]
        progress("complete", len(train_loader), len(train_loader))
        del direction
    arrays = {
        "prediction_index": predictions["prediction_index"],
        "confidence": predictions["confidence"],
        "nll": predictions["nll"],
        "signed_influence": fast_totals["signed"],
        "positive_influence": fast_totals["positive"],
        "negative_influence": fast_totals["negative"],
        "negative_influence_magnitude": -fast_totals["negative"],
        "self_influence": fast_totals["self_influence"],
        "adapter_signed_influence": adapter_signed,
        "adapter_negative_influence_magnitude": np.maximum(-adapter_signed, 0),
    }
    if any(len(value) != EXPECTED_TRAIN_ROWS for value in arrays.values()):
        raise AuditContractError("Train score conservation failed")
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise AuditContractError("Train scores contain NaN or infinity")
    _save_npz(destination, **arrays)


def _safe_csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, set)):
        return "|".join(str(item) for item in value)
    if value is None:
        return ""
    return value


def _write_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite audit artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(fields), extrasaction="ignore"
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {field: _safe_csv_value(row.get(field)) for field in fields}
                )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite audit artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _md(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .replace("|", "\\|")
        .replace("\n", "<br>")
    )


def _write_detailed_markdown(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite audit artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("# PRTA-CXR 近似 TracIn 全部高风险样本内部审计\n\n")
            handle.write(
                "> 只读内部审计；以下均为高风险候选，不是已证明的错标或有害样本。"
                "未修改标签、样本、划分或检查点，未启动重训。\n\n"
            )
            handle.write(f"候选总数：{len(rows)}。本文档无 Top-K 截断。\n\n")
            for ordinal, row in enumerate(rows, 1):
                handle.write(
                    f"## {ordinal}. {_md(row['risk_tier'])} · {_md(row['split'])} · "
                    f"{_md(row['source'])} · {_md(row['finding'])}\n\n"
                )
                handle.write(f"- Luna 标签：`{_md(row['progression_label'])}`\n")
                handle.write(f"- Sample ID：`{_md(row['sample_id'])}`\n")
                handle.write(f"- Patient hash：`{_md(row['patient_id_hash'])}`\n")
                handle.write(
                    f"- Study/Image：`{_md(row.get('prior_study_id'))}` / "
                    f"`{_md(row.get('current_study_id'))}`；"
                    f"`{_md(row.get('prior_image_path'))}` / "
                    f"`{_md(row.get('current_image_path'))}`\n"
                )
                handle.write(
                    f"- 内部日期/间隔：`{_md(row.get('prior_datetime'))}` → "
                    f"`{_md(row.get('current_datetime'))}`；"
                    f"{_md(row.get('interval_days'))} days；"
                    f"{_md(row.get('interval_basis'))}\n"
                )
                handle.write(f"- 入选原因：{_md(row.get('selection_reasons', []))}\n")
                for seed in SEEDS:
                    prediction = _md(row.get(f"seed{seed}_prediction"))
                    handle.write(
                        f"- Seed {seed}：pred=`{prediction}`，"
                        f"conf={_md(row.get(f'seed{seed}_confidence'))}，"
                        f"NLL={_md(row.get(f'seed{seed}_nll'))}，"
                        f"negative={_md(row.get(f'seed{seed}_negative_influence'))}，"
                        f"positive={_md(row.get(f'seed{seed}_positive_influence'))}，"
                        f"self={_md(row.get(f'seed{seed}_self_influence'))}，"
                        f"adapter={_md(row.get(f'seed{seed}_adapter_signed_influence'))}\n"
                    )
                handle.write(
                    f"\n**PRIOR report**\n\n{_md(row.get('prior_report'))}\n\n"
                )
                handle.write(
                    f"**CURRENT report**\n\n{_md(row.get('current_report'))}\n\n"
                )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _score_fields(split: str) -> list[str]:
    fields = [
        "split",
        "source",
        "finding",
        "progression_label",
        "sample_id",
        "patient_id_hash",
        "risk_tier",
        "selection_reasons",
        "wrong_seed_count",
        "opposite_direction_error_seed_count",
        "seed_disagreement",
        "mean_nll",
        "mean_nll_percentile_within_source_label",
    ]
    for seed in SEEDS:
        fields.extend(
            [
                f"seed{seed}_prediction",
                f"seed{seed}_confidence",
                f"seed{seed}_nll",
                f"seed{seed}_wrong",
                f"seed{seed}_opposite_direction_error",
            ]
        )
        if split == "train":
            fields.extend(
                [
                    f"seed{seed}_signed_influence",
                    f"seed{seed}_positive_influence",
                    f"seed{seed}_negative_influence",
                    f"seed{seed}_negative_influence_magnitude",
                    f"seed{seed}_negative_influence_magnitude_percentile_within_source_label",
                    f"seed{seed}_self_influence",
                    f"seed{seed}_self_influence_percentile_within_source_label",
                    f"seed{seed}_adapter_signed_influence",
                    f"seed{seed}_adapter_negative_influence_magnitude",
                    f"seed{seed}_adapter_negative_percentile_within_source_label",
                ]
            )
    if split == "train":
        fields.extend(
            [
                "negative_influence_seed_hits_top5",
                "self_influence_seed_hits_top10",
                "self_influence_seed_hits_top5",
                "adapter_confirmation_unstable",
            ]
        )
    return fields


def _aggregate_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    dimensions = ("split", "source", "progression_label", "finding", "risk_tier")
    result: dict[str, Any] = {
        "schema": "prta-cxr.approximate-tracin-aggregate.v1",
        "candidate_claim": "high_risk_candidates_not_proven_errors",
        "counts": {},
        "error_types": dict(
            Counter(
                reason for row in rows for reason in row.get("selection_reasons", [])
            )
        ),
    }
    for dimension in dimensions:
        result["counts"][dimension] = dict(Counter(str(row[dimension]) for row in rows))
    return result


def assemble_outputs(
    rows: Sequence[dict[str, Any]],
    *,
    output: Path,
    snapshot_before: Mapping[str, str],
    split_manifest: Path,
    cache_root: Path,
    text_cache: Path,
    weights: Path,
    runs_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    train_rows = [dict(row) for row in rows if row["split"] == "train"]
    dev_rows = [dict(row) for row in rows if row["split"] == "dev"]
    train_predictions: dict[int, dict[str, np.ndarray]] = {}
    dev_predictions: dict[int, dict[str, np.ndarray]] = {}
    seed_overlap: dict[str, float] = {}
    for seed in SEEDS:
        train = _load_npz(output / "_work" / f"train_seed{seed}.npz")
        dev = _load_npz(output / "_work" / f"dev_seed{seed}.npz")
        train_predictions[seed] = {
            "prediction": np.asarray(
                [PROGRESSION_LABELS[int(value)] for value in train["prediction_index"]],
                dtype=str,
            ),
            "confidence": train["confidence"],
            "nll": train["nll"],
        }
        dev_predictions[seed] = {
            "prediction": np.asarray(
                [PROGRESSION_LABELS[int(value)] for value in dev["prediction_index"]],
                dtype=str,
            ),
            "confidence": dev["confidence"],
            "nll": dev["nll"],
        }
        for index, row in enumerate(train_rows):
            for name in (
                "signed_influence",
                "positive_influence",
                "negative_influence",
                "negative_influence_magnitude",
                "self_influence",
                "adapter_signed_influence",
                "adapter_negative_influence_magnitude",
            ):
                row[f"seed{seed}_{name}"] = float(train[name][index])
        fast_percentile = grouped_percentiles(
            train_rows, f"seed{seed}_negative_influence_magnitude"
        )
        adapter_percentile = grouped_percentiles(
            train_rows, f"seed{seed}_adapter_negative_influence_magnitude"
        )
        overlap_groups: list[float] = []
        for source in sorted({str(row["source"]) for row in train_rows}):
            for label in PROGRESSION_LABELS:
                indices = [
                    index
                    for index, row in enumerate(train_rows)
                    if row["source"] == source and row["progression_label"] == label
                ]
                fast_top = {
                    index for index in indices if fast_percentile[index] >= 0.95
                }
                adapter_top = {
                    index for index in indices if adapter_percentile[index] >= 0.95
                }
                denominator = max(1, min(len(fast_top), len(adapter_top)))
                overlap_groups.append(len(fast_top & adapter_top) / denominator)
        overlap = float(np.median(overlap_groups))
        seed_overlap[str(seed)] = overlap
        unstable = overlap < 0.60
        for index, row in enumerate(train_rows):
            row[f"seed{seed}_adapter_negative_percentile_within_source_label"] = float(
                adapter_percentile[index]
            )
            disagreement = (fast_percentile[index] >= 0.95) != (
                adapter_percentile[index] >= 0.95
            )
            row["adapter_confirmation_unstable"] = bool(
                row.get("adapter_confirmation_unstable", False)
                or (unstable and disagreement)
            )
    add_prediction_summary(train_rows, train_predictions)
    add_prediction_summary(dev_rows, dev_predictions)
    tier_train_rows(train_rows)
    tier_dev_rows(dev_rows)
    numeric = ["mean_nll"]
    for seed in SEEDS:
        numeric.extend(
            [
                f"seed{seed}_nll",
                f"seed{seed}_confidence",
                f"seed{seed}_negative_influence_magnitude",
                f"seed{seed}_self_influence",
                f"seed{seed}_adapter_signed_influence",
            ]
        )
    ensure_finite_columns(train_rows, numeric)
    ensure_finite_columns(dev_rows, ["mean_nll"] + [f"seed{s}_nll" for s in SEEDS])
    if len({row["sample_id"] for row in train_rows}) != EXPECTED_TRAIN_ROWS:
        raise AuditContractError("final Train mapping is missing or duplicated")
    if len({row["sample_id"] for row in dev_rows}) != EXPECTED_DEV_ROWS:
        raise AuditContractError("final Dev mapping is missing or duplicated")
    flagged = [row for row in [*train_rows, *dev_rows] if row["risk_tier"] != "Context"]
    flagged.sort(
        key=lambda row: (
            {"Tier A": 0, "Tier B": 1, "Tier C": 2}[row["risk_tier"]],
            row["split"],
            row["source"],
            row["progression_label"],
            row["sample_id"],
        )
    )
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "train_all_scores.csv", train_rows, _score_fields("train"))
    _write_csv(output / "dev_all_scores.csv", dev_rows, _score_fields("dev"))
    flagged_fields = list(dict.fromkeys(_score_fields("train") + _score_fields("dev")))
    _write_csv(output / "all_flagged_candidates.csv", flagged, flagged_fields)
    case_rows: list[dict[str, Any]] = []
    original = {str(row["sample_id"]): dict(row) for row in rows}
    for row in flagged:
        details = original[str(row["sample_id"])] | dict(row)
        details["audit_claim"] = "high_risk_candidate_not_proven_error"
        case_rows.append(details)
    _write_jsonl(output / "case_details.jsonl", case_rows)
    _write_detailed_markdown(
        output / "PRTA_CXR_TracIn全部高风险样本内部审计.md", case_rows
    )
    summary = _aggregate_summary(flagged)
    summary["all_rows"] = {
        "train": len(train_rows),
        "dev": len(dev_rows),
        "flagged": len(flagged),
        "context": len(train_rows) + len(dev_rows) - len(flagged),
    }
    summary["adapter_top5_overlap_median_by_seed"] = seed_overlap
    replace_json_atomic(output / "aggregate_summary.json", summary)
    snapshot_after = input_snapshot(
        split_manifest=split_manifest,
        cache_root=cache_root,
        text_cache=text_cache,
        weights=weights,
        runs_root=runs_root,
    )
    if dict(snapshot_before) != snapshot_after:
        raise AuditContractError("read-only input hash changed during audit")
    artifacts = [
        output / "train_all_scores.csv",
        output / "dev_all_scores.csv",
        output / "all_flagged_candidates.csv",
        output / "PRTA_CXR_TracIn全部高风险样本内部审计.md",
        output / "case_details.jsonl",
        output / "aggregate_summary.json",
    ]
    code_files = [
        repo_root / "src" / "prta_cxr" / "audit" / "tracin.py",
        repo_root / "src" / "prta_cxr" / "audit" / "runner.py",
        repo_root / "src" / "prta_cxr" / "cli_tracin_audit.py",
        repo_root / "scripts" / "14_run_tracin_audit.py",
        repo_root / "scripts" / "15_keep_tracin_audit.py",
        repo_root / "tests" / "test_tracin_audit.py",
    ]
    receipt = {
        "schema": AUDIT_SCHEMA,
        "status": "COMPLETE_READONLY_APPROXIMATE_TRACIN_AUDIT",
        "completed_at": datetime.now(UTC).isoformat(),
        "claim_boundary": "high_risk_candidates_not_proven_errors",
        "formal_development_gate_unchanged": "STOP_DEVELOPMENT_GATE",
        "training_started": False,
        "optimizer_step_called": False,
        "labels_modified": False,
        "samples_deleted": False,
        "splits_modified": False,
        "checkpoints_modified": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
        "counts": {
            "train": len(train_rows),
            "dev": len(dev_rows),
            "probes": EXPECTED_PROBES,
            "flagged": len(flagged),
            "tier": dict(Counter(row["risk_tier"] for row in flagged)),
        },
        "checkpoints_per_seed": {str(seed): ["best.pt", "last.pt"] for seed in SEEDS},
        "last_layer_method": "captum_tracincpfast_exact_gradient_dot",
        "adapter_confirmation_method": (
            "symmetric_finite_difference_classifier_plus_four_adapters"
        ),
        "adapter_top5_overlap_median_by_seed": seed_overlap,
        "input_hashes_before": dict(snapshot_before),
        "input_hashes_after": snapshot_after,
        "input_hashes_unchanged": True,
        "output_hashes": {path.name: sha256_file(path) for path in artifacts},
        "code": {
            "git_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "captum": __import__("captum").__version__,
            "file_sha256": {
                str(path.relative_to(repo_root)).replace("\\", "/"): sha256_file(path)
                for path in code_files
            },
        },
    }
    replace_json_atomic(output / "audit_receipt.json", receipt)
    return receipt


def code_safety_scan(repo_root: Path) -> dict[str, Any]:
    roots = [
        repo_root / "src" / "prta_cxr" / "audit",
        repo_root / "src" / "prta_cxr" / "cli_tracin_audit.py",
        repo_root / "scripts" / "14_run_tracin_audit.py",
        repo_root / "scripts" / "15_keep_tracin_audit.py",
    ]
    files = [
        path
        for root in roots
        for path in ([root] if root.is_file() else root.rglob("*.py"))
    ]
    forbidden = (
        re.compile(r"optimizer\s*\.\s*step\s*\("),
        re.compile(r"(?<![A-Za-z0-9_])train_model\s*\("),
    )
    violations = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern.search(text):
                violations.append(f"{path.name}:{pattern.pattern}")
    if violations:
        raise AuditContractError(f"audit code safety scan failed: {violations}")
    return {
        "python_files": len(files),
        "forbidden_training_calls": 0,
        "patterns": [pattern.pattern for pattern in forbidden],
    }
