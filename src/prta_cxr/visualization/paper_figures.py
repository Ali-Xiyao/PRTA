from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file

METHOD_NAMES = {
    "B401": "Current-only",
    "B402": "Siamese Diff",
    "B403": "TILA",
    "B404": "PRTA-CXR",
}


def _pyplot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _save(fig, output: Path, figure_id: str) -> list[Path]:
    paths = []
    for suffix in ("png", "svg"):
        path = output / f"{figure_id}.{suffix}"
        fig.savefig(path, dpi=220, bbox_inches="tight")
        paths.append(path)
    _pyplot().close(fig)
    return paths


def _patient_weighted_confusion(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    labels = tuple(PROGRESSION_LABELS)
    index = {label: offset for offset, label in enumerate(labels)}
    sizes = Counter(str(row["patient_id"]) for row in rows)
    matrix = np.zeros((len(labels), len(labels)), dtype=float)
    for row in rows:
        patient = str(row["patient_id"])
        matrix[index[str(row["target"])]][index[str(row["prediction"])]] += (
            1.0 / sizes[patient]
        )
    return matrix


def _hash_rank(sample_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}|{sample_id}".encode()).hexdigest()


def select_case_buckets(
    true_rows: Sequence[Mapping[str, Any]],
    matched_rows: Sequence[Mapping[str, Any]],
    wrong_query_rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    cases_per_bucket: int,
) -> dict[str, list[dict[str, Any]]]:
    matched = {str(row["observation_id"]): row for row in matched_rows}
    wrong_query = {str(row["observation_id"]): row for row in wrong_query_rows}
    if set(matched) != {str(row["observation_id"]) for row in true_rows}:
        raise ValueError("matched-prior case layout differs from true PRIOR")
    if set(wrong_query) != set(matched):
        raise ValueError("wrong-query case layout differs from true PRIOR")
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in true_rows:
        sample_id = str(row["observation_id"])
        alt = matched[sample_id]
        query = wrong_query[sample_id]
        correct = row["prediction"] == row["target"]
        alt_correct = alt["prediction"] == alt["target"]
        payload = {
            "observation_id": sample_id,
            "finding": str(row["finding"]),
            "target": str(row["target"]),
            "true_prediction": str(row["prediction"]),
            "true_confidence": float(row["confidence"]),
            "true_probabilities": list(row["probabilities"]),
            "matched_wrong_prediction": str(alt["prediction"]),
            "wrong_query_prediction": str(query["prediction"]),
            "selection_rank": _hash_rank(sample_id, seed),
        }
        if correct and float(row["confidence"]) >= 0.8:
            buckets["correct_high_confidence"].append(payload)
        if not correct and float(row["confidence"]) >= 0.8:
            buckets["wrong_high_confidence"].append(payload)
        if correct and not alt_correct:
            buckets["true_to_wrong_after_matched_prior"].append(payload)
        if not correct and alt_correct:
            buckets["wrong_to_correct_after_matched_prior"].append(payload)
        if row["prediction"] != query["prediction"]:
            buckets["prediction_flip_after_wrong_query"].append(payload)
    expected = (
        "correct_high_confidence",
        "wrong_high_confidence",
        "true_to_wrong_after_matched_prior",
        "wrong_to_correct_after_matched_prior",
        "prediction_flip_after_wrong_query",
    )
    selected = {}
    for name in expected:
        candidates = sorted(buckets[name], key=lambda value: value["selection_rank"])
        selected[name] = candidates[:cases_per_bucket]
    return selected


def make_pipeline_figure(output: Path) -> list[Path]:
    plt = _pyplot()
    fig, axis = plt.subplots(figsize=(12, 3.2))
    axis.set_axis_off()
    labels = (
        "Paired CXR\nPRIOR + CURRENT",
        "Luna-primary Silver\nUnclear discarded",
        "Frozen Block-8\nvisual tokens",
        "PRTA\nstate + transition",
        "5-way progression\ntrust audits",
    )
    xs = np.linspace(0.08, 0.92, len(labels))
    colors = ("#dbeafe", "#dcfce7", "#fef3c7", "#ede9fe", "#fee2e2")
    for offset, (x, label, color) in enumerate(zip(xs, labels, colors, strict=True)):
        axis.text(
            x,
            0.52,
            label,
            ha="center",
            va="center",
            fontsize=10,
            bbox={"boxstyle": "round,pad=0.7", "fc": color, "ec": "#334155"},
        )
        if offset:
            axis.annotate(
                "",
                xy=(x - 0.09, 0.52),
                xytext=(xs[offset - 1] + 0.09, 0.52),
                arrowprops={"arrowstyle": "->", "lw": 1.8, "color": "#475569"},
            )
    axis.set_title("PRTA-CXR formal pipeline", fontsize=15, weight="bold")
    return _save(fig, output, "V701_figure1_pipeline")


def make_data_figure(
    rows: Sequence[Mapping[str, Any]], quality: Mapping[str, Any], output: Path
) -> list[Path]:
    plt = _pyplot()
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    split_counts = Counter(str(row["split"]) for row in rows)
    source_counts = Counter(str(row["source"]) for row in rows)
    label_counts = Counter(str(row["progression_label"]) for row in rows)
    axes[0].bar(split_counts.keys(), split_counts.values(), color="#2563eb")
    axes[0].set_title("Final rows by split")
    axes[0].tick_params(axis="x", rotation=20)
    axes[1].bar(source_counts.keys(), source_counts.values(), color="#16a34a")
    axes[1].set_title("Final rows by source")
    axes[1].tick_params(axis="x", rotation=20)
    axes[2].bar(label_counts.keys(), label_counts.values(), color="#7c3aed")
    axes[2].set_title("Progression class distribution")
    axes[2].tick_params(axis="x", rotation=35)
    agreement = quality.get("overall_agreement", quality.get("overall", "N/A"))
    fig.suptitle(f"Data construction audit (clinician agreement: {agreement})")
    return _save(fig, output, "V702_figure2_data")


def make_scaling_figure(
    scaling: Sequence[Mapping[str, Any]], output: Path
) -> list[Path]:
    plt = _pyplot()
    ordered = sorted(scaling, key=lambda row: float(row["fraction"]))
    fig, axis = plt.subplots(figsize=(6.8, 4.2))
    axis.plot(
        [100 * float(row["fraction"]) for row in ordered],
        [float(row["macro_f1"]) for row in ordered],
        marker="o",
        linewidth=2,
        color="#7c3aed",
    )
    axis.set(xlabel="Training patients (%)", ylabel="Dev Macro-F1")
    axis.set_title("Luna-primary Silver scaling")
    axis.grid(alpha=0.25)
    return _save(fig, output, "V703_figure3_scaling")


def make_forest_figure(trust: Mapping[str, Any], output: Path) -> list[Path]:
    plt = _pyplot()
    contrasts = trust["bootstrap"]["main_methods"]["contrasts"]
    rows = []
    for name, values in contrasts.items():
        interval = values["interval"]
        if interval is None:
            raise ValueError(f"invalid bootstrap interval: {name}")
        rows.append(
            (
                name,
                values["point_pp"],
                100 * interval["lower"],
                100 * interval["upper"],
            )
        )
    fig, axis = plt.subplots(figsize=(7.5, 4.2))
    y = np.arange(len(rows))
    points = np.asarray([row[1] for row in rows])
    lower = points - np.asarray([row[2] for row in rows])
    upper = np.asarray([row[3] for row in rows]) - points
    axis.errorbar(points, y, xerr=[lower, upper], fmt="o", color="#7c3aed", capsize=4)
    axis.axvline(0, color="#64748b", linestyle="--")
    axis.set_yticks(y, [row[0].replace("B404_minus_", "PRTA - ") for row in rows])
    axis.set_xlabel("Paired Macro-F1 difference (percentage points)")
    axis.set_title("PRTA-CXR paired effects with 95% bootstrap CI")
    return _save(fig, output, "V704_figure4_forest")


def make_confusion_figure(
    rows: Sequence[Mapping[str, Any]], output: Path
) -> list[Path]:
    plt = _pyplot()
    matrix = _patient_weighted_confusion(rows)
    normalized = matrix / np.maximum(matrix.sum(axis=1, keepdims=True), 1e-12)
    fig, axis = plt.subplots(figsize=(6.2, 5.2))
    image = axis.imshow(normalized, vmin=0, vmax=1, cmap="Blues")
    for row in range(5):
        for column in range(5):
            axis.text(
                column,
                row,
                f"{normalized[row, column]:.2f}",
                ha="center",
                va="center",
            )
    axis.set_xticks(range(5), PROGRESSION_LABELS, rotation=35, ha="right")
    axis.set_yticks(range(5), PROGRESSION_LABELS)
    axis.set(xlabel="Predicted", ylabel="Reference", title="PRTA-CXR confusion matrix")
    fig.colorbar(image, ax=axis, label="Row-normalized patient weight")
    return _save(fig, output, "V705_figure5_confusion")


def make_heatmap_figure(
    rows: Sequence[Mapping[str, Any]], output: Path
) -> list[Path]:
    plt = _pyplot()
    findings = sorted({str(row["finding"]) for row in rows})
    numerator = np.zeros((len(findings), 5), dtype=float)
    denominator = np.zeros_like(numerator)
    finding_index = {value: offset for offset, value in enumerate(findings)}
    label_index = {value: offset for offset, value in enumerate(PROGRESSION_LABELS)}
    for row in rows:
        i = finding_index[str(row["finding"])]
        j = label_index[str(row["target"])]
        denominator[i, j] += 1
        numerator[i, j] += row["prediction"] == row["target"]
    recall = np.divide(
        numerator,
        denominator,
        out=np.full_like(numerator, np.nan),
        where=denominator > 0,
    )
    fig, axis = plt.subplots(figsize=(8.2, max(4.5, len(findings) * 0.35)))
    image = axis.imshow(recall, vmin=0, vmax=1, cmap="viridis", aspect="auto")
    axis.set_xticks(range(5), PROGRESSION_LABELS, rotation=35, ha="right")
    axis.set_yticks(range(len(findings)), findings)
    axis.set_title("Finding × progression recall")
    fig.colorbar(image, ax=axis, label="Recall")
    return _save(fig, output, "V706_figure6_heatmap")


def make_calibration_figure(
    rows: Sequence[Mapping[str, Any]], output: Path
) -> list[Path]:
    plt = _pyplot()
    confidence = np.asarray([float(row["confidence"]) for row in rows])
    correct = np.asarray(
        [row["prediction"] == row["target"] for row in rows], dtype=float
    )
    bins = np.linspace(0, 1, 16)
    centers = []
    accuracy = []
    for left, right in zip(bins[:-1], bins[1:], strict=True):
        upper = confidence < right if right < 1 else confidence <= right
        mask = (confidence >= left) & upper
        if mask.any():
            centers.append(float(confidence[mask].mean()))
            accuracy.append(float(correct[mask].mean()))
    order = np.argsort(-confidence)
    risk = 1 - np.cumsum(correct[order]) / np.arange(1, len(rows) + 1)
    coverage = np.arange(1, len(rows) + 1) / len(rows)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    axes[0].plot([0, 1], [0, 1], linestyle="--", color="#64748b")
    axes[0].plot(centers, accuracy, marker="o", color="#2563eb")
    axes[0].set(xlabel="Confidence", ylabel="Accuracy", title="Reliability")
    axes[1].plot(coverage, risk, color="#dc2626")
    axes[1].set(xlabel="Coverage", ylabel="Risk", title="Risk–coverage")
    return _save(fig, output, "V707_figure7_calibration")


def make_case_figure(
    selected: Mapping[str, Sequence[Mapping[str, Any]]], output: Path
) -> list[Path]:
    plt = _pyplot()
    fig, axes = plt.subplots(len(selected), 1, figsize=(12, 2.0 * len(selected)))
    for axis, (bucket, cases) in zip(axes, selected.items(), strict=True):
        axis.set_axis_off()
        if not cases:
            text = "No eligible case under the frozen rule"
        else:
            row = cases[0]
            text = (
                f"Finding: {row['finding']} | Reference: {row['target']} | "
                f"True PRIOR: {row['true_prediction']} "
                f"({row['true_confidence']:.2f}) | "
                f"Matched-wrong: {row['matched_wrong_prediction']} | "
                f"Wrong query: {row['wrong_query_prediction']}"
            )
        axis.text(0.01, 0.5, text, va="center", fontsize=10)
        axis.set_title(bucket.replace("_", " "), loc="left", weight="bold")
    fig.suptitle("Frozen PRIOR/query case audit (success and failure)", weight="bold")
    return _save(fig, output, "V708_figure8_cases")


def build_figure_manifest(
    paths: Sequence[Path], *, inputs: Mapping[str, Path], case_counts: Mapping[str, int]
) -> dict[str, Any]:
    return {
        "schema": "prta-cxr.paper-figures.v1",
        "status": "PASS_PAPER_FIGURES_FINISHED",
        "figures": [
            {"path": str(path.resolve()), "sha256": sha256_file(path)} for path in paths
        ],
        "inputs": {
            key: {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for key, path in inputs.items()
        },
        "case_counts": dict(case_counts),
        "attention_maps_claimed": False,
        "manual_case_cherry_pick": False,
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
