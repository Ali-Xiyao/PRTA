import pytest

from prta_cxr.state_pruning_evidence import compare_prediction_blocks


def _row(sample, prediction="Stable", delta=0.0):
    return {
        "observation_id": sample,
        "target": "Stable",
        "prediction": prediction,
        "logits": [1.0 + delta, 0.0, 0.0, 0.0, 0.0],
    }


def test_exact_state_pruning_parity_passes():
    result = compare_prediction_blocks([_row("a")], [_row("a")])
    assert result["parity_pass"] is True
    assert result["max_abs_logit_difference"] == 0.0


def test_state_pruning_parity_detects_logit_drift():
    result = compare_prediction_blocks([_row("a")], [_row("a", delta=1e-3)])
    assert result["parity_pass"] is False


def test_state_pruning_parity_rejects_roster_drift():
    with pytest.raises(ValueError, match="roster"):
        compare_prediction_blocks([_row("a")], [_row("b")])
