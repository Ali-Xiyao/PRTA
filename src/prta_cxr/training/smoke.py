from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from prta_cxr.models.heads import NativeH1Head
from prta_cxr.models.prta import PRTATemporalAdapter


def run_synthetic_smoke(
    output_path: Path, *, seed: int = 17, steps: int = 3
) -> dict[str, Any]:
    if steps < 1 or steps > 20:
        raise ValueError("smoke steps must be within [1, 20]")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    width = 16
    model = PRTATemporalAdapter(
        [nn.Identity() for _ in range(4)],
        width=width,
        heads=4,
        adapter_rank=4,
        state_tokens=4,
        transition_tokens=4,
    )
    head = NativeH1Head(width, hidden_width=16)
    parameters = [
        parameter
        for parameter in list(model.parameters()) + list(head.parameters())
        if parameter.requires_grad
    ]
    optimizer = torch.optim.AdamW(parameters, lr=1e-3)
    prior = torch.randn(5, 9, width)
    current = torch.randn(5, 9, width)
    query = torch.randn(5, width)
    target = torch.arange(5)
    losses = []
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        output = model(prior, current, query)
        logits = head(output, query)
        loss = F.cross_entropy(logits, target)
        if not torch.isfinite(loss):
            raise RuntimeError("synthetic smoke loss is not finite")
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach()))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "schema": "prta-cxr.synthetic-smoke-checkpoint.v1",
        "seed": seed,
        "steps": steps,
        "model_state": model.state_dict(),
        "head_state": head.state_dict(),
    }
    torch.save(checkpoint, output_path)
    receipt = {
        "status": "PASS_SYNTHETIC_SMOKE",
        "formal_experiment": False,
        "real_data_opened": False,
        "protected_outcomes_opened": False,
        "seed": seed,
        "steps": steps,
        "losses": losses,
        "checkpoint_path": output_path.as_posix(),
        "checkpoint_bytes": output_path.stat().st_size,
    }
    receipt_path = output_path.with_suffix(".receipt.json")
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt
