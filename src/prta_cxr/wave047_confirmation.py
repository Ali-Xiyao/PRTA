from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.provenance import resolve_source_commit

SEEDS = (17, 28, 43)
VARIANTS = ("V0", "V1", "V2")
EXPECTED_WAVE045_PREPARATION_SHA256 = (
    "0c53524cfdc89d2a112f0fee91c9ee9283aeaa61d8b59e80e5e6a60d458616a5"
)
EXPECTED_WAVE046_PREPARATION_SHA256 = (
    "a417b03e22b54da612e673600cac91b5233cfffcb7e533c8611adfda9d7f2aaa"
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def build_tail8_tila_config(parent: Mapping[str, Any], *, seed: int) -> dict[str, Any]:
    config = json.loads(json.dumps(dict(parent)))
    if config.get("schema") != "prta-cxr.training.v1":
        raise ValueError("TILA parent config schema drift")
    model = dict(config.get("model", {}))
    if model.get("family") != "tila":
        raise ValueError("scope-matched parent is not TILA")
    if model.get("adapter_scope") != "tail4":
        raise ValueError("scope-matched parent is not Tail4")
    if model.get("adapter_rank") != 32 or model.get("native_head") != "H0":
        raise ValueError("scope-matched TILA parent rank/head drift")
    if any(
        float(value) != 0.0
        for key, value in config["loss_weights"].items()
        if key != "classification"
    ):
        raise ValueError("scope-matched TILA parent has an auxiliary loss")
    if float(config["loss_weights"]["classification"]) != 1.0:
        raise ValueError("scope-matched TILA classification weight drift")
    model["adapter_scope"] = "tail8"
    config["model"] = model
    config["seed"] = int(seed)
    config["experiment_id"] = f"W047-TILA8-S{seed}"
    config["development_axis"] = "wave047_tail8_tila_scope_matched_confirmation"
    return config


def _server_job_queues() -> dict[int, list[str]]:
    return {
        3066: [
            "W047D-V0-S17",
            "W047D-V1-S17",
            "W047D-V2-S17",
            "W047D-V0-S28",
            "W047D-V2-S28",
            "W047-TILA8-S17",
            "W047-TILA8-S28",
        ],
        9929: [
            "W047D-V0-S43",
            "W047D-V1-S43",
            "W047D-V2-S43",
            "W047D-V1-S28",
            "W047-TILA8-S43",
        ],
    }


def prepare_confirmation_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze V2 candidate diagnostics and Tail8-TILA confirmation"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--wave045-root", type=Path, required=True)
    parser.add_argument("--wave046-preparation", type=Path, required=True)
    parser.add_argument("--server-input-audit", type=Path, required=True)
    parser.add_argument("--server-root", type=PurePosixPath, required=True)
    parser.add_argument("--server-source", type=PurePosixPath, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output_root.exists():
        parser.error("--output-root must be a new immutable directory")
    if sha256_file(args.wave045_root / "experiments/preparation_receipt.json") != (
        EXPECTED_WAVE045_PREPARATION_SHA256
    ):
        raise ValueError("Wave045 preparation hash drift")
    if sha256_file(args.wave046_preparation) != EXPECTED_WAVE046_PREPARATION_SHA256:
        raise ValueError("Wave046 preparation hash drift")
    wave045 = _read_json(args.wave045_root / "experiments/preparation_receipt.json")
    if wave045.get("status") != "PASS_WAVE045_18_CELL_MATRIX_FROZEN":
        raise ValueError("Wave045 preparation is not frozen PASS")
    if wave045.get("protected_outcome_read_count") != 0:
        raise ValueError("Wave045 preparation reports protected reads")
    wave046 = _read_json(args.wave046_preparation)
    if wave046.get("protected_outcome_read_count") != 0:
        raise ValueError("Wave046 preparation reports protected reads")
    audit = _read_json(args.server_input_audit)
    if audit.get("status") != "PASS_WAVE047_SERVER_INPUT_AUDIT":
        raise ValueError("server input audit is not PASS")
    if audit.get("protected_outcome_read_count") != 0:
        raise ValueError("server input audit reports protected reads")

    arm_by_run = {str(arm["run_id"]): dict(arm) for arm in wave045["arms"]}
    server_inputs = {
        str(item["run_id"]): dict(item) for item in audit.get("source_runs", [])
    }
    expected_server_runs = {
        f"W045-{variant}-S{seed}" for variant in VARIANTS for seed in (17, 43)
    }
    if set(server_inputs) != expected_server_runs:
        raise ValueError("server candidate checkpoint audit matrix drift")
    local_inputs = {}
    for variant in VARIANTS:
        run_id = f"W045-{variant}-S28"
        run = args.wave045_root / "experiments/runs" / run_id
        receipt_path = run / "training_receipt.json"
        checkpoint_path = run / "best.pt"
        if not receipt_path.is_file() or not checkpoint_path.is_file():
            raise FileNotFoundError(f"local candidate source missing: {run_id}")
        receipt = _read_json(receipt_path)
        if receipt.get("status") != "PASS_TRAINING_FINISHED":
            raise ValueError(f"local candidate source is not PASS: {run_id}")
        if receipt.get("internal_test_opened") is not False:
            raise ValueError(f"local candidate source opened Internal-test: {run_id}")
        if receipt.get("protected_outcomes_opened") is not False:
            raise ValueError(f"local candidate source opened protected data: {run_id}")
        if (
            receipt.get("config_sha256")
            != arm_by_run[run_id]["effective_config_sha256"]
        ):
            raise ValueError(f"local candidate source config drift: {run_id}")
        local_inputs[run_id] = {
            "run_id": run_id,
            "variant": variant,
            "seed": 28,
            "checkpoint_path": str(checkpoint_path.resolve()),
            "checkpoint_sha256": sha256_file(checkpoint_path),
            "training_receipt_path": str(receipt_path.resolve()),
            "training_receipt_sha256": sha256_file(receipt_path),
            "effective_config_sha256": arm_by_run[run_id]["effective_config_sha256"],
            "config_file_sha256": arm_by_run[run_id]["config_sha256"],
        }

    reused_tila = {
        int(item["seed"]): dict(item)
        for item in wave046["reused_runs"]
        if item.get("family") == "tila"
    }
    if set(reused_tila) != set(SEEDS):
        raise ValueError("Wave046 TILA parent seed matrix drift")
    configs = {}
    config_dir = args.output_root / "configs"
    config_dir.mkdir(parents=True, exist_ok=False)
    for seed in SEEDS:
        parent_item = reused_tila[seed]
        parent_path = Path(parent_item["config_path"])
        if sha256_file(parent_path) != parent_item["config_file_sha256"]:
            raise ValueError(f"TILA parent config file hash drift: seed{seed}")
        parent = _read_json(parent_path)
        config = build_tail8_tila_config(parent, seed=seed)
        path = config_dir / f"W047-TILA8-S{seed}.json"
        write_json_atomic(path, config)
        configs[seed] = {
            "run_id": config["experiment_id"],
            "seed": seed,
            "path": str(path.resolve()),
            "file_sha256": sha256_file(path),
            "effective_config_sha256": canonical_sha256(config),
            "parent_run_id": parent_item["experiment_id"],
            "parent_config_file_sha256": parent_item["config_file_sha256"],
            "only_scientific_change": "adapter_scope_tail4_to_tail8",
        }

    source_root = Path(__file__).resolve().parents[2]
    source_commit = resolve_source_commit(source_root)
    source_files = {
        relative: sha256_file(source_root / relative)
        for relative in (
            "scripts/07_train.py",
            "scripts/45_evaluate_prta_v2_mechanisms.py",
            "scripts/70_wave047_server_controller.py",
            "scripts/sues_hpc_run_dev_search_arm.sh",
            "src/prta_cxr/prta_v2_diagnostics.py",
            "src/prta_cxr/training/engine.py",
        )
    }
    server_root = PurePosixPath(args.server_root)
    server_source = PurePosixPath(args.server_source)
    server_wave045 = PurePosixPath(str(audit["server_wave045_root"]))
    diagnostic_jobs = {}
    for variant in VARIANTS:
        for seed in SEEDS:
            source_run = f"W045-{variant}-S{seed}"
            run_id = f"W047D-{variant}-S{seed}"
            if seed == 28:
                item = local_inputs[source_run]
                checkpoint = server_root / "inputs" / source_run / "best.pt"
                training_receipt = (
                    server_root / "inputs" / source_run / "training_receipt.json"
                )
            else:
                item = server_inputs[source_run]
                checkpoint = (
                    server_wave045 / "experiments" / "runs" / source_run / "best.pt"
                )
                training_receipt = (
                    server_wave045
                    / "experiments"
                    / "runs"
                    / source_run
                    / "training_receipt.json"
                )
            diagnostic_jobs[run_id] = {
                "kind": "candidate_prior_diagnostic",
                "run_id": run_id,
                "source_run_id": source_run,
                "variant": variant,
                "seed": seed,
                "checkpoint_path": str(checkpoint),
                "checkpoint_sha256": item["checkpoint_sha256"],
                "training_receipt_path": str(training_receipt),
                "training_receipt_sha256": item["training_receipt_sha256"],
                "effective_config_sha256": arm_by_run[source_run][
                    "effective_config_sha256"
                ],
            }

    queues = _server_job_queues()
    input_paths = dict(audit["global_input_paths"])
    input_sha256 = dict(audit["global_input_sha256"])
    manifests = {}
    for allocation, queue in queues.items():
        jobs = []
        for run_id in queue:
            if run_id in diagnostic_jobs:
                jobs.append(diagnostic_jobs[run_id])
                continue
            seed = int(run_id.rsplit("S", 1)[1])
            item = configs[seed]
            jobs.append(
                {
                    "kind": "tail8_tila_training",
                    "run_id": run_id,
                    "seed": seed,
                    "config_path": str(server_root / "configs" / f"{run_id}.json"),
                    "config_file_sha256": item["file_sha256"],
                    "effective_config_sha256": item["effective_config_sha256"],
                    "parent_run_id": item["parent_run_id"],
                    "parent_config_file_sha256": item["parent_config_file_sha256"],
                    "only_scientific_change": item["only_scientific_change"],
                }
            )
        manifest = {
            "schema": "prta-cxr.wave047-server-manifest.v1",
            "status": "PASS_WAVE047_SERVER_QUEUE_FROZEN",
            "created_at": datetime.now(UTC).isoformat(),
            "allocation": allocation,
            "hardware_class": "A800-80GB",
            "source_commit": source_commit,
            "source_path": str(server_source),
            "source_files": source_files,
            "server_root": str(server_root),
            "jobs": jobs,
            "global_input_paths": input_paths,
            "global_input_sha256": input_sha256,
            "wave045_preparation_sha256": EXPECTED_WAVE045_PREPARATION_SHA256,
            "wave046_preparation_sha256": EXPECTED_WAVE046_PREPARATION_SHA256,
            "no_outcome_selection": True,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        }
        path = args.output_root / f"server_manifest_{allocation}.json"
        write_json_atomic(path, manifest)
        manifests[allocation] = {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "queue": queue,
        }

    preparation = {
        "schema": "prta-cxr.wave047-candidate-confirmation-preparation.v1",
        "status": "PASS_WAVE047_CANDIDATE_CONFIRMATION_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": source_commit,
        "wave045_preparation_sha256": EXPECTED_WAVE045_PREPARATION_SHA256,
        "wave046_preparation_sha256": EXPECTED_WAVE046_PREPARATION_SHA256,
        "server_input_audit_sha256": sha256_file(args.server_input_audit),
        "candidate_identity": "FROZEN_MAIN_CANDIDATE_PENDING_CONFIRMATION",
        "fallback_identity": "FROZEN_FALLBACK",
        "core_reference_identity": "CORE_REFERENCE",
        "stop_new_architecture_search": True,
        "local_seed28_inputs": list(local_inputs.values()),
        "tail8_tila_configs": list(configs.values()),
        "server_manifests": manifests,
        "diagnostic_matrix": [diagnostic_jobs[key] for key in sorted(diagnostic_jobs)],
        "selection_performed": False,
        "winner_selected": False,
        "training_started": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(args.output_root / "preparation_receipt.json", preparation)
    print(json.dumps(preparation, indent=2, sort_keys=True))
    return 0
