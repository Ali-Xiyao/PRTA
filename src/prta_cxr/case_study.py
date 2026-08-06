from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.contracts import PROGRESSION_LABELS, ContractError, sha256_file

PROTECTED_PATH_MARKERS = ("internal-test", "internal_test", "gold")
OPPOSITE = {
    ("Improved", "Worse"),
    ("Worse", "Improved"),
    ("New", "Resolved"),
    ("Resolved", "New"),
}
CONDITIONS = ("true", "matched_wrong", "null", "reversed")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _reject_protected_path(path: Path) -> None:
    lowered = str(Path(path)).lower()
    if any(marker in lowered for marker in PROTECTED_PATH_MARKERS):
        raise ContractError(f"protected path is forbidden in case study: {path}")


def _index(rows: Sequence[Mapping[str, Any]], *, key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in rows:
        identifier = str(value[key])
        if identifier in result:
            raise ContractError(f"duplicate {key}: {identifier}")
        result[identifier] = dict(value)
    return result


def _validate_prediction_pair(
    left: Mapping[str, Any], right: Mapping[str, Any], *, condition: str
) -> None:
    for row in (left, right):
        if row.get("cohort") != "dev":
            raise ContractError("case study accepts Dev predictions only")
        if row.get("prior_intervention") != condition:
            raise ContractError("prediction intervention mismatch")
        if row.get("target") not in PROGRESSION_LABELS:
            raise ContractError("prediction target is not a progression label")
        if row.get("prediction") not in PROGRESSION_LABELS:
            raise ContractError("prediction is not a progression label")
    identity = ("observation_id", "patient_id", "target", "source", "finding")
    if any(left.get(key) != right.get(key) for key in identity):
        raise ContractError("PRTA/B403 prediction rows are misaligned")


def _validate_same_observation(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> None:
    identity = ("observation_id", "patient_id", "target", "source", "finding")
    if any(left.get(key) != right.get(key) for key in identity):
        raise ContractError("intervention prediction rows are misaligned")


def _interval_bin(row: Mapping[str, Any]) -> str:
    if not bool(row.get("calendar_interval_available", False)):
        return "ordinal"
    value = float(row.get("interval_days", 0.0))
    for bound in (1, 7, 30, 90, 365):
        if value <= bound:
            return f"le_{bound}d"
    return "gt_365d"


def _nll(row: Mapping[str, Any]) -> float:
    index = PROGRESSION_LABELS.index(str(row["target"]))
    probability = max(float(row["probabilities"][index]), 1e-12)
    return -math.log(probability)


def _paired_status(prta: Mapping[str, Any], b403: Mapping[str, Any]) -> str:
    target = str(prta["target"])
    p_correct = prta["prediction"] == target
    b_correct = b403["prediction"] == target
    if p_correct and b_correct:
        return "both_correct"
    if p_correct:
        return "prta_only_correct"
    if b_correct:
        return "b403_only_correct"
    return "both_wrong"


def _group_summary(rows: Sequence[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    result = []
    for value, group in sorted(groups.items()):
        counts = Counter(str(row["paired_status"]) for row in group)
        result.append(
            {
                key: value,
                "rows": len(group),
                **{name: counts[name] for name in (
                    "both_correct",
                    "prta_only_correct",
                    "b403_only_correct",
                    "both_wrong",
                )},
                "prta_accuracy": sum(
                    row["prta_prediction"] == row["target"] for row in group
                )
                / len(group),
                "b403_accuracy": sum(
                    row["b403_prediction"] == row["target"] for row in group
                )
                / len(group),
            }
        )
    return result


def _confusion_delta(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        target = str(row["target"])
        counts[(target, str(row["prta_prediction"]))]["prta"] += 1
        counts[(target, str(row["b403_prediction"]))]["b403"] += 1
    result = []
    for (target, prediction), count in counts.items():
        result.append(
            {
                "target": target,
                "prediction": prediction,
                "prta": count["prta"],
                "b403": count["b403"],
                "prta_minus_b403": count["prta"] - count["b403"],
                "opposite_direction": (target, prediction) in OPPOSITE,
            }
        )
    return sorted(
        result,
        key=lambda row: (
            -abs(int(row["prta_minus_b403"])),
            row["target"],
            row["prediction"],
        ),
    )


def _intervention_summary(
    true_rows: Mapping[str, Mapping[str, Any]],
    changed_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    corrected = regressed = prediction_changed = direction_errors = 0
    for identifier, true_row in true_rows.items():
        changed = changed_rows[identifier]
        target = str(true_row["target"])
        true_correct = true_row["prediction"] == target
        changed_correct = changed["prediction"] == target
        corrected += int(not true_correct and changed_correct)
        regressed += int(true_correct and not changed_correct)
        prediction_changed += int(true_row["prediction"] != changed["prediction"])
        direction_errors += int((target, str(changed["prediction"])) in OPPOSITE)
    total = len(true_rows)
    return {
        "rows": total,
        "prediction_changed": prediction_changed,
        "prediction_changed_rate": prediction_changed / total,
        "true_correct_to_wrong": regressed,
        "true_wrong_to_correct": corrected,
        "net_correctness_change": corrected - regressed,
        "opposite_direction_errors": direction_errors,
        "opposite_direction_error_rate": direction_errors / total,
    }


def _case_score(row: Mapping[str, Any]) -> float:
    if row["paired_status"] == "prta_only_correct":
        return float(row["b403_confidence"]) + float(row["b403_nll"])
    if row["paired_status"] == "b403_only_correct":
        return float(row["prta_confidence"]) + float(row["prta_nll"])
    return max(float(row["prta_nll"]), float(row["b403_nll"]))


def _select_cases(
    rows: Sequence[Mapping[str, Any]], per_target: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for status in ("prta_only_correct", "b403_only_correct"):
        for target in PROGRESSION_LABELS:
            candidates = [
                row
                for row in rows
                if row["paired_status"] == status and row["target"] == target
            ]
            candidates.sort(key=_case_score, reverse=True)
            selected.extend(dict(row) for row in candidates[:per_target])
    direction = [
        row
        for row in rows
        if (row["target"], row["prta_prediction"]) in OPPOSITE
        or (row["target"], row["b403_prediction"]) in OPPOSITE
    ]
    direction.sort(key=_case_score, reverse=True)
    selected.extend(dict(row) for row in direction[: per_target * 2])
    deduplicated: dict[str, dict[str, Any]] = {}
    for row in selected:
        deduplicated.setdefault(str(row["observation_id"]), row)
    return list(deduplicated.values())


def _markdown(cases: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    lines = [
        "# PRTA-CXR PRTA vs B403 内部 Case Study",
        "",
        "> 仅限内部 Train/Dev 方法诊断。病例报告、内部日期、路径和哈希不得提交 Git。",
        "",
        "## 总结",
        "",
        f"- Dev：{summary['rows']:,} 条，患者 {summary['patients']:,} 名。",
        f"- PRTA 独有正确：{summary['paired_counts']['prta_only_correct']:,}；"
        f"B403 独有正确：{summary['paired_counts']['b403_only_correct']:,}。",
        "- 该文档中的病例是诊断性代表样本，不构成医学 Gold。",
        "",
        "## 代表病例",
        "",
    ]
    for index, row in enumerate(cases, start=1):
        lines.extend(
            [
                f"### Case {index}: {row['paired_status']} / {row['target']}",
                "",
                f"- sample：`{row['observation_id']}`；"
                f"patient：`{row['patient_id_hash']}`",
                f"- source/finding：`{row['source']}` / `{row['finding']}`",
                f"- interval/view：`{row['interval_days']}` days；"
                f"`{row['prior_view']} -> {row['current_view']}`",
                f"- target：`{row['target']}`；PRTA：`{row['prta_prediction']}` "
                f"(conf={row['prta_confidence']:.4f}, NLL={row['prta_nll']:.4f})；"
                f"B403：`{row['b403_prediction']}` "
                f"(conf={row['b403_confidence']:.4f}, NLL={row['b403_nll']:.4f})",
                f"- PRIOR image：`{row['prior_image_path']}`",
                f"- CURRENT image：`{row['current_image_path']}`",
                "",
                "**PRIOR report**",
                "",
                str(row["prior_report"]),
                "",
                "**CURRENT report**",
                "",
                str(row["current_report"]),
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def build_case_study(
    *,
    manifest_path: Path,
    prta_root: Path,
    b403_root: Path,
    output_root: Path,
    per_target: int = 3,
) -> dict[str, Any]:
    paths = [
        Path(manifest_path),
        Path(prta_root),
        Path(b403_root),
        Path(output_root),
    ]
    for path in paths:
        _reject_protected_path(path)
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite case study: {output_root}")
    if per_target <= 0:
        raise ValueError("per_target must be positive")

    manifest_rows = _read_jsonl(Path(manifest_path))
    if any(row.get("split") not in {"train", "dev"} for row in manifest_rows):
        raise ContractError("case-study manifest must contain Train/Dev only")
    dev_manifest = _index(
        [row for row in manifest_rows if row.get("split") == "dev"],
        key="sample_id",
    )
    predictions: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for system, root in (("prta", prta_root), ("b403", b403_root)):
        predictions[system] = {}
        for condition in CONDITIONS:
            path = Path(root) / f"{condition}.predictions.jsonl"
            _reject_protected_path(path)
            predictions[system][condition] = _index(
                _read_jsonl(path), key="observation_id"
            )

    expected = set(dev_manifest)
    for system in predictions.values():
        for condition, rows in system.items():
            if set(rows) != expected:
                raise ContractError(
                    f"{condition} predictions do not exactly cover cleaned Dev"
                )
    for condition in CONDITIONS:
        for identifier in expected:
            _validate_prediction_pair(
                predictions["prta"][condition][identifier],
                predictions["b403"][condition][identifier],
                condition=condition,
            )

    paired_rows: list[dict[str, Any]] = []
    for identifier in sorted(expected):
        prta = predictions["prta"]["true"][identifier]
        b403 = predictions["b403"]["true"][identifier]
        _validate_prediction_pair(prta, b403, condition="true")
        detail = dev_manifest[identifier]
        if detail["progression_label"] != prta["target"]:
            raise ContractError("manifest/prediction target mismatch")
        paired_rows.append(
            {
                "observation_id": identifier,
                "patient_id_hash": str(detail["patient_id_hash"]),
                "source": str(prta["source"]),
                "finding": str(prta["finding"]),
                "target": str(prta["target"]),
                "prta_prediction": str(prta["prediction"]),
                "b403_prediction": str(b403["prediction"]),
                "prta_confidence": float(prta["confidence"]),
                "b403_confidence": float(b403["confidence"]),
                "prta_nll": _nll(prta),
                "b403_nll": _nll(b403),
                "paired_status": _paired_status(prta, b403),
                "interval_bin": _interval_bin(prta),
                "interval_days": float(prta["interval_days"]),
                "view_pair": f"{prta['prior_view']}->{prta['current_view']}",
                "prior_view": str(prta["prior_view"]),
                "current_view": str(prta["current_view"]),
                "prior_study_id": str(detail["prior_study_id"]),
                "current_study_id": str(detail["current_study_id"]),
                "prior_image_path": str(detail["prior_image_path"]),
                "current_image_path": str(detail["current_image_path"]),
                "prior_datetime": str(detail["prior_datetime"]),
                "current_datetime": str(detail["current_datetime"]),
                "prior_report": str(detail["prior_report"]),
                "current_report": str(detail["current_report"]),
            }
        )

    counts = Counter(str(row["paired_status"]) for row in paired_rows)
    patients = len({str(row["patient_id_hash"]) for row in paired_rows})
    summary: dict[str, Any] = {
        "schema": "prta-cxr.exploratory-case-study.v1",
        "status": "PASS_EXPLORATORY_DEV_CASE_STUDY",
        "created_at": datetime.now(UTC).isoformat(),
        "rows": len(paired_rows),
        "patients": patients,
        "paired_counts": dict(sorted(counts.items())),
        "by_target": _group_summary(paired_rows, "target"),
        "by_source": _group_summary(paired_rows, "source"),
        "by_finding": _group_summary(paired_rows, "finding"),
        "by_interval_bin": _group_summary(paired_rows, "interval_bin"),
        "by_view_pair": _group_summary(paired_rows, "view_pair"),
        "confusion_delta": _confusion_delta(paired_rows),
        "prior_interventions": {},
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    for condition in CONDITIONS[1:]:
        summary["prior_interventions"][condition] = {}
        for system in ("prta", "b403"):
            true_rows = predictions[system]["true"]
            changed = predictions[system][condition]
            for identifier in expected:
                _validate_same_observation(true_rows[identifier], changed[identifier])
            summary["prior_interventions"][condition][system] = (
                _intervention_summary(true_rows, changed)
            )

    cases = _select_cases(paired_rows, per_target)
    output_root.mkdir(parents=True)
    summary_path = output_root / "case_study_summary.json"
    cases_path = output_root / "case_study_cases.jsonl"
    markdown_path = output_root / "PRTA_CXR_PRTA_vs_B403_case_study_internal.md"
    write_json_atomic(summary_path, summary)
    write_jsonl_atomic(cases_path, cases)
    markdown_path.write_text(_markdown(cases, summary), encoding="utf-8")
    receipt = {
        "schema": "prta-cxr.exploratory-case-study-receipt.v1",
        "status": "PASS_EXPLORATORY_DEV_CASE_STUDY",
        "rows": len(paired_rows),
        "patients": patients,
        "representative_cases": len(cases),
        "input_sha256": {
            "manifest": sha256_file(Path(manifest_path)),
            **{
                f"{system}_{condition}": sha256_file(
                    Path(root) / f"{condition}.predictions.jsonl"
                )
                for system, root in (("prta", prta_root), ("b403", b403_root))
                for condition in CONDITIONS
            },
        },
        "output_sha256": {
            "summary": sha256_file(summary_path),
            "cases": sha256_file(cases_path),
            "markdown": sha256_file(markdown_path),
        },
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(output_root / "case_study_receipt.json", receipt)
    return receipt


def case_study_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a private Train/Dev-only PRTA-vs-B403 case study"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prta-root", type=Path, required=True)
    parser.add_argument("--b403-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-target", type=int, default=3)
    args = parser.parse_args(argv)
    result = build_case_study(
        manifest_path=args.manifest,
        prta_root=args.prta_root,
        b403_root=args.b403_root,
        output_root=args.output,
        per_target=args.per_target,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
