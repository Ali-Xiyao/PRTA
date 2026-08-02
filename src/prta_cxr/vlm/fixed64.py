from __future__ import annotations

from dataclasses import dataclass

import torch

from prta_cxr.models.prta import PRTAOutput

TOKEN_LAYOUT = (4, 12, 16, 16, 12, 4)
TOKEN_TYPE_IDS = tuple(
    type_id for type_id, count in enumerate(TOKEN_LAYOUT) for _ in range(count)
)


@dataclass(frozen=True)
class Fixed64Bundle:
    tokens: torch.Tensor
    token_type_ids: torch.Tensor
    logical_validity: torch.Tensor


def mean_preserving_reduce(tokens: torch.Tensor, output_tokens: int) -> torch.Tensor:
    if tokens.ndim != 3:
        raise ValueError("tokens must have shape [B,N,D]")
    if not 0 < output_tokens <= tokens.shape[1]:
        raise ValueError("output token count is outside the input length")
    groups = []
    input_tokens = tokens.shape[1]
    for index in range(output_tokens):
        start = input_tokens * index // output_tokens
        end = input_tokens * (index + 1) // output_tokens
        groups.append(
            tokens[:, start:end].sum(dim=1)
            * (float(output_tokens) / float(input_tokens))
        )
    return torch.stack(groups, dim=1)


def pack_prta_fixed64(
    output: PRTAOutput, finding_query: torch.Tensor
) -> Fixed64Bundle:
    if finding_query.ndim != 2:
        raise ValueError("finding query must have shape [B,D]")
    batch, width = finding_query.shape
    query = finding_query[:, None, :].expand(-1, 4, -1)
    state = mean_preserving_reduce(output.state_tokens, 12)
    transition = mean_preserving_reduce(output.transition_tokens, 16)
    centered = output.transition_tokens - output.transition_tokens.mean(
        dim=1, keepdim=True
    )
    local_transition = mean_preserving_reduce(centered, 16)
    relation = mean_preserving_reduce(output.aligned_prior_tokens, 12)
    reserved = torch.zeros(
        batch,
        4,
        width,
        device=finding_query.device,
        dtype=finding_query.dtype,
    )
    tokens = torch.cat(
        (query, state, transition, local_transition, relation, reserved), dim=1
    )
    if tokens.shape != (batch, 64, width):
        raise RuntimeError("fixed-64 PRTA layout drift")
    token_types = torch.tensor(
        TOKEN_TYPE_IDS, device=tokens.device, dtype=torch.long
    ).expand(batch, -1)
    validity = torch.ones(batch, 64, device=tokens.device, dtype=torch.bool)
    validity[:, 60:] = False
    return Fixed64Bundle(tokens, token_types, validity)
