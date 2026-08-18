from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.phase20_comparator_program import COMPARATOR_SPECS, COMPARATOR_STATUS
from prta_cxr.phase20_training_finalize import (
    _closed,
    _read_json,
    _write_new_json,
    validate_phase20_training_job,
)

COMPARISON_PROTOCOL = {
    "V2": "Native PRTA reference",
    "S0": "Native PRTA reference",
    "B401": "Native",
    "B402": "Native",
    "TILA8": "Native",
    "BioViLT": "Architecture-inspired",
    "CheXRelNet": "Architecture-inspired",
    "TILAPaper": "Paper-based reimplementation",
}


def _mean_sd(values: Sequence[float]) -> dict[str, float | int]:
    return {
        "mean": float(mean(values)),
        "sample_sd": float(stdev(values)),
        "n": len(values),
    }


def _method_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if sorted(int(row["seed"]) for row in rows) != [17, 28, 43]:
        raise ValueError("comparator method lacks the exact three-Seed roster")
    scalar_names = (
        "macro_f1",
        "balanced_accuracy",
        "min_class_recall",
        "opposite_direction_error_rate",
        "nll",
        "brier",
    )
    scalars = {
        metric: _mean_sd([float(dict(row["metrics"])[metric]) for row in rows])
        for metric in scalar_names
        if all(metric in dict(row["metrics"]) for row in rows)
    }
    per_class = {}
    for metric in ("per_class_recall", "per_class_f1"):
        if not all(
            set(dict(row["ordinary"]).get(metric, {})) == set(PROGRESSION_LABELS)
            for row in rows
        ):
            raise ValueError(f"comparator best epoch lacks complete {metric}")
        per_class[metric] = {
            label: _mean_sd(
                [float(dict(row["ordinary"])[metric][label]) for row in rows]
            )
            for label in PROGRESSION_LABELS
        }
    parameter_audits = [dict(row["parameter_audit"]) for row in rows]
    if any(
        set(value) != {"total_parameters", "trainable_parameters"}
        for value in parameter_audits
    ):
        raise ValueError("comparator run lacks exact parameter audit")
    if any(value != parameter_audits[0] for value in parameter_audits[1:]):
        raise ValueError("comparator parameter count drifts across Seeds")
    durations = [float(row["duration_seconds"]) for row in rows]
    return {
        "seeds": [17, 28, 43],
        "scalar_metrics": scalars,
        **per_class,
        "parameter_count": parameter_audits[0],
        "training_time_seconds": _mean_sd(durations),
        "by_seed": {
            str(row["seed"]): {
                "experiment_id": row["experiment_id"],
                "hardware_class": row["hardware_class"],
                "best_epoch": row["best_epoch"],
                "completed_epochs": row["completed_epochs"],
                "duration_seconds": row["duration_seconds"],
                "checkpoint_sha256": row["checkpoint_sha256"],
                "training_receipt_sha256": row["training_receipt_sha256"],
            }
            for row in sorted(rows, key=lambda value: int(value["seed"]))
        },
    }


