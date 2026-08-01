from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import ContractError

RUN_RECEIPT_FIELDS = frozenset(
    {
        "experiment_id",
        "date",
        "owner",
        "git_commit",
        "config_path",
        "config_hash",
        "split_manifest_hash",
        "label_manifest_hash",
        "seed",
        "gpu",
        "start_time",
        "end_time",
        "status",
        "checkpoint_path",
        "prediction_path",
        "metrics_path",
        "log_path",
        "notes",
    }
)


def validate_run_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if set(receipt) != RUN_RECEIPT_FIELDS:
        missing = sorted(RUN_RECEIPT_FIELDS - set(receipt))
        extra = sorted(set(receipt) - RUN_RECEIPT_FIELDS)
        raise ContractError(f"run receipt mismatch; missing={missing}, extra={extra}")
    for key, value in receipt.items():
        if key == "seed":
            if not isinstance(value, int):
                raise ContractError("receipt seed must be integer")
        elif not isinstance(value, str):
            raise ContractError(f"receipt {key} must be a string")
    return dict(receipt)
