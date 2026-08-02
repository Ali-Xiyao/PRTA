from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import torch
from torch import nn

from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.vlm.projector import Projected64


def freeze_module(module: nn.Module) -> nn.Module:
    module.eval().requires_grad_(False)
    return module


def frozen_parameter_audit(module: nn.Module) -> dict[str, Any]:
    parameters = list(module.named_parameters())
    trainable = [name for name, value in parameters if value.requires_grad]
    return {
        "parameter_count": sum(value.numel() for _, value in parameters),
        "trainable_parameter_count": sum(
            value.numel() for _, value in parameters if value.requires_grad
        ),
        "trainable_parameter_names": trainable,
        "all_frozen": not trainable,
        "training": module.training,
    }


def build_prompt_ids(
    tokenizer: Any,
    *,
    finding: str,
    placeholder_token_id: int,
) -> torch.Tensor:
    text = (
        "You are comparing a current chest radiograph with its prior study. "
        f"Finding of interest: {finding}. The next 64 physical positions "
        "contain fixed PRTA visual tokens. Compared with the prior study, "
        "what is the progression? Answer with exactly one word: stable, "
        "improved, worse, new, or resolved. Visual tokens:"
    )
    prefix = tokenizer(text, add_special_tokens=True)["input_ids"]
    suffix = tokenizer("\nAnswer:", add_special_tokens=False)["input_ids"]
    ids = [*prefix, *([placeholder_token_id] * 64), *suffix]
    value = torch.tensor([ids], dtype=torch.long)
    if int(value.eq(placeholder_token_id).sum()) != 64:
        raise RuntimeError("VLM prompt does not contain exactly 64 placeholders")
    return value


class FrozenQwenProgressionScorer(nn.Module):
    def __init__(
        self,
        model: nn.Module,
        tokenizer: Any,
        *,
        placeholder_token_id: int,
    ) -> None:
        super().__init__()
        self.model = freeze_module(model)
        self.placeholder_token_id = int(placeholder_token_id)
        label_ids = []
        for label in PROGRESSION_LABELS:
            ids = tokenizer(label.lower(), add_special_tokens=False)["input_ids"]
            if not ids:
                raise ValueError(f"empty VLM label tokenization: {label}")
            label_ids.append(torch.tensor(ids, dtype=torch.long))
        maximum = max(value.numel() for value in label_ids)
        padded = torch.zeros(len(label_ids), maximum, dtype=torch.long)
        lengths = torch.empty(len(label_ids), dtype=torch.long)
        for index, value in enumerate(label_ids):
            padded[index, : value.numel()] = value
            lengths[index] = value.numel()
        self.register_buffer("label_ids", padded)
        self.register_buffer("label_lengths", lengths)

    def train(self, mode: bool = True):
        super().train(mode)
        self.model.eval()
        return self

    def freeze_audit(self) -> dict[str, Any]:
        audit = frozen_parameter_audit(self.model)
        audit.update({"pixel_inputs_used": False, "token_budget": 64})
        return audit

    def _logits(self, output: Any) -> torch.Tensor:
        if hasattr(output, "logits"):
            return output.logits
        if isinstance(output, Mapping) and "logits" in output:
            return output["logits"]
        if isinstance(output, Sequence) and output:
            return output[0]
        raise TypeError("frozen VLM output does not expose logits")

    def score(
        self, prompt_ids: torch.Tensor, projected: Projected64
    ) -> torch.Tensor:
        if prompt_ids.ndim != 2 or prompt_ids.shape[0] != 1:
            raise ValueError("VLM scoring currently requires one prompt row")
        if projected.embeddings.shape[0] != 1:
            raise ValueError("VLM scoring currently requires one projected row")
        placeholder = prompt_ids.eq(self.placeholder_token_id)
        if int(placeholder.sum()) != 64:
            raise ValueError("prompt must contain exactly 64 placeholders")
        device = prompt_ids.device
        label_count = len(PROGRESSION_LABELS)
        prompt_length = prompt_ids.shape[1]
        full_length = prompt_length + int(self.label_lengths.max())
        full_ids = torch.zeros(
            label_count, full_length, dtype=torch.long, device=device
        )
        attention = torch.zeros_like(full_ids)
        target_positions = torch.zeros(
            label_count,
            self.label_ids.shape[1],
            dtype=torch.long,
            device=device,
        )
        targets = torch.zeros_like(target_positions)
        target_mask = torch.zeros_like(target_positions, dtype=torch.bool)
        for label_index in range(label_count):
            length = int(self.label_lengths[label_index])
            full_ids[label_index, :prompt_length] = prompt_ids[0]
            label = self.label_ids[label_index, :length].to(device)
            full_ids[label_index, prompt_length : prompt_length + length] = label
            attention[label_index, : prompt_length + length] = 1
            target_positions[label_index, :length] = torch.arange(
                prompt_length - 1,
                prompt_length + length - 1,
                device=device,
            )
            targets[label_index, :length] = label
            target_mask[label_index, :length] = True
        embeddings = self.model.get_input_embeddings()(full_ids)
        expanded_placeholder = full_ids.eq(self.placeholder_token_id)
        indices = expanded_placeholder.long().cumsum(dim=1).sub(1).clamp_min(0)
        gather = indices.unsqueeze(-1).expand(-1, -1, projected.embeddings.shape[-1])
        source = projected.embeddings.expand(label_count, -1, -1)
        replacement = source.gather(1, gather)
        embeddings = torch.where(
            expanded_placeholder.unsqueeze(-1),
            replacement.to(embeddings.dtype),
            embeddings,
        )
        positions = attention.cumsum(dim=-1).sub(1).clamp_min(0)
        positions = positions.unsqueeze(0).expand(3, -1, -1).contiguous()
        output = self.model(
            inputs_embeds=embeddings,
            attention_mask=attention,
            position_ids=positions,
            use_cache=False,
            logits_to_keep=0,
        )
        logits = self._logits(output)
        gathered = logits.gather(
            1,
            target_positions.unsqueeze(-1).expand(-1, -1, logits.shape[-1]),
        )
        log_probabilities = gathered.float().log_softmax(dim=-1)
        token_scores = log_probabilities.gather(
            -1, targets.unsqueeze(-1)
        ).squeeze(-1)
        return (token_scores * target_mask).sum(dim=1) / self.label_lengths.to(device)
