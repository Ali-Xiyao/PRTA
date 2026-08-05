from __future__ import annotations

from copy import deepcopy

import pytest

from prta_cxr.audit.tracin import AuditContractError
from prta_cxr.cleaned_rerun import (
    CLEANED_BASELINE_RUNS,
    CLEANED_PRTA_RUNS,
    build_cleaned_rerun_configs,
)
from prta_cxr.contracts import PROGRESSION_LABELS


def _parent(family: str) -> dict:
    return {
        "schema": "prta-cxr.training.v1",
        "experiment_id": "PARENT",
        "seed": 99,
        "development_axis": "parent",
        "data": {"train_fraction": 1.0, "fraction_salt": "fixed"},
        "classification_loss": {
            "name": "class_balanced_focal",
            "class_counts": [1, 1, 1, 1, 1],
        },
        "optimization": {"epochs": 20, "batch_size": 16},
        "model": {"family": family},
    }


def test_cleaned_configs_freeze_user_selected_seeds_and_budgets() -> None:
    prta = _parent("prta")
    b402 = _parent("siamese_diff")
    b403 = _parent("tila")
    configs = build_cleaned_rerun_configs(
        prta_parent=prta,
        baseline_parents={"siamese_diff": b402, "tila": b403},
        train_class_counts={
            label: index + 10
            for index, label in enumerate(PROGRESSION_LABELS)
        },
    )
    assert [value["experiment_id"] for value in configs] == [
        value[0] for value in (*CLEANED_PRTA_RUNS, *CLEANED_BASELINE_RUNS)
    ]
    assert [value["seed"] for value in configs] == [17, 28, 43, 17, 17]
    assert [value["optimization"] for value in configs[:3]] == [
        prta["optimization"]
    ] * 3
    assert configs[3]["optimization"] == b402["optimization"]
    assert configs[4]["optimization"] == b403["optimization"]


def test_cleaned_configs_reject_partial_train_fraction() -> None:
    prta = _parent("prta")
    prta["data"]["train_fraction"] = 0.5
    with pytest.raises(AuditContractError, match="full retained Train"):
        build_cleaned_rerun_configs(
            prta_parent=prta,
            baseline_parents={
                "siamese_diff": deepcopy(_parent("siamese_diff")),
                "tila": deepcopy(_parent("tila")),
            },
            train_class_counts={label: 10 for label in PROGRESSION_LABELS},
        )
