from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import torch
from torch.utils.data import DataLoader

from prta_cxr.contracts import PROGRESSION_LABELS


@torch.no_grad()
def predict_loader(
    model: torch.nn.Module,
    loader: DataLoader,
    *,
    device: torch.device,
    temperature: float = 1.0,
    system: str,
    seed: int,
    cohort: str,
) -> list[dict[str, Any]]:
    if temperature <= 0:
        raise ValueError("inference temperature must be positive")
    model.eval()
    rows = []
    for batch in loader:
        _, logits, _ = model(
            batch["prior"].to(device),
            batch["current"].to(device),
            batch["finding_text"].to(device),
        )
        probabilities = (logits / temperature).softmax(dim=-1).cpu()
        predictions = probabilities.argmax(dim=-1).tolist()
        targets = batch["target"].tolist()
        for index, (target, prediction) in enumerate(
            zip(targets, predictions, strict=True)
        ):
            rows.append(
                {
                    "system": system,
                    "training_seed": seed,
                    "cohort": cohort,
                    "patient_id": str(batch["patient_id_hash"][index]),
                    "observation_id": str(batch["sample_id"][index]),
                    "target": PROGRESSION_LABELS[int(target)],
                    "prediction": PROGRESSION_LABELS[int(prediction)],
                    "probabilities": probabilities[index].tolist(),
                    "confidence": float(probabilities[index].max()),
                    "source": str(batch["source"][index]),
                    "finding": str(batch["finding"][index]),
                    "prior_view": str(batch["prior_view"][index]),
                    "current_view": str(batch["current_view"][index]),
                    "interval_days": float(batch["interval_days"][index]),
                    "interval_basis": str(batch["interval_basis"][index]),
                    "calendar_interval_available": bool(
                        batch["calendar_interval_available"][index]
                    ),
                    "prior_intervention": str(
                        batch["prior_intervention"][index]
                    ),
                    "query_finding": str(batch["query_finding"][index]),
                    "temperature": temperature,
                }
            )
    return rows


def logits_and_targets(
    rows: Iterable[dict[str, Any]],
) -> tuple[torch.Tensor, torch.Tensor]:
    values = list(rows)
    label_index = {label: index for index, label in enumerate(PROGRESSION_LABELS)}
    probabilities = torch.tensor(
        [row["probabilities"] for row in values], dtype=torch.float64
    ).clamp_min(1e-12)
    logits = probabilities.log()
    targets = torch.tensor(
        [label_index[str(row["target"])] for row in values], dtype=torch.long
    )
    return logits, targets
