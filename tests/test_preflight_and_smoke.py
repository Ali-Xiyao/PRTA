import json

import torch

from prta_cxr.preflight import run_preflight
from prta_cxr.training.smoke import run_synthetic_smoke


def test_preflight_is_no_data_and_hashes_authority():
    result = run_preflight()
    assert result["status"] == "PASS_PRTA_CXR_ENGINEERING_PREFLIGHT"
    assert result["formal_experiment_started"] is False
    assert result["real_data_opened"] is False
    assert result["absolute_path_hits"] == []
    assert "configs/final/prta_cxr_slim_s1.json" in result["authority_hashes"]
    assert "manifests/final_prta_cxr_checkpoints.json" in result["authority_hashes"]


def test_synthetic_smoke_saves_checkpoint_and_receipt(tmp_path):
    path = tmp_path / "smoke.pt"
    result = run_synthetic_smoke(path, steps=2)
    assert result["status"] == "PASS_SYNTHETIC_SMOKE"
    assert result["formal_experiment"] is False
    assert result["real_data_opened"] is False
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    assert checkpoint["schema"] == "prta-cxr.synthetic-smoke-checkpoint.v1"
    receipt = json.loads(path.with_suffix(".receipt.json").read_text(encoding="utf-8"))
    assert receipt["checkpoint_bytes"] > 0


def test_new_fusion_families_pass_synthetic_smoke(tmp_path):
    for family in ("early_concat", "symmetric_cross_attention"):
        path = tmp_path / f"{family}.pt"
        result = run_synthetic_smoke(path, steps=1, family=family)
        assert result["status"] == "PASS_SYNTHETIC_SMOKE"
        assert result["family"] == family
