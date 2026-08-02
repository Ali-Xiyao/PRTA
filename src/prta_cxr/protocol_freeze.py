from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.run_registry import read_run_registry


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
    run_registry: Path,
    train_dev_manifest: Path,
    sealed_internal_test_manifest: Path,
    gold_manifest: Path,
    main_cache_manifest: Path,
    gold_cache_manifest: Path,
    weights: Path,
    main_text_cache: Path,
    gold_text_cache: Path,
    quality_audit: Path,
    protocol_config: Path,
    trust_config: Path,
    case_selection_config: Path,
    vlm_config: Path,
    vlm_model_config: Path,
    vlm_model_index: Path,
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
    registry = {
        str(row["experiment_id"]): row for row in read_run_registry(run_registry)
    }
    for alias, source in matrix["prta_aliases"].items():
        if source not in registry or registry[source]["status"] != (
            "PASS_TRAINING_FINISHED"
        ):
            raise ValueError(f"PRTA alias source is incomplete: {source}")
        path = Path(str(registry[source]["config_path"]))
        if sha256_file(path) != registry[source]["config_hash"]:
            raise ValueError(f"PRTA alias config changed: {source}")
        config_hashes[str(alias)] = sha256_file(path)
    outcome_files = {
        "sealed_internal_test_manifest": sealed_internal_test_manifest,
        "gold_manifest": gold_manifest,
    }
    if vlm_model_config.parent.resolve() != vlm_model_index.parent.resolve():
        raise ValueError("VLM model config and index must share one model root")
    model_index = json.loads(vlm_model_index.read_text(encoding="utf-8"))
    weight_names = sorted(set(model_index["weight_map"].values()))
    model_root = vlm_model_config.parent
    vlm_assets = {
        "vlm_model_config": vlm_model_config,
        "vlm_model_index": vlm_model_index,
        **{
            f"vlm_weight_{index:02d}": model_root / name
            for index, name in enumerate(weight_names, start=1)
        },
        **{
            f"vlm_asset_{name.replace('.', '_')}": model_root / name
            for name in (
                "tokenizer.json",
                "tokenizer_config.json",
                "chat_template.json",
                "merges.txt",
                "vocab.json",
            )
            if (model_root / name).is_file()
        },
    }
    missing_vlm_assets = [
        str(path) for path in vlm_assets.values() if not path.is_file()
    ]
    if missing_vlm_assets:
        raise FileNotFoundError(f"VLM model assets missing: {missing_vlm_assets}")
    inputs: dict[str, Path] = {
        "development_gate": gate_receipt,
        "formal_matrix_receipt": formal_matrix_receipt,
        "formal_queue": formal_queue,
        "train_dev_manifest": train_dev_manifest,
        "main_cache_manifest": main_cache_manifest,
        "gold_cache_manifest": gold_cache_manifest,
        "weights": weights,
        "main_text_cache": main_text_cache,
        "gold_text_cache": gold_text_cache,
        "quality_audit": quality_audit,
        "protocol_config": protocol_config,
        "trust_config": trust_config,
        "case_selection_config": case_selection_config,
        "vlm_config": vlm_config,
        **vlm_assets,
        **outcome_files,
    }
    input_hashes = {key: sha256_file(value) for key, value in inputs.items()}
    code_paths = {
        "evaluation": repo_root / "src/prta_cxr/cli_evaluate.py",
        "metrics": repo_root / "src/prta_cxr/evaluation/progression.py",
        "training": repo_root / "src/prta_cxr/training/engine.py",
        "trust_entrypoint": repo_root / "scripts/09_run_trust_audits.py",
        "figure_entrypoint": repo_root / "scripts/10_make_figures.py",
        "figure_cli": repo_root / "src/prta_cxr/cli_figures.py",
        "figure_implementation": (
            repo_root / "src/prta_cxr/visualization/paper_figures.py"
        ),
        "vlm_entrypoint": repo_root / "scripts/11_vlm_additional.py",
        "vlm_cli": repo_root / "src/prta_cxr/cli_vlm.py",
        "vlm_implementation": repo_root / "src/prta_cxr/vlm/additional.py",
        "vlm_fixed64": repo_root / "src/prta_cxr/vlm/fixed64.py",
        "vlm_projector": repo_root / "src/prta_cxr/vlm/projector.py",
        "vlm_scorer": repo_root / "src/prta_cxr/vlm/frozen_qwen.py",
        "table_entrypoint": repo_root / "scripts/12_build_paper_tables.py",
        "table_cli": repo_root / "src/prta_cxr/cli_tables.py",
        "table_implementation": (
            repo_root / "src/prta_cxr/reporting/paper_tables.py"
        ),
    }
    result = {
        "schema": "prta-cxr.protocol-freeze.v1",
        "status": "PASS_PROTOCOL_FROZEN__FORMAL_OUTCOMES_CLOSED",
        "frozen_at": datetime.now(UTC).isoformat(),
        "git_commit": commit,
        "run_registry_path": str(run_registry.resolve()),
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
