from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import canonical_sha256, sha256_file


def _git_state(repo_root: Path) -> tuple[str, str]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise ValueError("protocol freeze requires a clean Git worktree")
    return commit, status


def freeze_formal_protocol(
    *,
    repo_root: Path,
    gate_receipt: Path,
    formal_matrix_receipt: Path,
    formal_queue: Path,
    train_dev_manifest: Path,
    sealed_internal_test_manifest: Path,
    gold_manifest: Path,
    main_cache_manifest: Path,
    gold_cache_manifest: Path,
    quality_audit: Path,
    protocol_config: Path,
    trust_config: Path,
    case_selection_config: Path,
    output: Path,
) -> dict[str, Any]:
    gate = json.loads(gate_receipt.read_text(encoding="utf-8"))
    matrix = json.loads(formal_matrix_receipt.read_text(encoding="utf-8"))
    if gate.get("decision") != "GO":
        raise ValueError("protocol freeze requires a GO development gate")
    if matrix.get("status") != "PASS_FORMAL_MATRIX_PREPARED":
        raise ValueError("formal matrix is not prepared")
    queue = json.loads(formal_queue.read_text(encoding="utf-8"))
    if len(queue) != int(matrix["generated_runs"]):
        raise ValueError("formal queue count differs from matrix receipt")
    if canonical_sha256(queue) != matrix["queue_sha256"]:
        raise ValueError("formal queue hash differs from matrix receipt")
    commit, _ = _git_state(repo_root)
    config_hashes = {
        str(row["experiment_id"]): sha256_file(Path(str(row["config_path"])))
        for row in queue
    }
    if any(
        config_hashes[str(row["experiment_id"])] != row["config_sha256"]
        for row in queue
    ):
        raise ValueError("formal config hash mismatch")
    outcome_files = {
        "sealed_internal_test_manifest": sealed_internal_test_manifest,
        "gold_manifest": gold_manifest,
    }
    inputs: dict[str, Path] = {
        "development_gate": gate_receipt,
        "formal_matrix_receipt": formal_matrix_receipt,
        "formal_queue": formal_queue,
        "train_dev_manifest": train_dev_manifest,
        "main_cache_manifest": main_cache_manifest,
        "gold_cache_manifest": gold_cache_manifest,
        "quality_audit": quality_audit,
        "protocol_config": protocol_config,
        "trust_config": trust_config,
        "case_selection_config": case_selection_config,
        **outcome_files,
    }
    input_hashes = {key: sha256_file(value) for key, value in inputs.items()}
    code_paths = {
        "evaluation": repo_root / "src/prta_cxr/cli_evaluate.py",
        "metrics": repo_root / "src/prta_cxr/evaluation/progression.py",
        "training": repo_root / "src/prta_cxr/training/engine.py",
        "trust_entrypoint": repo_root / "scripts/09_run_trust_audits.py",
        "figure_entrypoint": repo_root / "scripts/10_make_figures.py",
    }
    result = {
        "schema": "prta-cxr.protocol-freeze.v1",
        "status": "PASS_PROTOCOL_FROZEN__FORMAL_OUTCOMES_CLOSED",
        "frozen_at": datetime.now(UTC).isoformat(),
        "git_commit": commit,
        "input_paths": {key: str(value.resolve()) for key, value in inputs.items()},
        "input_hashes": input_hashes,
        "formal_config_hashes": dict(sorted(config_hashes.items())),
        "formal_config_bundle_sha256": canonical_sha256(
            dict(sorted(config_hashes.items()))
        ),
        "code_hashes": {key: sha256_file(value) for key, value in code_paths.items()},
        "prta_aliases": matrix["prta_aliases"],
        "n_a": matrix["n_a"],
        "development_decision": gate["decision"],
        "internal_test_outcomes_read": False,
        "gold_outcomes_read": False,
        "formal_outcome_session_opened": False,
    }
    write_json_atomic(output, result)
    return result


def validate_protocol_freeze(
    receipt: Mapping[str, Any], *, receipt_path: Path
) -> dict[str, Any]:
    value = dict(receipt)
    if value.get("status") != "PASS_PROTOCOL_FROZEN__FORMAL_OUTCOMES_CLOSED":
        raise ValueError("protocol is not frozen with outcomes closed")
    for key, path in value["input_paths"].items():
        if sha256_file(Path(path)) != value["input_hashes"][key]:
            raise ValueError(f"frozen protocol input changed: {key}")
    value["receipt_file_sha256"] = sha256_file(receipt_path)
    return value
