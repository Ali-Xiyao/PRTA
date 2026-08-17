import json
from pathlib import Path

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.phase16_safety_routing import evaluate_safety_routing


def _write_receipt(root: Path, system: str, seed: int) -> Path:
    output = root / f"{system}-S{seed}"
    output.mkdir(parents=True)
    blocks = {}
    for intervention in ("true", "matched_hard", "null", "reversed"):
        path = output / f"{intervention}.jsonl"
        rows = []
        for index, target in enumerate(PROGRESSION_LABELS):
            prediction = target
            if system == "V2" and intervention != "true":
                prediction = PROGRESSION_LABELS[(index + 1) % len(PROGRESSION_LABELS)]
            rows.append(
                {
                    "cohort": "dev",
                    "observation_id": f"o{index}",
                    "patient_id": f"p{index}",
                    "target": target,
                    "prediction": prediction,
                    "prior_intervention": intervention,
                    "system": system,
                    "training_seed": seed,
                }
            )
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        blocks[intervention] = {
            "path": path.name,
            "rows": len(rows),
            "sha256": sha256_file(path),
        }
    receipt = output / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "variant": system,
                "seed": seed,
                "prediction_blocks": blocks,
                "selection_performed": False,
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            }
        ),
        encoding="utf-8",
    )
    return receipt


def test_safety_routing_uses_current_only_for_known_invalid_prior(tmp_path: Path):
    v2 = [_write_receipt(tmp_path / "v2", "V2", seed) for seed in (17, 28, 43)]
    current = [
        _write_receipt(tmp_path / "current", "B401", seed) for seed in (17, 28, 43)
    ]
    result = evaluate_safety_routing(v2, current)
    matched = result["three_seed_summary"]["matched_hard"]
    assert matched["always_v2"]["metrics"]["macro_f1"]["mean"] == 0.0
    assert matched["invalid_to_current_only"]["metrics"]["macro_f1"]["mean"] == 1.0
    assert matched["invalid_to_abstain"]["coverage"] == 0.0
    assert result["threshold_tuning_performed"] is False
