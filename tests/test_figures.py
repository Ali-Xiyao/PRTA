from prta_cxr.visualization.paper_figures import (
    make_pipeline_figure,
    select_case_buckets,
)


def _row(sample, target, prediction, confidence, *, intervention="true"):
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    probabilities = [0.025] * 5
    probabilities[labels.index(prediction)] = confidence
    return {
        "observation_id": sample,
        "patient_id": f"patient-{sample}",
        "finding": "edema",
        "target": target,
        "prediction": prediction,
        "confidence": confidence,
        "probabilities": probabilities,
        "prior_intervention": intervention,
    }


def test_case_selection_is_deterministic_and_includes_failure_buckets():
    true = [
        _row("a", "Stable", "Stable", 0.9),
        _row("b", "Worse", "Stable", 0.9),
        _row("c", "New", "New", 0.9),
    ]
    matched = [
        _row("a", "Stable", "Worse", 0.8, intervention="matched_wrong"),
        _row("b", "Worse", "Worse", 0.8, intervention="matched_wrong"),
        _row("c", "New", "New", 0.8, intervention="matched_wrong"),
    ]
    query = [
        _row("a", "Stable", "Improved", 0.8),
        _row("b", "Worse", "Stable", 0.8),
        _row("c", "New", "New", 0.8),
    ]
    first = select_case_buckets(true, matched, query, seed=11, cases_per_bucket=5)
    second = select_case_buckets(true, matched, query, seed=11, cases_per_bucket=5)
    assert first == second
    assert first["wrong_high_confidence"][0]["observation_id"] == "b"
    assert first["true_to_wrong_after_matched_prior"][0]["observation_id"] == "a"
    assert first["wrong_to_correct_after_matched_prior"][0]["observation_id"] == "b"


def test_pipeline_figure_writes_png_and_svg(tmp_path):
    paths = make_pipeline_figure(tmp_path)
    assert {path.suffix for path in paths} == {".png", ".svg"}
    assert all(path.stat().st_size > 100 for path in paths)
