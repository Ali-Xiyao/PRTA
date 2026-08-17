from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import nn

from prta_cxr.contracts import PROGRESSION_LABELS

INVERSION_INDEX = torch.tensor((0, 2, 1, 4, 3), dtype=torch.long)


@dataclass(frozen=True)
class PRTAVariant:
    identifier: str
    trainable_adapter: bool
    classification: bool
    transition_alignment: bool
    temporal_inversion: bool
    cmcp: bool
    state_preservation: bool
    availability_gated: bool = False


def prta_variant_registry() -> dict[str, PRTAVariant]:
    return {
        "A0": PRTAVariant("A0", False, False, False, False, False, False),
        "A1": PRTAVariant("A1", False, False, False, False, False, False, True),
        "A2": PRTAVariant("A2", True, True, False, False, False, False),
        "A3": PRTAVariant("A3", True, True, True, False, False, False),
        "A4": PRTAVariant("A4", True, True, True, True, False, False),
        "A5": PRTAVariant("A5", True, True, True, False, True, False),
        "A6": PRTAVariant("A6", True, True, True, True, True, True),
        "A7": PRTAVariant("A7", False, False, False, False, False, False, True),
    }


class FrozenBiomedCLIPDifference(nn.Module):
    def __init__(
        self,
        frozen_blocks: Sequence[nn.Module],
        *,
        final_norm: nn.Module,
    ) -> None:
        super().__init__()
        if len(frozen_blocks) not in {4, 6, 8, 10}:
            raise ValueError("A0 requires a 4-, 6-, 8-, or 10-block BiomedCLIP tail")
        self.frozen_blocks = nn.ModuleList(frozen_blocks)
        self.final_norm = final_norm
        self.eval().requires_grad_(False)

    def train(self, mode: bool = True):
        super().train(False)
        return self

    def encode(self, block8_tokens: torch.Tensor) -> torch.Tensor:
        tokens = block8_tokens
        for block in self.frozen_blocks:
            tokens = block(tokens)
        return self.final_norm(tokens)

    @torch.no_grad()
    def forward(
        self,
        prior_block8: torch.Tensor,
        current_block8: torch.Tensor,
    ) -> torch.Tensor:
        if prior_block8.shape != current_block8.shape:
            raise ValueError("A0 prior/current token shapes differ")
        prior_cls = self.encode(prior_block8)[:, 0]
        current_cls = self.encode(current_block8)[:, 0]
        return F.normalize(current_cls - prior_cls, dim=-1)


class BottleneckAdapter(nn.Module):
    def __init__(
        self,
        width: int,
        rank: int,
        *,
        dropout: float = 0.0,
        initial_scale: float = 1e-3,
    ) -> None:
        super().__init__()
        if rank <= 0 or rank >= width:
            raise ValueError("adapter rank must be within (0, width)")
        self.norm = nn.LayerNorm(width)
        self.down = nn.Linear(width, rank, bias=False)
        self.up = nn.Linear(rank, width, bias=False)
        self.dropout = nn.Dropout(dropout)
        self.scale = nn.Parameter(torch.tensor(float(initial_scale)))
        nn.init.kaiming_uniform_(self.down.weight, a=5**0.5)
        nn.init.zeros_(self.up.weight)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        update = self.up(F.gelu(self.down(self.norm(tokens))))
        return tokens + self.scale * self.dropout(update)


