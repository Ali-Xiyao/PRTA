from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.protocol_freeze import freeze_formal_protocol


def protocol_freeze_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze the formal outcome protocol")
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    for name in (
        "gate-receipt",
        "formal-matrix-receipt",
        "formal-queue",
        "run-registry",
        "train-dev-manifest",
        "sealed-internal-test-manifest",
        "gold-manifest",
        "cleaned-split-freeze",
        "main-cache-manifest",
        "gold-cache-manifest",
        "weights",
        "main-text-cache",
        "gold-text-cache",
        "quality-audit",
        "protocol-config",
        "trust-config",
        "case-selection-config",
        "vlm-config",
        "vlm-model-config",
        "vlm-model-index",
        "output",
    ):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_PROTOCOL_FREEZE_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    values = {
        key: value
        for key, value in vars(args).items()
        if key not in {"mode", "formal"}
    }
    missing = [key for key, value in values.items() if value is None]
    if missing:
        parser.error("formal protocol freeze paths missing: " + ", ".join(missing))
    result = freeze_formal_protocol(
        repo_root=Path.cwd(),
        gate_receipt=args.gate_receipt,
        formal_matrix_receipt=args.formal_matrix_receipt,
        formal_queue=args.formal_queue,
        run_registry=args.run_registry,
        train_dev_manifest=args.train_dev_manifest,
        sealed_internal_test_manifest=args.sealed_internal_test_manifest,
        gold_manifest=args.gold_manifest,
        cleaned_split_freeze=args.cleaned_split_freeze,
        main_cache_manifest=args.main_cache_manifest,
        gold_cache_manifest=args.gold_cache_manifest,
        weights=args.weights,
        main_text_cache=args.main_text_cache,
        gold_text_cache=args.gold_text_cache,
        quality_audit=args.quality_audit,
        protocol_config=args.protocol_config,
        trust_config=args.trust_config,
        case_selection_config=args.case_selection_config,
        vlm_config=args.vlm_config,
        vlm_model_config=args.vlm_model_config,
        vlm_model_index=args.vlm_model_index,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
