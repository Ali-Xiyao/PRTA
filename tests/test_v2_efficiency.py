import json

import torch
from torch import nn

from prta_cxr.v2_efficiency import (
    benchmark_forward,
    cache_disk_inventory,
    parameter_inventory,
    profiled_flops,
    validate_efficiency_system,
)


class _TinyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.projection = nn.Linear(4, 3)

    def forward(self, prior, current, finding):
        return self.projection(prior + current + finding)


def test_parameter_benchmark_and_flops_are_reported():
    model = _TinyModel()
    inputs = (torch.ones(2, 4), torch.ones(2, 4), torch.ones(2, 4))
    inventory = parameter_inventory(model)
    benchmark = benchmark_forward(model, inputs, warmup=1, repeats=3)
    flops = profiled_flops(model, inputs)
    assert inventory == {"total": 15, "trainable": 15}
    assert benchmark["batch_size"] == 2
    assert benchmark["latency_ms"]["mean"] > 0
    assert benchmark["throughput_samples_per_second"] > 0
    assert flops["batch_flops"] > 0
    assert flops["flops_per_sample"] > 0


def test_cache_inventory_separates_active_and_archival_files(tmp_path):
    (tmp_path / "image_inventory.json").write_text("[]", encoding="utf-8")
    (tmp_path / "store.bin").write_bytes(b"1234")
    (tmp_path / "legacy.pt").write_bytes(b"legacy")
    text_cache = tmp_path / "text_cache.pt"
    text_cache.write_bytes(b"text")
    manifest = {
        "cached_image_count": 2,
        "inventory_path": "image_inventory.json",
        "training_store": {"path": "store.bin"},
        "shards": [{"path": "legacy.pt"}],
    }
    (tmp_path / "cache_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    result = cache_disk_inventory(tmp_path, text_cache)
    assert result["cached_images"] == 2
    assert result["legacy_shards_retained"] == 1
    assert result["full_archival_root_bytes"] > result["active_deployment_bytes"]


def test_efficiency_system_identity_is_narrow_and_tail8_bound():
    slim_s1 = {
        "experiment_id": "P20-FINAL-S1-S17",
        "prta_v2_variant": "Slim-S1",
        "phase20_protocol": "full-train-official-dev-slim-s1-confirmation-v1",
        "phase20_axis": "final_mainline_confirmation",
        "model": {"family": "prta", "adapter_scope": "tail8"},
    }
    assert validate_efficiency_system(slim_s1, "Slim-S1") == "prta"

    current = {
        "experiment_id": "W046-B401-S28",
        "model": {"family": "current_only", "adapter_scope": "tail4"},
    }
    assert validate_efficiency_system(current, "B401") == "current_only"

    tila_tail4 = {
        "experiment_id": "M305-B403-S17",
        "model": {"family": "tila", "adapter_scope": "tail4"},
    }
    try:
        validate_efficiency_system(tila_tail4, "TILA8")
    except ValueError as error:
        assert "Tail8" in str(error)
    else:
        raise AssertionError("Tail4 TILA must not be profiled as Tail8")

    fusion = {
        "experiment_id": "IF-F02-S43",
        "ifusion_variant": "IF-F02",
        "model": {
            "family": "symmetric_cross_attention",
            "adapter_scope": "tail8",
        },
    }
    assert validate_efficiency_system(fusion, "IF-F02") == ("symmetric_cross_attention")
