import torch
from torch import nn
from torch.utils.data import DataLoader

from prta_cxr.evaluation.inference import predict_loader


class _Model(nn.Module):
    def forward(self, prior, current, finding):
        del prior, current, finding
        logits = torch.tensor([[3.0, 0.0, 0.0, 0.0, 0.0]])
        return None, logits, None


def test_predict_loader_preserves_registered_metadata():
    dataset = [
        {
            "prior": torch.zeros(197, 8),
            "current": torch.zeros(197, 8),
            "finding_text": torch.zeros(512),
            "target": 0,
            "patient_id_hash": "patient",
            "sample_id": "sample",
            "source": "mimic",
            "finding": "Edema",
            "prior_view": "AP",
            "current_view": "AP",
            "interval_days": 10.0,
            "interval_basis": "calendar",
            "calendar_interval_available": True,
            "prior_intervention": "true",
            "query_finding": "Edema",
        }
    ]
    rows = predict_loader(
        _Model(),
        DataLoader(dataset, batch_size=1),
        device=torch.device("cpu"),
        system="PRTA",
        seed=17,
        cohort="dev",
    )
    assert rows[0]["prediction"] == "Stable"
    assert rows[0]["observation_id"] == "sample"
    assert len(rows[0]["probabilities"]) == 5