class FrozenTailWithAdapters(nn.Module):
    def __init__(
        self,
        frozen_blocks: Sequence[nn.Module],
        *,
        width: int,
        adapter_rank: int,
        dropout: float = 0.0,
        final_norm: nn.Module | None = None,
        adapter_indices: Sequence[int] | None = None,
    ) -> None:
        super().__init__()
        if len(frozen_blocks) not in {4, 6, 8, 10}:
            raise ValueError("PRTA requires a 4-, 6-, 8-, or 10-block frozen ViT tail")
        self.frozen_blocks = nn.ModuleList(frozen_blocks)
        for block in self.frozen_blocks:
            block.eval().requires_grad_(False)
        self.final_norm = final_norm if final_norm is not None else nn.Identity()
        self.final_norm.eval().requires_grad_(False)
        indices = (
            tuple(range(len(frozen_blocks)))
            if adapter_indices is None
            else tuple(adapter_indices)
        )
        if any(index not in range(len(frozen_blocks)) for index in indices):
            raise ValueError("adapter indices must be a subset of the tail")
        if len(indices) != len(set(indices)):
            raise ValueError("adapter indices must be unique")
        self.adapter_indices = indices
        self.adapters = nn.ModuleDict(
            {
                str(index): BottleneckAdapter(width, adapter_rank, dropout=dropout)
                for index in indices
            }
        )

    def train(self, mode: bool = True):
        super().train(mode)
        for block in self.frozen_blocks:
            block.eval()
        self.final_norm.eval()
        return self

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        for index, block in enumerate(self.frozen_blocks):
            # Frozen parameters still participate in autograd so gradients can
            # reach adapters inserted before later frozen blocks.
            frozen_output = block(tokens)
            key = str(index)
            tokens = (
                self.adapters[key](frozen_output)
                if key in self.adapters
                else frozen_output
            )
        return self.final_norm(tokens)

    def forward_frozen(self, tokens: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            for block in self.frozen_blocks:
                tokens = block(tokens)
            return self.final_norm(tokens)


class QueryResampler(nn.Module):
    def __init__(
        self,
        *,
        width: int,
        heads: int,
        output_tokens: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.queries = nn.Parameter(torch.empty(output_tokens, width))
        nn.init.normal_(self.queries, std=0.02)
        self.attention = nn.MultiheadAttention(
            width, heads, dropout=dropout, batch_first=True
        )
        self.norm = nn.LayerNorm(width)

    def forward(
        self, source: torch.Tensor, query_condition: torch.Tensor
    ) -> torch.Tensor:
        batch = source.shape[0]
        queries = self.queries.unsqueeze(0).expand(batch, -1, -1)
        queries = queries + query_condition.unsqueeze(1)
        output, _ = self.attention(
            self.norm(queries),
            self.norm(source),
            self.norm(source),
            need_weights=False,
        )
        return queries + output


@dataclass
class PRTAOutput:
    state_tokens: torch.Tensor
    transition_tokens: torch.Tensor
    state_embedding: torch.Tensor
    transition_embedding: torch.Tensor
    aligned_prior_tokens: torch.Tensor
    frozen_current_embedding: torch.Tensor
    change_gate: torch.Tensor | None = None
    change_energy: torch.Tensor | None = None
    prior_reliability: torch.Tensor | None = None


class PRTATemporalAdapter(nn.Module):
    def __init__(
        self,
        frozen_tail_blocks: Sequence[nn.Module],
        *,
        width: int = 768,
        heads: int = 12,
        adapter_rank: int = 32,
        state_tokens: int = 20,
        transition_tokens: int = 20,
        dropout: float = 0.0,
        frozen_final_norm: nn.Module | None = None,
        cross_time_alignment: bool = True,
        bounded_state_anchor: bool = False,
        state_branch: bool = True,
        adapter_indices: Sequence[int] | None = None,
        learned_relation_residual_scale: bool = False,
        relation_residual_initial_scale: float = 1e-3,
        prior_reliability_gate: bool = False,
        unaligned_prior_mode: str = "conditioned",
        temporal_relation_residual: bool = True,
    ) -> None:
        super().__init__()
        if width % heads:
            raise ValueError("width must be divisible by heads")
        self.tail = FrozenTailWithAdapters(
            frozen_tail_blocks,
            width=width,
            adapter_rank=adapter_rank,
            dropout=dropout,
            final_norm=frozen_final_norm,
            adapter_indices=adapter_indices,
        )
        self.cross_time_alignment = bool(cross_time_alignment)
        self.bounded_state_anchor = bool(bounded_state_anchor)
        self.state_branch = bool(state_branch)
        self.learned_relation_residual_scale = bool(learned_relation_residual_scale)
        self.prior_reliability_gate = bool(prior_reliability_gate)
        self.unaligned_prior_mode = str(unaligned_prior_mode)
        self.temporal_relation_residual = bool(temporal_relation_residual)
        if self.unaligned_prior_mode not in {"conditioned", "raw"}:
            raise ValueError("unaligned prior mode must be conditioned or raw")
        if not self.temporal_relation_residual and (
            self.learned_relation_residual_scale or self.prior_reliability_gate
        ):
            raise ValueError(
                "relation residual scale/gate requires temporal relation residual"
            )
        if self.prior_reliability_gate and not self.learned_relation_residual_scale:
            raise ValueError(
                "prior reliability gate requires learned relation residual scale"
            )
        if relation_residual_initial_scale < 0:
            raise ValueError("relation residual initial scale must be non-negative")
        self.query_projection = nn.Sequential(
            nn.LayerNorm(width),
            nn.Linear(width, width),
            nn.GELU(),
            nn.Linear(width, width),
        )
        self.cross_time = nn.MultiheadAttention(
            width, heads, dropout=dropout, batch_first=True
        )
        self.cross_norm = nn.LayerNorm(width)
        self.relation_projection = nn.Sequential(
            nn.LayerNorm(width * 5),
            nn.Linear(width * 5, width * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(width * 2, width),
        )
        self.relation_residual_scale = (
            nn.Parameter(torch.tensor(float(relation_residual_initial_scale)))
            if self.learned_relation_residual_scale
            else None
        )
        self.prior_reliability_projection = (
            nn.Sequential(
                nn.LayerNorm(width * 4),
                nn.Linear(width * 4, width),
                nn.GELU(),
                nn.Linear(width, 1),
            )
            if self.prior_reliability_gate
            else None
        )
        self.state_resampler = (
            QueryResampler(
                width=width,
                heads=heads,
                output_tokens=state_tokens,
                dropout=dropout,
            )
            if self.state_branch
            else None
        )
        self.transition_resampler = QueryResampler(
            width=width,
            heads=heads,
            output_tokens=transition_tokens,
            dropout=dropout,
        )
        self.state_norm = nn.LayerNorm(width) if self.state_branch else None
        self.transition_norm = nn.LayerNorm(width)
        self.change_gate_projection = (
            nn.Sequential(
                nn.LayerNorm(width * 2),
                nn.Linear(width * 2, width),
                nn.GELU(),
                nn.Linear(width, 1),
            )
            if self.bounded_state_anchor
            else None
        )

    def forward(
        self,
        prior_block8: torch.Tensor,
        current_block8: torch.Tensor,
        finding_query: torch.Tensor,
        *,
        deployment_prune_state: bool = False,
    ) -> PRTAOutput:
        if prior_block8.shape != current_block8.shape:
            raise ValueError("prior/current Block-8 token shapes differ")
        if prior_block8.ndim != 3:
            raise ValueError("Block-8 tokens must have shape [B, N, D]")
        if finding_query.shape != (
            prior_block8.shape[0],
            prior_block8.shape[2],
        ):
            raise ValueError("finding query must have shape [B, D]")

        query_condition = self.query_projection(finding_query)
        prior = self.tail(prior_block8)
        current = self.tail(current_block8)
        conditioned_current = current + query_condition.unsqueeze(1)
        conditioned_prior = prior + query_condition.unsqueeze(1)
        if self.cross_time_alignment:
            aligned_prior, _ = self.cross_time(
                self.cross_norm(conditioned_current),
                self.cross_norm(conditioned_prior),
                self.cross_norm(prior),
                need_weights=False,
            )
        else:
            aligned_prior = (
                conditioned_prior
                if self.unaligned_prior_mode == "conditioned"
                else prior
            )
        prior_reliability = None
        if self.temporal_relation_residual:
            relation = torch.cat(
                (
                    current,
                    aligned_prior,
                    current - aligned_prior,
                    (current - aligned_prior).abs(),
                    current * aligned_prior,
                ),
                dim=-1,
            )
            relation_residual = self.relation_projection(relation)
            if self.prior_reliability_projection is not None:
                reliability_context = torch.cat(
                    (
                        current.mean(dim=1),
                        aligned_prior.mean(dim=1),
                        (current - aligned_prior).abs().mean(dim=1),
                        query_condition,
                    ),
                    dim=-1,
                )
                prior_reliability = torch.sigmoid(
                    self.prior_reliability_projection(reliability_context)
                )
                relation_residual = relation_residual * prior_reliability.unsqueeze(1)
            if self.relation_residual_scale is None:
                transition_source = current + relation_residual
            else:
                transition_source = (
                    current + self.relation_residual_scale * relation_residual
                )
        else:
            transition_source = current
        transition_tokens = self.transition_resampler(
            transition_source, query_condition
        )
        transition_embedding = F.normalize(
            self.transition_norm(transition_tokens.mean(dim=1)), dim=-1
        )
        if deployment_prune_state or self.state_resampler is None:
            state_tokens = transition_tokens
            state_embedding = transition_embedding
        else:
            state_tokens = self.state_resampler(current, query_condition)
            if self.state_norm is None:  # pragma: no cover - constructor invariant
                raise RuntimeError("state norm missing for enabled state branch")
            state_embedding = F.normalize(
                self.state_norm(state_tokens.mean(dim=1)), dim=-1
            )
        frozen_current_embedding = F.normalize(
            self.tail.forward_frozen(current_block8).mean(dim=1), dim=-1
        )
        difference = current - prior
        change_energy = difference.square().mean(dim=(1, 2), keepdim=False)
        change_gate = None
        if self.change_gate_projection is not None:
            change_signal = 1 - torch.exp(-change_energy)
            gate_context = torch.cat(
                (difference.abs().mean(dim=1), query_condition), dim=-1
            )
            learned_gate = torch.sigmoid(self.change_gate_projection(gate_context))
            change_gate = change_signal.unsqueeze(-1) * learned_gate
        return PRTAOutput(
            state_tokens=state_tokens,
            transition_tokens=transition_tokens,
            state_embedding=state_embedding,
            transition_embedding=transition_embedding,
            aligned_prior_tokens=aligned_prior,
            frozen_current_embedding=frozen_current_embedding,
            change_gate=change_gate,
            change_energy=change_energy,
            prior_reliability=prior_reliability,
        )


class PRTATrainingHeads(nn.Module):
    def __init__(
        self,
        *,
        visual_width: int = 768,
        text_width: int = 512,
    ) -> None:
        super().__init__()
        self.finding_projection = nn.Sequential(
            nn.LayerNorm(text_width),
            nn.Linear(text_width, visual_width),
        )
        self.transition_text_projection = nn.Sequential(
            nn.LayerNorm(text_width),
            nn.Linear(text_width, visual_width),
        )
        self.progression_classifier = nn.Sequential(
            nn.LayerNorm(visual_width),
            nn.Linear(visual_width, len(PROGRESSION_LABELS)),
        )

    def finding_query(self, text_embedding: torch.Tensor) -> torch.Tensor:
        return self.finding_projection(text_embedding)

    def transition_text(self, text_embedding: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.transition_text_projection(text_embedding), dim=-1)

    def progression_logits(self, transition_embedding: torch.Tensor) -> torch.Tensor:
        return self.progression_classifier(transition_embedding)


def transition_alignment_loss(
    transition_embeddings: torch.Tensor,
    text_embeddings: torch.Tensor,
    *,
    temperature: float = 0.07,
) -> torch.Tensor:
    if transition_embeddings.shape != text_embeddings.shape:
        raise ValueError("transition/text embedding shapes differ")
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    visual = F.normalize(transition_embeddings, dim=-1)
    text = F.normalize(text_embeddings, dim=-1)
    logits = visual @ text.transpose(0, 1) / temperature
    targets = torch.arange(logits.shape[0], device=logits.device)
    return 0.5 * (
        F.cross_entropy(logits, targets)
        + F.cross_entropy(logits.transpose(0, 1), targets)
    )


def finding_conditioned_prototype_alignment_loss(
    transition_embeddings: torch.Tensor,
    prototype_embeddings: torch.Tensor,
    target: torch.Tensor,
    *,
    temperature: float = 0.07,
) -> torch.Tensor:
    if transition_embeddings.ndim != 2:
        raise ValueError("transition embeddings must have shape [B, D]")
    expected = (
        transition_embeddings.shape[0],
        len(PROGRESSION_LABELS),
        transition_embeddings.shape[1],
    )
    if prototype_embeddings.shape != expected:
        raise ValueError("prototype embeddings must have shape [B, 5, D]")
    if target.shape != (transition_embeddings.shape[0],):
        raise ValueError("prototype target must have shape [B]")
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    visual = F.normalize(transition_embeddings, dim=-1)
    prototypes = F.normalize(prototype_embeddings, dim=-1)
    logits = torch.einsum("bd,bkd->bk", visual, prototypes) / temperature
    return F.cross_entropy(logits, target)


def cmcp_margin_loss(
    true_transition: torch.Tensor,
    counterfactual_transition: torch.Tensor,
    target_text: torch.Tensor,
    *,
    margin: float = 0.2,
) -> torch.Tensor:
    if not (
        true_transition.shape == counterfactual_transition.shape == target_text.shape
    ):
        raise ValueError("CMCP embedding shapes differ")
    true_score = F.cosine_similarity(true_transition, target_text, dim=-1)
    counterfactual_score = F.cosine_similarity(
        counterfactual_transition, target_text, dim=-1
    )
    return F.relu(margin - true_score + counterfactual_score).mean()


def invert_progression_logits(logits: torch.Tensor) -> torch.Tensor:
    if logits.shape[-1] != len(PROGRESSION_LABELS):
        raise ValueError("progression logits must contain five classes")
    return logits.index_select(-1, INVERSION_INDEX.to(device=logits.device))


def project_equivariant_inversion_logits(
    forward_logits: torch.Tensor,
    reversed_logits: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    if forward_logits.shape != reversed_logits.shape:
        raise ValueError("forward/reversed logit shapes differ")
    projected_forward = 0.5 * (
        forward_logits + invert_progression_logits(reversed_logits)
    )
    projected_reversed = invert_progression_logits(projected_forward)
    return projected_forward, projected_reversed


def temporal_inversion_loss(
    forward_logits: torch.Tensor, reversed_logits: torch.Tensor
) -> torch.Tensor:
    mapped_forward = invert_progression_logits(forward_logits)
    target = F.softmax(mapped_forward.detach(), dim=-1)
    return F.kl_div(
        F.log_softmax(reversed_logits, dim=-1),
        target,
        reduction="batchmean",
    )


def opposite_direction_margin_loss(
    logits: torch.Tensor,
    target: torch.Tensor,
    *,
    margin: float = 0.2,
) -> torch.Tensor:
    if logits.ndim != 2 or logits.shape[-1] != len(PROGRESSION_LABELS):
        raise ValueError("direction-margin logits must have shape [B, 5]")
    if target.shape != (logits.shape[0],):
        raise ValueError("direction-margin target must have shape [B]")
    if margin < 0:
        raise ValueError("direction-margin margin must be non-negative")
    inversion = INVERSION_INDEX.to(device=target.device)
    directional = target != 0
    if not bool(directional.any()):
        return logits.sum() * 0
    row = torch.arange(target.shape[0], device=target.device)
    target_logits = logits[row, target]
    opposite_logits = logits[row, inversion[target]]
    return F.relu(margin - target_logits + opposite_logits)[directional].mean()


def opposite_direction_cost_loss(
    logits: torch.Tensor,
    target: torch.Tensor,
) -> torch.Tensor:
    """Directly penalize probability mass assigned to the opposite label."""
    if logits.ndim != 2 or logits.shape[-1] != len(PROGRESSION_LABELS):
        raise ValueError("opposite-direction-cost logits must have shape [B, 5]")
    if target.shape != (logits.shape[0],):
        raise ValueError("opposite-direction-cost target must have shape [B]")
    inversion = INVERSION_INDEX.to(device=target.device)
    directional = target != 0
    if not bool(directional.any()):
        return logits.sum() * 0
    row = torch.arange(target.shape[0], device=target.device)
    opposite = inversion[target]
    non_opposite_logits = logits.masked_fill(
        F.one_hot(opposite, num_classes=len(PROGRESSION_LABELS)).bool(),
        float("-inf"),
    )
    negative_log_complement = torch.logsumexp(logits, dim=-1) - torch.logsumexp(
        non_opposite_logits,
        dim=-1,
    )
    return negative_log_complement[row[directional]].mean()


def state_preservation_loss(
    adapted_state: torch.Tensor,
    frozen_current_state: torch.Tensor,
    *,
    sample_weights: torch.Tensor | None = None,
) -> torch.Tensor:
    if adapted_state.shape != frozen_current_state.shape:
        raise ValueError("state-preservation embedding shapes differ")
    losses = 1 - F.cosine_similarity(
        adapted_state, frozen_current_state.detach(), dim=-1
    )
    if sample_weights is None:
        return losses.mean()
    if sample_weights.shape != losses.shape:
        raise ValueError("state-preservation sample weights must have shape [B]")
    if bool((sample_weights < 0).any()):
        raise ValueError("state-preservation sample weights must be non-negative")
    denominator = sample_weights.sum().clamp_min(torch.finfo(losses.dtype).eps)
    return (losses * sample_weights).sum() / denominator


def branch_decorrelation_loss(
    state_embedding: torch.Tensor, transition_embedding: torch.Tensor
) -> torch.Tensor:
    """Discourage per-sample state/transition collapse without fixing direction."""
    if state_embedding.shape != transition_embedding.shape:
        raise ValueError("state/transition embedding shapes differ")
    cosine = F.cosine_similarity(
        state_embedding,
        transition_embedding,
        dim=-1,
    )
    return cosine.square().mean()
