import pytest
import torch
from torch import nn

from prta_cxr.models.heads import NativeH0Head, NativeH1Head, NativeH2Head
from prta_cxr.models.prta import (
    PRTATemporalAdapter,
    cmcp_margin_loss,
    invert_progression_logits,
    state_preservation_loss,
    transition_alignment_loss,
)
from prta_cxr.training.engine import build_train_model


def model() -> PRTATemporalAdapter:
    return PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
    )


def test_prta_shapes_native_heads_and_gradient_path():
    adapter = model()
    prior = torch.randn(3, 9, 16)
    current = torch.randn(3, 9, 16)
    query = torch.randn(3, 16)
    output = adapter(prior, current, query)
    assert output.state_tokens.shape == (3, 4, 16)
    assert output.transition_tokens.shape == (3, 4, 16)
    assert NativeH0Head(16)(output, query).shape == (3, 5)
    logits = NativeH1Head(16)(output, query)
    assert logits.shape == (3, 5)
    assert NativeH2Head(16)(output, query).shape == (3, 5)
    logits.sum().backward()
    assert any(
        parameter.grad is not None
        for parameter in adapter.tail.adapters.parameters()
    )


def test_losses_and_inversion_are_finite():
    first = torch.randn(5, 16)
    second = torch.randn(5, 16)
    assert torch.isfinite(transition_alignment_loss(first, second))
    assert torch.isfinite(cmcp_margin_loss(first, second, torch.randn(5, 16)))
    assert torch.isfinite(state_preservation_loss(first, second))
    logits = torch.arange(5.0).unsqueeze(0)
    assert invert_progression_logits(logits).tolist() == [[0.0, 2.0, 1.0, 4.0, 3.0]]


@pytest.mark.parametrize("family", ("current_only", "siamese_diff", "tila"))
def test_native_baseline_families_produce_five_logits(family):
    config = {
        "model": {
            "family": family,
            "width": 16,
            "heads": 4,
            "adapter_rank": 4,
            "dropout": 0.0,
        }
    }
    value = build_train_model(
        [nn.Identity() for _ in range(4)], nn.Identity(), config
    )
    output, logits, query = value(
        torch.randn(2, 9, 16),
        torch.randn(2, 9, 16),
        torch.randn(2, 512),
    )
    assert output is None
    assert logits.shape == (2, 5)
    assert query.shape == (2, 16)


def test_adapter_scope_can_be_limited_to_last_two_tail_blocks():
    adapter = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
        adapter_indices=(2, 3),
    )
    assert tuple(adapter.tail.adapter_indices) == (2, 3)
    assert set(adapter.tail.adapters) == {"2", "3"}
