from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.run_registry import read_run_registry


def _metrics(receipt: dict[str, Any]) -> tuple[float, float]:
    return (
        float(receipt["best_dev_macro_f1"]),
        float(receipt["dev_prior_audit"]["true_minus_wrong_prior_gap"]),
    )


def select_dev_candidate(
    baseline_id: str,
    candidates: list[str],
    receipts: dict[str, dict[str, Any]],
    *,
    minimum_f1_gain: float,
) -> dict[str, Any]:
    baseline_f1, baseline_gap = _metrics(receipts[baseline_id])
    qualified = []
    for experiment_id in candidates:
        macro_f1, prior_gap = _metrics(receipts[experiment_id])
        if (
            macro_f1 >= baseline_f1 + minimum_f1_gain
            and prior_gap >= baseline_gap - 1e-8
        ):
            qualified.append((macro_f1, prior_gap, experiment_id))
    chosen = max(qualified)[2] if qualified else baseline_id
    chosen_f1, chosen_gap = _metrics(receipts[chosen])
    return {
        "baseline_experiment_id": baseline_id,
        "candidate_experiment_ids": candidates,
        "minimum_f1_gain": minimum_f1_gain,
        "prior_gap_may_worsen": False,
        "qualified_experiment_ids": [value[2] for value in qualified],
        "chosen_experiment_id": chosen,
        "baseline_macro_f1": baseline_f1,
        "chosen_macro_f1": chosen_f1,
        "baseline_prior_gap": baseline_gap,
        "chosen_prior_gap": chosen_gap,
    }


def _completed_runs(
    registry_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    receipts = {}
    configs = {}
    for row in read_run_registry(registry_path):
        if row["status"] != "PASS_TRAINING_FINISHED":
            continue
        receipt_path = Path(str(row["metrics_path"]))
        config_path = Path(str(row["config_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if receipt.get("status") != "PASS_TRAINING_FINISHED":
            raise ValueError("registry points to an incomplete training receipt")
        if sha256_file(config_path) != row["config_hash"]:
            raise ValueError("registered training config hash mismatch")
        receipts[str(row["experiment_id"])] = receipt
        configs[str(row["experiment_id"])] = config
    return receipts, configs


def _write_queue(
    output: Path, configs: list[dict[str, Any]], *, stage: str
) -> list[dict[str, Any]]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite development stage: {output}")
    config_root = output / "configs"
    config_root.mkdir(parents=True)
    queue = []
    for config in configs:
        experiment_id = str(config["experiment_id"])
        path = config_root / f"{experiment_id}.json"
        write_json_atomic(path, config)
        queue.append(
            {
                "experiment_id": experiment_id,
                "status": "PLANNED",
                "stage": stage,
                "config_path": str(path.resolve()),
                "config_sha256": sha256_file(path),
                "effective_config_sha256": canonical_sha256(config),
                "train_fraction": float(config["data"]["train_fraction"]),
                "seed": int(config["seed"]),
                "internal_test_opened": False,
                "gold_opened": False,
            }
        )
    write_json_atomic(output / "run_queue.json", queue)
    return queue


def prepare_next_development_stage(
    *,
    stage: str,
    registry_path: Path,
    previous_selection: Path | None,
    output: Path,
) -> dict[str, Any]:
    receipts, configs = _completed_runs(registry_path)
    previous = (
        json.loads(previous_selection.read_text(encoding="utf-8"))
        if previous_selection is not None
        else None
    )
    if stage == "loss":
        required = {"D205", "M301-H1", "M301-H2"}
        if not required.issubset(receipts):
            raise ValueError("head screening runs are incomplete")
        selection = select_dev_candidate(
            "D205",
            ["M301-H1", "M301-H2"],
            receipts,
            minimum_f1_gain=0.015,
        )
        base_id = str(selection["chosen_experiment_id"])
        generated = []
        for experiment_id, loss_name in (
            ("M302-BS", "balanced_softmax"),
            ("M302-CBF", "class_balanced_focal"),
        ):
            config = deepcopy(configs[base_id])
            config["experiment_id"] = experiment_id
            config["development_axis"] = "classification_loss"
            config["classification_loss"]["name"] = loss_name
            generated.append(config)
        reuse_id = base_id
    elif stage == "adapter":
        if previous is None or previous.get("stage") != "loss":
            raise ValueError("adapter stage requires the loss selection receipt")
        base_id = str(previous["reuse_experiment_id"])
        required = {base_id, "M302-BS", "M302-CBF"}
        if not required.issubset(receipts):
            raise ValueError("loss screening runs are incomplete")
        selection = select_dev_candidate(
            base_id,
            ["M302-BS", "M302-CBF"],
            receipts,
            minimum_f1_gain=1e-8,
        )
        reuse_id = str(selection["chosen_experiment_id"])
        config = deepcopy(configs[reuse_id])
        config["experiment_id"] = "M303-last2"
        config["development_axis"] = "adapter_scope"
        config["model"]["adapter_scope"] = "last2"
        generated = [config]
    elif stage == "confirm":
        if previous is None or previous.get("stage") != "adapter":
            raise ValueError("confirm stage requires the adapter selection receipt")
        base_id = str(previous["reuse_experiment_id"])
        required = {base_id, "M303-last2"}
        if not required.issubset(receipts):
            raise ValueError("adapter screening runs are incomplete")
        selection = select_dev_candidate(
            base_id,
            ["M303-last2"],
            receipts,
            minimum_f1_gain=1e-8,
        )
        reuse_id = str(selection["chosen_experiment_id"])
        generated = []
        for seed in (29, 43):
            config = deepcopy(configs[reuse_id])
            config["experiment_id"] = f"M304-S{seed}"
            config["development_axis"] = "three_seed_confirmation"
            config["seed"] = seed
            generated.append(config)
    else:
        raise ValueError("stage must be loss, adapter, or confirm")
    queue = _write_queue(output, generated, stage=stage)
    result = {
        "schema": "prta-cxr.development-selection.v1",
        "status": "PASS_NEXT_DEVELOPMENT_STAGE_PREPARED",
        "stage": stage,
        "selection": selection,
        "reuse_experiment_id": reuse_id,
        "generated_experiment_ids": [row["experiment_id"] for row in queue],
        "queue_sha256": canonical_sha256(queue),
        "registry_sha256": sha256_file(registry_path),
        "internal_test_opened": False,
        "gold_opened": False,
    }
    write_json_atomic(output / "selection_receipt.json", result)
    return result
