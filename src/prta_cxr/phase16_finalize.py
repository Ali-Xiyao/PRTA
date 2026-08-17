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

import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.phase16_queue import validate_registry

TRAINING_METRICS = (
    "macro_f1",
    "balanced_accuracy",
    "min_class_recall",
    "opposite_direction_error_rate",
    "nll",
    "brier",
)
LEGACY_GROUP_ALIASES = {
    "internal_longitudinal_comparator": {"official_baseline"},
}


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


def _validate_protected_fields(value: Mapping[str, Any], *, label: str) -> None:
    for key in ("internal_test_opened", "gold_opened", "protected_outcomes_opened"):
        if key in value and value[key] is not False:
            raise ValueError(f"{label} reports protected access through {key}")
    for key in ("protected_outcome_read_count", "protected_read_count"):
        if key in value and int(value[key]) != 0:
            raise ValueError(f"{label} reports protected reads through {key}")


def _expected_output_suffix(raw_path: str) -> str:
    marker = "{output_root}"
    suffix = raw_path.split(marker, 1)[-1] if marker in raw_path else raw_path
    return suffix.replace("\\", "/").lstrip("/")


def _validate_output_checks(
    job: Mapping[str, Any], state: Mapping[str, Any]
) -> list[dict[str, Any]]:
    expected = [str(value) for value in job.get("expected_outputs", [])]
    checks = state.get("output_checks")
    if not isinstance(checks, list) or len(checks) != len(expected):
        raise ValueError(f"output-check count drift: {job['job_id']}")
    validated: list[dict[str, Any]] = []
    for raw_expected, raw_check in zip(expected, checks, strict=True):
        check = dict(raw_check)
        path = Path(str(check.get("path", "")))
        suffix = _expected_output_suffix(raw_expected)
        normalized = str(path).replace("\\", "/")
        if not normalized.endswith(suffix):
            raise ValueError(f"unexpected output path for {job['job_id']}: {path}")
        if check.get("exists") is not True or not path.is_file():
            raise ValueError(f"missing expected output for {job['job_id']}: {path}")
        actual_sha = sha256_file(path)
        if check.get("sha256") != actual_sha:
            raise ValueError(f"output hash drift for {job['job_id']}: {path}")
        validated.append({"path": str(path), "sha256": actual_sha})
    return validated


def _command_option(command: Sequence[object], option: str) -> str | None:
    values = [str(value) for value in command]
    try:
        index = values.index(option)
    except ValueError:
        return None
    if index + 1 >= len(values):
        raise ValueError(f"missing value for command option {option}")
    return values[index + 1]


def _best_training_metrics(receipt: Mapping[str, Any]) -> dict[str, float]:
    best_epoch = int(receipt["best_epoch"])
    rows = [
        dict(row)
        for row in receipt.get("history", [])
        if int(row.get("epoch", -1)) == best_epoch
    ]
    if len(rows) != 1:
        raise ValueError("training best epoch is not unique in receipt history")
    best = rows[0]
    metrics = {key: float(best[key]) for key in TRAINING_METRICS if key in best}
    if "macro_f1" not in metrics:
        raise ValueError("training receipt lacks best-epoch Macro-F1")
    if abs(metrics["macro_f1"] - float(receipt["best_dev_macro_f1"])) > 1e-12:
        raise ValueError("training receipt best Macro-F1 drift")
    return metrics


