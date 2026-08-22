import copy

import numpy as np
import torch

from prta_cxr.attention_flow import (
    EXPECTED_SEEDS,
    _private_to_public_case,
    capture_true_attention,
    patch_attention_flow,
    salted_sample_hash,
    select_attention_candidates,
    shared_attention_clip,
    strongest_routes,
)
from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.models.prta import PRTATemporalAdapter


def _rows(seed: int):
    rows = []
    labels = ("Improved", "Worse")
    for label in labels:
        label_index = PROGRESSION_LABELS.index(label)
        for index in range(125):
            probabilities = np.full(5, 0.01)
            probability = 0.55 + index / 1000
            probabilities[label_index] = probability
            probabilities[(label_index + 1) % 5] += 1.0 - probabilities.sum()
            rows.append(
                {
                    "observation_id": f"{label}-{index:03d}",
                    "patient_id": f"patient-{label}-{index:03d}",
                    "finding": "Pleural Effusion",
                    "target": label,
                    "prediction": label,
                    "probabilities": probabilities.tolist(),
                    "confidence": float(probabilities[label_index]),
                    "source": "mimic_cxr_jpg",
                    "interval_basis": "calendar",
                    "interval_days": 10.0,
                    "prior_view": "AP",
                    "current_view": "AP",
                    "training_seed": seed,
                }
            )
    return rows


def test_preselection_is_deterministic_and_preview_safe():
    blocks = [(seed, _rows(seed)) for seed in EXPECTED_SEEDS]
    first = select_attention_candidates(blocks)
    second = select_attention_candidates(copy.deepcopy(blocks))
    assert first == second
    assert first["selection_performed_before_image_or_attention_view"] is True
    assert first["images_opened"] is False
    assert first["attention_opened"] is False
    assert set(first["selected"]) == {"improvement", "worsening"}
    for row in first["selected"].values():
        assert row["cell_support"] == 125
        assert row["sample_hash"] == salted_sample_hash(row["sample_id"])


def test_preselection_rejects_non_unanimous_predictions():
    blocks = [(seed, _rows(seed)) for seed in EXPECTED_SEEDS]
    blocks[1][1][0]["prediction"] = "Stable"
    result = select_attention_candidates(blocks)
    rejected_id = blocks[1][1][0]["observation_id"]
    all_hashes = sum(result["ordered_candidate_hashes"].values(), [])
    assert salted_sample_hash(rejected_id) not in all_hashes


def test_preselection_rejects_cohort_drift():
    blocks = [(seed, _rows(seed)) for seed in EXPECTED_SEEDS]
    blocks[1][1][0]["finding"] = "Edema"
    try:
        select_attention_candidates(blocks)
    except ValueError as error:
        assert "identity drift" in str(error)
    else:
        raise AssertionError("cohort identity drift was not rejected")


def test_patch_flow_removes_cls_and_renormalizes():
    rng = np.random.default_rng(17)
    align = rng.random((12, 197, 197))
    align /= align.sum(axis=-1, keepdims=True)
    transition = rng.random((12, 20, 197))
    transition /= transition.sum(axis=-1, keepdims=True)
    flow = patch_attention_flow(align, transition)
    assert flow["A_bar"].shape == (196, 196)
    assert np.allclose(flow["A_bar"].sum(axis=-1), 1.0)
    assert np.isclose(flow["r_current"].sum(), 1.0)
    assert np.isclose(flow["r_prior"].sum(), 1.0)
    assert np.allclose(
        flow["edge"], flow["r_current"][:, None] * flow["A_bar"]
    )


def test_route_nms_limits_and_separates_both_endpoints():
    edge = np.zeros((196, 196))
    edge[0, 0] = 1.0
    edge[1, 14] = 0.9
    edge[30, 40] = 0.8
    edge[60, 80] = 0.7
    routes = strongest_routes(edge, maximum_routes=3)
    assert len(routes) == 3
    assert routes[0]["current_patch"] == 0
    assert routes[1]["current_patch"] == 30
    assert routes[2]["current_patch"] == 60


def test_shared_clip_uses_all_cases_and_maps():
    flows = [
        {"r_prior": np.array([0.1, 0.2]), "r_current": np.array([0.3, 0.4])},
        {"r_prior": np.array([0.5, 0.6]), "r_current": np.array([0.7, 0.8])},
    ]
    expected = np.quantile(np.arange(1, 9) / 10, 0.99)
    assert np.isclose(shared_attention_clip(flows), expected)


class _TinyTrainModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.adapter = PRTATemporalAdapter(
            [torch.nn.Identity() for _ in range(4)],
            width=24,
            heads=12,
            adapter_rank=4,
            state_tokens=20,
            transition_tokens=20,
            dropout=0.0,
        )
        self.head = torch.nn.Linear(24, 5)

    def forward(self, prior, current, finding_text):
        output = self.adapter(prior, current, finding_text)
        logits = self.head(output.transition_embedding)
        return output, logits, finding_text


def test_true_attention_capture_uses_per_head_weights_and_exact_replay():
    torch.manual_seed(43)
    model = _TinyTrainModel()
    logits, align, transition = capture_true_attention(
        model,
        prior=torch.randn(1, 197, 24),
        current=torch.randn(1, 197, 24),
        finding_text=torch.randn(1, 24),
    )
    assert logits.shape == (1, 5)
    assert align.shape == (1, 12, 197, 197)
    assert transition.shape == (1, 12, 20, 197)


def test_public_case_rejects_private_fields():
    try:
        _private_to_public_case(
            {"sample_hash": "abc", "prior_image_path": "private.jpg"},
            tensor_sha256="def",
        )
    except ValueError as error:
        assert "private fields" in str(error)
    else:
        raise AssertionError("private path was accepted for public export")
