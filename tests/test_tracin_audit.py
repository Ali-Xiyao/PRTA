from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset

from prta_cxr.audit import runner
from prta_cxr.audit.tracin import (
    AuditContractError,
    CaptumClassificationLoss,
    LogitsOnly,
    adapter_directional_scores,
    aggregate_probe_gradient,
    audit_path,
    compute_streaming_fast_influence,
    make_tracincp_fast,
    rank_percentiles,
    select_dev_probes,
    tier_train_rows,
    validate_open_manifest,
)
from prta_cxr.contracts import PROGRESSION_LABELS


def _manifest_row(sample_id: str, split: str) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "patient_id_hash": f"patient-{sample_id}",
        "split": split,
        "source": "mimic_cxr_jpg",
        "finding": "opacity",
        "progression_label": "Stable",
        "prior_study_id": f"prior-{sample_id}",
        "current_study_id": f"current-{sample_id}",
        "prior_image_path": f"prior-{sample_id}.jpg",
        "current_image_path": f"current-{sample_id}.jpg",
        "prior_report": "prior report",
        "current_report": "current report",
    }


def test_manifest_contract_accepts_only_exact_train_dev() -> None:
    rows = [
        _manifest_row("t1", "train"),
        _manifest_row("t2", "train"),
        _manifest_row("d1", "dev"),
    ]
    receipt = validate_open_manifest(rows, expected_train=2, expected_dev=1)
    assert receipt["unique_sample_ids"] == 3
    with pytest.raises(AuditContractError, match="only train and dev"):
        validate_open_manifest(
            [*rows, _manifest_row("x", "internal_test")],
            expected_train=2,
            expected_dev=1,
        )


@pytest.mark.parametrize(
    "value",
    [
        r"H:\runtime\sealed\manifest.jsonl",
        r"H:\runtime\Gold\labels.xlsx",
        r"H:\runtime\internal-test\predictions.csv",
        r"H:\runtime\internal_test\predictions.csv",
    ],
)
def test_protected_paths_fail_before_any_open(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    opens = 0
    original = Path.open

    def monitored_open(self: Path, *args, **kwargs):
        nonlocal opens
        opens += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", monitored_open)
    with pytest.raises(AuditContractError, match="protected outcome path"):
        runner._required_file(Path(value), "forbidden fixture")
    assert opens == 0


def test_allowed_train_dev_path_and_percentiles() -> None:
    value = audit_path(r"H:\runtime\splits\train_dev_v1.jsonl", role="manifest")
    assert value.name == "train_dev_v1.jsonl"
    assert np.allclose(rank_percentiles([4, 1, 1, 3]), [1, 1 / 6, 1 / 6, 2 / 3])


def test_probe_selection_is_exact_balanced_and_deterministic() -> None:
    rows = []
    for source in ("chexpert_plus", "mimic_cxr_jpg"):
        for label in PROGRESSION_LABELS:
            for index in range(35):
                rows.append(
                    {
                        "source": source,
                        "progression_label": label,
                        "sample_id": f"{source}-{label}-{index:02d}",
                        "wrong_seed_count": 1 + int(index < 31),
                        "opposite_direction_error_seed_count": int(index < 5),
                        "mean_nll": float(index),
                        "seed_disagreement": index % 3,
                    }
                )
    first = select_dev_probes(rows)
    second = select_dev_probes(rows)
    assert first == second
    assert len(first) == 300
    assert len(set(first)) == 300
    counts: dict[tuple[str, str], int] = {}
    for index in first:
        key = (str(rows[index]["source"]), str(rows[index]["progression_label"]))
        counts[key] = counts.get(key, 0) + 1
    assert set(counts.values()) == {30}


def _tier_row(index: int) -> dict[str, object]:
    row: dict[str, object] = {
        "sample_id": str(index),
        "source": "mimic_cxr_jpg",
        "progression_label": "Stable",
        "prior_study_id": f"p{index}",
        "current_study_id": f"c{index}",
        "prior_image_path": f"p{index}.jpg",
        "current_image_path": f"c{index}.jpg",
        "prior_report": "prior",
        "current_report": "current",
        "calendar_interval_available": True,
        "interval_days": 3,
        "wrong_seed_count": 2 if index == 99 else 0,
        "seed_disagreement": 0,
        "mean_nll": float(index),
        "adapter_confirmation_unstable": False,
    }
    for seed in (17, 29, 43):
        row[f"seed{seed}_negative_influence_magnitude"] = float(index)
        row[f"seed{seed}_self_influence"] = float(index)
    return row


def test_tier_a_requires_stable_negative_influence_plus_gate() -> None:
    rows = [_tier_row(index) for index in range(100)]
    tier_train_rows(rows)
    assert rows[-1]["risk_tier"] == "Tier A"
    assert rows[-1]["negative_influence_seed_hits_top5"] == 3
    assert rows[0]["risk_tier"] == "Context"


class _TupleDataset(Dataset[tuple[torch.Tensor, ...]]):
    def __init__(self, features: torch.Tensor, labels: torch.Tensor) -> None:
        self.features = features
        self.labels = labels

    def __len__(self) -> int:
        return len(self.features)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, ...]:
        return (
            self.features[index],
            torch.zeros(1),
            torch.zeros(1),
            self.labels[index],
        )


