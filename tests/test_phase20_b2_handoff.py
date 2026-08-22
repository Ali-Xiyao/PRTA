import json
from pathlib import Path

from prta_cxr.contracts import sha256_file
from prta_cxr.phase20_b2_handoff import collect_phase20_b2_exports


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_b2_handoff_copies_only_hash_verified_pass_exports(tmp_path):
    program = tmp_path / "program"
    source_state = tmp_path / "source_state"
    source_artifact = tmp_path / "source_artifact"
    destination_state = tmp_path / "destination_state"
    destination_artifact = tmp_path / "destination_artifact"
    output = source_artifact / "probability" / "V2" / "S17" / "receipt.json"
    block = output.parent / "true.jsonl"
    block.parent.mkdir(parents=True, exist_ok=True)
    block.write_text('{"test": true}\n', encoding="utf-8")
    _write(
        output,
        {
            "status": "PASS_PHASE20_B2_COMPARATOR_DEV_PROBABILITY_EXPORT",
            "prediction_blocks": {
                "true": {
                    "path": "true.jsonl",
                    "sha256": sha256_file(block),
                    "rows": 1,
                }
            },
        },
    )
    queue = program / "queue" / "rtx3090_0.json"
    job = {
        "job_id": "b2-export-V2-S17",
        "group": "phase20_b2_probability_export",
        "lane": "rtx3090_0",
        "expected_outputs": ["{output_root}/probability/V2/S17/receipt.json"],
    }
    _write(queue, [job])
    _write(program / "job_registry.json", {"jobs": [job], "job_count": 28})
    registry_sha256 = sha256_file(program / "job_registry.json")
    _write(
        program / "preparation_receipt.json",
        {
            "status": "PASS_PHASE20_B2_PROGRAM_FROZEN",
            "job_count": 28,
            "source_commit": "a" * 40,
            "registry_sha256": registry_sha256,
            "queue_hashes": {"rtx3090_0.json": sha256_file(queue)},
        },
    )
    state = {
        "schema": "prta-cxr.phase20-job-state.v1",
        "status": "PASS",
        "job_id": job["job_id"],
        "lane": "rtx3090_0",
        "source_commit": "a" * 40,
        "queue_sha256": sha256_file(queue),
        "return_code": 0,
        "output_checks": [
            {"path": str(output), "exists": True, "sha256": sha256_file(output)}
        ],
    }
    _write(source_state / f"{job['job_id']}.json", state)

    result = collect_phase20_b2_exports(
        program_root=program,
        lanes=["rtx3090_0"],
        source_state_roots={"rtx3090_0": source_state},
        source_artifact_roots={"rtx3090_0": source_artifact},
        destination_state_root=destination_state,
        destination_artifact_root=destination_artifact,
    )

    assert result["status"] == "PASS_PHASE20_B2_CROSS_HOST_HANDOFF"
    assert result["git_safe"] is False
    copied = destination_artifact / "probability" / "V2" / "S17" / "receipt.json"
    assert sha256_file(copied) == sha256_file(output)
    assert sha256_file(copied.parent / "true.jsonl") == sha256_file(block)
    assert (destination_state / f"{job['job_id']}.json").is_file()
