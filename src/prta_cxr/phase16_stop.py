from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.provenance import resolve_source_commit

ACTIVE_EXPERIMENT_MARKERS = (
    "99_run_phase16_queue.py",
    "phase16_lane_3066",
    "phase16_lane_9929",
    "phase16_corrected_lane_3066",
    "phase16_corrected_lane_9929",
    "phase16_corrected_supervisor_3066",
    "phase16_corrected_supervisor_9929",
    "phase16_repair_lane_3066",
    "phase16_repair_lane_9929",
    "phase16_corrected_finalizer_supervisor",
    "slim_priority_supervisor",
    "114_finalize_slim_matrix.py",
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


def _validate_closed(value: Mapping[str, Any], *, label: str) -> None:
    for key in ("internal_test_opened", "gold_opened"):
        if value.get(key) is not False:
            raise ValueError(f"{label} reports protected access through {key}")
    if int(value.get("protected_outcome_read_count", -1)) != 0:
        raise ValueError(f"{label} reports protected reads")


def active_phase16_experiment_processes(phase_root: Path) -> list[dict[str, Any]]:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    phase_text = str(phase_root.resolve())
    current_pid = os.getpid()
    active: list[dict[str, Any]] = []
    for process in proc_root.iterdir():
        if not process.name.isdigit() or int(process.name) == current_pid:
            continue
        try:
            raw = (process / "cmdline").read_bytes()
            status = (process / "status").read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        command = raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
        if not command or phase_text not in command:
            continue
        if not any(marker in command for marker in ACTIVE_EXPERIMENT_MARKERS):
            continue
        state_line = next(
            (line for line in status.splitlines() if line.startswith("State:")), ""
        )
        active.append(
            {
                "pid": int(process.name),
                "state": state_line.removeprefix("State:").strip(),
                "command": command,
            }
        )
    return sorted(active, key=lambda row: int(row["pid"]))


def build_terminal_stop_receipt(
    final_aggregate: Mapping[str, Any],
    lane_completions: Mapping[str, tuple[Mapping[str, Any], str]],
    *,
    final_aggregate_sha256: str,
    residual_processes: Sequence[Mapping[str, Any]],
    source_commit: str,
    slim_final: tuple[Mapping[str, Any], str] | None = None,
) -> dict[str, Any]:
    if final_aggregate.get("schema") != "prta-cxr.phase16-final-reconciliation.v1":
        raise ValueError("unsupported Phase16 final aggregate schema")
    if final_aggregate.get("status") != "PASS_PHASE16_FINAL_NO_SELECTION_AGGREGATE":
        raise ValueError("Phase16 final aggregate is not terminal PASS")
    _validate_closed(final_aggregate, label="Phase16 final aggregate")
    if final_aggregate.get("selection_performed") is not False:
        raise ValueError("Phase16 final aggregate reports selection")
    if final_aggregate.get("winner_selected") is not False:
        raise ValueError("Phase16 final aggregate reports a winner")
    if int(final_aggregate.get("expected_job_count", -1)) != int(
        final_aggregate.get("selected_pass_count", -2)
    ):
        raise ValueError("Phase16 final aggregate has incomplete PASS coverage")

    lane_inventory: dict[str, Any] = {}
    expected_lanes = {"a800_3066", "a800_9929"}
    if set(lane_completions) != expected_lanes:
        raise ValueError("terminal stop requires both corrected A800 lanes")
    for lane, (completion, completion_sha256) in lane_completions.items():
        if completion.get("schema") != "prta-cxr.phase16-lane-completion.v1":
            raise ValueError(f"unsupported lane completion schema: {lane}")
        if completion.get("status") != "PASS" or completion.get("lane") != lane:
            raise ValueError(f"corrected lane is not terminal PASS: {lane}")
        if completion.get("failures") != []:
            raise ValueError(f"corrected lane reports failures: {lane}")
        _validate_closed(completion, label=f"corrected lane {lane}")
        lane_inventory[lane] = {
            "completion_sha256": completion_sha256,
            "completed_job_count": len(completion.get("completed", [])),
            "skipped_job_count": len(completion.get("skipped", [])),
        }

    if residual_processes:
        raise ValueError(
            "Phase16 experiment processes remain active: "
            + ", ".join(str(row.get("pid")) for row in residual_processes)
        )
    slim_inventory = None
    if slim_final is not None:
        slim, slim_sha256 = slim_final
        if slim.get("schema") != "prta-cxr.slim-matrix-final.v1":
            raise ValueError("unsupported Slim final aggregate schema")
        if slim.get("status") != "PASS_SLIM_MATRIX_SELECTED":
            raise ValueError("Slim final aggregate is not PASS")
        _validate_closed(slim, label="Slim final aggregate")
        if slim.get("selection_performed") is not True:
            raise ValueError("Slim final aggregate lacks frozen selection")
        if slim.get("winner_selected") is not True or not slim.get("selected_arm"):
            raise ValueError("Slim final aggregate lacks selected arm")
        slim_inventory = {
            "final_sha256": slim_sha256,
            "status": str(slim["status"]),
            "selected_arm": str(slim["selected_arm"]),
            "selection_disposition": str(slim["selection_disposition"]),
        }
    return {
        "schema": "prta-cxr.terminal-experiment-stop.v1",
        "status": "STOP_ALL_MODEL_AND_EXPERIMENT_SELECTION",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": source_commit,
        "final_aggregate_sha256": final_aggregate_sha256,
        "final_aggregate_status": str(final_aggregate["status"]),
        "final_expected_job_count": int(final_aggregate["expected_job_count"]),
        "final_selected_pass_count": int(final_aggregate["selected_pass_count"]),
        "corrected_lane_completions": lane_inventory,
        "slim_final": slim_inventory,
        "active_phase16_experiment_processes": [],
        "automatic_downstream_experiments_enabled": False,
        "slurm_allocations_cancelled": False,
        "unrelated_telemetry_cancelled": False,
        "selection_performed": slim_inventory is not None,
        "winner_selected": slim_inventory is not None,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def phase16_terminal_stop_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create the terminal Phase16 experiment STOP marker"
    )
    parser.add_argument("--phase-root", type=Path, required=True)
    parser.add_argument("--final-aggregate", type=Path, required=True)
    parser.add_argument("--lane-3066-completion", type=Path, required=True)
    parser.add_argument("--lane-9929-completion", type=Path, required=True)
    parser.add_argument("--slim-final-aggregate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    lane_paths = {
        "a800_3066": args.lane_3066_completion,
        "a800_9929": args.lane_9929_completion,
    }
    final_aggregate = _read_json(args.final_aggregate)
    lanes = {
        lane: (_read_json(path), sha256_file(path)) for lane, path in lane_paths.items()
    }
    residual = active_phase16_experiment_processes(args.phase_root)
    receipt = build_terminal_stop_receipt(
        final_aggregate,
        lanes,
        final_aggregate_sha256=sha256_file(args.final_aggregate),
        residual_processes=residual,
        source_commit=resolve_source_commit(Path(__file__).resolve().parents[2]),
        slim_final=(
            _read_json(args.slim_final_aggregate),
            sha256_file(args.slim_final_aggregate),
        ),
    )
    _write_new_json(args.output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
