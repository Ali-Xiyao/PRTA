import pytest
import torch
from torch import nn

from prta_cxr.models.heads import (
    NativeH0Head,
    NativeH1Head,
    NativeH2Head,
    NativeH3StateAnchoredHead,
    NativeH4TransitionPrimaryGatedHead,
)
from prta_cxr.models.prta import (
    PRTATemporalAdapter,
    branch_decorrelation_loss,
    cmcp_margin_loss,
    finding_conditioned_prototype_alignment_loss,
    invert_progression_logits,
    opposite_direction_cost_loss,
    opposite_direction_margin_loss,
    state_preservation_loss,
    transition_alignment_loss,
)
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import (
    adapter_scope_cache_entry_block,
    tail_modules,
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
    assert NativeH2Head(16)(output, query).shape == (3, 5)
    logits.sum().backward()
    assert any(
        parameter.grad is not None for parameter in adapter.tail.adapters.parameters()
    )


def test_losses_and_inversion_are_finite():
    first = torch.randn(5, 16)
    second = torch.randn(5, 16)
    assert torch.isfinite(transition_alignment_loss(first, second))
    assert torch.isfinite(cmcp_margin_loss(first, second, torch.randn(5, 16)))
    assert torch.isfinite(state_preservation_loss(first, second))
    logits = torch.arange(5.0).unsqueeze(0)
    assert invert_progression_logits(logits).tolist() == [[0.0, 2.0, 1.0, 4.0, 3.0]]


def test_finding_conditioned_prototype_alignment_uses_five_class_target():
    visual = torch.tensor([[1.0, 0.0], [0.0, 1.0]], requires_grad=True)
    prototypes = torch.zeros(2, 5, 2)
    prototypes[0, 1] = torch.tensor([1.0, 0.0])
    prototypes[1, 3] = torch.tensor([0.0, 1.0])
    loss = finding_conditioned_prototype_alignment_loss(
        visual, prototypes, torch.tensor([1, 3])
    )
    loss.backward()
    assert torch.isfinite(loss)
    assert visual.grad is not None


def test_relation_residual_scale_is_near_zero_and_receives_gradient():
    adapter = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
        learned_relation_residual_scale=True,
        relation_residual_initial_scale=1e-3,
    )
    assert adapter.relation_residual_scale is not None
    assert adapter.relation_residual_scale.item() == pytest.approx(1e-3)
    output = adapter(
        torch.randn(2, 9, 16),
        torch.randn(2, 9, 16),
        torch.randn(2, 16),
    )
    output.transition_embedding.sum().backward()
    assert adapter.relation_residual_scale.grad is not None


def test_prior_reliability_gate_is_bounded_and_residual_only():
    adapter = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
        learned_relation_residual_scale=True,
        prior_reliability_gate=True,
    )
    output = adapter(
        torch.randn(2, 9, 16),
        torch.randn(2, 9, 16),
        torch.randn(2, 16),
    )
    assert output.prior_reliability is not None
    assert output.prior_reliability.shape == (2, 1)
    assert bool((output.prior_reliability >= 0).all())
    assert bool((output.prior_reliability <= 1).all())
    output.transition_embedding.sum().backward()
    assert any(
        parameter.grad is not None
        for parameter in adapter.prior_reliability_projection.parameters()
    )


def test_selective_state_preservation_downweights_large_change():
    adapted = torch.tensor([[1.0, 0.0], [0.0, 1.0]], requires_grad=True)
    frozen = torch.tensor([[1.0, 0.0], [1.0, 0.0]])
    unweighted = state_preservation_loss(adapted, frozen)
    weighted = state_preservation_loss(
        adapted, frozen, sample_weights=torch.tensor([1.0, 0.01])
    )
    assert weighted < unweighted
    weighted.backward()
    assert adapted.grad is not None