def _validate_training_artifacts(
    job: Mapping[str, Any],
    state: Mapping[str, Any],
    outputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_name = {Path(str(row["path"])).name: dict(row) for row in outputs}
    if set(by_name) != {"training_receipt.json", "best.pt"}:
        raise ValueError(f"training output identity drift: {job['job_id']}")
    receipt_path = Path(str(by_name["training_receipt.json"]["path"]))
    checkpoint_path = Path(str(by_name["best.pt"]["path"]))
    receipt = _read_json(receipt_path)
    if receipt.get("schema") != "prta-cxr.training-receipt.v1":
        raise ValueError(f"unsupported training receipt: {job['job_id']}")
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError(f"non-PASS training receipt: {job['job_id']}")
    _validate_protected_fields(receipt, label=f"receipt {job['job_id']}")
    if receipt.get("internal_test_opened") is not False:
        raise ValueError(
            f"training receipt lacks closed Internal-test flag: {job['job_id']}"
        )
    if receipt.get("protected_outcomes_opened") is not False:
        raise ValueError(
            f"training receipt lacks closed protected flag: {job['job_id']}"
        )

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if (
        not isinstance(checkpoint, dict)
        or checkpoint.get("schema") != "prta-cxr.checkpoint.v1"
    ):
        raise ValueError(f"unsupported checkpoint: {job['job_id']}")
    config = dict(checkpoint.get("config", {}))
    input_hashes = dict(checkpoint.get("input_hashes", {}))
    experiment_id = str(job["job_id"]).removeprefix("train-")
    if config.get("experiment_id") != experiment_id:
        raise ValueError(f"checkpoint experiment identity drift: {job['job_id']}")
    if int(config.get("seed", -1)) != int(receipt.get("seed", -2)):
        raise ValueError(f"training seed drift: {job['job_id']}")
    config_sha = canonical_sha256(config)
    if receipt.get("config_sha256") != config_sha:
        raise ValueError(f"training config hash drift: {job['job_id']}")
    if dict(receipt.get("input_hashes", {})) != input_hashes or not input_hashes:
        raise ValueError(f"training input-hash drift: {job['job_id']}")

    executed_config = _command_option(state.get("command", []), "--config")
    if executed_config is None or not Path(executed_config).is_file():
        raise ValueError(f"executed config is unavailable: {job['job_id']}")
    if canonical_sha256(_read_json(Path(executed_config))) != config_sha:
        raise ValueError(f"executed config hash drift: {job['job_id']}")
    return {
        "experiment_id": experiment_id,
        "seed": int(receipt["seed"]),
        "config_sha256": config_sha,
        "executed_config_path": executed_config,
        "input_hashes": input_hashes,
        "training_receipt_sha256": sha256_file(receipt_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "best_epoch": int(receipt["best_epoch"]),
        "metrics": _best_training_metrics(receipt),
    }


def _validate_pass_state(
    job: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any]:
    job_id = str(job["job_id"])
    if state.get("schema") != "prta-cxr.phase16-job-state.v1":
        raise ValueError(f"unsupported job-state schema: {job_id}")
    if state.get("status") != "PASS" or state.get("job_id") != job_id:
        raise ValueError(f"invalid selected job state: {job_id}")
    expected_group = str(job["group"])
    actual_group = str(state.get("group", ""))
    allowed_groups = {expected_group, *LEGACY_GROUP_ALIASES.get(expected_group, set())}
    if actual_group not in allowed_groups:
        raise ValueError(f"job group drift for {job_id}: {actual_group}")
    if int(state.get("return_code", -1)) != 0:
        raise ValueError(f"nonzero return code in PASS state: {job_id}")
    source_commit = str(state.get("source_commit", ""))
    if not source_commit:
        raise ValueError(f"missing source commit in PASS state: {job_id}")
    _validate_protected_fields(state, label=f"state {job_id}")
    outputs = _validate_output_checks(job, state)
    for output in outputs:
        path = Path(str(output["path"]))
        if path.suffix == ".json":
            _validate_protected_fields(_read_json(path), label=f"output {path}")
    row: dict[str, Any] = {
        "job_id": job_id,
        "group": expected_group,
        "executed_group": actual_group,
        "source_commit": source_commit,
        "state_sha256": str(state["_state_sha256"]),
        "state_root_label": str(state["_state_root_label"]),
        "outputs": outputs,
    }
    if job_id.startswith("train-"):
        row["training"] = _validate_training_artifacts(job, state, outputs)
    if actual_group != expected_group:
        row["identity_normalization"] = {
            "from_group": actual_group,
            "to_group": expected_group,
            "reason": "historical internal reimplementation was mislabeled official",
        }
    return row


def _aggregate_training(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_experiment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if "training" not in row:
            continue
        training = dict(row["training"])
        base = str(training["experiment_id"]).rsplit("-S", 1)[0]
        by_experiment[base].append(training)
    aggregates: dict[str, Any] = {}
    for experiment, values in sorted(by_experiment.items()):
        seeds = sorted(int(value["seed"]) for value in values)
        if seeds != [17, 28, 43]:
            continue
        metric_names = set.intersection(
            *(set(dict(value["metrics"])) for value in values)
        )
        metrics: dict[str, Any] = {}
        for metric in sorted(metric_names):
            observations = [float(dict(value["metrics"])[metric]) for value in values]
            metrics[metric] = {
                "mean": float(mean(observations)),
                "sample_sd": float(stdev(observations)),
                "by_seed": {
                    str(value["seed"]): float(dict(value["metrics"])[metric])
                    for value in sorted(values, key=lambda item: int(item["seed"]))
                },
            }
        aggregates[experiment] = {"seeds": seeds, "metrics": metrics}
    return aggregates


def reconcile_phase16_states(
    registry: Mapping[str, Any], state_roots: Mapping[str, Path]
) -> dict[str, Any]:
    jobs = validate_registry(registry)
    expected = {str(job["job_id"]): job for job in jobs}
    attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unrelated: list[dict[str, Any]] = []
    for label, root in state_roots.items():
        if not root.is_dir():
            raise ValueError(f"state root is unavailable: {label}={root}")
        for path in sorted(root.glob("*.json")):
            state = _read_json(path)
            if state.get("schema") != "prta-cxr.phase16-job-state.v1":
                continue
            row = {
                **state,
                "_state_sha256": sha256_file(path),
                "_state_root_label": label,
                "_state_path": str(path),
            }
            job_id = str(state.get("job_id", ""))
            if job_id in expected:
                attempts[job_id].append(row)
            else:
                unrelated.append(
                    {
                        "job_id": job_id,
                        "status": str(state.get("status", "")),
                        "state_root_label": label,
                        "state_sha256": sha256_file(path),
                        "included_in_corrected_protocol": False,
                    }
                )

    selected: list[dict[str, Any]] = []
    attempt_audit: list[dict[str, Any]] = []
    for job_id, job in expected.items():
        job_attempts = attempts.get(job_id, [])
        pass_attempts = [row for row in job_attempts if row.get("status") == "PASS"]
        if len(pass_attempts) != 1:
            raise ValueError(
                f"expected exactly one PASS for {job_id}, found {len(pass_attempts)}; "
                f"attempts={[row.get('status') for row in job_attempts]}"
            )
        selected.append(_validate_pass_state(job, pass_attempts[0]))
        attempt_audit.append(
            {
                "job_id": job_id,
                "attempts": [
                    {
                        "status": str(row.get("status", "")),
                        "state_root_label": str(row["_state_root_label"]),
                        "state_sha256": str(row["_state_sha256"]),
                        "selected": row is pass_attempts[0],
                    }
                    for row in job_attempts
                ],
            }
        )
    return {
        "schema": "prta-cxr.phase16-final-reconciliation.v1",
        "status": "PASS_PHASE16_FINAL_NO_SELECTION_AGGREGATE",
        "created_at": datetime.now(UTC).isoformat(),
        "expected_job_count": len(expected),
        "selected_pass_count": len(selected),
        "state_roots": {key: str(value) for key, value in state_roots.items()},
        "source_commits": sorted({str(row["source_commit"]) for row in selected}),
        "selected_jobs": sorted(selected, key=lambda row: str(row["job_id"])),
        "attempt_audit": sorted(attempt_audit, key=lambda row: str(row["job_id"])),
        "excluded_legacy_attempts": sorted(
            unrelated,
            key=lambda row: (str(row["job_id"]), str(row["state_root_label"])),
        ),
        "training_three_seed_summary": _aggregate_training(selected),
        "comparator_identity": "architecture-inspired internal reimplementation",
        "selection_performed": False,
        "winner_selected": False,
        "external_evaluation_included": False,
        "clinician_manual_work_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def finalize_phase16_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile corrected Phase16 states and provenance"
    )
    parser.add_argument("--job-registry", type=Path, required=True)
    parser.add_argument(
        "--state-root",
        action="append",
        required=True,
        help="Repeatable LABEL=PATH state root",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    state_roots: dict[str, Path] = {}
    for raw in args.state_root:
        if "=" not in raw:
            parser.error("--state-root must use LABEL=PATH")
        label, raw_path = raw.split("=", 1)
        if not label or label in state_roots:
            parser.error("state-root labels must be non-empty and unique")
        state_roots[label] = Path(raw_path)
    registry = _read_json(args.job_registry)
    receipt = reconcile_phase16_states(registry, state_roots)
    _write_new_json(args.output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
