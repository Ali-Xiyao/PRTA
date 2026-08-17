from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.evaluation.progression import classification_metrics

SEEDS = (17, 28, 43)
INTERVENTIONS = ("true", "matched_hard", "null", "reversed")
INVALID_INTERVENTIONS = frozenset({"matched_hard", "null", "reversed"})


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _validate_closed_receipt(receipt: Mapping[str, Any], *, label: str) -> None:
    if receipt.get("internal_test_opened") is not False:
        raise ValueError(f"{label} reports Internal-test access")
    if receipt.get("gold_opened") is not False:
        raise ValueError(f"{label} reports Gold access")
    if int(receipt.get("protected_outcome_read_count", -1)) != 0:
        raise ValueError(f"{label} reports protected reads")
    if receipt.get("selection_performed") is not False:
        raise ValueError(f"{label} reports model selection")


def _load_blocks(
    receipt_path: Path,
) -> tuple[str, int, dict[str, list[dict[str, Any]]]]:
    receipt = _read_json(receipt_path)
    _validate_closed_receipt(receipt, label=str(receipt_path))
    system = str(receipt.get("variant", ""))
    seed = int(receipt.get("seed", -1))
    if seed not in SEEDS:
        raise ValueError(f"unexpected routing Seed: {seed}")
    required = INTERVENTIONS if system == "V2" else ("true",)
    inventory = receipt.get("prediction_blocks")
    if not isinstance(inventory, dict) or not set(required) <= set(inventory):
        raise ValueError(f"routing receipt lacks intervention blocks: {receipt_path}")
    blocks: dict[str, list[dict[str, Any]]] = {}
    parent = receipt_path.parent.resolve()
    for intervention in required:
        block = dict(inventory[intervention])
        path = (receipt_path.parent / str(block["path"])).resolve()
        if path.parent != parent:
            raise ValueError(f"routing prediction block escapes receipt root: {path}")
        if sha256_file(path) != str(block["sha256"]):
            raise ValueError(f"routing prediction hash drift: {path}")
        rows = _read_jsonl(path)
        if len(rows) != int(block["rows"]):
            raise ValueError(f"routing prediction row-count drift: {path}")
        for row in rows:
            if str(row.get("cohort")) != "dev":
                raise ValueError("routing accepts Dev predictions only")
            if str(row.get("prior_intervention")) != intervention:
                raise ValueError("routing intervention identity drift")
            if str(row.get("system")) != system:
                raise ValueError("routing system identity drift")
            if int(row.get("training_seed", -1)) != seed:
                raise ValueError("routing Seed identity drift")
        blocks[intervention] = rows
    return system, seed, blocks


def _index(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed = {str(row["observation_id"]): dict(row) for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("duplicate routing observation ID")
    return indexed


def _aligned_rows(
    v2_rows: Sequence[Mapping[str, Any]], current_rows: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    v2 = _index(v2_rows)
    current = _index(current_rows)
    if set(v2) != set(current):
        raise ValueError("V2/current-only routing observation roster drift")
    for observation in v2:
        left = v2[observation]
        right = current[observation]
        identity = ("patient_id", "target")
        if any(str(left[key]) != str(right[key]) for key in identity):
            raise ValueError("V2/current-only routing target identity drift")
    order = sorted(v2)
    return [v2[key] for key in order], [current[key] for key in order]


def _metric_payload(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metrics = classification_metrics(rows, labels=PROGRESSION_LABELS)
    return {
        "coverage": 1.0,
        "retained_rows": len(rows),
        "metrics": metrics,
    }


def evaluate_safety_routing(
    v2_receipts: Sequence[Path], current_only_receipts: Sequence[Path]
) -> dict[str, Any]:
    loaded: dict[str, dict[int, dict[str, list[dict[str, Any]]]]] = defaultdict(dict)
    receipt_hashes: dict[str, str] = {}
    for expected_system, paths in (
        ("V2", v2_receipts),
        ("B401", current_only_receipts),
    ):
        for path in paths:
            system, seed, blocks = _load_blocks(path)
            if system != expected_system:
                raise ValueError(
                    f"expected {expected_system} routing receipt, got {system}"
                )
            if seed in loaded[system]:
                raise ValueError(f"duplicate routing receipt: {system}/S{seed}")
            loaded[system][seed] = blocks
            receipt_hashes[f"{system}/S{seed}"] = sha256_file(path)
        if set(loaded[expected_system]) != set(SEEDS):
            raise ValueError(f"incomplete routing Seed roster: {expected_system}")

    by_seed: dict[str, Any] = {}
    aggregate_values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for seed in SEEDS:
        seed_result: dict[str, Any] = {}
        current_true = loaded["B401"][seed]["true"]
        for intervention in INTERVENTIONS:
            v2, current = _aligned_rows(loaded["V2"][seed][intervention], current_true)
            invalid = intervention in INVALID_INTERVENTIONS
            strategies = {
                "always_v2": _metric_payload(v2),
                "invalid_to_current_only": _metric_payload(current if invalid else v2),
                "invalid_to_abstain": (
                    {
                        "coverage": 0.0,
                        "retained_rows": 0,
                        "metrics": None,
                    }
                    if invalid
                    else _metric_payload(v2)
                ),
            }
            seed_result[intervention] = strategies
            for strategy, result in strategies.items():
                if result["metrics"] is None:
                    continue
                ordinary = dict(result["metrics"]["ordinary"])
                for metric in ("macro_f1", "opposite_direction_error_rate"):
                    aggregate_values[(intervention, strategy, metric)].append(
                        float(ordinary[metric])
                    )
        by_seed[str(seed)] = seed_result

    aggregates: dict[str, Any] = {}
    for intervention in INTERVENTIONS:
        aggregates[intervention] = {}
        for strategy in (
            "always_v2",
            "invalid_to_current_only",
            "invalid_to_abstain",
        ):
            metrics: dict[str, Any] = {}
            for metric in ("macro_f1", "opposite_direction_error_rate"):
                values = aggregate_values.get((intervention, strategy, metric), [])
                if values:
                    metrics[metric] = {
                        "mean": float(mean(values)),
                        "sample_sd": float(stdev(values)),
                    }
            aggregates[intervention][strategy] = {
                "coverage": 0.0
                if strategy == "invalid_to_abstain"
                and intervention in INVALID_INTERVENTIONS
                else 1.0,
                "metrics": metrics or None,
            }
    return {
        "schema": "prta-cxr.phase16-prior-safety-routing.v1",
        "status": "PASS_PHASE16_PRIOR_SAFETY_ROUTING_NO_SELECTION",
        "created_at": datetime.now(UTC).isoformat(),
        "seeds": list(SEEDS),
        "interventions": list(INTERVENTIONS),
        "receipt_hashes": receipt_hashes,
        "routing_detector": "known synthetic intervention identity",
        "interpretation": "oracle-detectable invalid-history routing simulation",
        "threshold_tuning_performed": False,
        "by_seed": by_seed,
        "three_seed_summary": aggregates,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def phase16_safety_routing_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate frozen PRIOR safety routing")
    parser.add_argument("--v2-receipt", type=Path, action="append", required=True)
    parser.add_argument(
        "--current-only-receipt", type=Path, action="append", required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    result = evaluate_safety_routing(args.v2_receipt, args.current_only_receipt)
    _write_new_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
