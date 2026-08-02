from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

METHOD_NAMES = {
    "B401": "Current-only",
    "B402": "Siamese Diff",
    "B403": "TILA",
    "B404": "PRTA-CXR",
}


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("cannot average an empty result sequence")
    return sum(values) / len(values)


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    return f"{float(value):.{digits}f}"


def _summary_rows(
    trust: Mapping[str, Any], system: str, cohort: str, condition: str = "true"
) -> list[Mapping[str, Any]]:
    prefix = f"{system}|"
    suffix = f"|{cohort}|{condition}"
    rows = [
        value
        for key, value in trust["summaries"].items()
        if key.startswith(prefix) and key.endswith(suffix)
    ]
    if len(rows) != 3:
        raise ValueError(
            f"expected three frozen summaries for {system}/{cohort}/{condition}"
        )
    return rows


def method_result(
    trust: Mapping[str, Any], system: str, *, cohort: str = "internal_test"
) -> dict[str, Any]:
    summaries = _summary_rows(trust, system, cohort)
    metrics = [row["classification"]["patient_balanced"] for row in summaries]
    calibration = [row["calibration"] for row in summaries]
    risk = [row["risk_coverage"] for row in summaries]
    interval = None
    if cohort == "internal_test" and system in trust["bootstrap"]["main_methods"][
        "system_intervals"
    ]:
        interval = trust["bootstrap"]["main_methods"]["system_intervals"][system]
    return {
        "system": system,
        "method": METHOD_NAMES.get(system, system),
        **{
            key: _mean([float(row[key]) for row in metrics])
            for key in (
                "macro_f1",
                "balanced_accuracy",
                "accuracy",
                "min_class_recall",
                "opposite_direction_error_rate",
            )
        },
        **{
            key: _mean([float(row[key]) for row in calibration])
            for key in ("nll", "brier", "ece", "mean_confidence")
        },
        "aurc": _mean([float(row["aurc"]) for row in risk]),
        "risk_at_coverage": {
            coverage: _mean(
                [float(row["risk_at_coverage"][coverage]) for row in risk]
            )
            for coverage in ("0.9", "0.8", "0.7")
        },
        "ci95": interval,
    }


def intervention_result(
    trust: Mapping[str, Any], condition: str
) -> dict[str, Any]:
    summaries = _summary_rows(trust, "B404", "internal_test", condition)
    classification = [row["classification"]["patient_balanced"] for row in summaries]
    calibration = [row["calibration"] for row in summaries]
    comparisons = [
        value
        for key, value in trust["interventions"].items()
        if key.startswith("B404|")
        and key.endswith(f"|internal_test|{condition}")
    ]
    if condition == "true":
        comparisons = []
    elif len(comparisons) != 3:
        raise ValueError(f"expected three intervention comparisons: {condition}")
    true_f1 = method_result(trust, "B404")["macro_f1"]
    macro_f1 = _mean([float(row["macro_f1"]) for row in classification])
    return {
        "condition": condition,
        "macro_f1": macro_f1,
        "delta_vs_true": macro_f1 - true_f1,
        "nll": _mean([float(row["nll"]) for row in calibration]),
        "brier": _mean([float(row["brier"]) for row in calibration]),
        "confidence": _mean(
            [float(row["mean_confidence"]) for row in calibration]
        ),
        "flip_rate": (
            0.0
            if not comparisons
            else _mean([float(row["flip_rate"]) for row in comparisons])
        ),
        "correct_to_wrong": (
            0.0
            if not comparisons
            else _mean(
                [float(row["correct_to_wrong_rate"]) for row in comparisons]
            )
        ),
        "wrong_to_correct": (
            0.0
            if not comparisons
            else _mean(
                [float(row["wrong_to_correct_rate"]) for row in comparisons]
            )
        ),
        "oder": _mean(
            [float(row["opposite_direction_error_rate"]) for row in classification]
        ),
    }


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if not 0 <= successes <= total or total <= 0:
        raise ValueError("Wilson interval counts are invalid")
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return center - radius, center + radius


