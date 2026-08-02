import json

import torch

from prta_cxr.data.cache_writer import write_block8_cache
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key


def test_generic_block8_cache_uses_relative_paths(tmp_path):
    part = tmp_path / "part0"
    part.mkdir()
    torch.save({"features": torch.randn(2, 197, 768)}, part / "shard.pt")
    (part / "image_inventory.json").write_text(
        json.dumps([{"dicom_id": "a"}, {"dicom_id": "b"}]), encoding="utf-8"
    )
    (part / "manifest.json").write_text(
        json.dumps({"shards": [{"path": "shard.pt", "images": 2}]}),
        encoding="utf-8",
    )
    (tmp_path / "cache_manifest.json").write_text(
        json.dumps(
            {
                "status": "PASS_PRTA_CXR_BLOCK8_CACHE",
                "cached_image_count": 2,
                "parts": [{"manifest_path": "part0/manifest.json"}],
            }
        ),
        encoding="utf-8",
    )
    cache = Block8CacheIndex(tmp_path)
    assert cache.get_many(["b", "a"]).shape == (2, 197, 768)


def test_direct_cache_round_trip_and_namespaced_key(tmp_path):
    first = image_cache_key("mimic", "folder/image.jpg")
    second = image_cache_key("chexpert", "folder/image.jpg")
    assert first != second
    inventory = [
        {
            "image_key": first,
            "source": "mimic",
            "image_path": "folder/image.jpg",
        },
        {
            "image_key": second,
            "source": "chexpert",
            "image_path": "folder/image.jpg",
        },
    ]
    features = torch.randn(2, 197, 768)
    root = tmp_path / "cache"
    manifest = write_block8_cache(root, inventory, features, shard_size=1)
    assert manifest["contains_labels"] is False
    cache = Block8CacheIndex(root)
    loaded = cache.get_many([second, first])
    assert loaded.dtype == torch.float16
    assert loaded.shape == (2, 197, 768)
