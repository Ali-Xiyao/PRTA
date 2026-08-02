from prta_cxr.data.sealing import (
    CACHE_INPUT_FIELDS,
    outcome_free_roster_cache_rows,
    seal_split_surfaces,
)


def test_outcome_free_roster_cache_input_drops_labels_and_patients():
    roster = [{"sample_id": "a", "clinician_label": None}]
    silver = [
        {
            "sample_id": "a",
            "source": "mimic",
            "finding": "Edema",
            "prior_image_path": "prior.png",
            "current_image_path": "current.png",
            "progression_label": "Worse",
            "patient_id_hash": "private",
        }
    ]
    rows, audit = outcome_free_roster_cache_rows(roster, silver)
    assert set(rows[0]) == set(CACHE_INPUT_FIELDS)
    assert audit["contains_human_outcomes"] is False
    assert "progression_label" not in rows[0]
    assert "patient_id_hash" not in rows[0]


def test_split_sealing_removes_outcomes_from_cache_surface():
    rows = []
    for index, split in enumerate(("train", "dev", "internal_test")):
        rows.append(
            {
                "sample_id": f"sample-{index}",
                "patient_id_hash": f"patient-{index}",
                "source": "mimic",
                "finding": "Edema",
                "prior_image_path": f"prior-{index}.jpg",
                "current_image_path": f"current-{index}.jpg",
                "progression_label": "Stable",
                "label_source": "luna",
                "label_tier": "Silver",
                "split": split,
            }
        )
    train_dev, internal_test, cache_input, audit = seal_split_surfaces(rows)
    assert len(train_dev) == 2
    assert len(internal_test) == 1
    assert len(cache_input) == 3
    assert set(cache_input[0]) == set(CACHE_INPUT_FIELDS)
    assert audit["cache_input_contains_outcomes"] is False
    assert audit["status"] == "PASS_SPLIT_SURFACES_SEALED"
