import json

import pytest
import torch

from prta_cxr.data.cache_writer import (
    finalize_streaming_block8_cache,
    prepare_streaming_block8_cache,
    write_block8_cache,
    write_streaming_block8_shard,
)
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


def test_block4_cache_has_distinct_identity_and_remains_indexable(tmp_path):
    inventory = [
        {
            "image_key": image_cache_key("mimic", "image.jpg"),
            "source": "mimic",
            "image_path": "image.jpg",
        }
    ]
    root = tmp_path / "block4"
    manifest = write_block8_cache(
        root,
        inventory,
        torch.randn(1, 197, 768),
        encoder_receipt={"output_block": 4},
    )
    assert manifest["schema"] == "prta-cxr.block4-cache.v1"
    assert manifest["status"] == "PASS_PRTA_CXR_BLOCK4_CACHE"
    assert manifest["shards"][0]["path"] == "block4_00000.pt"
    cache = Block8CacheIndex(root)
    assert cache.cache_entry_block == 4
    assert cache.get_many([inventory[0]["image_key"]]).shape == (1, 197, 768)


def test_block2_cache_has_distinct_identity_and_remains_indexable(tmp_path):
    inventory = [
        {
            "image_key": image_cache_key("mimic", "image.jpg"),
            "source": "mimic",
            "image_path": "image.jpg",
        }
    ]
    root = tmp_path / "block2"
    manifest = write_block8_cache(
        root,
        inventory,
        torch.randn(1, 197, 768),
        encoder_receipt={"output_block": 2},
    )
    assert manifest["schema"] == "prta-cxr.block2-cache.v1"
    assert manifest["status"] == "PASS_PRTA_CXR_BLOCK2_CACHE"
    assert manifest["shards"][0]["path"] == "block2_00000.pt"
    cache = Block8CacheIndex(root)
    assert cache.cache_entry_block == 2
    assert cache.get_many([inventory[0]["image_key"]]).shape == (1, 197, 768)


def test_streaming_cache_resumes_without_rewriting_completed_shards(tmp_path):
    inventory = [
        {
            "image_key": image_cache_key("mimic", f"image-{index}.jpg"),
            "source": "mimic",
            "image_path": f"image-{index}.jpg",
        }
        for index in range(5)
    ]
    root = tmp_path / "streaming"
    normalized, state = prepare_streaming_block8_cache(
        root,
        inventory,
        shard_size=2,
        encoder_receipt={"weights_sha256": "a" * 64},
        resume=False,
    )
    assert normalized == inventory
    write_streaming_block8_shard(root, state, torch.randn(2, 197, 768))
    first_hash = state["shards"][0]["sha256"]

    normalized, state = prepare_streaming_block8_cache(
        root,
        inventory,
        shard_size=2,
        encoder_receipt={"weights_sha256": "a" * 64},
        resume=True,
    )
    assert state["completed_images"] == 2
    write_streaming_block8_shard(root, state, torch.randn(2, 197, 768))
    write_streaming_block8_shard(root, state, torch.randn(1, 197, 768))
    manifest = finalize_streaming_block8_cache(root, state)
    assert manifest["resume_safe"] is True
    assert manifest["cached_image_count"] == 5
    assert manifest["shards"][0]["sha256"] == first_hash
    cache = Block8CacheIndex(root)
    assert len(cache) == 5


def test_streaming_cache_resume_rejects_inventory_change(tmp_path):
    inventory = [
        {
            "image_key": image_cache_key("mimic", "one.jpg"),
            "source": "mimic",
            "image_path": "one.jpg",
        }
    ]
    root = tmp_path / "streaming"
    prepare_streaming_block8_cache(
        root,
        inventory,
        shard_size=1,
        encoder_receipt={"weights_sha256": "b" * 64},
        resume=False,
    )
    changed = [dict(inventory[0], image_path="changed.jpg")]
    with pytest.raises(ValueError, match="identity mismatch"):
        prepare_streaming_block8_cache(
            root,
            changed,
            shard_size=1,
            encoder_receipt={"weights_sha256": "b" * 64},
            resume=True,
        )
