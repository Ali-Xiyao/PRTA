from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_training_finalize import _closed, _read_json, _write_new_json


def _output_suffix(template: str) -> str:
    return template.split("{output_root}", 1)[-1].replace("\\", "/").lstrip("/")


def _validate_program_states(
    *,
    program_root: Path,
    state_roots: Mapping[str, Path],
    artifact_roots: Mapping[str, Path],
    preparation_status: str,
    state_schema: str,
    expected_jobs: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if set(state_roots) != set(artifact_roots):
        raise ValueError("evidence state/artifact root labels must match")
    preparation_path = program_root / "preparation_receipt.json"
    registry_path = program_root / "job_registry.json"
    input_manifest_path = program_root / "input_manifest.json"
    preparation = _read_json(preparation_path)
    registry = _read_json(registry_path)
    input_manifest = _read_json(input_manifest_path)
    _closed(preparation, label=f"{preparation_status} preparation")
    _closed(input_manifest, label=f"{preparation_status} inputs")
    if (
        preparation.get("status") != preparation_status
        or preparation.get("registry_sha256") != sha256_file(registry_path)
        or preparation.get("input_manifest_sha256") != sha256_file(input_manifest_path)
        or int(preparation.get("job_count", -1)) != expected_jobs
    ):
        raise ValueError(
            f"evidence frozen program identity drift: {preparation_status}"
        )
    jobs = [dict(job) for job in registry.get("jobs", [])]
    if len(jobs) != expected_jobs or len({str(job["job_id"]) for job in jobs}) != len(
        jobs
    ):
        raise ValueError(f"evidence registry uniqueness drift: {preparation_status}")
    expected = {str(job["job_id"]): job for job in jobs}
    attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for label, root in state_roots.items():
        if not root.is_dir():
            raise ValueError(f"evidence state root unavailable: {label}")
        for path in sorted(root.glob("*.json")):
            value = _read_json(path)
            if value.get("schema") != state_schema:
                continue
            job_id = str(value.get("job_id", ""))
            if job_id in expected:
                attempts[job_id].append(
                    {
                        **value,
                        "_state_sha256": sha256_file(path),
                        "_artifact_root": str(artifact_roots[label]),
                    }
                )
    selected = []
    audit = []
    source_commit = str(preparation["source_commit"])
    queue_hashes = dict(preparation.get("queue_hashes", {}))
    if not queue_hashes and "queue_sha256" in preparation:
        queue_hashes = {"single": str(preparation["queue_sha256"])}
    for job_id, job in expected.items():
        values = attempts.get(job_id, [])
        passes = [value for value in values if value.get("status") == "PASS"]
        if len(passes) != 1:
            raise ValueError(
                f"expected exactly one evidence PASS for {job_id}, found {len(passes)}"
            )
        state = passes[0]
        lane = str(job["lane"])
        expected_queue = queue_hashes.get(f"{lane}.json", queue_hashes.get("single"))
        if (
            state.get("job_id") != job_id
            or state.get("group") != job.get("group")
            or state.get("lane") != lane
            or state.get("source_commit") != source_commit
            or state.get("queue_sha256") != expected_queue
            or int(state.get("return_code", -1)) != 0
        ):
            raise ValueError(f"evidence PASS state identity drift: {job_id}")
        _closed(state, label=f"evidence state {job_id}")
        checks = state.get("output_checks")
        templates = list(map(str, job.get("expected_outputs", [])))
        if not isinstance(checks, list) or len(checks) != len(templates):
            raise ValueError(f"evidence output-check count drift: {job_id}")
        outputs = []
        for template, raw_check in zip(templates, checks, strict=True):
            check = dict(raw_check)
            suffix = _output_suffix(template)
            path = Path(str(check.get("path", "")))
            if not path.is_file():
                path = Path(state["_artifact_root"]) / Path(suffix)
            if (
                not path.is_file()
                or check.get("exists") is not True
                or sha256_file(path) != check.get("sha256")
            ):
                raise ValueError(f"evidence output hash drift: {job_id}")
            if path.suffix == ".json":
                payload = _read_json(path)
                _closed(payload, label=f"evidence output {job_id}")
                status = payload.get("status")
                if status is not None and not str(status).startswith("PASS"):
                    raise ValueError(f"evidence output is not PASS: {job_id}")
            outputs.append({"suffix": suffix, "sha256": sha256_file(path)})
        selected.append(
            {
                "job_id": job_id,
                "group": str(job["group"]),
                "lane": lane,
                "state_sha256": state["_state_sha256"],
                "outputs": outputs,
            }
        )
        audit.append(
            {
                "job_id": job_id,
                "attempts": [
                    {
                        "status": value.get("status"),
                        "state_sha256": value["_state_sha256"],
                        "selected": value is state,
                    }
                    for value in values
                ],
            }
        )
    return selected, audit


def finalize_phase20_evidence(
    *,
    b1_program: Path,
    b1_state_roots: Mapping[str, Path],
    b1_artifact_roots: Mapping[str, Path],
    b2_program: Path,
    b2_state_roots: Mapping[str, Path],
    b2_artifact_roots: Mapping[str, Path],
    phase20_a_final: Path,
    comparator_final: Path,
) -> dict[str, Any]:
    a_final = _read_json(phase20_a_final)
    comparator = _read_json(comparator_final)
    if (
        a_final.get("status") != "PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE"
        or comparator.get("status")
        != "PASS_PHASE20_COMPARATOR_FINAL_NO_SELECTION_AGGREGATE"
    ):
        raise ValueError("evidence finalizer requires upstream finalizers PASS")
    b1, b1_audit = _validate_program_states(
        program_root=b1_program,
        state_roots=b1_state_roots,
        artifact_roots=b1_artifact_roots,
        preparation_status="PASS_PHASE20_SLIM_S1_EVIDENCE_PROGRAM_FROZEN",
        state_schema="prta-cxr.phase20-evidence-job-state.v1",
        expected_jobs=20,
    )
    b2, b2_audit = _validate_program_states(
        program_root=b2_program,
        state_roots=b2_state_roots,
        artifact_roots=b2_artifact_roots,
        preparation_status="PASS_PHASE20_B2_PROGRAM_FROZEN",
        state_schema="prta-cxr.phase20-job-state.v1",
        expected_jobs=28,
    )
    b1_groups = {str(row["group"]) for row in b1}
    required_b1 = {
        "modality_assets",
        "probability_and_prior_stress",
        "state_pruning",
        "modality_stress",
        "calibration_selective_prediction",
        "subgroup_long_tail",
        "efficiency",
    }
    if not required_b1 <= b1_groups:
        raise ValueError("Phase20-B1 evidence family coverage drift")
    if sum(row["job_id"] == "b2-post-comparator-statistics" for row in b2) != 1:
        raise ValueError("Phase20-B2 statistics job is not unique PASS")
    return {
        "schema": "prta-cxr.phase20-evidence-final-aggregate.v1",
        "status": "PASS_PHASE20_EVIDENCE_FINAL_NO_SELECTION_AGGREGATE",
        "created_at": datetime.now(UTC).isoformat(),
        "phase20_a_final_sha256": sha256_file(phase20_a_final),
        "comparator_final_sha256": sha256_file(comparator_final),
        "b1_job_count": 20,
        "b2_job_count": 28,
        "b1_jobs": sorted(b1, key=lambda row: str(row["job_id"])),
        "b2_jobs": sorted(b2, key=lambda row: str(row["job_id"])),
        "attempt_audit": {
            "b1": sorted(b1_audit, key=lambda row: str(row["job_id"])),
            "b2": sorted(b2_audit, key=lambda row: str(row["job_id"])),
        },
        "evidence_families": [
            "PRIOR stress",
            "finding stress",
            "current corruption",
            "calibration",
            "risk coverage",
            "subgroups",
            "state pruning",
            "cached-feature efficiency",
            "safety routing",
            "three-seed disagreement",
            "patient-cluster paired bootstrap",
            "Holm-adjusted primary contrasts",
        ],
        "selection_performed": False,
        "winner_selected": False,
        "external_evaluation_included": False,
        "clinician_manual_work_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def phase20_evidence_finalize_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize Phase20 B1+B2 evidence")
    parser.add_argument("--b1-program", type=Path, required=True)
    parser.add_argument("--b1-state-root", action="append", required=True)
    parser.add_argument("--b1-artifact-root", action="append", required=True)
    parser.add_argument("--b2-program", type=Path, required=True)
    parser.add_argument("--b2-state-root", action="append", required=True)
    parser.add_argument("--b2-artifact-root", action="append", required=True)
    parser.add_argument("--phase20-a-final", type=Path, required=True)
    parser.add_argument("--comparator-final", type=Path, required=True)
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

    result = finalize_phase20_evidence(
        b1_program=args.b1_program,
        b1_state_roots=parse(args.b1_state_root, "--b1-state-root"),
        b1_artifact_roots=parse(args.b1_artifact_root, "--b1-artifact-root"),
        b2_program=args.b2_program,
        b2_state_roots=parse(args.b2_state_root, "--b2-state-root"),
        b2_artifact_roots=parse(args.b2_artifact_root, "--b2-artifact-root"),
        phase20_a_final=args.phase20_a_final,
        comparator_final=args.comparator_final,
    )
    _write_new_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