def data_table(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sources = sorted({str(row["source"]) for row in rows})
    output = []
    for source in sources:
        selected = [row for row in rows if str(row["source"]) == source]
        splits = Counter(str(row["split"]) for row in selected)
        output.append(
            {
                "source": source,
                "candidate_rows": "N/A—not frozen",
                "luna_silver_rows": "N/A—not frozen by source",
                "train": splits.get("train", 0),
                "dev": splits.get("dev", 0),
                "internal_test": splits.get("internal_test", 0),
                "patients": len({str(row["patient_id_hash"]) for row in selected}),
            }
        )
    return output


def render_markdown(bundle: Mapping[str, Any]) -> str:
    lines = [
        "# PRTA-CXR 论文正式结果表（自动复算）",
        "",
        "> 所有数字由冻结 artifact 自动生成；N/A 表示该字段没有被正式协议冻结，",
        "> 不用聊天记录或旧调试结果补写。Luna 质量数字是资深医生可见 Luna 标签的",
        "> 辅助确认率，不是独立盲法医学准确率。",
        "",
        "## Table 1：数据与最终划分",
        "",
        "| Source | Candidate rows | Luna Silver | Train | Dev | "
        "Internal test | Patients |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in bundle["table1_data"]:
        lines.append(
            "| {source} | {candidate_rows} | {luna_silver_rows} | {train} | "
            "{dev} | {internal_test} | {patients} |".format(**row)
        )
    quality = bundle["table2_quality"]
    lines.extend(
        [
            "",
            "## Table 2：标签质量审计",
            "",
            "| Pipeline | Reviewed | Assisted confirmation | 95% CI | New | "
            "Resolved | Improved | Stable | Worse |",
            "|---|---:|---:|---|---:|---:|---:|---:|---:|",
            "| Luna-primary Silver | {reviewed_rows} | {silver_accuracy:.4f} | "
            "[{ci_lower:.4f}, {ci_upper:.4f}] | {New:.4f} | {Resolved:.4f} | "
            "{Improved:.4f} | {Stable:.4f} | {Worse:.4f} |".format(
                **quality, **quality["accuracy_by_label"]
            ),
            "",
            "## Table 3：正式主结果（3 seeds）",
            "",
            "| Method | Macro-F1 | Balanced Acc | Accuracy | Min recall | "
            "ODER | 95% CI |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in bundle["table3_main"]:
        interval = row["ci95"]
        ci = "N/A" if interval is None else (
            f"[{interval['lower']:.4f}, {interval['upper']:.4f}]"
        )
        lines.append(
            f"| {row['method']} | {_fmt(row['macro_f1'])} | "
            f"{_fmt(row['balanced_accuracy'])} | {_fmt(row['accuracy'])} | "
            f"{_fmt(row['min_class_recall'])} | "
            f"{_fmt(row['opposite_direction_error_rate'])} | {ci} |"
        )
    lines.extend(
        [
            "",
            "## Table 4：Luna-primary 数据规模（Dev screening）",
            "",
            "| Train fraction | Patients | Rows | PRTA-H0 Dev F1 | Strong baseline |",
            "|---:|---:|---:|---:|---|",
        ]
    )
    for row in bundle["table4_scaling"]:
        lines.append(
            f"| {100 * row['fraction']:.0f}% | {row['patients']} | {row['rows']} | "
            f"{row['macro_f1']:.4f} | N/A—not in frozen scaling queue |"
        )
    lines.extend(
        [
            "",
            "## Table 5：方法消融",
            "",
            "| Variant | Macro-F1 | Balanced Acc | Min recall | ODER |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in bundle["table5_ablations"]:
        lines.append(
            f"| {row['method']} | {_fmt(row['macro_f1'])} | "
            f"{_fmt(row['balanced_accuracy'])} | {_fmt(row['min_class_recall'])} | "
            f"{_fmt(row['opposite_direction_error_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## Table 6：可信输入干预",
            "",
            "| Condition | Macro-F1 | Δ vs True | NLL | Brier | Confidence | "
            "Flip | C→W | W→C | ODER |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in bundle["table6_interventions"]:
        lines.append(
            f"| {row['condition']} | {_fmt(row['macro_f1'])} | "
            f"{_fmt(row['delta_vs_true'])} | {_fmt(row['nll'])} | "
            f"{_fmt(row['brier'])} | {_fmt(row['confidence'])} | "
            f"{_fmt(row['flip_rate'])} | {_fmt(row['correct_to_wrong'])} | "
            f"{_fmt(row['wrong_to_correct'])} | {_fmt(row['oder'])} |"
        )
    lines.extend(
        [
            "",
            "## Table 7：校准与选择性预测",
            "",
            "| Method | NLL | Brier | ECE | AURC | Risk@90% | Risk@80% | Risk@70% |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in bundle["table7_calibration"]:
        risk = row["risk_at_coverage"]
        lines.append(
            f"| {row['method']} | {_fmt(row['nll'])} | {_fmt(row['brier'])} | "
            f"{_fmt(row['ece'])} | {_fmt(row['aurc'])} | {_fmt(risk['0.9'])} | "
            f"{_fmt(risk['0.8'])} | {_fmt(risk['0.7'])} |"
        )
    vlm = bundle["table8_vlm"]
    lines.extend(
        [
            "",
            "## Table 8：VLM 附加部署",
            "",
            "| Visual model | Setting | Macro-F1 | Schema validity | "
            "Finding consistency | Temporal contradiction | Status |",
            "|---|---|---:|---:|---:|---:|---|",
            f"| Final PRTA-CXR | exact-64 + frozen Qwen3-VL-4B | "
            f"{_fmt(vlm['macro_f1'])} | {_fmt(vlm['schema_validity'])} | "
            f"{_fmt(vlm['finding_consistency'])} | "
            f"{_fmt(vlm['temporal_contradiction'])} | {vlm['paper_inclusion']} |",
            "",
            "## Expert Gold 附表（原生 ViT，3 seeds）",
            "",
            "| Method | Macro-F1 | Balanced Acc | Accuracy | Min recall | ODER |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in bundle["gold_main"]:
        lines.append(
            f"| {row['method']} | {_fmt(row['macro_f1'])} | "
            f"{_fmt(row['balanced_accuracy'])} | {_fmt(row['accuracy'])} | "
            f"{_fmt(row['min_class_recall'])} | "
            f"{_fmt(row['opposite_direction_error_rate'])} |"
        )
    return "\n".join(lines) + "\n"