@pytest.mark.parametrize(
    "family",
    (
        "current_only",
        "siamese_diff",
        "tila",
        "early_concat",
        "symmetric_cross_attention",
        "biovilt_adapted",
        "chexrelnet_adapted",
    ),
)
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
    value = build_train_model([nn.Identity() for _ in range(4)], nn.Identity(), config)
    output, logits, query = value(
        torch.randn(2, 9, 16),
        torch.randn(2, 9, 16),
        torch.randn(2, 512),
    )
    assert output is None
    assert logits.shape == (2, 5)
    assert query.shape == (2, 16)


def test_no_cross_time_ablation_uses_raw_prior_tokens():
    adapter = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
        cross_time_alignment=False,
        unaligned_prior_mode="raw",
    )
    prior = torch.randn(2, 9, 16)
    current = torch.randn(2, 9, 16)
    query = torch.randn(2, 16)
    expected = adapter.tail(prior)
    output = adapter(prior, current, query)
    assert torch.equal(output.aligned_prior_tokens, expected)


def test_no_relation_residual_bypasses_relation_projection():
    adapter = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
        temporal_relation_residual=False,
    )
    output = adapter(
        torch.randn(2, 9, 16),
        torch.randn(2, 9, 16),
        torch.randn(2, 16),
    )
    output.transition_embedding.sum().backward()
    assert all(
        parameter.grad is None for parameter in adapter.relation_projection.parameters()
    )


def test_new_ablation_defaults_preserve_frozen_adapter_logits():
    original = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
    )
    explicit = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
        unaligned_prior_mode="conditioned",
        temporal_relation_residual=True,
    )
    explicit.load_state_dict(original.state_dict())
    prior = torch.randn(2, 9, 16)
    current = torch.randn(2, 9, 16)
    query = torch.randn(2, 16)
    original_output = original(prior, current, query)
    explicit_output = explicit(prior, current, query)
    assert torch.equal(
        original_output.transition_embedding,
        explicit_output.transition_embedding,
    )


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


@pytest.mark.parametrize(
    ("scope", "tail_length", "expected_indices", "entry_block"),
    (
        ("no_tail", 4, (), 8),
        ("tail2", 4, (2, 3), 8),
        ("tail4", 4, tuple(range(4)), 8),
        ("tail6", 8, tuple(range(2, 8)), 4),
        ("tail8", 8, tuple(range(8)), 4),
        ("tail10", 10, tuple(range(10)), 2),
    ),
)
def test_formal_adapter_scope_matrix(scope, tail_length, expected_indices, entry_block):
    config = {
        "model": {
            "family": "prta",
            "width": 16,
            "heads": 4,
            "adapter_rank": 4,
            "adapter_scope": scope,
            "state_tokens": 4,
            "transition_tokens": 4,
            "dropout": 0.0,
        }
    }
    value = build_train_model(
        [nn.Identity() for _ in range(tail_length)], nn.Identity(), config
    )
    assert tuple(value.adapter.tail.adapter_indices) == expected_indices
    assert set(value.adapter.tail.adapters) == {
        str(index) for index in expected_indices
    }
    assert adapter_scope_cache_entry_block(scope) == entry_block


@pytest.mark.parametrize(
    ("scope", "expected_indices"),
    (
        ("tail6", tuple(range(2, 8))),
        ("tail8", tuple(range(8))),
    ),
)
def test_expanded_adapter_scopes_use_block4_cache(scope, expected_indices):
    config = {
        "model": {
            "family": "prta",
            "width": 16,
            "heads": 4,
            "adapter_rank": 4,
            "adapter_scope": scope,
            "state_tokens": 4,
            "transition_tokens": 4,
            "dropout": 0.0,
        }
    }
    value = build_train_model([nn.Identity() for _ in range(8)], nn.Identity(), config)
    assert tuple(value.adapter.tail.adapter_indices) == expected_indices
    assert adapter_scope_cache_entry_block(scope) == 4


