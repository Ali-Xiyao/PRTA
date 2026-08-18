import torch

from prta_cxr.modality_stress import (
    RANDOM_FINDING_CONDITIONS,
    _finding_transform,
    compare_condition_rows,
    validate_modality_checkpoint_config,
)


def _row(sample, probabilities):
    prediction = ("Stable", "Improved")[probabilities[1] > probabilities[0]]
    return {
        "observation_id": sample,
        "target": "Stable",
        "prediction": prediction,
        "probabilities": probabilities,
    }


def test_modality_comparison_detects_flip_and_probability_drop():
    baseline = [_row("a", [0.9, 0.1, 0, 0, 0])]
    stressed = [_row("a", [0.2, 0.8, 0, 0, 0])]
    result = compare_condition_rows(baseline, stressed)
    assert result["prediction_flip_count"] == 1
    assert result["mean_true_label_probability_drop"] > 0
    assert result["mean_js_divergence"] > 0


def test_random_finding_is_sample_level_and_uses_three_frozen_salts():
    base = {
        "A": torch.full((512,), 1.0),
        "B": torch.full((512,), 2.0),
        "C": torch.full((512,), 3.0),
    }
    batch = {
        "finding": ["A"] * 40,
        "sample_id": [f"sample-{index}" for index in range(40)],
    }
    outputs = []
    for condition in RANDOM_FINDING_CONDITIONS:
        transform = _finding_transform(
            condition,
            base_embeddings=base,
            intervention_embeddings={},
        )
        first = transform(batch, torch.zeros(40, 512))
        second = transform(batch, torch.zeros(40, 512))
        assert torch.equal(first, second)
        assert not torch.any(first[:, 0].eq(1.0))
        assert len(set(first[:, 0].tolist())) > 1
        outputs.append(first)
    assert any(not torch.equal(outputs[0], value) for value in outputs[1:])


def test_modality_stress_accepts_only_frozen_phase20_final_s1():
    config = {
        "experiment_id": "P20-FINAL-S1-S28",
        "prta_v2_variant": "Slim-S1",
        "phase20_protocol": "full-train-official-dev-slim-s1-confirmation-v1",
        "phase20_axis": "final_mainline_confirmation",
    }
    assert validate_modality_checkpoint_config(config) == "Slim-S1"
    config["experiment_id"] = "P20-ABL-NOSTATE-S28"
    try:
        validate_modality_checkpoint_config(config)
    except ValueError as error:
        assert "frozen V2 or Phase20 Slim-S1" in str(error)
    else:
        raise AssertionError("a Phase20 ablation cannot enter final-S1 modality stress")
