from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import ContractError, canonical_sha256, sha256_file

LOSS_ARMS: tuple[tuple[str, Mapping[str, Any]], ...] = (
    (
        "TUNE-FG1-S17",
        {"name": "class_balanced_focal", "beta": 0.9999, "gamma": 1.0},
    ),
    ("TUNE-WCE-S17", {"name": "weighted_ce"}),
    ("TUNE-BS-S17", {"name": "balanced_softmax"}),
    ("TUNE-CE-S17", {"name": "cross_entropy"}),
)
ZERO_AUXILIARY = {"alignment", "cmcp", "inversion", "state"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate_parent(parent: Mapping[str, Any]) -> None:
    if parent.get("experiment_id") != "A509-S17" or parent.get("seed") != 17:
        raise ContractError("tuning parent must be the frozen A509-S17 config")
    model = parent.get("model", {})
    if model.get("family") != "prta" or model.get("native_head") != "H0":
        raise ContractError("tuning parent must retain PRTA H0")
    weights = parent.get("loss_weights", {})
    if any(float(weights.get(name, -1)) != 0 for name in ZERO_AUXILIARY):
        raise ContractError("tuning parent must be classification-only")
    if float(weights.get("classification", 0)) != 1:
        raise ContractError("tuning parent classification weight drift")


def build_loss_screen_configs(parent: Mapping[str, Any]) -> list[dict[str, Any]]:
    _validate_parent(parent)
    result = []
    class_counts = list(parent["classification_loss"]["class_counts"])
    for experiment_id, loss in LOSS_ARMS:
        config = deepcopy(dict(parent))
        config["experiment_id"] = experiment_id
        config["development_axis"] = "exploratory_loss_screen_v1"
        config["classification_loss"] = dict(loss)
        if loss["name"] != "cross_entropy":
            config["classification_loss"]["class_counts"] = class_counts
        result.append(config)
    return result


def prepare_loss_screen(
    *,
    parent_config: Path,
    previous_decision: Path,
    case_study_receipt: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite tuning screen: {output_root}")
    parent = _load_json(parent_config)
    decision = _load_json(previous_decision)
    case_receipt = _load_json(case_study_receipt)
    if decision.get("decision") != "STOP_CURRENT_PRTA_ROUTE":
        raise ContractError("previous route-stop decision is not immutable")
    if case_receipt.get("status") != "PASS_EXPLORATORY_DEV_CASE_STUDY":
        raise ContractError("case study is not complete")
    if case_receipt.get("protected_outcome_read_count") != 0:
        raise ContractError("case study reports protected outcome reads")

    configs = build_loss_screen_configs(parent)
    config_root = output_root / "configs"
    config_root.mkdir(parents=True)
    queue = []
    config_hashes = {}
    for config in configs:
        experiment_id = str(config["experiment_id"])
        path = config_root / f"{experiment_id}.json"
        write_json_atomic(path, config)
        config_hashes[experiment_id] = sha256_file(path)
        queue.append(
            {
                "experiment_id": experiment_id,
                "stage": "exploratory_loss_screen_v1",
                "status": "PLANNED",
                "config_path": str(path.resolve()),
                "config_sha256": config_hashes[experiment_id],
                "depends_on": [],
            }
        )
    write_json_atomic(output_root / "run_queue.json", queue)
    receipt = {
        "schema": "prta-cxr.exploratory-loss-screen-preparation.v1",
        "status": "PASS_EXPLORATORY_LOSS_SCREEN_PREPARED",
        "created_at": datetime.now(UTC).isoformat(),
        "run_ids": [config["experiment_id"] for config in configs],
        "run_count": len(configs),
        "seed": 17,
        "selection_rule": {
            "primary": "maximize_dev_macro_f1_subject_to_oder",
            "b403_macro_f1": 0.5260939600646948,
            "b403_oder": 0.00553522006963664,
            "minimum_macro_f1_delta_for_lr_followup": 0.003,
            "conditional_learning_rates": [0.00005, 0.0002],
        },
        "parent_config_sha256": sha256_file(parent_config),
        "parent_config_canonical_sha256": canonical_sha256(parent),
        "previous_decision_sha256": sha256_file(previous_decision),
        "case_study_receipt_sha256": sha256_file(case_study_receipt),
        "config_sha256": config_hashes,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
        "training_started": False,
    }
    write_json_atomic(output_root / "preparation_receipt.json", receipt)
    return receipt


def prepare_loss_screen_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a frozen Train/Dev-only PRTA loss screen"
    )
    parser.add_argument("--parent-config", type=Path, required=True)
    parser.add_argument("--previous-decision", type=Path, required=True)
    parser.add_argument("--case-study-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = prepare_loss_screen(
        parent_config=args.parent_config,
        previous_decision=args.previous_decision,
        case_study_receipt=args.case_study_receipt,
        output_root=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
