from types import SimpleNamespace

import pytest
import torch
from torch import nn
from torch.utils.data import DataLoader

from prta_cxr.prta_v2_diagnostics import (
    _distribution,
    _evaluate_intervention,
    _state_value,
    _validate_checkpoint_input_hashes,
)


class _DiagnosticModel(nn.Module):
    def forward(self, prior, current, finding_text):
        del current
        target = finding_text[:, 0].long()
        logits = torch.full((target.shape[0], 5), -4.0, device=prior.device)
        logits.scatter_(1, target.unsqueeze(1), 4.0)
        output = SimpleNamespace(
            prior_reliability=torch.sigmoid(prior[:, :1]),
            change_energy=prior[:, 0].square(),
        )
        return output, logits, finding_text


def test_distribution_and_checkpoint_scalar_helpers():
    summary = _distribution([torch.tensor([1.0, 2.0, 3.0])])
    assert summary is not None
    assert summary["count"] == 3
    assert summary["mean"] == pytest.approx(2.0)
    assert summary["std"] == pytest.approx((2.0 / 3.0) ** 0.5)
    assert _state_value(
        {"model.adapter.relation_residual_scale": torch.tensor(0.125)},
        "adapter.relation_residual_scale",
    ) == pytest.approx(0.125)


def test_evaluate_intervention_collects_aggregate_mechanism_statistics():
    rows = []
    for index in range(5):
        rows.append(
            {
                "sample_id": f"sample-{index}",
                "patient_id_hash": f"patient-{index}",
                "prior": torch.tensor([float(index + 1)]),
                "current": torch.tensor([0.0]),
                "finding_text": torch.tensor([float(index)]),
                "target": index,
            }
        )
    result = _evaluate_intervention(
        _DiagnosticModel(),
        DataLoader(rows, batch_size=2, shuffle=False),
        device=torch.device("cpu"),
        selective_state_beta=1.0,
    )
    assert result["metrics"]["ordinary"]["macro_f1"] == pytest.approx(1.0)
    assert result["prior_reliability"]["count"] == 5
    assert result["change_energy"]["count"] == 5
    assert result["selective_state_weight"]["count"] == 5
    assert result["predictions"] == {f"sample-{index}": index for index in range(5)}
    assert result["prediction_rows"][0] == {
        "patient_id": "patient-0",
        "observation_id": "sample-0",
        "target": "Stable",
        "prediction": "Stable",
    }


def test_checkpoint_input_hashes_accept_base_or_full_diagnostic_contract():
    diagnostic = {
        "split_manifest": "split",
        "text_cache": "text",
        "weights": "weights",
        "cache_manifest": "cache",
        "label_quality_audit": "quality",
        "cleaned_split_freeze": "freeze",
        "matched_hard_prior_map": "map",
    }
    base = {
        key: value
        for key, value in diagnostic.items()
        if key != "matched_hard_prior_map"
    }
    _validate_checkpoint_input_hashes(base, diagnostic)
    _validate_checkpoint_input_hashes(diagnostic, diagnostic)


def test_checkpoint_input_hashes_reject_unsupported_key_sets_and_hash_drift():
    diagnostic = {
        "split_manifest": "split",
        "text_cache": "text",
        "weights": "weights",
        "cache_manifest": "cache",
        "label_quality_audit": "quality",
        "cleaned_split_freeze": "freeze",
        "matched_hard_prior_map": "map",
    }
    unsupported = dict(diagnostic)
    unsupported.pop("weights")
    with pytest.raises(ValueError, match="unsupported checkpoint input-hash key set"):
        _validate_checkpoint_input_hashes(unsupported, diagnostic)

    drifted = dict(diagnostic)
    drifted["weights"] = "wrong"
    with pytest.raises(ValueError, match="diagnostic input hash mismatch for weights"):
        _validate_checkpoint_input_hashes(drifted, diagnostic)
