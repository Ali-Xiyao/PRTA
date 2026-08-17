import json
from pathlib import Path

import pytest

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.ifusion_bootstrap import (
    IF_VARIANTS,
    INTERVENTIONS,
    SEEDS,
    collect_diagnostic_evidence,
    paired_ifusion_bootstrap,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _build_receipt(root: Path, system: str, seed: int, *, v2: bool) -> Path:
    output = root / f"{system}-S{seed}"
    output.mkdir(parents=True)
    blocks = {}
    for intervention in INTERVENTIONS:
        path = output / f"{intervention}.predictions.jsonl"
        rows = []
        for index, target in enumerate(PROGRESSION_LABELS):
            prediction = target
            if not v2 and index == 0:
                prediction = PROGRESSION_LABELS[1]
            rows.append(
                {
                    "cohort": "dev",
                    "observation_id": f"o{index}",
                    "patient_id": f"p{index}",
                    "prediction": prediction,
                    "prior_intervention": intervention,
                    "system": system,
                    "target": target,
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
    receipt = output / (
        "candidate_prior_diagnostic_receipt.json"
        if v2
        else "ifusion_dev_diagnostic_receipt.json"
    )
    _write_json(
        receipt,
        {
            "status": (
                "PASS_WAVE047_CANDIDATE_TRAIN_DEV_PRIOR_DIAGNOSTIC"
                if v2
                else "PASS_IFUSION_TRAIN_DEV_PRIOR_DIAGNOSTIC"
            ),
            "variant": system,
            "seed": seed,
            "prediction_blocks": blocks,
            "selection_performed": False,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
    )
    return receipt


def _build_matrix(tmp_path: Path) -> tuple[list[Path], Path]:
    if_root = tmp_path / "if"
    for variant in IF_VARIANTS:
        for seed in SEEDS:
            _build_receipt(if_root, variant, seed, v2=False)
    v2_root = tmp_path / "v2"
    entries = []
    for seed in SEEDS:
        receipt = _build_receipt(v2_root, "V2", seed, v2=True)
        entries.append(
            {
                "variant": "V2",
                "seed": seed,
                "receipt_path": str(receipt),
                "receipt_sha256": sha256_file(receipt),
            }
        )
    manifest = tmp_path / "v2_manifest.json"
    _write_json(
        manifest,
        {
            "status": "PASS_WAVE047_CANDIDATE_DIAGNOSTICS_FROZEN",
            "diagnostic_receipts": entries,
            "internal_test_opened": False,
            "gold_opened": False,
            "protected_outcome_read_count": 0,
        },
    )
    return [if_root], manifest


def test_reconcile_and_bootstrap_complete_matrix(tmp_path: Path) -> None:
    roots, v2_manifest = _build_matrix(tmp_path)
    manifest, rows = collect_diagnostic_evidence(roots, v2_manifest)
    assert manifest["if_diagnostic_cell_count"] == 33
    assert manifest["diagnostic_receipt_count"] == 36

    result = paired_ifusion_bootstrap(rows, replicates=20, rng_seed=7)
    assert result["patients"] == len(PROGRESSION_LABELS)
    assert result["observations"] == len(PROGRESSION_LABELS)
    assert len(result["contrasts"]) == len(IF_VARIANTS)
    contrast = result["contrasts"]["V2_minus_IF-A01"]
    assert contrast["scopes"]["mean_across_seeds"]["macro_f1"]["point"] > 0
    assert result["bootstrap"]["valid_replicates"] == 20


def test_reconcile_rejects_prediction_hash_drift(tmp_path: Path) -> None:
    roots, v2_manifest = _build_matrix(tmp_path)
    target = next(roots[0].rglob("true.predictions.jsonl"))
    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="prediction hash drift"):
        collect_diagnostic_evidence(roots, v2_manifest)
