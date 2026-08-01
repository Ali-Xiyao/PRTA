import torch
from torch import nn

from prta_cxr.models.heads import NativeH0Head, NativeH1Head
from prta_cxr.models.prta import (
    PRTATemporalAdapter,
    cmcp_margin_loss,
    invert_progression_logits,
    state_preservation_loss,
    transition_alignment_loss,
)


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
