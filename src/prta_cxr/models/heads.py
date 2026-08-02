from __future__ import annotations

import torch
from torch import nn

from .prta import PROGRESSION_LABELS, PRTAOutput


class NativeH0Head(nn.Module):
    """Mean transition token followed by LayerNorm and five-way linear head."""

    def __init__(self, width: int = 768) -> None:
        super().__init__()
        self.head = nn.Sequential(
            nn.LayerNorm(width), nn.Linear(width, len(PROGRESSION_LABELS))
        )

    def forward(self, output: PRTAOutput, query: torch.Tensor) -> torch.Tensor:
        del query
        return self.head(output.transition_tokens.mean(dim=1))


class NativeH1Head(nn.Module):
    """Paper H1: [state, transition, interaction, query] -> MLP -> five."""

    def __init__(
        self, width: int = 768, *, hidden_width: int | None = None, dropout: float = 0.0
    ) -> None:
        super().__init__()
        hidden = width if hidden_width is None else hidden_width
        self.head = nn.Sequential(
            nn.LayerNorm(width * 4),
            nn.Linear(width * 4, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, len(PROGRESSION_LABELS)),
        )

    def forward(self, output: PRTAOutput, query: torch.Tensor) -> torch.Tensor:
        state = output.state_tokens.mean(dim=1)
        transition = output.transition_tokens.mean(dim=1)
        features = torch.cat((state, transition, state * transition, query), dim=-1)
        return self.head(features)


class NativeH2Head(nn.Module):
    """Query-attentive state/transition pooling followed by an H1-style MLP."""

    def __init__(
        self, width: int = 768, *, hidden_width: int | None = None, dropout: float = 0.0
    ) -> None:
        super().__init__()
        hidden = width if hidden_width is None else hidden_width
        self.query = nn.Sequential(nn.LayerNorm(width), nn.Linear(width, width))
        self.state_key = nn.Linear(width, width, bias=False)
        self.transition_key = nn.Linear(width, width, bias=False)
        self.scale = width**-0.5
        self.head = nn.Sequential(
            nn.LayerNorm(width * 4),
            nn.Linear(width * 4, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, len(PROGRESSION_LABELS)),
        )

    def _pool(
        self, tokens: torch.Tensor, query: torch.Tensor, key: nn.Module
    ) -> torch.Tensor:
        scores = torch.einsum(
            "bnd,bd->bn", key(tokens), self.query(query)
        ) * self.scale
        return torch.einsum("bn,bnd->bd", scores.softmax(dim=-1), tokens)

    def forward(self, output: PRTAOutput, query: torch.Tensor) -> torch.Tensor:
        state = self._pool(output.state_tokens, query, self.state_key)
        transition = self._pool(
            output.transition_tokens, query, self.transition_key
        )
        features = torch.cat((state, transition, state * transition, query), dim=-1)
        return self.head(features)
