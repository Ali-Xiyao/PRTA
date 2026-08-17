import json
from pathlib import Path

from prta_cxr.contracts import sha256_file
from prta_cxr.phase15_queue_runner import _job_command, validate_job_output


def _job(tmp_path: Path, *, task: str, system: str):
    checkpoint = tmp_path / "best.pt"
    checkpoint.write_bytes(b"checkpoint")
    return {
        "job_id": f"{task}-{system}-S43",
        "task": task,
        "system": system,
        "seed": 43,
        "checkpoint": checkpoint,
        "training_receipt": tmp_path / "training_receipt.json",
        "inputs": {
            key: tmp_path / key
            for key in (
                "split_manifest",
                "cleaned_split_freeze",
                "cache_root",
                "text_cache",
                "matched_hard_prior_map",
                "weights",
                "label_quality_audit",
            )
        },
    }


def test_probability_command_is_true_only_and_scope_bound(tmp_path):
    job = _job(tmp_path, task="probability", system="IF-F02")
    command = _job_command(
        source=tmp_path, job=job, output=tmp_path / "output", device="cuda:0"
    )
    assert "--retain-logits" in command
    assert "--true-only" in command
    assert command[command.index("--diagnostic-scope") + 1] == "ifusion_final"
    assert command[command.index("--cleaned-split-platform-root") + 1] == str(tmp_path)


def test_probability_and_efficiency_output_validation(tmp_path):
    probability_job = _job(tmp_path, task="probability", system="B401")
    output = tmp_path / "probability"
    output.mkdir()
    block = output / "true.predictions.jsonl"
    block.write_text("{}\n", encoding="utf-8")
    receipt = {
        "schema": "prta-cxr.comparator-dev-probability-diagnostic.v1",
        "status": "PASS_COMPARATOR_DEV_PROBABILITY_EXPORT",
        "variant": "B401",
        "seed": 43,
        "evaluation_interventions": ["true"],
        "prediction_blocks": {
            "true": {"path": block.name, "rows": 1, "sha256": sha256_file(block)}
        },
    }
    receipt_path = output / "candidate_probability_diagnostic_receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert validate_job_output(probability_job, output)["rows"] == 1

    efficiency_job = _job(tmp_path, task="efficiency", system="IF-F02")
    evidence = tmp_path / "efficiency.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "prta-cxr.comparator-efficiency-evidence.v1",
                "status": "PASS_COMPARATOR_FIXED_HARDWARE_EFFICIENCY",
                "system": "IF-F02",
                "seed": 43,
                "checkpoint_sha256": sha256_file(efficiency_job["checkpoint"]),
            }
        ),
        encoding="utf-8",
    )
    assert "receipt_sha256" in validate_job_output(efficiency_job, evidence)
