from prta_cxr.contracts import PROGRESSION_LABELS
from prta_cxr.phase20_b2_statistics import (
    COMPARATOR_SYSTEMS,
    INTERVENTIONS,
    SEEDS,
    phase20_b2_statistics,
)


def _rows(system, seed, intervention="true"):
    rows = []
    for index, target in enumerate(PROGRESSION_LABELS):
        prediction = target
        if system == "B402" and index == seed % len(PROGRESSION_LABELS):
            prediction = PROGRESSION_LABELS[(index + 1) % len(PROGRESSION_LABELS)]
        if system == "Slim-S1" and intervention != "true" and index == 0:
            prediction = PROGRESSION_LABELS[1]
        rows.append(
            {
                "patient_id": f"patient-{index}",
                "observation_id": f"observation-{index}",
                "target": target,
                "prediction": prediction,
                "confidence": 0.9 - index * 0.05,
            }
        )
    return rows


def test_phase20_b2_runs_cluster_bootstrap_holm_disagreement_and_routing():
    loaded = {
        "Slim-S1": {
            seed: {
                intervention: _rows("Slim-S1", seed, intervention)
                for intervention in INTERVENTIONS
            }
            for seed in SEEDS
        }
    }
    for system in COMPARATOR_SYSTEMS:
        loaded[system] = {seed: {"true": _rows(system, seed)} for seed in SEEDS}
    result = phase20_b2_statistics(loaded, replicates=20, rng_seed=7)
    assert result["status"] == "PASS_PHASE20_B2_POST_COMPARATOR_STATISTICS"
    assert result["bootstrap"]["replicates"] == 20
    contrast = result["bootstrap"]["contrasts"]["S1_vs_S0"]
    assert "holm_adjusted_p" in contrast["scopes"]["mean_across_seeds"]["macro_f1"]
    assert result["three_seed_disagreement"]["Slim-S1"]["rows"] == len(
        PROGRESSION_LABELS
    )
    assert (
        result["safety_routing"]["by_intervention"]["null"]["17"]["invalid_to_abstain"][
            "status"
        ]
        == "ABSTAIN_ALL"
    )
    assert (
        result["strongest_compatible_comparator"]["inference_role"]
        == "outcome-ranked exploratory; excluded from Holm family"
    )
