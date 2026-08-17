from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.phase16_queue import validate_registry
from prta_cxr.provenance import resolve_source_commit

REPAIR_GROUPS = {
    "modality_stress",
    "source_held_out",
    "source_held_out_exploratory",
    "source_held_out_confirmatory",
    "state_pruning",
}


def build_repair_registry(registry: dict, *, raw_image_root: Path) -> dict[str, object]:
    selected = [
        deepcopy(job)
        for job in validate_registry(registry)
        if str(job["group"]) in REPAIR_GROUPS
    ]
    selected_ids = {str(job["job_id"]) for job in selected}
    for job in selected:
        dependencies = {str(value) for value in job.get("dependencies", [])}
        if not dependencies <= selected_ids:
            raise ValueError(f"repair dependency escaped selection: {job['job_id']}")
        if str(job["job_id"]).startswith("modality-current-cache-"):
            command = list(job["command"])
            command[-1:-1] = ["--raw-image-root", str(raw_image_root)]
            job["command"] = command
        job["repair_protocol"] = "phase16-scientific-correction-and-repair-v2"
    return {"schema": "prta-cxr.phase16-job-registry.v1", "jobs": selected}


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def prepare_phase16_repair_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the Phase16 repair registry")
    parser.add_argument("--job-registry", type=Path, required=True)
    parser.add_argument("--raw-image-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    registry = build_repair_registry(
        json.loads(args.job_registry.read_text(encoding="utf-8")),
        raw_image_root=args.raw_image_root,
    )
    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    registry_path = staging / "job_registry.json"
    _write_new_json(registry_path, registry)
    receipt = {
        "schema": "prta-cxr.phase16-repair-preparation.v1",
        "status": "PASS_PHASE16_REPAIR_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "parent_registry_sha256": sha256_file(args.job_registry),
        "repair_registry_sha256": sha256_file(registry_path),
        "repair_matrix_sha256": canonical_sha256(registry["jobs"]),
        "job_count": len(registry["jobs"]),
        "groups": sorted(REPAIR_GROUPS),
        "raw_image_root": str(args.raw_image_root.resolve()),
        "external_evaluation_included": False,
        "clinician_manual_work_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "preparation_receipt.json", receipt)
    staging.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
