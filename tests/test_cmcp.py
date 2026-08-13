import json

import pytest
import torch

from prta_cxr.contracts import ContractError
from prta_cxr.data.cmcp import build_cmcp_matches, transition_examples
from prta_cxr.data.hard_cmcp import (
    build_matched_hard_prior_entries,
    read_matched_hard_prior_map,
)


def test_cmcp_is_cross_patient_and_opposite_label():
    pairs = [
        {
            "pair_id": "a",
            "patient_id": "p1",
            "partition": "train",
            "current_view": "PA",
            "prior_dicom_id": "a0",
            "current_dicom_id": "a1",
            "transition_supervision": [{"finding": "effusion", "label": "Worse"}],
        },
        {
            "pair_id": "b",
            "patient_id": "p2",
            "partition": "train",
            "current_view": "PA",
            "prior_dicom_id": "b0",
            "current_dicom_id": "b1",
            "transition_supervision": [{"finding": "effusion", "label": "Improved"}],
        },
    ]
    examples = transition_examples(pairs)
    matches, audit = build_cmcp_matches(
        examples, {"a1": torch.tensor([1.0, 0.0]), "b1": torch.tensor([0.9, 0.1])}
    )
    assert len(matches) == 2
    assert audit["coverage"] == 1.0
    assert all(
        row["target_patient_id"] != row["counterfactual_patient_id"] for row in matches
    )
    assert all(row["target_label"] != row["counterfactual_label"] for row in matches)


def test_training_hard_cmcp_is_finding_matched_and_cosine_hard():
    rows = [
        {
            "sample_id": "target",
            "patient_id_hash": "p0",
            "split": "train",
            "source": "a",
            "finding": "Edema",
            "current_view": "PA",
            "prior_image_path": "p0.png",
            "current_image_path": "c0.png",
            "progression_label": "Stable",
        },
        {
            "sample_id": "hard",
            "patient_id_hash": "p1",
            "split": "train",
            "source": "a",
            "finding": "Edema",
            "current_view": "PA",
            "prior_image_path": "p1.png",
            "current_image_path": "c1.png",
            "progression_label": "Worse",
        },
        {
            "sample_id": "easy",
            "patient_id_hash": "p2",
            "split": "train",
            "source": "a",
            "finding": "Edema",
            "current_view": "PA",
            "prior_image_path": "p2.png",
            "current_image_path": "c2.png",
            "progression_label": "Improved",
        },
    ]
    embeddings = {
        "target": torch.tensor([1.0, 0.0]),
        "hard": torch.tensor([0.99, 0.01]),
        "easy": torch.tensor([0.0, 1.0]),
    }
    entries, audit = build_matched_hard_prior_entries(rows, embeddings)
    match = next(row for row in entries if row["target_sample_id"] == "target")
    assert match["counterfactual_sample_id"] == "hard"
    assert match["finding"] == "Edema"
    assert match["target_label"] != match["counterfactual_label"]
    assert audit["coverage"] == 1.0


def test_matched_hard_map_fails_closed_on_input_identity_drift(tmp_path):
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps(
            {
                "schema": "prta-cxr.matched-hard-prior-map.v1",
                "split_manifest_sha256": "split-a",
                "cache_manifest_sha256": "cache-a",
                "cache_entry_block": 4,
                "entries": [
                    {
                        "target_sample_id": "target",
                        "counterfactual_sample_id": "candidate",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert read_matched_hard_prior_map(
        path,
        expected_split_manifest_sha256="split-a",
        expected_cache_manifest_sha256="cache-a",
        expected_cache_entry_block=4,
    ) == {"target": "candidate"}
    with pytest.raises(ContractError, match="split_manifest_sha256 mismatch"):
        read_matched_hard_prior_map(
            path,
            expected_split_manifest_sha256="split-b",
        )
    with pytest.raises(ContractError, match="cache_manifest_sha256 mismatch"):
        read_matched_hard_prior_map(
            path,
            expected_cache_manifest_sha256="cache-b",
        )
    with pytest.raises(ContractError, match="cache_entry_block mismatch"):
        read_matched_hard_prior_map(path, expected_cache_entry_block=8)
