import torch

from prta_cxr.modality_stress import (
    FINDING_CONDITIONS,
    RANDOM_FINDING_CONDITIONS,
    _finding_transform,
    _predict,
    compare_condition_rows,
    validate_modality_checkpoint_config,
)
from prta_cxr.prta_v2_diagnostics import (
    _experiment_identity_matches,
    _probability_export_allowed,
    _resolve_diagnostic_variant,
)


class _ProjectedQueryProbe:
    def __init__(self):
        self.force_zero = None

    def eval(self):
        return self

    def __call__(self, prior, current, finding, *, force_zero_projected_query=False):
        self.force_zero = force_zero_projected_query
        logits = torch.tensor([[1.0, 0.0, 0.0, 0.0, 0.0]])
        return None, logits, torch.zeros(1, 3)


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


def test_finding_stress_separates_zero_embedding_from_zero_projected_query():
    assert "F1_zero_text_embedding" in FINDING_CONDITIONS
    assert "F1b_zero_projected_query" in FINDING_CONDITIONS
    transform = _finding_transform(
        "F1_zero_text_embedding",
        base_embeddings={"A": torch.ones(512), "B": torch.zeros(512)},
        intervention_embeddings={},
    )
    assert torch.equal(
        transform({"finding": ["A"], "sample_id": ["x"]}, torch.ones(1, 512)),
        torch.zeros(1, 512),
    )
    model = _ProjectedQueryProbe()
    loader = [
        {
            "prior": torch.zeros(1, 2, 3),
            "current": torch.zeros(1, 2, 3),
            "finding_text": torch.ones(1, 512),
            "sample_id": ["sample"],
            "patient_id_hash": ["patient"],
            "target": torch.tensor([0]),
            "source": ["source"],
            "finding": ["A"],
            "special_prior_available": [False],
            "special_prior_sample_id": [""],
        }
    ]
    _predict(
        model,
        loader,
        device=torch.device("cpu"),
        force_zero_projected_query=True,
    )
    assert model.force_zero is True


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


def test_phase20_b2_diagnostic_scope_accepts_rebuild_and_f02_only():
    config = {
        "experiment_id": "P20-REBUILD-CheXRelNet-S28",
        "phase20_role": "CheXRelNet",
    }
    variant, allowed, _ = _resolve_diagnostic_variant(config, "phase20_b2")
    assert variant == "CheXRelNet"
    assert variant in allowed
    assert _experiment_identity_matches(
        config["experiment_id"], diagnostic_scope="phase20_b2", variant=variant
    )
    assert _probability_export_allowed("phase20_b2", variant)
    f02 = {"experiment_id": "P20-F02-DMW0-S43", "phase20_role": "ignored"}
    variant, allowed, _ = _resolve_diagnostic_variant(f02, "phase20_b2")
    assert variant == "F02-DMW0"
    assert variant in allowed
