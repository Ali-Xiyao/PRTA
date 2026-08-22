from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.provenance import resolve_source_commit

MODES = ("uncalibrated", "cross_fitted_calibrated")


def _validate(report: Mapping[str, Any]) -> None:
    if report.get("schema") != "prta-cxr.calibration-joint-cells.v1":
        raise ValueError("unsupported calibration/joint-cell evidence schema")
    if report.get("status") != "PASS_CALIBRATION_JOINT_CELLS_COMPLETE":
        raise ValueError("calibration/joint-cell evidence is not terminal PASS")
    privacy = report.get("privacy", {})
    if (
        privacy.get("aggregate_only") is not True
        or privacy.get("patient_identifiers_published") is not False
        or privacy.get("patient_level_predictions_published") is not False
    ):
        raise ValueError("calibration/joint-cell evidence privacy contract failed")
    if tuple(report.get("seeds", ())) != (17, 28, 43):
        raise ValueError("calibration/joint-cell evidence seed contract failed")


def reliability_plot_series(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    _validate(report)
    output: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        points = []
        for cell in report["calibration_bins"][mode]["fixed_width"]:
            accuracy = cell["accuracy"]
            confidence = cell["confidence"]
            if (
                float(cell["count_mean"]) <= 0
                or accuracy["mean"] is None
                or confidence["mean"] is None
            ):
                continue
            points.append(
                {
                    "bin_index": int(cell["bin_index"]),
                    "confidence": float(confidence["mean"]),
                    "accuracy": float(accuracy["mean"]),
                    "accuracy_sd": (
                        None
                        if accuracy["sd"] is None
                        else float(accuracy["sd"])
                    ),
                    "count_mean": float(cell["count_mean"]),
                }
            )
        output[mode] = {"points": points}
    return output


def joint_recall_matrix(
    report: Mapping[str, Any],
) -> tuple[list[str], list[str], np.ndarray, np.ndarray]:
    _validate(report)
    joint = report["finding_progression"]
    findings = [str(value) for value in joint["findings"]]
    labels = [str(value) for value in joint["progression_labels"]]
    if labels != list(PROGRESSION_LABELS):
        raise ValueError("joint-cell progression label order drift")
    matrix = np.full((len(findings), len(labels)), np.nan, dtype=float)
    counts = np.zeros_like(matrix, dtype=int)
    finding_index = {value: index for index, value in enumerate(findings)}
    label_index = {value: index for index, value in enumerate(labels)}
    for cell in joint["cells"]:
        row = finding_index[str(cell["finding"])]
        column = label_index[str(cell["progression_label"])]
        counts[row, column] = int(cell["rows"])
        if not bool(cell["suppressed"]):
            matrix[row, column] = float(cell["recall"]["mean"])
    if int(np.isfinite(matrix).sum()) + int(np.isnan(matrix).sum()) != matrix.size:
        raise ValueError("joint-cell matrix contains invalid values")
    return findings, labels, matrix, counts


def _pyplot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _save(fig: Any, output: Path, stem: str) -> list[Path]:
    plt = _pyplot()
    paths = []
    for suffix in ("png", "svg"):
        path = output / f"{stem}.{suffix}"
        fig.savefig(path, dpi=220, bbox_inches="tight")
        if suffix == "svg":
            _normalize_svg(path)
        paths.append(path)
    plt.close(fig)
    return paths


def _normalize_svg(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(
        "\n".join(line.rstrip() for line in lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def plot_aggregate_figures(
    report: Mapping[str, Any],
    output: Path,
    *,
    minimum_reliability_count_mean: float = 20.0,
) -> list[Path]:
    _validate(report)
    if minimum_reliability_count_mean < 1:
        raise ValueError("minimum reliability count must be positive")
    plt = _pyplot()
    series = reliability_plot_series(report)
    fig, axis = plt.subplots(figsize=(6.0, 5.2))
    axis.plot([0, 1], [0, 1], linestyle="--", color="#64748b", label="Ideal")
    styles = {
        "uncalibrated": ("Uncalibrated", "#dc2626", "o"),
        "cross_fitted_calibrated": (
            "Cross-fitted calibrated",
            "#2563eb",
            "s",
        ),
    }
    for mode in MODES:
        label, color, marker = styles[mode]
        points = [
            point
            for point in series[mode]["points"]
            if point["count_mean"] >= minimum_reliability_count_mean
        ]
        x = [point["confidence"] for point in points]
        y = [point["accuracy"] for point in points]
        yerr = [point["accuracy_sd"] or 0.0 for point in points]
        axis.errorbar(
            x,
            y,
            yerr=yerr,
            marker=marker,
            markersize=4,
            linewidth=1.5,
            capsize=2,
            color=color,
            label=label,
        )
    axis.set(
        xlim=(0, 1),
        ylim=(0, 1),
        xlabel="Mean confidence",
        ylabel="Empirical accuracy",
        title="PRTA-CXR reliability (three-seed bins)",
    )
    axis.legend(frameon=False)
    paths = _save(fig, output, "PRTA_CXR_reliability_curve")

    findings, labels, matrix, counts = joint_recall_matrix(report)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad(color="#e5e7eb")
    fig, axis = plt.subplots(figsize=(8.6, max(5.4, len(findings) * 0.42)))
    image = axis.imshow(matrix, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    axis.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
    axis.set_yticks(range(len(findings)), findings)
    axis.set_title("PRTA-CXR finding × progression recall")
    for row in range(len(findings)):
        for column in range(len(labels)):
            value = matrix[row, column]
            text = "—" if np.isnan(value) else f"{value:.2f}"
            color = "#111827" if np.isnan(value) or value > 0.62 else "white"
            axis.text(column, row, text, ha="center", va="center", color=color)
    fig.colorbar(image, ax=axis, label="Recall; gray = suppressed")
    paths.extend(_save(fig, output, "PRTA_CXR_finding_progression_heatmap"))
    return paths


def aggregate_figures_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plot PRTA-CXR aggregate calibration and joint-cell evidence"
    )
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--minimum-reliability-count-mean", type=float, default=20.0
    )
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    report = json.loads(args.evidence.read_text(encoding="utf-8"))
    _validate(report)
    args.output.mkdir(parents=True, exist_ok=False)
    paths = plot_aggregate_figures(
        report,
        args.output,
        minimum_reliability_count_mean=args.minimum_reliability_count_mean,
    )
    manifest = {
        "schema": "prta-cxr.aggregate-evidence-figures.v1",
        "status": "PASS_AGGREGATE_EVIDENCE_FIGURES_COMPLETE",
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "evidence_sha256": sha256_file(args.evidence),
        "aggregate_only": True,
        "minimum_reliability_count_mean": (
            args.minimum_reliability_count_mean
        ),
        "figures": {
            path.name: sha256_file(path)
            for path in paths
        },
    }
    manifest_path = args.output / "aggregate_figure_manifest.json"
    write_json_atomic(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0
