import torch

from prta_cxr.data.cache_writer import (
    build_block8_training_store,
    write_block8_cache,
)
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key
from prta_cxr.data.training_dataset import PRTAFeatureDataset


def test_feature_dataset_joins_cache_text_and_label(tmp_path):
    inventory = []
    for path in ("prior.png", "current.png"):
        inventory.append(
            {
                "image_key": image_cache_key("source-a", path),
                "source": "source-a",
                "image_path": path,
            }
        )
    cache_root = tmp_path / "cache"
    write_block8_cache(
        cache_root, inventory, torch.randn(2, 197, 768), shard_size=2
    )
    text_path = tmp_path / "text.pt"
    torch.save(
        {
            "finding_embeddings": {"Edema": torch.randn(512)},
            "transition_prototypes": {
                "Edema|Stable": torch.randn(512),
            },
        },
        text_path,
    )
    rows = [
        {
            "sample_id": "sample-1",
            "patient_id_hash": "patient-hash",
            "source": "source-a",
            "prior_image_path": "prior.png",
            "current_image_path": "current.png",
            "finding": "Edema",
            "progression_label": "Stable",
            "split": "train",
        }
    ]
    dataset = PRTAFeatureDataset(
        rows,
        cache=Block8CacheIndex(cache_root),
        text_cache_path=text_path,
        split="train",
    )
    item = dataset[0]
    assert item["prior"].shape == (197, 768)
    assert item["finding_text"].shape == (512,)
    assert item["transition_text"].shape == (512,)
    assert item["target"] == 0


def test_feature_dataset_prefers_contiguous_training_store(tmp_path):
    inventory = [
        {
            "image_key": image_cache_key("source-a", f"image-{index}.png"),
            "source": "source-a",
            "image_path": f"image-{index}.png",
        }
        for index in range(3)
    ]
    expected = (
        torch.arange(3 * 197 * 768, dtype=torch.float32).reshape(3, 197, 768)
        / 10_000
    )
    root = tmp_path / "cache"
    write_block8_cache(root, inventory, expected, shard_size=2)
    receipt = build_block8_training_store(root)
    assert receipt["rows"] == 3
    index = Block8CacheIndex(root)
    actual = index.get_many([inventory[2]["image_key"], inventory[0]["image_key"]])
    assert index._training_store_path is not None
    assert torch.equal(actual, expected[[2, 0]].to(torch.float16))


def test_matched_wrong_prior_comes_from_a_different_patient(tmp_path):
    rows = []
    inventory = []
    for index in range(3):
        prior = f"prior-{index}.png"
        current = f"current-{index}.png"
        for path in (prior, current):
            inventory.append(
                {
                    "image_key": image_cache_key("source-a", path),
                    "source": "source-a",
                    "image_path": path,
                }
            )
        rows.append(
            {
                "sample_id": f"sample-{index}",
                "patient_id_hash": f"patient-{index}",
                "source": "source-a",
                "prior_image_path": prior,
                "current_image_path": current,
                "finding": "Edema",
                "progression_label": "Stable",
                "current_view": "AP",
                "calendar_interval_available": True,
                "interval_days": 10.0,
                "split": "dev",
            }
        )
    root = tmp_path / "cache"
    features = torch.arange(6, dtype=torch.float32).reshape(6, 1, 1).expand(
        6, 197, 768
    )
    write_block8_cache(root, inventory, features, shard_size=6)
    text = tmp_path / "text.pt"
    torch.save(
        {
            "finding_embeddings": {"Edema": torch.zeros(512)},
            "transition_prototypes": {"Edema|Stable": torch.zeros(512)},
        },
        text,
    )
    dataset = PRTAFeatureDataset(
        rows,
        cache=Block8CacheIndex(root),
        text_cache_path=text,
        split="dev",
        prior_intervention="matched_wrong",
    )
    item = dataset[0]
    assert item["matched_wrong_sample_id"] != item["sample_id"]
    wrong = rows[dataset.wrong_prior_indices[0]]
    assert wrong["patient_id_hash"] != rows[0]["patient_id_hash"]
