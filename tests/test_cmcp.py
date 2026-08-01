import torch

from prta_cxr.data.cmcp import build_cmcp_matches, transition_examples


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
        row["target_patient_id"] != row["counterfactual_patient_id"]
        for row in matches
    )
    assert all(row["target_label"] != row["counterfactual_label"] for row in matches)