def finalize_phase20_comparators(
    program_root: Path,
    state_roots: Mapping[str, Path],
    artifact_roots: Mapping[str, Path],
    *,
    host: str | None = None,
) -> dict[str, Any]:
    if host not in {None, "server", "local"}:
        raise ValueError("comparator finalizer host must be server, local, or global")
    if set(state_roots) != set(artifact_roots):
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
        or int(preparation.get("job_count", -1)) != 24
        or set(preparation.get("systems", [])) != set(COMPARATOR_SPECS)
    ):
        raise ValueError("frozen comparator program identity drift")
    jobs = [dict(job) for job in registry.get("jobs", [])]
    if len(jobs) != 24 or len({str(job["job_id"]) for job in jobs}) != 24:
        raise ValueError("comparator registry is not 24 unique jobs")
    expected = {
        str(job["job_id"]): job
        for job in jobs
        if host is None or str(job.get("host")) == host
    }
    if not expected:
        raise ValueError("comparator finalizer selected an empty host shard")
    attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for label, root in state_roots.items():
        if not root.is_dir():
            raise ValueError(f"comparator state root unavailable: {label}")
        for path in sorted(root.glob("*.json")):
            value = _read_json(path)
            if value.get("schema") != "prta-cxr.phase20-job-state.v1":
                continue
            job_id = str(value.get("job_id", ""))
            if job_id in expected:
                attempts[job_id].append(
                    {
                        **value,
                        "_artifact_root": str(artifact_roots[label]),
                        "_state_sha256": sha256_file(path),
                    }
                )
    rows = []
    attempt_audit = []
    for job_id, job in expected.items():
        values = attempts.get(job_id, [])
        passes = [value for value in values if value.get("status") == "PASS"]
        if len(passes) != 1:
            raise ValueError(
                f"expected exactly one comparator PASS for {job_id}, "
                f"found {len(passes)}"
            )
        lane = str(job["lane"])
        row = validate_phase20_training_job(
            job,
            passes[0],
            program_root=program_root,
            program_source_commit=str(preparation["source_commit"]),
            queue_sha256=str(preparation["queue_hashes"][f"{lane}.json"]),
            frozen_inputs=dict(input_manifest["input_sha256"]),
        )
        config = _read_json(program_root / "configs" / f"{row['experiment_id']}.json")
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
        rows.append(
            {
                **row,
                "method": method,
                "method_provenance": config["method_provenance"],
                "comparison_protocol": COMPARISON_PROTOCOL[method],
                "official_implementation": False,
                "official_checkpoint": False,
            }
        )
        attempt_audit.append(
            {
                "job_id": job_id,
                "attempts": [
                    {
                        "status": value.get("status"),
                        "state_sha256": value["_state_sha256"],
                        "selected": value is passes[0],
                    }
                    for value in values
                ],
            }
        )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["method"])].append(row)
    if host is None and set(grouped) != set(COMPARATOR_SPECS):
        raise ValueError("comparator method coverage drift")
    summaries = {}
    for method, values in sorted(grouped.items()):
        if host is not None:
            continue
        summaries[method] = {
            "method_provenance": COMPARATOR_SPECS[method]["method_provenance"],
            "comparison_protocol": COMPARISON_PROTOCOL[method],
            "official_implementation": False,
            "official_checkpoint": False,
            **_method_summary(values),
        }
    return {
        "schema": "prta-cxr.phase20-comparator-final-aggregate.v1",
        "status": (
            "PASS_PHASE20_COMPARATOR_FINAL_NO_SELECTION_AGGREGATE"
            if host is None
            else "PASS_PHASE20_COMPARATOR_HOST_SHARD_VALIDATED"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "host": host or "global_direct",
        "program_preparation_sha256": sha256_file(preparation_path),
        "source_commit": preparation["source_commit"],
        "expected_cell_count": len(expected),
        "unique_pass_count": len(expected),
        "job_ids": sorted(expected),
        "methods": summaries,
        "cells": sorted(rows, key=lambda row: str(row["job_id"])),
        "attempt_audit": sorted(attempt_audit, key=lambda row: str(row["job_id"])),
        "selection_performed": False,
        "winner_selected": False,
        "official_implementation_included": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def merge_phase20_comparator_shards(
    program_root: Path, shard_paths: Sequence[Path]
) -> dict[str, Any]:
    preparation_path = program_root / "preparation_receipt.json"
    registry_path = program_root / "job_registry.json"
    preparation = _read_json(preparation_path)
    registry = _read_json(registry_path)
    if preparation.get("status") != COMPARATOR_STATUS or preparation.get(
        "registry_sha256"
    ) != sha256_file(registry_path):
        raise ValueError("comparator shard merge program identity drift")
    expected = {str(job["job_id"]) for job in registry.get("jobs", [])}
    shards = [_read_json(path) for path in shard_paths]
    if len(shards) != 2 or {str(shard.get("host")) for shard in shards} != {
        "server",
        "local",
    }:
        raise ValueError("comparator merge requires one server and one local shard")
    preparation_sha = sha256_file(preparation_path)
    observed = []
    for shard, path in zip(shards, shard_paths, strict=True):
        _closed(shard, label=f"comparator shard {path}")
        if (
            shard.get("status") != "PASS_PHASE20_COMPARATOR_HOST_SHARD_VALIDATED"
            or shard.get("program_preparation_sha256") != preparation_sha
            or shard.get("source_commit") != preparation.get("source_commit")
            or int(shard.get("unique_pass_count", -1)) != len(shard.get("job_ids", []))
        ):
            raise ValueError(f"comparator host shard identity drift: {path}")
        if {str(row["job_id"]) for row in shard.get("cells", [])} != set(
            map(str, shard["job_ids"])
        ):
            raise ValueError(f"comparator host shard payload/job drift: {path}")
        observed.extend(map(str, shard["job_ids"]))
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("comparator host shards have duplicate or missing jobs")
    rows = [row for shard in shards for row in shard["cells"]]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["method"])].append(row)
    if set(grouped) != set(COMPARATOR_SPECS) or len(rows) != 24:
        raise ValueError("merged comparator method/cell coverage drift")
    summaries = {
        method: {
            "method_provenance": COMPARATOR_SPECS[method]["method_provenance"],
            "comparison_protocol": COMPARISON_PROTOCOL[method],
            "official_implementation": False,
            "official_checkpoint": False,
            **_method_summary(values),
        }
        for method, values in sorted(grouped.items())
    }
    return {
        "schema": "prta-cxr.phase20-comparator-final-aggregate.v1",
        "status": "PASS_PHASE20_COMPARATOR_FINAL_NO_SELECTION_AGGREGATE",
        "created_at": datetime.now(UTC).isoformat(),
        "host": "global_shard_merge",
        "program_preparation_sha256": preparation_sha,
        "source_commit": preparation["source_commit"],
        "expected_cell_count": 24,
        "unique_pass_count": 24,
        "job_ids": sorted(observed),
        "methods": summaries,
        "cells": sorted(rows, key=lambda row: str(row["job_id"])),
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
        "official_implementation_included": False,
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def finalize_phase20_comparators_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize Phase20 comparators")
    parser.add_argument("--comparator-program", type=Path, required=True)
    parser.add_argument("--state-root", action="append")
    parser.add_argument("--artifact-root", action="append")
    parser.add_argument("--host", choices=("server", "local"))
    parser.add_argument("--shard", type=Path, action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)

    def parse(values: Sequence[str], option: str) -> dict[str, Path]:
        result = {}
        for raw in values:
            if "=" not in raw:
                parser.error(f"{option} must use LABEL=PATH")
            label, path = raw.split("=", 1)
            if not label or label in result:
                parser.error(f"{option} labels must be unique")
            result[label] = Path(path)
        return result

    if args.shard:
        if args.state_root or args.artifact_root or args.host:
            parser.error("--shard merge cannot include host state/artifact options")
        result = merge_phase20_comparator_shards(
            args.comparator_program.resolve(), args.shard
        )
        _write_new_json(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if not args.state_root or not args.artifact_root:
        parser.error("host/direct finalization requires state and artifact roots")
    result = finalize_phase20_comparators(
        args.comparator_program.resolve(),
        parse(args.state_root, "--state-root"),
        parse(args.artifact_root, "--artifact-root"),
        host=args.host,
    )
    _write_new_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
