import json
from pathlib import Path

from prta_cxr.phase20_state_efficiency import phase20_state_efficiency_main


def _option(argv: list[str], name: str) -> Path:
    return Path(argv[argv.index(name) + 1])


def test_phase20_state_efficiency_is_one_immutable_seed43_unit(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "PRTA_CXR_ALLOW_FORMAL", "I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN"
    )
    baseline = tmp_path / "baseline" / "candidate_probability_diagnostic_receipt.json"
    baseline.parent.mkdir()
    baseline.write_text("{}", encoding="utf-8")
    checkpoint = tmp_path / "best.pt"
    checkpoint.write_bytes(b"checkpoint")

    def fake_diagnostic(argv):
        output = _option(argv, "--output")
        output.mkdir(parents=True)
        (output / "true.predictions.jsonl").write_text("{}\n", encoding="utf-8")
        (output / "candidate_probability_diagnostic_receipt.json").write_text(
            json.dumps({"seed": 43}), encoding="utf-8"
        )
        return 0

    def fake_compare(argv):
        output = _option(argv, "--output")
        output.write_text(
            json.dumps({"status": "PASS_STATE_PRUNING_LOGIT_PARITY", "seed": 43}),
            encoding="utf-8",
        )
        return 0

    def fake_efficiency(argv):
        output = _option(argv, "--output")
        output.write_text(
            json.dumps(
                {
                    "status": "PASS_PHASE20_S1_FIXED_HARDWARE_EFFICIENCY",
                    "seed": 43,
                    "deployment_state_pruned": "--deployment-prune-state" in argv,
                }
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(
        "prta_cxr.phase20_state_efficiency.diagnostic_main", fake_diagnostic
    )
    monkeypatch.setattr(
        "prta_cxr.phase20_state_efficiency.state_pruning_compare_main", fake_compare
    )
    monkeypatch.setattr(
        "prta_cxr.phase20_state_efficiency.efficiency_main", fake_efficiency
    )

    output = tmp_path / "evidence"
    common_files = {
        name: tmp_path / f"{name}.bin"
        for name in (
            "training-receipt",
            "split-manifest",
            "cleaned-split-freeze",
            "text-cache",
            "matched-hard-prior-map",
            "weights",
            "label-quality-audit",
        )
    }
    for path in common_files.values():
        path.write_bytes(b"x")
    cleaned_root = tmp_path / "cleaned"
    cache_root = tmp_path / "cache"
    cleaned_root.mkdir()
    cache_root.mkdir()
    argv = [
        "--checkpoint",
        str(checkpoint),
        "--baseline-receipt",
        str(baseline),
        "--cleaned-split-platform-root",
        str(cleaned_root),
        "--cache-root",
        str(cache_root),
        "--output",
        str(output),
        "--formal",
    ]
    for option, path in common_files.items():
        argv.extend([f"--{option}", str(path)])
    assert phase20_state_efficiency_main(argv) == 0
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS_PHASE20_S1_STATE_PRUNING_AND_EFFICIENCY"
    assert manifest["seed"] == 43
    assert set(manifest["artifacts"]) == {
        "pruned_probability_receipt",
        "parity",
        "efficiency_full",
        "efficiency_pruned",
    }
