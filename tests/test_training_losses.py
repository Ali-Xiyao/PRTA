import pytest
import torch

from prta_cxr.training.losses import progression_classification_loss


@pytest.mark.parametrize(
    "name",
    ("cross_entropy", "weighted_ce", "balanced_softmax", "class_balanced_focal"),
)
def test_registered_classification_losses_are_finite(name):
    logits = torch.randn(10, 5, requires_grad=True)
    target = torch.arange(10) % 5
    spec = {
        "name": name,
        "class_counts": [100, 80, 20, 70, 60],
        "beta": 0.999,
        "gamma": 2.0,
    }
    loss = progression_classification_loss(logits, target, spec)
    assert loss.ndim == 0
    assert torch.isfinite(loss)
    loss.backward()
    assert logits.grad is not None


def test_imbalance_losses_require_valid_class_counts():
    with pytest.raises(ValueError, match="five class counts"):
        progression_classification_loss(
            torch.randn(2, 5),
            torch.tensor([0, 1]),
            {"name": "weighted_ce"},
        )
