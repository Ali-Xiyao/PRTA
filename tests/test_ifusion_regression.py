import pytest
import torch

from prta_cxr.ifusion_regression import compare_logit_payloads


def test_ifusion_v2_regression_accepts_tolerance_and_equal_parameters():
    old = {
        "logits": torch.tensor([[1.0, 2.0]]),
        "checkpoint_sha256": "checkpoint",
        "trainable_parameters": 10,
    }
    new = {
        "logits": torch.tensor([[1.0, 2.0 + 5e-7]]),
        "checkpoint_sha256": "checkpoint",
        "trainable_parameters": 10,
    }
    result = compare_logit_payloads(old, new)
    assert result["passed"]
    assert result["trainable_parameter_count_equal"]


def test_ifusion_v2_regression_rejects_checkpoint_drift():
    with pytest.raises(ValueError, match="checkpoint identities"):
        compare_logit_payloads(
            {
                "logits": torch.zeros(1, 2),
                "checkpoint_sha256": "old",
                "trainable_parameters": 10,
            },
            {
                "logits": torch.zeros(1, 2),
                "checkpoint_sha256": "new",
                "trainable_parameters": 10,
            },
        )