def test_expanded_adapter_scope_rejects_legacy_block8_tail():
    config = {
        "model": {
            "family": "prta",
            "width": 16,
            "heads": 4,
            "adapter_rank": 4,
            "adapter_scope": "tail6",
            "state_tokens": 4,
            "transition_tokens": 4,
        }
    }
    with pytest.raises(ValueError, match="Block-4 cache"):
        build_train_model([nn.Identity() for _ in range(4)], nn.Identity(), config)


def test_block4_tail_exposes_eight_frozen_transformer_blocks():
    visual = nn.Module()
    visual.blocks = nn.ModuleList(nn.Identity() for _ in range(12))
    visual.norm = nn.Identity()
    blocks, final_norm = tail_modules(visual, start_block=4)
    assert len(blocks) == 8
    assert final_norm is visual.norm


def test_block2_tail_exposes_ten_frozen_transformer_blocks():
    visual = nn.Module()
    visual.blocks = nn.ModuleList(nn.Identity() for _ in range(12))
    visual.norm = nn.Identity()
    blocks, final_norm = tail_modules(visual, start_block=2)
    assert len(blocks) == 10
    assert final_norm is visual.norm


def test_state_anchor_gate_is_bounded_and_zero_for_identical_pair():
    adapter = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
        bounded_state_anchor=True,
    )
    current = torch.randn(3, 9, 16)
    query = torch.randn(3, 16)
    identical = adapter(current, current, query)
    assert identical.change_gate is not None
    assert torch.equal(identical.change_gate, torch.zeros_like(identical.change_gate))
    changed = adapter(torch.zeros_like(current), current, query)
    assert changed.change_gate is not None
    assert bool((changed.change_gate >= 0).all())
    assert bool((changed.change_gate <= 1).all())
    logits = NativeH3StateAnchoredHead(16)(changed, query)
    logits.sum().backward()
    assert any(
        parameter.grad is not None
        for parameter in adapter.change_gate_projection.parameters()
    )


def test_h4_is_transition_primary_and_trains_both_branches_when_changed():
    adapter = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=16,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
        bounded_state_anchor=True,
    )
    head = NativeH4TransitionPrimaryGatedHead(16, hidden_width=16)
    current = torch.randn(3, 9, 16)
    query = torch.randn(3, 16)

    identical = adapter(current, current, query)
    transition = identical.transition_tokens.mean(dim=1)
    expected = head.transition_head(transition)
    assert torch.allclose(head(identical, query), expected)

    changed = adapter(torch.zeros_like(current), current, query)
    logits = head(changed, query)
    logits.sum().backward()
    assert any(
        parameter.grad is not None for parameter in adapter.state_resampler.parameters()
    )
    assert any(
        parameter.grad is not None
        for parameter in adapter.transition_resampler.parameters()
    )


def test_clean_transition_only_omits_state_branch_parameters():
    config = {
        "model": {
            "family": "prta",
            "width": 16,
            "heads": 4,
            "adapter_rank": 4,
            "adapter_scope": "tail4",
            "state_tokens": 4,
            "transition_tokens": 4,
            "dropout": 0.0,
            "native_head": "H0",
            "components": {
                "dual_branch": False,
                "branch_mode": "transition_only",
            },
        }
    }
    value = build_train_model([nn.Identity() for _ in range(4)], nn.Identity(), config)
    output, logits, _ = value(
        torch.randn(2, 9, 16),
        torch.randn(2, 9, 16),
        torch.randn(2, 512),
    )
    assert value.adapter.state_resampler is None
    assert value.adapter.state_norm is None
    assert output.state_tokens is output.transition_tokens
    assert output.state_embedding is output.transition_embedding
    assert logits.shape == (2, 5)
    assert not any("state_resampler" in name for name, _ in value.named_parameters())


