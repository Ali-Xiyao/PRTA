from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.protocol_freeze import validate_protocol_freeze
from prta_cxr.vlm.additional import run_vlm_additional


def vlm_additional_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the single frozen PRTA-to-VLM additional deployment"
    )
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--protocol-freeze", type=Path)
    parser.add_argument("--outcome-session", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_VLM_ADDITIONAL_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not all((args.protocol_freeze, args.outcome_session, args.output)):
        parser.error("formal VLM deployment requires freeze/outcome/output")
    freeze_raw = json.loads(args.protocol_freeze.read_text(encoding="utf-8"))
    freeze = validate_protocol_freeze(freeze_raw, receipt_path=args.protocol_freeze)
    config = json.loads(
        Path(freeze["input_paths"]["vlm_config"]).read_text(encoding="utf-8")
    )
    config["model"]["path"] = str(
        Path(freeze["input_paths"]["vlm_model_config"]).parent
    )
    outcome = json.loads(args.outcome_session.read_text(encoding="utf-8"))
    result = run_vlm_additional(
        freeze=freeze,
        config=config,
        outcome_receipt=outcome,
        output=args.output,
        device=torch.device(args.device),
        resume=args.resume,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
