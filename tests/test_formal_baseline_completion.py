import json
from copy import deepcopy

import pytest

from prta_cxr.audit.tracin import AuditContractError
from prta_cxr.contracts import PROGRESSION_LABELS, canonical_sha256
from prta_cxr.formal_baseline_completion import (
    build_formal_baseline_completion_configs,
    verify_reused_run,
)


def _parent(family: str) -> dict:
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": f"parent-{family}",
        "seed": 17,
        "development_axis": "parent",
        "data": {"train_fraction": 1.0, "fraction_salt": "fixed"},
        "classification_loss": {
            "name": "class_balanced_focal",
            "beta": 0.9999,
            "gamma": 2.0,
            "class_counts": [1, 1, 1, 1, 1],
        },
        "optimization": {"epochs": 20, "batch_size": 16},
        "loss_weights": {
            "classification": 1.0,
            "alignment": 0.0,
            "cmcp": 0.0,
            "inversion": 0.0,
            "state": 0.0,
        },
        "model": {
            "family": family,
            "adapter_scope": "tail4",
            "native_head": "H0",
        },
    }


def _counts() -> dict[str, int]:
    return {label: index + 10 for index, label in enumerate(PROGRESSION_LABELS)}


def test_completion_configs_freeze_only_missing_native_baselines() -> None:
    b401 = _parent("current_only")
    b402 = _parent("siamese_diff")
    configs = build_formal_baseline_completion_configs(
        b401_parent=b401,
        b402_parent=b402,
        train_class_counts=_counts(),
    )
    assert [row["experiment_id"] for row in configs] == [
        "W046-B401-S17",
        "W046-B401-S28",
        "W046-B401-S43",
        "W046-B402-S28",
        "W046-B402-S43",
    ]
    assert [row["seed"] for row in configs] == [17, 28, 43, 28, 43]
    assert [row["model"]["family"] for row in configs] == [
        "current_only",
        "current_only",
        "current_only",
        "siamese_diff",
        "siamese_diff",
    ]
    expected_counts = [_counts()[label] for label in PROGRESSION_LABELS]
    assert all(
        row["classification_loss"]["class_counts"] == expected_counts for row in configs
    )
    assert b401 == _parent("current_only")
    assert b402 == _parent("siamese_diff")


def test_completion_configs_reject_budget_drift() -> None:
    b401 = _parent("current_only")
    b402 = deepcopy(_parent("siamese_diff"))
    b402["optimization"]["epochs"] = 21
    with pytest.raises(AuditContractError, match="budgets differ"):
        build_formal_baseline_completion_configs(
            b401_parent=b401,
            b402_parent=b402,
            train_class_counts=_counts(),
        )


def test_completion_configs_reject_partial_train() -> None:
    b401 = _parent("current_only")
    b401["data"]["train_fraction"] = 0.5
    with pytest.raises(AuditContractError, match="full retained Train"):
        build_formal_baseline_completion_configs(
            b401_parent=b401,
            b402_parent=_parent("siamese_diff"),
            train_class_counts=_counts(),
        )


def test_reused_run_resolves_checkpoint_relative_to_receipt(tmp_path) -> None:
    config = _parent("tila")
    config["experiment_id"] = "B403-S28"
    config["seed"] = 28
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    checkpoint_path = tmp_path / "best.pt"
    checkpoint_path.write_bytes(b"checkpoint")
    receipt_path = tmp_path / "training_receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "status": "PASS_TRAINING_FINISHED",
                "config_sha256": canonical_sha256(config),
                "protected_outcomes_opened": False,
                "internal_test_opened": False,
                "checkpoint_path": "best.pt",
            }
        ),
        encoding="utf-8",
    )
    result = verify_reused_run(
        config_path=config_path,
        receipt_path=receipt_path,
        expected_id="B403-S28",
        expected_family="tila",
        expected_seed=28,
    )
    assert result["checkpoint_path"] == str(checkpoint_path.resolve())
    assert result["zero_protected_reads"] is True
