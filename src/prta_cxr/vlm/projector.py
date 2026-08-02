from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from prta_cxr.vlm.fixed64 import Fixed64Bundle


@dataclass(frozen=True)
class Projected64:
    embeddings: torch.Tensor
    attention_mask: torch.Tensor
    position_ids: torch.Tensor
    logical_validity: torch.Tensor


class Fixed64Projector(nn.Module):
    def __init__(self, input_width: int = 768, hidden_size: int = 2560) -> None:
        super().__init__()
        self.input_width = input_width
        self.hidden_size = hidden_size
        self.feature = nn.Sequential(
            nn.Linear(input_width, hidden_size),
            nn.GELU(),
            nn.Linear(hidden_size, hidden_size),
        )
        self.types = nn.Embedding(6, hidden_size)
        self.norm = nn.LayerNorm(hidden_size)
        self.neutral = nn.Parameter(torch.empty(hidden_size))
        nn.init.normal_(self.neutral, std=0.02)

    def forward(self, bundle: Fixed64Bundle) -> Projected64:
        if bundle.tokens.ndim != 3 or bundle.tokens.shape[1:] != (
            64,
            self.input_width,
        ):
            raise ValueError("projector input must have shape [B,64,input_width]")
        if bundle.token_type_ids.shape != bundle.tokens.shape[:2]:
            raise ValueError("token-type layout does not match fixed tokens")
        projected = self.norm(
            self.feature(bundle.tokens) + self.types(bundle.token_type_ids)
        )
        neutral = self.neutral.to(projected.dtype).view(1, 1, -1)
        embeddings = torch.where(
            bundle.logical_validity.unsqueeze(-1), projected, neutral
        )
        batch = bundle.tokens.shape[0]
        attention = torch.ones(
            batch, 64, device=bundle.tokens.device, dtype=torch.long
        )
        positions = (
            torch.arange(64, device=bundle.tokens.device, dtype=torch.long)
            .view(1, 1, 64)
            .expand(3, batch, -1)
        )
        return Projected64(
            embeddings=embeddings,
            attention_mask=attention,
            position_ids=positions,
            logical_validity=bundle.logical_validity,
        )
