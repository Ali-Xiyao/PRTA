from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256, sha256_file

TRAINING_METRICS = (
    "macro_f1",
    "balanced_accuracy",
    "min_class_recall",
    "opposite_direction_error_rate",
    "nll",
    "brier",
)
SOURCE_HELD_METRICS = (
    "accuracy",
    "macro_f1",
    "balanced_accuracy",
    "min_class_recall",
    "opposite_direction_error_rate",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _closed(value: Mapping[str, Any], *, label: str) -> None:
    for key in (
        "external_opened",
        "external_evaluation_included",
        "internal_test_opened",
        "gold_opened",
        "protected_outcomes_opened",
    ):
        if key in value and value[key] is not False:
            raise ValueError(f"{label} reports protected/external access through {key}")
    for key in ("protected_outcome_read_count", "protected_read_count"):
        if key in value and int(value[key]) != 0:
            raise ValueError(f"{label} reports protected reads through {key}")


def _command_value(command: Sequence[object], option: str) -> str:
    values = list(map(str, command))
    try:
        index = values.index(option)
    except ValueError as error:
        raise ValueError(f"missing command option {option}") from error
    if index + 1 >= len(values):
        raise ValueError(f"missing command value {option}")
    return values[index + 1]


def _validated_outputs(
    job: Mapping[str, Any], state: Mapping[str, Any]
) -> list[dict[str, Any]]:
    expected = list(map(str, job.get("expected_outputs", [])))
    checks = state.get("output_checks")
    if not isinstance(checks, list) or len(checks) != len(expected):
        raise ValueError(f"output-check count drift: {job['job_id']}")
    result = []
    for template, raw in zip(expected, checks, strict=True):
        check = dict(raw)
        suffix = template.split("{output_root}", 1)[-1].replace("\\", "/").lstrip("/")
        recorded_path = Path(str(check.get("path", "")))
        artifact_root = state.get("_artifact_root")
        path = recorded_path
        if not path.is_file() and artifact_root:
            path = Path(str(artifact_root)) / Path(suffix)
        if not str(path).replace("\\", "/").endswith(suffix):
            raise ValueError(f"output path drift: {job['job_id']}")
        if check.get("exists") is not True or not path.is_file():
            raise ValueError(f"missing output: {job['job_id']}={path}")
        actual = sha256_file(path)
        if check.get("sha256") != actual:
            raise ValueError(f"output hash drift: {job['job_id']}={path}")
        result.append({"path": str(path), "sha256": actual})
    return result


def _best_metrics(receipt: Mapping[str, Any]) -> dict[str, float]:
    best_epoch = int(receipt["best_epoch"])
    rows = [
        dict(row)
        for row in receipt.get("history", [])
        if int(row.get("epoch", -1)) == best_epoch
    ]
    if len(rows) != 1:
        raise ValueError("training best epoch is not unique")
    metrics = {key: float(rows[0][key]) for key in TRAINING_METRICS if key in rows[0]}
    if "macro_f1" not in metrics:
        raise ValueError("training best epoch lacks Macro-F1")
    if abs(metrics["macro_f1"] - float(receipt["best_dev_macro_f1"])) > 1e-12:
        raise ValueError("training best Macro-F1 drift")
    return metrics


def _duration_seconds(receipt: Mapping[str, Any]) -> float | None:
    start = receipt.get("start_time")
    end = receipt.get("end_time")
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    return float(
        (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    )


def _validate_materialized_training_config(
    checkpoint_config: Mapping[str, Any],
    frozen_config: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[str, str]:
    """Validate the one runtime-derived field added after the frozen config loads."""
    runtime_sha = canonical_sha256(checkpoint_config)
    frozen_sha = canonical_sha256(frozen_config)
    if runtime_sha == frozen_sha:
        return runtime_sha, frozen_sha

    audit = receipt.get("fraction_audit")
    label_counts = (
        dict(audit.get("label_counts", {})) if isinstance(audit, Mapping) else {}
    )
    noise_audit = audit.get("label_noise") if isinstance(audit, Mapping) else None
    if isinstance(noise_audit, Mapping):
        before_counts = dict(noise_audit.get("before_label_counts", {}))
        if (
            before_counts != label_counts
            or int(noise_audit.get("dev_label_changes", -1)) != 0
        ):
            raise ValueError("label-noise audit does not preserve frozen Dev labels")
        label_counts = dict(noise_audit.get("after_label_counts", {}))
    if set(label_counts) != set(PROGRESSION_LABELS):
        raise ValueError("runtime config drift lacks complete train label-count audit")
    expected_counts = [int(label_counts[label]) for label in PROGRESSION_LABELS]
    observed_loss = dict(checkpoint_config.get("classification_loss", {}))
    if list(observed_loss.get("class_counts", [])) != expected_counts:
        raise ValueError("runtime class counts disagree with train fraction audit")

    normalized = deepcopy(dict(checkpoint_config))
    normalized_loss = dict(normalized.get("classification_loss", {}))
    frozen_loss = dict(frozen_config.get("classification_loss", {}))
    if "class_counts" in frozen_loss:
        normalized_loss["class_counts"] = frozen_loss["class_counts"]
    else:
        normalized_loss.pop("class_counts", None)
    normalized["classification_loss"] = normalized_loss
    if canonical_sha256(normalized) != frozen_sha:
        raise ValueError(
            "training config drift exceeds runtime-materialized class counts"
        )
    return runtime_sha, frozen_sha


def validate_phase20_training_job(
    job: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    program_root: Path,
    program_source_commit: str,
    queue_sha256: str,
    frozen_inputs: Mapping[str, str],
) -> dict[str, Any]:
    job_id = str(job["job_id"])
    if (
        state.get("schema") != "prta-cxr.phase20-job-state.v1"
        or state.get("status") != "PASS"
        or state.get("job_id") != job_id
        or state.get("group") != job.get("group")
        or state.get("lane") != job.get("lane")
        or int(state.get("return_code", -1)) != 0
    ):
        raise ValueError(f"invalid Phase20 PASS state: {job_id}")
    if state.get("source_commit") != program_source_commit:
        raise ValueError(f"Phase20 source commit drift: {job_id}")
    if state.get("queue_sha256") != queue_sha256:
        raise ValueError(f"Phase20 queue hash drift: {job_id}")
    _closed(state, label=f"state {job_id}")
    outputs = _validated_outputs(job, state)
    by_name = {Path(row["path"]).name: row for row in outputs}
    if set(by_name) != {"training_receipt.json", "best.pt"}:
        raise ValueError(f"training output identity drift: {job_id}")
    receipt_path = Path(by_name["training_receipt.json"]["path"])
    checkpoint_path = Path(by_name["best.pt"]["path"])
    receipt = _read_json(receipt_path)
    _closed(receipt, label=f"training receipt {job_id}")
    if (
        receipt.get("schema") != "prta-cxr.training-receipt.v1"
        or receipt.get("status") != "PASS_TRAINING_FINISHED"
        or receipt.get("formal_experiment") is not True
    ):
        raise ValueError(f"invalid training receipt: {job_id}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError(f"invalid training checkpoint: {job_id}")
    config = dict(checkpoint.get("config", {}))
    experiment_id = job_id.removeprefix("train-")
    config_path = program_root / "configs" / f"{experiment_id}.json"
    frozen_config = _read_json(config_path)
    config_sha, frozen_config_sha = _validate_materialized_training_config(
        config, frozen_config, receipt
    )
    if (
        config.get("experiment_id") != experiment_id
        or int(config.get("seed", -1)) != int(receipt.get("seed", -2))
        or receipt.get("config_sha256") != config_sha
    ):
        raise ValueError(f"training config/seed drift: {job_id}")
    executed_config = Path(_command_value(state.get("command", []), "--config"))
    if executed_config.name != config_path.name:
        raise ValueError(f"executed config identity drift: {job_id}")
    if executed_config.is_file() and canonical_sha256(
        _read_json(executed_config)
    ) != canonical_sha256(frozen_config):
        raise ValueError(f"executed config content drift: {job_id}")
    input_hashes = dict(checkpoint.get("input_hashes", {}))
    if not input_hashes or dict(receipt.get("input_hashes", {})) != input_hashes:
        raise ValueError(f"training receipt/checkpoint input drift: {job_id}")
    for role in (
        "split_manifest",
        "cleaned_split_freeze",
        "cache_manifest",
        "text_cache",
        "weights",
        "label_quality_audit",
    ):
        if input_hashes.get(role) != frozen_inputs.get(role):
            raise ValueError(f"training frozen input drift: {job_id}/{role}")
    if "--counterfactual-prior-map" in list(map(str, state.get("command", []))):
        map_path = Path(
            _command_value(state.get("command", []), "--counterfactual-prior-map")
        )
        if input_hashes.get("matched_hard_prior_map") != sha256_file(map_path):
            raise ValueError(f"training matched-hard map drift: {job_id}")
    metrics = _best_metrics(receipt)
    best_history = next(
        dict(row)
        for row in receipt["history"]
        if int(row.get("epoch", -1)) == int(receipt["best_epoch"])
    )
    ordinary = dict(best_history.get("ordinary", {}))
    parameter_audit = dict(receipt.get("parameter_audit", {}))
    checkpoint_parameter_audit = dict(checkpoint.get("parameter_audit", {}))
    if parameter_audit != checkpoint_parameter_audit:
        raise ValueError(f"checkpoint parameter audit drift: {job_id}")
    if (
        int(checkpoint.get("best_epoch", -1)) != int(receipt["best_epoch"])
        or abs(
            float(checkpoint.get("best_dev_macro_f1", -1.0))
            - float(receipt["best_dev_macro_f1"])
        )
        > 1e-12
    ):
        raise ValueError(f"checkpoint best-epoch metric drift: {job_id}")
    return {
        "job_id": job_id,
        "experiment_id": experiment_id,
        "seed": int(receipt["seed"]),
        "lane": str(job["lane"]),
        "hardware_class": str(job["hardware_class"]),
        "hardware_provenance": "frozen_lane_assignment",
        "source_commit": program_source_commit,
        "queue_sha256": queue_sha256,
        "config_sha256": config_sha,
        "frozen_config_sha256": frozen_config_sha,
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "training_receipt_sha256": sha256_file(receipt_path),
        "input_hashes": input_hashes,
        "best_epoch": int(receipt["best_epoch"]),
        "completed_epochs": int(
            receipt.get("completed_epochs", len(receipt["history"]))
        ),
        "duration_seconds": _duration_seconds(receipt),
        "parameter_audit": parameter_audit,
        "metrics": metrics,
        "ordinary": ordinary,
    }


def _validate_map_job(
    job: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    program_root: Path,
    frozen_inputs: Mapping[str, str],
) -> dict[str, Any]:
    outputs = _validated_outputs(job, state)
    if len(outputs) != 1:
        raise ValueError(f"map output count drift: {job['job_id']}")
    path = Path(outputs[0]["path"])
    value = _read_json(path)
    _closed(value, label=f"map {job['job_id']}")
    executed_config = Path(_command_value(state.get("command", []), "--config"))
    config_path = program_root / "configs" / executed_config.name
    if not config_path.is_file():
        raise ValueError(f"map frozen config missing: {job['job_id']}")
    if (
        value.get("schema") != "prta-cxr.matched-hard-prior-map.v1"
        or value.get("status") != "PASS_PHASE16_TRANSFORMED_MATCHED_HARD_MAP"
        or value.get("split_manifest_sha256") != frozen_inputs["split_manifest"]
        or value.get("cache_manifest_sha256") != frozen_inputs["cache_manifest"]
        or value.get("config_sha256") != sha256_file(config_path)
        or value.get("target_roster_complete") is not True
        or value.get("candidate_roster_subset") is not True
    ):
        raise ValueError(f"transformed map identity/coverage drift: {job['job_id']}")
    return {
        "job_id": str(job["job_id"]),
        "sha256": sha256_file(path),
        "config_file_sha256": sha256_file(config_path),
        "transformed_roster_sha256": value.get("transformed_roster_sha256"),
        "target_roster_sha256": value.get("target_roster_sha256"),
        "candidate_roster_sha256": value.get("candidate_roster_sha256"),
    }


def _validate_evaluation_job(
    job: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any]:
    outputs = _validated_outputs(job, state)
    if len(outputs) != 1:
        raise ValueError(f"source-held output count drift: {job['job_id']}")
    path = Path(outputs[0]["path"])
    value = _read_json(path)
    _closed(value, label=f"source-held evaluation {job['job_id']}")
    experiment_id = str(job["job_id"]).removeprefix("evaluate-")
    artifact_root = Path(str(state.get("_artifact_root", "")))
    checkpoint_path = artifact_root / "runs" / experiment_id / "best.pt"
    training_receipt_path = (
        artifact_root / "runs" / experiment_id / "training_receipt.json"
    )
    if (
        value.get("schema") != "prta-cxr.source-held-out-dev-evaluation.v1"
        or value.get("status") != "PASS_SOURCE_HELD_OUT_TARGET_DEV_EVALUATION"
        or value.get("selection_performed") is not False
        or value.get("target_source_used_for_selection") is not False
        or not checkpoint_path.is_file()
        or value.get("checkpoint_sha256") != sha256_file(checkpoint_path)
        or not training_receipt_path.is_file()
        or value.get("training_receipt_sha256") != sha256_file(training_receipt_path)
    ):
        raise ValueError(f"source-held evaluation identity drift: {job['job_id']}")
    return {
        "job_id": str(job["job_id"]),
        "experiment_id": str(value["experiment_id"]),
        "seed": int(value["seed"]),
        "target_source": str(value["target_source"]),
        "receipt_sha256": sha256_file(path),
        "metrics": value["metrics"],
    }


def _three_seed_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["experiment_id"]).rsplit("-S", 1)[0]].append(row)
    result = {}
    for experiment, values in sorted(grouped.items()):
        if sorted(int(value["seed"]) for value in values) != [17, 28, 43]:
            continue
        metrics = {}
        for metric in TRAINING_METRICS:
            observations = [
                float(dict(value["metrics"])[metric])
                for value in values
                if metric in dict(value["metrics"])
            ]
            if len(observations) == 3:
                metrics[metric] = {
                    "mean": float(mean(observations)),
                    "sample_sd": float(stdev(observations)),
                }
        result[experiment] = {"seeds": [17, 28, 43], "metrics": metrics}
    return result


def _source_held_three_seed_summary(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["experiment_id"]).rsplit("-S", 1)[0]].append(row)
    result = {}
    for experiment, values in sorted(grouped.items()):
        if sorted(int(value.get("seed", -1)) for value in values) != [17, 28, 43]:
            continue
        target_sources = {str(value.get("target_source", "")) for value in values}
        rows_seen = {int(dict(value["metrics"])["rows"]) for value in values}
        patients_seen = {int(dict(value["metrics"])["patients"]) for value in values}
        if len(target_sources) != 1 or len(rows_seen) != 1 or len(patients_seen) != 1:
            raise ValueError(f"source-held three-Seed identity drift: {experiment}")
        scopes = {}
        for scope in ("ordinary", "patient_balanced"):
            scoped = [dict(dict(value["metrics"])[scope]) for value in values]
            metrics = {}
            for metric in SOURCE_HELD_METRICS:
                observations = [float(value[metric]) for value in scoped]
                metrics[metric] = {
                    "mean": float(mean(observations)),
                    "sample_sd": float(stdev(observations)),
                }
            per_class = {}
            for metric in ("per_class_f1", "per_class_recall"):
                per_class[metric] = {}
                for label in PROGRESSION_LABELS:
                    observations = [
                        float(dict(value[metric])[label]) for value in scoped
                    ]
                    per_class[metric][label] = {
                        "mean": float(mean(observations)),
                        "sample_sd": float(stdev(observations)),
                    }
            scopes[scope] = {"metrics": metrics, **per_class}
        result[experiment] = {
            "seeds": [17, 28, 43],
            "target_source": next(iter(target_sources)),
            "rows": next(iter(rows_seen)),
            "patients": next(iter(patients_seen)),
            "scopes": scopes,
        }
    return result


def finalize_phase20_training(
    program_root: Path,
    state_roots: Mapping[str, Path],
    artifact_roots: Mapping[str, Path] | None = None,
    *,
    host: str | None = None,
) -> dict[str, Any]:
    if host not in {None, "server", "local"}:
        raise ValueError("Phase20-A finalizer host must be server, local, or global")
    artifact_roots = dict(artifact_roots or {})
    if set(artifact_roots) != set(state_roots):
        raise ValueError("Phase20-A state/artifact root labels must match")
    preparation = _read_json(program_root / "preparation_receipt.json")
    registry_path = program_root / "job_registry.json"
    registry = _read_json(registry_path)
    input_manifest_path = program_root / "input_manifest.json"
    input_manifest = _read_json(input_manifest_path)
    _closed(preparation, label="Phase20-A preparation")
    _closed(input_manifest, label="Phase20-A inputs")
    if (
        preparation.get("status") != "PASS_PHASE20_SLIM_S1_PROGRAM_FROZEN"
        or preparation.get("registry_sha256") != sha256_file(registry_path)
        or preparation.get("input_manifest_sha256") != sha256_file(input_manifest_path)
        or int(preparation.get("training_cell_count", -1)) != 63
        or int(preparation.get("job_count", -1)) != 88
    ):
        raise ValueError("Phase20-A frozen program identity drift")
    jobs = [dict(job) for job in registry.get("jobs", [])]
    if len(jobs) != 88 or len({str(job["job_id"]) for job in jobs}) != 88:
        raise ValueError("Phase20-A registry is not 88 unique jobs")
    expected = {
        str(job["job_id"]): job
        for job in jobs
        if host is None or str(job.get("host")) == host
    }
    if not expected:
        raise ValueError("Phase20-A finalizer selected an empty host shard")
    attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for label, root in state_roots.items():
        if not root.is_dir():
            raise ValueError(f"Phase20-A state root unavailable: {label}")
        for path in sorted(root.glob("*.json")):
            value = _read_json(path)
            if value.get("schema") != "prta-cxr.phase20-job-state.v1":
                continue
            job_id = str(value.get("job_id", ""))
            if job_id in expected:
                attempts[job_id].append(
                    {
                        **value,
                        "_path": str(path),
                        "_sha256": sha256_file(path),
                        "_artifact_root": str(artifact_roots[label]),
                    }
                )
    selected = {}
    attempt_audit = []
    for job_id, _job in expected.items():
        values = attempts.get(job_id, [])
        passes = [value for value in values if value.get("status") == "PASS"]
        if len(passes) != 1:
            raise ValueError(
                f"expected exactly one Phase20-A PASS for {job_id}, found {len(passes)}"
            )
        selected[job_id] = passes[0]
        attempt_audit.append(
            {
                "job_id": job_id,
                "attempts": [
                    {
                        "status": value.get("status"),
                        "state_sha256": value["_sha256"],
                        "selected": value is passes[0],
                    }
                    for value in values
                ],
            }
        )
    queue_hashes = dict(preparation["queue_hashes"])
    source_commit = str(preparation["source_commit"])
    frozen_inputs = dict(input_manifest["input_sha256"])
    training = []
    maps = []
    evaluations = []
    for job_id, job in expected.items():
        state = selected[job_id]
        lane = str(job["lane"])
        queue_sha = str(queue_hashes[f"{lane}.json"])
        if job_id.startswith("train-"):
            training.append(
                validate_phase20_training_job(
                    job,
                    state,
                    program_root=program_root,
                    program_source_commit=source_commit,
                    queue_sha256=queue_sha,
                    frozen_inputs=frozen_inputs,
                )
            )
        else:
            if (
                state.get("source_commit") != source_commit
                or state.get("queue_sha256") != queue_sha
                or state.get("lane") != lane
                or state.get("status") != "PASS"
                or int(state.get("return_code", -1)) != 0
            ):
                raise ValueError(f"Phase20-A non-training state drift: {job_id}")
            _closed(state, label=f"state {job_id}")
            if job_id.startswith("map-"):
                maps.append(
                    _validate_map_job(
                        job,
                        state,
                        program_root=program_root,
                        frozen_inputs=frozen_inputs,
                    )
                )
            elif job_id.startswith("evaluate-"):
                evaluations.append(_validate_evaluation_job(job, state))
            else:
                raise ValueError(f"unknown Phase20-A job type: {job_id}")
    expected_training = sum(job_id.startswith("train-") for job_id in expected)
    expected_evaluations = sum(job_id.startswith("evaluate-") for job_id in expected)
    expected_maps = sum(job_id.startswith("map-") for job_id in expected)
    if (
        len(training) != expected_training
        or len(evaluations) != expected_evaluations
        or len(maps) != expected_maps
    ):
        raise ValueError("Phase20-A terminal family counts drift")
    if host is None and (len(training), len(maps), len(evaluations)) != (63, 19, 6):
        raise ValueError("Phase20-A global terminal family counts drift")
    return {
        "schema": "prta-cxr.phase20-a-final-no-selection-aggregate.v1",
        "status": (
            "PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE"
            if host is None
            else "PASS_PHASE20_A_HOST_SHARD_VALIDATED"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "host": host or "global_direct",
        "program_preparation_sha256": sha256_file(
            program_root / "preparation_receipt.json"
        ),
        "source_commit": source_commit,
        "expected_job_count": len(expected),
        "unique_pass_count": len(expected),
        "job_ids": sorted(expected),
        "training_cell_count": len(training),
        "transformed_map_count": len(maps),
        "source_held_evaluation_count": len(evaluations),
        "training": sorted(training, key=lambda row: str(row["job_id"])),
        "transformed_maps": sorted(maps, key=lambda row: str(row["job_id"])),
        "source_held_evaluations": sorted(
            evaluations, key=lambda row: str(row["job_id"])
        ),
        "training_three_seed_summary": _three_seed_summary(training),
        "source_held_three_seed_summary": _source_held_three_seed_summary(
            evaluations
        ),
        "attempt_audit": sorted(attempt_audit, key=lambda row: str(row["job_id"])),
        "selection_performed": False,
        "winner_selected": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def merge_phase20_training_shards(
    program_root: Path, shard_paths: Sequence[Path]
) -> dict[str, Any]:
    preparation_path = program_root / "preparation_receipt.json"
    registry_path = program_root / "job_registry.json"
    preparation = _read_json(preparation_path)
    registry = _read_json(registry_path)
    if preparation.get(
        "status"
    ) != "PASS_PHASE20_SLIM_S1_PROGRAM_FROZEN" or preparation.get(
        "registry_sha256"
    ) != sha256_file(registry_path):
        raise ValueError("Phase20-A shard merge program identity drift")
    expected = {str(job["job_id"]) for job in registry.get("jobs", [])}
    shards = [_read_json(path) for path in shard_paths]
    if len(shards) != 2 or {str(shard.get("host")) for shard in shards} != {
        "server",
        "local",
    }:
        raise ValueError("Phase20-A merge requires one server and one local shard")
    preparation_sha = sha256_file(preparation_path)
    observed = []
    for shard, path in zip(shards, shard_paths, strict=True):
        _closed(shard, label=f"Phase20-A shard {path}")
        if (
            shard.get("status") != "PASS_PHASE20_A_HOST_SHARD_VALIDATED"
            or shard.get("program_preparation_sha256") != preparation_sha
            or shard.get("source_commit") != preparation.get("source_commit")
            or int(shard.get("unique_pass_count", -1)) != len(shard.get("job_ids", []))
        ):
            raise ValueError(f"Phase20-A host shard identity drift: {path}")
        payload_jobs = {
            str(row["job_id"])
            for family in (
                shard.get("training", []),
                shard.get("transformed_maps", []),
                shard.get("source_held_evaluations", []),
            )
            for row in family
        }
        if payload_jobs != set(map(str, shard["job_ids"])):
            raise ValueError(f"Phase20-A host shard payload/job drift: {path}")
        observed.extend(map(str, shard["job_ids"]))
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("Phase20-A host shards have duplicate or missing jobs")
    training = [row for shard in shards for row in shard["training"]]
    maps = [row for shard in shards for row in shard["transformed_maps"]]
    evaluations = [row for shard in shards for row in shard["source_held_evaluations"]]
    if (len(training), len(maps), len(evaluations)) != (63, 19, 6):
        raise ValueError("Phase20-A merged terminal family counts drift")
    return {
        "schema": "prta-cxr.phase20-a-final-no-selection-aggregate.v1",
        "status": "PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE",
        "created_at": datetime.now(UTC).isoformat(),
        "host": "global_shard_merge",
        "program_preparation_sha256": preparation_sha,
        "source_commit": preparation["source_commit"],
        "expected_job_count": 88,
        "unique_pass_count": 88,
        "job_ids": sorted(observed),
        "training_cell_count": 63,
        "transformed_map_count": 19,
        "source_held_evaluation_count": 6,
        "training": sorted(training, key=lambda row: str(row["job_id"])),
        "transformed_maps": sorted(maps, key=lambda row: str(row["job_id"])),
        "source_held_evaluations": sorted(
            evaluations, key=lambda row: str(row["job_id"])
        ),
        "training_three_seed_summary": _three_seed_summary(training),
        "source_held_three_seed_summary": _source_held_three_seed_summary(
            evaluations
        ),
        "host_shards": [
            {
                "host": shard["host"],
                "sha256": sha256_file(path),
                "job_count": shard["unique_pass_count"],
            }
            for shard, path in zip(shards, shard_paths, strict=True)
        ],
        "selection_performed": False,
        "winner_selected": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def finalize_phase20_training_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize the frozen Phase20-A run")
    parser.add_argument("--phase20-program", type=Path, required=True)
    parser.add_argument("--state-root", action="append")
    parser.add_argument("--artifact-root", action="append")
    parser.add_argument("--host", choices=("server", "local"))
    parser.add_argument("--shard", type=Path, action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.shard:
        if args.state_root or args.artifact_root or args.host:
            parser.error("--shard merge cannot include host state/artifact options")
        result = merge_phase20_training_shards(
            args.phase20_program.resolve(), args.shard
        )
        _write_new_json(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if not args.state_root or not args.artifact_root:
        parser.error("host/direct finalization requires state and artifact roots")
    roots = {}
    for raw in args.state_root:
        if "=" not in raw:
            parser.error("--state-root must use LABEL=PATH")
        label, path = raw.split("=", 1)
        if not label or label in roots:
            parser.error("state-root labels must be unique")
        roots[label] = Path(path)
    artifact_roots = {}
    for raw in args.artifact_root:
        if "=" not in raw:
            parser.error("--artifact-root must use LABEL=PATH")
        label, path = raw.split("=", 1)
        if not label or label in artifact_roots:
            parser.error("artifact-root labels must be unique")
        artifact_roots[label] = Path(path)
    result = finalize_phase20_training(
        args.phase20_program.resolve(), roots, artifact_roots, host=args.host
    )
    _write_new_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
