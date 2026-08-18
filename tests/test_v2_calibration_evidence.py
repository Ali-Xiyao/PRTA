import json

import numpy as np

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.v2_calibration_evidence import (
    _load_probability_receipt,
    _selective_classification,
    _three_seed_disagreement,
    _uncertainty_summary,
    cross_fitted_temperature_probabilities,
)


def _rows(intervention: str):
    rows = []
    for index in range(25):
        target = index % len(PROGRESSION_LABELS)
        logits = np.full(len(PROGRESSION_LABELS), -1.0)
        logits[target] = 2.0
        if intervention == "reversed" and index % 3 == 0:
            logits[target] = -2.0
            logits[(target + 1) % len(PROGRESSION_LABELS)] = 2.0
        probabilities = np.exp(logits - logits.max())
        probabilities /= probabilities.sum()
        rows.append(
            {
                "patient_id": f"patient-{index // 2}",
                "observation_id": f"sample-{index}",
                "target": PROGRESSION_LABELS[target],
                "prediction": PROGRESSION_LABELS[int(probabilities.argmax())],
                "logits": logits.tolist(),
                "probabilities": probabilities.tolist(),
            }
        )
    return rows


def test_cross_fitted_temperature_is_patient_disjoint_and_aligned():
    blocks = {
        intervention: _rows(intervention)
        for intervention in ("true", "matched_hard", "null", "reversed")
    }
    result = cross_fitted_temperature_probabilities(blocks)
    assert len(result["temperatures"]) == 5
    assert sum(item["held_out_rows"] for item in result["fold_audit"]) == 25
    assert set(result["probabilities"]) == set(blocks)
    for probabilities in result["probabilities"].values():
        assert probabilities.shape == (25, 5)
        assert np.allclose(probabilities.sum(axis=1), 1.0)


def test_selective_classification_reports_fixed_coverages_and_classes():
    probabilities = np.eye(5)[np.arange(25) % 5] * 0.8 + 0.04
    targets = np.arange(25) % 5
    uncertainty = np.linspace(0.0, 1.0, 25)
    result = _selective_classification(probabilities, targets, uncertainty)
    assert set(result) == {"1.0", "0.95", "0.9", "0.8", "0.7"}
    assert result["1.0"]["metrics"]["accuracy"] == 1.0
    assert set(result["0.7"]["class_coverage"]) == set(PROGRESSION_LABELS)


def test_three_seed_disagreement_detects_seed_variation():
    targets = np.arange(25) % 5
    base = np.eye(5)[targets] * 0.8 + 0.04
    changed = base.copy()
    changed[0] = np.roll(changed[0], 1)
    result = _three_seed_disagreement([base, base, changed], targets)
    assert result["evaluated"] is True
    assert result["score_summary"]["mean_pairwise_total_variation"]["mean"] > 0
    assert result["score_summary"]["vote_disagreement"]["mean"] > 0


def test_true_only_comparator_calibration_does_not_invent_prior_scores():
    blocks = {"true": _rows("true")}
    cross_fitted = cross_fitted_temperature_probabilities(blocks)
    assert set(cross_fitted["probabilities"]) == {"true"}
    summary = _uncertainty_summary(
        cross_fitted["probabilities"], cross_fitted["targets"]
    )
    assert summary["prior_stress_scores_evaluated"] is False
    assert set(summary["score_definitions"]) == {
        "msp_uncertainty",
        "normalized_entropy",
    }


def test_phase20_s1_probability_receipt_contract(tmp_path):
    rows = _rows("true")
    block = tmp_path / "true.predictions.jsonl"
    block.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    receipt = {
        "schema": "prta-cxr.phase20-s1-dev-probability-diagnostic.v1",
        "status": "PASS_PHASE20_S1_DEV_PROBABILITY_EXPORT",
        "variant": "Slim-S1",
        "seed": 17,
        "probability_export": True,
        "internal_test_opened": False,
        "protected_outcome_read_count": 0,
        "evaluation_interventions": ["true"],
        "prediction_blocks": {
            "true": {
                "path": block.name,
                "sha256": sha256_file(block),
                "rows": len(rows),
            }
        },
    }
    path = tmp_path / "candidate_probability_diagnostic_receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    loaded, blocks = _load_probability_receipt(path, expected_system="Slim-S1")
    assert loaded["variant"] == "Slim-S1"
    assert len(blocks["true"]) == len(rows)
