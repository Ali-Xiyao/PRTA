from types import SimpleNamespace

import pytest
import torch
from torch import nn
from torch.utils.data import DataLoader

from prta_cxr.prta_v2_diagnostics import (
    _checkpoint_validation_hashes,
    _distribution,
    _evaluate_intervention,
    _experiment_identity_matches,
    _load_matched_map,
    _probability_export_allowed,
    _resolve_diagnostic_variant,
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


class _DiagnosticBaselineModel(nn.Module):
    def forward(self, prior, current, finding_text):
        del current
        target = finding_text[:, 0].long()
        logits = torch.full((target.shape[0], 5), -4.0, device=prior.device)
        logits.scatter_(1, target.unsqueeze(1), 4.0)
        return None, logits, finding_text


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


def test_evaluate_intervention_supports_baselines_without_prta_internals():
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
        _DiagnosticBaselineModel(),
        DataLoader(rows, batch_size=2, shuffle=False),
        device=torch.device("cpu"),
        selective_state_beta=1.0,
    )
    assert result["metrics"]["ordinary"]["macro_f1"] == pytest.approx(1.0)
    assert result["prior_reliability"] is None
    assert result["change_energy"] is None
    assert result["selective_state_weight"] is None


def test_evaluate_intervention_can_retain_logits_and_metadata():
    rows = [
        {
            "sample_id": f"sample-{index}",
            "patient_id_hash": f"patient-{index}",
            "prior": torch.tensor([1.0]),
            "current": torch.tensor([0.0]),
            "finding_text": torch.tensor([float(index)]),
            "target": index,
            "source": "source-a",
            "finding": "finding-a",
            "prior_view": "PA",
            "current_view": "AP",
            "interval_days": 4.0,
            "interval_basis": "calendar",
            "calendar_interval_available": True,
        }
        for index in range(5)
    ]
    result = _evaluate_intervention(
        _DiagnosticModel(),
        DataLoader(rows, batch_size=2, shuffle=False),
        device=torch.device("cpu"),
        selective_state_beta=1.0,
        retain_logits=True,
    )
    exported = result["prediction_rows"][0]
    assert exported["prediction"] == "Stable"
    assert exported["source"] == "source-a"
    assert len(exported["logits"]) == 5
    assert sum(exported["probabilities"]) == pytest.approx(1.0)


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


def test_ifusion_random_cmcp_validates_training_map_not_diagnostic_hard_map():
    diagnostic = {
        "split_manifest": "split",
        "text_cache": "text",
        "weights": "weights",
        "cache_manifest": "cache",
        "label_quality_audit": "quality",
        "cleaned_split_freeze": "freeze",
        "matched_hard_prior_map": "matched",
        "random_counterfactual_prior_map": "random",
    }
    checkpoint = _checkpoint_validation_hashes(diagnostic, variant="IF-A08")
    assert "matched_hard_prior_map" not in checkpoint
    assert checkpoint["random_counterfactual_prior_map"] == "random"
    _validate_checkpoint_input_hashes(checkpoint, checkpoint)

    without_random = {
        key: value
        for key, value in diagnostic.items()
        if key != "random_counterfactual_prior_map"
    }
    with pytest.raises(ValueError, match="requires the frozen random"):
        _checkpoint_validation_hashes(without_random, variant="IF-A08")


def test_ifusion_scope_uses_ifusion_variant_identity():
    variant, allowed, prefix = _resolve_diagnostic_variant(
        {"prta_v2_variant": "V2", "ifusion_variant": "IF-F02"},
        "ifusion_final",
    )

    assert variant == "IF-F02"
    assert variant in allowed
    assert prefix == "IF-"


def test_formal_baseline_scope_maps_only_allowlisted_native_families():
    variant, allowed, prefix = _resolve_diagnostic_variant(
        {"model": {"family": "current_only"}}, "formal_baseline"
    )
    assert variant == "B401"
    assert variant in allowed
    assert prefix == "B4"
    assert _experiment_identity_matches(
        "W046-B401-S28", diagnostic_scope="formal_baseline", variant="B401"
    )
    assert not _experiment_identity_matches(
        "W046-B402-S28", diagnostic_scope="formal_baseline", variant="B401"
    )


def test_probability_export_allowlist_preserves_v2_and_comparator_boundaries():
    assert _probability_export_allowed("phase20_s1", "Slim-S1")
    assert _probability_export_allowed("candidate_v0_v2", "V2")
    assert _probability_export_allowed("ifusion_final", "IF-F02")
    assert _probability_export_allowed("formal_baseline", "TILA8")
    assert not _probability_export_allowed("ifusion_final", "IF-A03")
    assert not _probability_export_allowed("formal_baseline", "B402")


def test_phase20_s1_scope_is_exact_and_probability_enabled():
    variant, allowed, prefix = _resolve_diagnostic_variant(
        {"prta_v2_variant": "Slim-S1"}, "phase20_s1"
    )
    assert variant == "Slim-S1"
    assert variant in allowed
    assert prefix == "P20-FINAL-S1-S"
    assert _experiment_identity_matches(
        "P20-FINAL-S1-S43",
        diagnostic_scope="phase20_s1",
        variant="Slim-S1",
    )
    assert not _experiment_identity_matches(
        "P20-ABL-NOSTATE-S43",
        diagnostic_scope="phase20_s1",
        variant="Slim-S1",
    )


def test_true_only_probability_fast_path_does_not_open_counterfactual_map(tmp_path):
    assert (
        _load_matched_map(
            tmp_path / "missing-map.json",
            true_only=True,
            split_manifest_sha256="split",
            cache_manifest_sha256="cache",
            cache_entry_block=8,
        )
        is None
    )
    with pytest.raises(FileNotFoundError):
        _load_matched_map(
            tmp_path / "missing-map.json",
            true_only=False,
            split_manifest_sha256="split",
            cache_manifest_sha256="cache",
            cache_entry_block=8,
        )


def test_formal_baseline_scope_distinguishes_tila_tail8_from_b403_tail4():
    tail8 = {
        "model": {"family": "tila", "adapter_scope": "tail8"},
    }
    variant, allowed, _ = _resolve_diagnostic_variant(tail8, "formal_baseline")
    assert variant == "TILA8"
    assert variant in allowed
    assert _experiment_identity_matches(
        "W047-TILA8-S43",
        diagnostic_scope="formal_baseline",
        variant="TILA8",
    )

    tail4 = {"model": {"family": "tila", "adapter_scope": "tail4"}}
    variant, allowed, _ = _resolve_diagnostic_variant(tail4, "formal_baseline")
    assert variant == ""
    assert variant not in allowed
