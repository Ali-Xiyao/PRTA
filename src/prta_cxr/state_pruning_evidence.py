from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.provenance import resolve_source_commit


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def compare_prediction_blocks(
    baseline: Sequence[dict[str, Any]], pruned: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    baseline_by_id = {str(row["observation_id"]): row for row in baseline}
    pruned_by_id = {str(row["observation_id"]): row for row in pruned}
    if set(baseline_by_id) != set(pruned_by_id):
        raise ValueError("state-pruning sample roster drift")
    max_abs_logit_diff = 0.0
    prediction_mismatches = 0
    for sample_id in sorted(baseline_by_id):
        left = baseline_by_id[sample_id]
        right = pruned_by_id[sample_id]
        if left["target"] != right["target"]:
            raise ValueError("state-pruning target drift")
        prediction_mismatches += left["prediction"] != right["prediction"]
        left_logits = list(map(float, left["logits"]))
        right_logits = list(map(float, right["logits"]))
        if len(left_logits) != len(right_logits):
            raise ValueError("state-pruning logit width drift")
        max_abs_logit_diff = max(
            max_abs_logit_diff,
            max(abs(a - b) for a, b in zip(left_logits, right_logits, strict=True)),
        )
    return {
        "rows": len(baseline_by_id),
        "prediction_mismatch_count": int(prediction_mismatches),
        "max_abs_logit_difference": float(max_abs_logit_diff),
        "parity_tolerance": 1e-6,
        "parity_pass": prediction_mismatches == 0 and max_abs_logit_diff <= 1e-6,
    }


def _block_from_receipt(path: Path) -> tuple[dict[str, Any], Path]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    block = dict(receipt.get("prediction_blocks", {}).get("true", {}))
    if not block:
        raise ValueError("probability receipt lacks true prediction block")
    block_path = path.parent / str(block["path"])
    if sha256_file(block_path) != block.get("sha256"):
        raise ValueError("probability block hash drift")
    return receipt, block_path


def state_pruning_compare_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove exact H0 state-pruning parity")
    parser.add_argument("--baseline-receipt", type=Path, required=True)
    parser.add_argument("--pruned-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable file")
    baseline_receipt, baseline_path = _block_from_receipt(args.baseline_receipt)
    pruned_receipt, pruned_path = _block_from_receipt(args.pruned_receipt)
    if baseline_receipt.get("checkpoint_sha256") != pruned_receipt.get(
        "checkpoint_sha256"
    ):
        raise ValueError("state-pruning checkpoint identity drift")
    if pruned_receipt.get("deployment_state_pruned") is not True:
        raise ValueError("pruned receipt does not declare deployment state pruning")
    comparison = compare_prediction_blocks(
        _read_jsonl(baseline_path), _read_jsonl(pruned_path)
    )
    if not comparison["parity_pass"]:
        raise ValueError(f"state-pruning parity failed: {comparison}")
    payload = {
        "schema": "prta-cxr.state-pruning-parity.v1",
        "status": "PASS_EXACT_H0_STATE_PRUNING_PARITY",
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "seed": int(pruned_receipt["seed"]),
        "checkpoint_sha256": pruned_receipt["checkpoint_sha256"],
        "baseline_receipt_sha256": sha256_file(args.baseline_receipt),
        "pruned_receipt_sha256": sha256_file(args.pruned_receipt),
        "comparison": comparison,
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