class _TinyBase(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.linear = nn.Linear(2, 2, bias=False)
        with torch.no_grad():
            self.linear.weight.copy_(torch.tensor([[2.0, 0.0], [-2.0, 0.0]]))

    def forward(self, prior, current, finding):
        del current, finding
        return None, self.linear(prior), None


def test_captum_fast_matches_direct_gradient_dot_and_sign() -> None:
    train_features = torch.tensor([[1.0, 0.0], [-1.0, 0.0]])
    train_labels = torch.tensor([1, 1])  # first row is deliberately mislabeled
    probe_features = torch.tensor([[1.0, 0.0]])
    probe_labels = torch.tensor([0])
    train = _TupleDataset(train_features, train_labels)
    probe = _TupleDataset(probe_features, probe_labels)
    wrapper = LogitsOnly(_TinyBase()).eval()
    loss = CaptumClassificationLoss({"name": "cross_entropy"})
    influence = make_tracincp_fast(wrapper, wrapper.model.linear, train, loss)
    result = compute_streaming_fast_influence(
        influence,
        DataLoader(train, batch_size=2),
        DataLoader(probe, batch_size=1),
        learning_rate=0.1,
        device=torch.device("cpu"),
    )
    train_logits = wrapper.model.linear(train_features)
    probe_logits = wrapper.model.linear(probe_features)
    train_jacobian = train_logits.softmax(-1) - F.one_hot(train_labels, 2).float()
    probe_jacobian = probe_logits.softmax(-1) - F.one_hot(probe_labels, 2).float()
    direct = (
        (train_jacobian @ probe_jacobian.T) * (train_features @ probe_features.T) * 0.1
    ).squeeze(1)
    assert np.allclose(result.signed, direct.detach().numpy(), atol=1e-7)
    assert result.signed[0] < 0  # mislabeled same-direction row is an opponent
    assert result.negative[0] < 0
    assert np.all(result.self_influence > 0)


class _ScalarAdapter(nn.Module):
    def __init__(self, value: float) -> None:
        super().__init__()
        self.scale = nn.Parameter(torch.tensor(value))


class _TinyAdapterTail(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.adapters = nn.ModuleDict(
            {str(index): _ScalarAdapter(1.0 + index * 0.01) for index in range(4)}
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        for adapter in self.adapters.values():
            value = value * adapter.scale
        return value


class _TinyAdapterBase(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.tail = _TinyAdapterTail()
        self.native_head = nn.Linear(2, 2, bias=False)
        with torch.no_grad():
            self.native_head.weight.copy_(torch.tensor([[0.7, -0.2], [-0.4, 0.5]]))

    def forward(self, prior, current, finding):
        del current, finding
        return None, self.native_head(self.tail(prior)), None


def test_adapter_finite_difference_matches_direct_gradient_dot() -> None:
    train = _TupleDataset(torch.tensor([[1.0, 0.5], [-0.5, 1.0]]), torch.tensor([0, 1]))
    probe = _TupleDataset(torch.tensor([[0.8, 0.2]]), torch.tensor([0]))
    wrapper = LogitsOnly(_TinyAdapterBase()).eval()
    loss = CaptumClassificationLoss({"name": "cross_entropy"})
    probe_loader = DataLoader(probe, batch_size=1)
    direction = aggregate_probe_gradient(
        wrapper, probe_loader, loss, device=torch.device("cpu")
    )
    estimated = adapter_directional_scores(
        wrapper,
        DataLoader(train, batch_size=2),
        loss,
        direction,
        learning_rate=0.1,
        device=torch.device("cpu"),
    )
    selected = {
        name: parameter
        for name, parameter in wrapper.named_parameters()
        if name.startswith("model.native_head.") or ".tail.adapters." in name
    }
    direct = []
    for batch in DataLoader(train, batch_size=1):
        logits = wrapper(*batch[:-1])
        gradients = torch.autograd.grad(
            loss(logits, batch[-1]), tuple(selected.values())
        )
        score = sum(
            float((gradient * direction[name]).sum())
            for name, gradient in zip(selected, gradients, strict=True)
        )
        direct.append(score * 0.1)
    assert np.allclose(estimated, direct, rtol=2e-3, atol=2e-5)


def test_audit_source_has_no_training_step_calls() -> None:
    repo = Path(__file__).resolve().parents[1]
    result = runner.code_safety_scan(repo)
    assert result["forbidden_training_calls"] == 0
