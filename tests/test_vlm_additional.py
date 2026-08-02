from types import SimpleNamespace

import torch
from torch import nn

from prta_cxr.models.prta import PRTAOutput
from prta_cxr.vlm.additional import select_vlm_training_rows
from prta_cxr.vlm.fixed64 import pack_prta_fixed64
from prta_cxr.vlm.frozen_qwen import (
    FrozenQwenProgressionScorer,
    build_prompt_ids,
)
from prta_cxr.vlm.projector import Fixed64Projector


class _Tokenizer:
    labels = {
        "stable": [10],
        "improved": [11],
        "worse": [12],
        "new": [13],
        "resolved": [14],
    }

    def __call__(self, text, *, add_special_tokens):
        del add_special_tokens
        return {"input_ids": self.labels.get(text, [1, 2])}


class _CausalModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding = nn.Embedding(200, 8)
        self.head = nn.Linear(8, 200, bias=False)

    def get_input_embeddings(self):
        return self.embedding

    def forward(self, *, inputs_embeds, **kwargs):
        del kwargs
        return SimpleNamespace(logits=self.head(inputs_embeds))


def test_fixed64_packer_has_exact_layout_and_reserved_nulls():
    output = PRTAOutput(
        state_tokens=torch.randn(2, 20, 8),
        transition_tokens=torch.randn(2, 20, 8),
        state_embedding=torch.randn(2, 8),
        transition_embedding=torch.randn(2, 8),
        aligned_prior_tokens=torch.randn(2, 197, 8),
        frozen_current_embedding=torch.randn(2, 8),
    )
    bundle = pack_prta_fixed64(output, torch.randn(2, 8))
    assert bundle.tokens.shape == (2, 64, 8)
    assert bundle.logical_validity[:, :60].all()
    assert not bundle.logical_validity[:, 60:].any()
    assert bundle.tokens[:, 60:].eq(0).all()


def test_frozen_vlm_scores_five_labels_and_backpropagates_to_projector():
    tokenizer = _Tokenizer()
    scorer = FrozenQwenProgressionScorer(
        _CausalModel(), tokenizer, placeholder_token_id=199
    )
    projector = Fixed64Projector(input_width=8, hidden_size=8)
    output = PRTAOutput(
        state_tokens=torch.randn(1, 20, 8),
        transition_tokens=torch.randn(1, 20, 8),
        state_embedding=torch.randn(1, 8),
        transition_embedding=torch.randn(1, 8),
        aligned_prior_tokens=torch.randn(1, 197, 8),
        frozen_current_embedding=torch.randn(1, 8),
    )
    projected = projector(pack_prta_fixed64(output, torch.randn(1, 8)))
    prompt = build_prompt_ids(
        tokenizer, finding="edema", placeholder_token_id=199
    )
    scores = scorer.score(prompt, projected)
    scores.sum().backward()
    assert scores.shape == (5,)
    assert scorer.freeze_audit()["all_frozen"] is True
    assert any(parameter.grad is not None for parameter in projector.parameters())


def test_vlm_training_subset_is_deterministic_and_has_all_labels():
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    rows = [
        {
            "split": "train",
            "sample_id": f"sample-{index}",
            "patient_id_hash": f"patient-{index // 2}",
            "progression_label": labels[index % len(labels)],
        }
        for index in range(100)
    ]
    first = select_vlm_training_rows(rows, count=50, seed=17)
    second = select_vlm_training_rows(rows, count=50, seed=17)
    assert first == second
    assert {row["progression_label"] for row in first} == set(labels)
