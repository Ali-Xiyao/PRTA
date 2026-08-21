from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import sha256_file
from prta_cxr.prta_v2_diagnostics import diagnostic_main
from prta_cxr.state_pruning_evidence import state_pruning_compare_main
from prta_cxr.v2_efficiency import efficiency_main


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _common_args(args: argparse.Namespace) -> list[str]:
    values = [
        "--checkpoint",
        str(args.checkpoint),
        "--training-receipt",
        str(args.training_receipt),
        "--split-manifest",
        str(args.split_manifest),
        "--cleaned-split-freeze",
        str(args.cleaned_split_freeze),
        "--cleaned-split-platform-root",
        str(args.cleaned_split_platform_root),
        "--cache-root",
        str(args.cache_root),
        "--text-cache",
        str(args.text_cache),
        "--matched-hard-prior-map",
        str(args.matched_hard_prior_map),
        "--weights",
        str(args.weights),
        "--label-quality-audit",
        str(args.label_quality_audit),
    ]
    return values


def phase20_state_efficiency_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed-Seed Phase20 state-pruning parity and paired efficiency "
            "profile as one immutable evidence unit"
        )
    )
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--baseline-receipt", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--matched-hard-prior-map", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable directory")
    if args.warmup < 1 or args.repeats < 2:
        parser.error("benchmark requires --warmup >=1 and --repeats >=2")

    staging = args.output.with_name(f".{args.output.name}.preparing.{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    common = _common_args(args)
    pruned_root = staging / "pruned_export"
    diagnostic_main(
        [
            *common,
            "--output",
            str(pruned_root),
            "--device",
            args.device,
            "--batch-size",
            "16",
            "--diagnostic-scope",
            "phase20_s1",
            "--retain-logits",
            "--true-only",
            "--deployment-prune-state",
            "--formal",
        ]
    )
    pruned_receipt = pruned_root / "candidate_probability_diagnostic_receipt.json"
    parity = staging / "parity.json"
    state_pruning_compare_main(
        [
            "--baseline-receipt",
            str(args.baseline_receipt),
            "--pruned-receipt",
            str(pruned_receipt),
            "--output",
            str(parity),
            "--formal",
        ]
    )

    efficiency_paths: dict[str, Path] = {}
    for pruned in (False, True):
        suffix = "pruned" if pruned else "full"
        output = staging / f"efficiency_{suffix}.json"
        command = [
            *common,
            "--output",
            str(output),
            "--device",
            args.device,
            "--warmup",
            str(args.warmup),
            "--repeats",
            str(args.repeats),
            "--system",
            "Slim-S1",
            "--formal",
        ]
        if pruned:
            command.append("--deployment-prune-state")
        efficiency_main(command)
        efficiency_paths[suffix] = output

    parity_payload = json.loads(parity.read_text(encoding="utf-8"))
    full_payload = json.loads(efficiency_paths["full"].read_text(encoding="utf-8"))
    pruned_payload = json.loads(
        efficiency_paths["pruned"].read_text(encoding="utf-8")
    )
    if int(parity_payload.get("seed", -1)) != 43:
        raise ValueError("Phase20 state-efficiency evidence must use frozen Seed43")
    if int(full_payload.get("seed", -1)) != 43 or int(
        pruned_payload.get("seed", -1)
    ) != 43:
        raise ValueError("Phase20 efficiency evidence must use frozen Seed43")
    if full_payload.get("deployment_state_pruned") is not False:
        raise ValueError("full efficiency profile identity drift")
    if pruned_payload.get("deployment_state_pruned") is not True:
        raise ValueError("pruned efficiency profile identity drift")

    artifacts: dict[str, Any] = {
        "pruned_probability_receipt": {
            "path": "pruned_export/candidate_probability_diagnostic_receipt.json",
            "sha256": sha256_file(pruned_receipt),
        },
        "parity": {"path": parity.name, "sha256": sha256_file(parity)},
        "efficiency_full": {
            "path": efficiency_paths["full"].name,
            "sha256": sha256_file(efficiency_paths["full"]),
        },
        "efficiency_pruned": {
            "path": efficiency_paths["pruned"].name,
            "sha256": sha256_file(efficiency_paths["pruned"]),
        },
    }
    manifest = {
        "schema": "prta-cxr.phase20-state-efficiency-composite.v1",
        "status": "PASS_PHASE20_S1_STATE_PRUNING_AND_EFFICIENCY",
        "created_at": datetime.now(UTC).isoformat(),
        "seed": 43,
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "baseline_receipt_sha256": sha256_file(args.baseline_receipt),
        "artifacts": artifacts,
        "profile_scope": "cached-feature endpoint",
        "selection_performed": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(staging / "manifest.json", manifest)
    staging.replace(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0
