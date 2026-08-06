from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import ContractError, canonical_sha256, sha256_file

B403_MACRO_F1 = 0.5260939600646948
B403_ODER = 0.00553522006963664
TARGET_MACRO_F1 = B403_MACRO_F1 + 0.003
DEFAULT_MARGIN = 0.2
ZERO_AUXILIARY = {"alignment", "cmcp", "inversion", "state"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate_parent(parent: Mapping[str, Any]) -> None:
    if parent.get("experiment_id") != "TUNE-FG1-S17":
        raise ContractError("server search parent must be TUNE-FG1-S17")
    if int(parent.get("seed", -1)) != 17:
        raise ContractError("server search parent must use seed 17")
    model = dict(parent.get("model", {}))
    if model.get("family") != "prta" or model.get("native_head") != "H0":
        raise ContractError("server search must retain the PRTA H0 method")
    loss = dict(parent.get("classification_loss", {}))
    if loss.get("name") != "class_balanced_focal":
        raise ContractError("server search parent must retain focal loss")
    if float(loss.get("gamma", -1)) != 1.0:
        raise ContractError("server search parent must retain focal gamma 1")
    weights = dict(parent.get("loss_weights", {}))
    if float(weights.get("classification", 0)) != 1.0:
        raise ContractError("server search classification weight drift")
    if any(float(weights.get(name, -1)) != 0 for name in ZERO_AUXILIARY):
        raise ContractError("server search parent must remain classification-only")


def _weight_code(weight: float) -> str:
    scaled = Decimal(str(weight)) * 1000
    if scaled != scaled.to_integral_value():
        raise ContractError("direction weight must use 0.001 increments")
    return f"{int(scaled):03d}"


def build_direction_margin_wave(
    parent: Mapping[str, Any], *, weights: Sequence[float]
) -> list[dict[str, Any]]:
    _validate_parent(parent)
    values = tuple(float(value) for value in weights)
    if len(values) != 2 or len(set(values)) != 2:
        raise ContractError("each server wave must contain two distinct weights")
    if any(value <= 0 or value > 0.5 for value in values):
        raise ContractError("direction weights must be in (0, 0.5]")
    configs = []
    for weight in values:
        config = deepcopy(dict(parent))
        config["experiment_id"] = f"SVR-FG1-DMW{_weight_code(weight)}-S17"
        config["development_axis"] = "server_direction_margin_weight_v1"
        config["loss_weights"]["direction_margin"] = weight
        config["direction_margin"] = {"margin": DEFAULT_MARGIN}
        configs.append(config)
    return configs


def prepare_direction_margin_wave(
    *,
    parent_config: Path,
    readiness_receipt: Path,
    output_root: Path,
    remote_output_root: PurePosixPath,
    weights: Sequence[float],
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(
            f"refusing to overwrite server search wave: {output_root}"
        )
    readiness = _load_json(readiness_receipt)
    if readiness.get("status") != "PASS_SUES_HPC_ENGINEERING_READINESS":
        raise ContractError("SUES engineering readiness is not PASS")
    if readiness.get("internal_test_opened") or readiness.get("gold_opened"):
        raise ContractError("readiness receipt reports protected outcome access")
    parent = _load_json(parent_config)
    configs = build_direction_margin_wave(parent, weights=weights)
    config_root = output_root / "configs"
    config_root.mkdir(parents=True)
    queue = []
    config_hashes = {}
    for allocation_id, config in zip((4161, 3066), configs, strict=True):
        experiment_id = str(config["experiment_id"])
        local_path = config_root / f"{experiment_id}.json"
        write_json_atomic(local_path, config)
        digest = sha256_file(local_path)
        config_hashes[experiment_id] = digest
        queue.append(
            {
                "experiment_id": experiment_id,
                "allocation_id": allocation_id,
                "status": "FROZEN",
                "search_axis": "direction_margin_weight",
                "direction_margin_weight": float(
                    config["loss_weights"]["direction_margin"]
                ),
                "config_sha256": digest,
                "effective_config_sha256": canonical_sha256(config),
                "remote_config_path": str(
                    remote_output_root / "configs" / local_path.name
                ),
                "remote_run_path": str(remote_output_root / "runs" / experiment_id),
                "internal_test_opened": False,
                "gold_opened": False,
            }
        )
    write_json_atomic(output_root / "run_queue.json", queue)
    receipt = {
        "schema": "prta-cxr.server-dev-search-preparation.v1",
        "status": "PASS_SERVER_DEV_SEARCH_WAVE_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "authority": "user_authorized_continuous_train_dev_search_until_stop",
        "search_axis": "direction_margin_weight",
        "run_ids": [row["experiment_id"] for row in queue],
        "run_count": len(queue),
        "seed": 17,
        "selection_rule": {
            "macro_f1_at_least": TARGET_MACRO_F1,
            "oder_at_most": B403_ODER,
            "intermediate_epoch_selection_forbidden": True,
        },
        "parent_config_sha256": sha256_file(parent_config),
        "parent_config_canonical_sha256": canonical_sha256(parent),
        "readiness_receipt_sha256": sha256_file(readiness_receipt),
        "config_sha256": config_hashes,
        "allocations": [4161, 3066],
        "new_slurm_job_submitted": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
        "training_started": False,
    }
    write_json_atomic(output_root / "preparation_receipt.json", receipt)
    return receipt


def _parse_weights(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in value.split(",") if item.strip())


def prepare_server_dev_search_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze one two-arm SUES Train/Dev direction-margin wave"
    )
    parser.add_argument("--parent-config", type=Path, required=True)
    parser.add_argument("--readiness-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-output", type=PurePosixPath, required=True)
    parser.add_argument("--weights", default="0.02,0.05")
    args = parser.parse_args(argv)
    result = prepare_direction_margin_wave(
        parent_config=args.parent_config,
        readiness_receipt=args.readiness_receipt,
        output_root=args.output,
        remote_output_root=args.remote_output,
        weights=_parse_weights(args.weights),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
