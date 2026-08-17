from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.phase16_maps import transform_rows_for_config


def _rows():
    rows = []
    for index in range(40):
        rows.append(
            {
                "sample_id": f"t-{index}",
                "patient_id_hash": f"tp-{index}",
                "source": "a" if index % 2 else "b",
                "finding": "Edema",
                "progression_label": PROGRESSION_LABELS[index % 5],
                "split": "train",
            }
        )
    for index in range(10):
        rows.append(
            {
                "sample_id": f"d-{index}",
                "patient_id_hash": f"dp-{index}",
                "source": "a" if index % 2 else "b",
                "finding": "Edema",
                "progression_label": PROGRESSION_LABELS[index % 5],
                "split": "dev",
            }
        )
    return rows


def test_transform_rows_combines_source_fraction_and_noise():
    selected, audit = transform_rows_for_config(
        _rows(),
        {
            "data": {
                "train_sources": ["a"],
                "dev_sources": ["a"],
                "train_fraction": 0.5,
                "label_noise": {"rate": 0.2, "family": "plausible", "salt": "x"},
            }
        },
    )
    train = [row for row in selected if row["split"] == "train"]
    dev = [row for row in selected if row["split"] == "dev"]
    assert len(train) == 10
    assert len(dev) == 5
    assert audit["label_noise"]["changed_rows"] == 2
    assert all("clean_progression_label" not in row for row in dev)
