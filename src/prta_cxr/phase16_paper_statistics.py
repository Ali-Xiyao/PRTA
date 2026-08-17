from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file

METRICS = (
    "macro_f1",
    "balanced_accuracy",
    "opposite_direction_error_rate",
)
HOLM_FAMILIES = {
    "all_11_sensitivity": (
        "IF-A01",
        "IF-A02",
        "IF-A03",
        "IF-A04",
        "IF-A05",
        "IF-A06",
        "IF-A08",
        "IF-A10",
        "IF-A11",
        "IF-F01",
        "IF-F02",
    ),
    "primary_structure": ("IF-A01", "IF-A02", "IF-A03"),
    "exploratory_training_objectives": (
        "IF-A04",
        "IF-A05",
        "IF-A06",
        "IF-A08",
        "IF-A10",
        "IF-A11",
    ),
    "generic_fusion_comparators": ("IF-F01", "IF-F02"),
}
PARETO_SYSTEMS = ("V2", "IF-F01", "IF-F02")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    if not p_values:
        raise ValueError("Holm family cannot be empty")
    ordered = sorted((float(value), key) for key, value in p_values.items())
    if any(value < 0 or value > 1 for value, _ in ordered):
        raise ValueError("p-values must be within [0, 1]")
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for rank, (value, key) in enumerate(ordered):
        running = max(running, (total - rank) * value)
        adjusted[key] = min(1.0, running)
    return adjusted


def _validate_closed(value: Mapping[str, Any], *, label: str) -> None:
    for key in ("internal_test_opened", "gold_opened"):
        if value.get(key) is not False:
            raise ValueError(f"{label} reports protected access through {key}")
    if int(value.get("protected_outcome_read_count", -1)) != 0:
        raise ValueError(f"{label} reports protected reads")
    if value.get("selection_performed") is not False:
        raise ValueError(f"{label} reports selection")


def _mean_sd(values: Sequence[float]) -> dict[str, float]:
    return {"mean": float(mean(values)), "sample_sd": float(stdev(values))}


def _pareto_rows(
    point_metrics: Mapping[str, Any], routing: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for system in PARETO_SYSTEMS:
        by_seed = dict(point_metrics[system])
        macro = [float(dict(value)["macro_f1"]) for value in by_seed.values()]
        oder = [
            float(dict(value)["opposite_direction_error_rate"])
            for value in by_seed.values()
        ]
        rows.append(
            {
                "system": system,
                "macro_f1": _mean_sd(macro),
                "opposite_direction_error_rate": _mean_sd(oder),
                "cost_attached": False,
            }
        )
    current = dict(
        routing["three_seed_summary"]["matched_hard"]["invalid_to_current_only"][
            "metrics"
        ]
    )
    rows.append(
        {
            "system": "B401",
            "macro_f1": dict(current["macro_f1"]),
            "opposite_direction_error_rate": dict(
                current["opposite_direction_error_rate"]
            ),
            "cost_attached": False,
        }
    )
    for row in rows:
        dominated_by = []
        for other in rows:
            if other is row:
                continue
            other_f1 = float(other["macro_f1"]["mean"])
            other_oder = float(other["opposite_direction_error_rate"]["mean"])
            row_f1 = float(row["macro_f1"]["mean"])
            row_oder = float(row["opposite_direction_error_rate"]["mean"])
            if (
                other_f1 >= row_f1
                and other_oder <= row_oder
                and (other_f1 > row_f1 or other_oder < row_oder)
            ):
                dominated_by.append(str(other["system"]))
        row["pareto_optimal_f1_oder"] = not dominated_by
        row["dominated_by"] = sorted(dominated_by)
    return rows


def build_phase16_paper_statistics(
    bootstrap: Mapping[str, Any], routing: Mapping[str, Any]
) -> dict[str, Any]:
    _validate_closed(bootstrap, label="bootstrap")
    _validate_closed(routing, label="routing")
    contrasts = dict(bootstrap.get("contrasts", {}))
    families: dict[str, Any] = {}
    for family, variants in HOLM_FAMILIES.items():
        family_metrics: dict[str, Any] = {}
        for metric in METRICS:
            raw = {
                variant: float(
                    contrasts[f"V2_minus_{variant}"]["scopes"]["mean_across_seeds"][
                        metric
                    ]["empirical_two_sided_p"]
                )
                for variant in variants
            }
            adjusted = holm_adjust(raw)
            family_metrics[metric] = {
                variant: {
                    "unadjusted_p": raw[variant],
                    "holm_adjusted_p": adjusted[variant],
                    "reject_at_0_05": adjusted[variant] <= 0.05,
                    "effect": float(
                        contrasts[f"V2_minus_{variant}"]["scopes"]["mean_across_seeds"][
                            metric
                        ]["point"]
                    ),
                    "interval": dict(
                        contrasts[f"V2_minus_{variant}"]["scopes"]["mean_across_seeds"][
                            metric
                        ]["interval"]
                    ),
                }
                for variant in variants
            }
        families[family] = {
            "members": list(variants),
            "correction": "Holm within family and metric",
            "metrics": family_metrics,
        }
    return {
        "schema": "prta-cxr.phase16-paper-statistics.v1",
        "status": "PASS_PHASE16_HOLM_PARETO_NO_SELECTION",
        "created_at": datetime.now(UTC).isoformat(),
        "holm_families": families,
        "f1_oder_pareto": _pareto_rows(dict(bootstrap["point_metrics"]), routing),
        "cost_dimension_status": "PENDING_ENDPOINT_OR_UNIFIED_CACHED_COST_JOIN",
        "cost_used_for_selection": False,
        "selection_performed": False,
        "winner_selected": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }


def phase16_paper_statistics_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze Phase16 Holm and Pareto report"
    )
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--routing", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    bootstrap = _read_json(args.bootstrap)
    routing = _read_json(args.routing)
    result = build_phase16_paper_statistics(bootstrap, routing)
    result["input_hashes"] = {
        "bootstrap": sha256_file(args.bootstrap),
        "routing": sha256_file(args.routing),
    }
    _write_new_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
