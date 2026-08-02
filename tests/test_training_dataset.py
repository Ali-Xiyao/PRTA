import torch

from prta_cxr.data.cache_writer import write_block8_cache
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
