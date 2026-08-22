from __future__ import annotations

import argparse
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file


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


def _output_suffix(template: str) -> Path:
    marker = "{output_root}"
    if marker not in template:
        raise ValueError("Phase20-B2 handoff output is not rooted at output_root")
    suffix = template.split(marker, 1)[1].replace("\\", "/").lstrip("/")
    path = Path(suffix)
    if not suffix or path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe Phase20-B2 handoff output suffix")
    return path


def _copy_verified(source: Path, destination: Path, expected_sha256: str) -> None:
    if not source.is_file() or sha256_file(source) != expected_sha256:
        raise ValueError(f"Phase20-B2 handoff source hash drift: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_file() and sha256_file(destination) == expected_sha256:
            return
        raise FileExistsError(
            f"Phase20-B2 handoff refuses conflicting destination: {destination}"
        )
    temporary = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    shutil.copy2(source, temporary)
    if sha256_file(temporary) != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise ValueError("Phase20-B2 handoff temporary copy hash drift")
    temporary.replace(destination)


def _copy_probability_companions(
    source_receipt: Path, destination_receipt: Path
) -> list[dict[str, Any]]:
    receipt = _read_json(source_receipt)
    inventory = receipt.get("prediction_blocks")
    if not isinstance(inventory, dict) or set(inventory) != {"true"}:
        raise ValueError("Phase20-B2 comparator receipt block roster drift")
    copied = []
    source_parent = source_receipt.parent.resolve()
    destination_parent = destination_receipt.parent.resolve()
    for intervention, raw in inventory.items():
        block = dict(raw)
        relative = Path(str(block.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe Phase20-B2 prediction block path")
        source = (source_parent / relative).resolve()
        destination = (destination_parent / relative).resolve()
        if source.parent != source_parent or destination.parent != destination_parent:
            raise ValueError("Phase20-B2 prediction block escapes receipt root")
        expected_sha256 = str(block.get("sha256", ""))
        if len(expected_sha256) != 64 or int(block.get("rows", 0)) <= 0:
            raise ValueError("Phase20-B2 prediction block contract drift")
        _copy_verified(source, destination, expected_sha256)
        copied.append(
            {
                "intervention": intervention,
                "path": relative.as_posix(),
                "sha256": expected_sha256,
                "rows": int(block["rows"]),
            }
        )
    return copied


def collect_phase20_b2_exports(
    *,
    program_root: Path,
    lanes: Sequence[str],
    source_state_roots: Mapping[str, Path],
    source_artifact_roots: Mapping[str, Path],
    destination_state_root: Path,
    destination_artifact_root: Path,
) -> dict[str, Any]:
    preparation_path = program_root / "preparation_receipt.json"
    registry_path = program_root / "job_registry.json"
    preparation = _read_json(preparation_path)
    registry = _read_json(registry_path)
    if (
        preparation.get("status") != "PASS_PHASE20_B2_PROGRAM_FROZEN"
        or preparation.get("registry_sha256") != sha256_file(registry_path)
        or int(preparation.get("job_count", -1)) != 28
    ):
        raise ValueError("Phase20-B2 handoff program identity drift")
    normalized_lanes = tuple(dict.fromkeys(map(str, lanes)))
    if (
        not normalized_lanes
        or set(normalized_lanes) != set(source_state_roots)
        or set(normalized_lanes) != set(source_artifact_roots)
    ):
        raise ValueError("Phase20-B2 handoff lane/root identity drift")
    queue_hashes = dict(preparation.get("queue_hashes", {}))
    jobs = [
        dict(job)
        for job in registry.get("jobs", [])
        if job.get("group") == "phase20_b2_probability_export"
        and str(job.get("lane")) in normalized_lanes
    ]
    if not jobs:
        raise ValueError("Phase20-B2 handoff has no selected export jobs")
    copied = []
    for job in jobs:
        job_id = str(job["job_id"])
        lane = str(job["lane"])
        state_source = source_state_roots[lane] / f"{job_id}.json"
        state = _read_json(state_source)
        expected_queue_sha256 = queue_hashes.get(f"{lane}.json")
        checks = state.get("output_checks")
        templates = list(map(str, job.get("expected_outputs", [])))
        if (
            state.get("schema") != "prta-cxr.phase20-job-state.v1"
            or state.get("status") != "PASS"
            or state.get("job_id") != job_id
            or state.get("lane") != lane
            or state.get("source_commit") != preparation.get("source_commit")
            or state.get("queue_sha256") != expected_queue_sha256
            or int(state.get("return_code", -1)) != 0
            or not isinstance(checks, list)
            or len(checks) != len(templates)
        ):
            raise ValueError(f"Phase20-B2 handoff state identity drift: {job_id}")
        output_rows = []
        for template, raw_check in zip(templates, checks, strict=True):
            check = dict(raw_check)
            suffix = _output_suffix(template)
            source = Path(str(check.get("path", "")))
            if not source.is_file():
                source = source_artifact_roots[lane] / suffix
            expected_sha256 = str(check.get("sha256", ""))
            destination = destination_artifact_root / suffix
            if check.get("exists") is not True or len(expected_sha256) != 64:
                raise ValueError(f"Phase20-B2 handoff output check drift: {job_id}")
            _copy_verified(source, destination, expected_sha256)
            companions = _copy_probability_companions(source, destination)
            output_rows.append(
                {
                    "suffix": suffix.as_posix(),
                    "sha256": expected_sha256,
                    "prediction_blocks": companions,
                }
            )
        state_sha256 = sha256_file(state_source)
        _copy_verified(
            state_source,
            destination_state_root / f"{job_id}.json",
            state_sha256,
        )
        copied.append(
            {
                "job_id": job_id,
                "lane": lane,
                "state_sha256": state_sha256,
                "outputs": output_rows,
            }
        )
    return {
        "schema": "prta-cxr.phase20-b2-cross-host-handoff.v1",
        "status": "PASS_PHASE20_B2_CROSS_HOST_HANDOFF",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": preparation["source_commit"],
        "program_sha256": sha256_file(preparation_path),
        "lanes": list(normalized_lanes),
        "job_count": len(copied),
        "jobs": copied,
        "patient_level_outputs_private": True,
        "git_safe": False,
        "external_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def phase20_b2_handoff_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hash-verify and collect completed B2 export lanes for statistics"
    )
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--lane", action="append", required=True)
    parser.add_argument("--source-state-root", action="append", required=True)
    parser.add_argument("--source-artifact-root", action="append", required=True)
    parser.add_argument("--destination-state-root", type=Path, required=True)
    parser.add_argument("--destination-artifact-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)

    def parse(values: Sequence[str], option: str) -> dict[str, Path]:
        result = {}
        for raw in values:
            if "=" not in raw:
                parser.error(f"{option} must use LANE=PATH")
            lane, raw_path = raw.split("=", 1)
            if not lane or lane in result:
                parser.error(f"{option} lane labels must be unique")
            result[lane] = Path(raw_path)
        return result

    result = collect_phase20_b2_exports(
        program_root=args.program,
        lanes=args.lane,
        source_state_roots=parse(args.source_state_root, "--source-state-root"),
        source_artifact_roots=parse(
            args.source_artifact_root, "--source-artifact-root"
        ),
        destination_state_root=args.destination_state_root,
        destination_artifact_root=args.destination_artifact_root,
    )
    _write_new_json(args.receipt, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