def test_h0_deployment_state_pruning_is_exact_and_skips_state_resampler():
    config = {
        "model": {
            "family": "prta",
            "width": 16,
            "heads": 4,
            "adapter_rank": 4,
            "adapter_scope": "tail4",
            "state_tokens": 4,
            "transition_tokens": 4,
            "dropout": 0.0,
            "native_head": "H0",
            "components": {"dual_branch": True, "branch_mode": "legacy"},
        }
    }
    value = build_train_model([nn.Identity() for _ in range(4)], nn.Identity(), config)
    value.eval()
    prior = torch.randn(2, 9, 16)
    current = torch.randn(2, 9, 16)
    finding = torch.randn(2, 512)
    calls = 0
    original = value.adapter.state_resampler.forward

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    value.adapter.state_resampler.forward = counted
    with torch.no_grad():
        _, ordinary_logits, _ = value(prior, current, finding)
        assert calls == 1
        pruned, pruned_logits, _ = value(
            prior, current, finding, deployment_prune_state=True
        )
    assert calls == 1
    assert pruned.state_tokens is pruned.transition_tokens
    assert pruned.state_embedding is pruned.transition_embedding
    assert torch.equal(ordinary_logits, pruned_logits)


def test_branch_decorrelation_penalizes_collapsed_embeddings():
    state = torch.eye(4)
    orthogonal = state.roll(1, dims=1)
    collapsed = branch_decorrelation_loss(state, state)
    separated = branch_decorrelation_loss(state, orthogonal)
    assert collapsed == pytest.approx(1.0)
    assert separated == pytest.approx(0.0)


def test_repaired_dual_requires_h4_and_bounded_gate():
    base = {
        "family": "prta",
        "width": 16,
        "heads": 4,
        "adapter_rank": 4,
        "adapter_scope": "tail4",
        "state_tokens": 4,
        "transition_tokens": 4,
        "dropout": 0.0,
        "native_head": "H4",
        "components": {
            "dual_branch": True,
            "branch_mode": "repaired_dual",
            "bounded_state_anchor": False,
        },
    }
    with pytest.raises(ValueError, match="bounded_state_anchor=true"):
        build_train_model(
            [nn.Identity() for _ in range(4)],
            nn.Identity(),
            {"model": base},
        )


def test_direction_margin_penalizes_opposite_more_than_target():
    target = torch.tensor([1, 2, 3, 4])
    good = torch.zeros(4, 5)
    good[torch.arange(4), target] = 2.0
    bad = good.clone()
    bad[torch.arange(4), torch.tensor([2, 1, 4, 3])] = 3.0
    assert opposite_direction_margin_loss(good, target) == 0
    assert opposite_direction_margin_loss(bad, target) > 0


def test_direction_cost_directly_penalizes_opposite_probability():
    target = torch.tensor([1, 2, 3, 4])
    good = torch.zeros(4, 5)
    good[torch.arange(4), target] = 4.0
    bad = good.clone()
    bad[torch.arange(4), torch.tensor([2, 1, 4, 3])] = 6.0

    good_loss = opposite_direction_cost_loss(good, target)
    bad.requires_grad_()
    bad_loss = opposite_direction_cost_loss(bad, target)
    bad_loss.backward()

    assert bad_loss > good_loss
    assert bool(
        (
            bad.grad[
                torch.arange(4),
                torch.tensor([2, 1, 4, 3]),
            ]
            > 0
        ).all()
    )


def test_direction_cost_ignores_stable_targets():
    logits = torch.randn(3, 5, requires_grad=True)
    loss = opposite_direction_cost_loss(logits, torch.zeros(3, dtype=torch.long))
    loss.backward()

    assert loss == 0
    assert torch.equal(logits.grad, torch.zeros_like(logits))


def test_direction_cost_remains_finite_for_extreme_opposite_logit():
    logits = torch.tensor([[0.0, 0.0, 100_000.0, 0.0, 0.0]])
    loss = opposite_direction_cost_loss(logits, torch.tensor([1]))

    assert torch.isfinite(loss)
    assert loss > 99_000
