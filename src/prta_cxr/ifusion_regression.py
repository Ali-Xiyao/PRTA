from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import (
    FORMAL_ENV_NAME,
    FORMAL_ENV_VALUE,
    require_formal_authorization,
)
from prta_cxr.contracts import sha256_file


def compare_logit_payloads(
    old: Mapping[str, Any], new: Mapping[str, Any], *, tolerance: float = 1e-6
) -> dict[str, Any]:
    old_logits = torch.as_tensor(old["logits"])
    new_logits = torch.as_tensor(new["logits"])
    if old_logits.shape != new_logits.shape:
        raise ValueError("old/new V2 regression logit shapes differ")
    if old.get("checkpoint_sha256") != new.get("checkpoint_sha256"):
        raise ValueError("old/new V2 regression checkpoint identities differ")
    maximum = float((old_logits - new_logits).abs().max().item())
    return {
        "shape": list(old_logits.shape),
        "max_abs_diff": maximum,
        "tolerance": float(tolerance),
        "passed": maximum <= tolerance,
        "old_trainable_parameters": int(old["trainable_parameters"]),
        "new_trainable_parameters": int(new["trainable_parameters"]),
        "trainable_parameter_count_equal": int(old["trainable_parameters"])
        == int(new["trainable_parameters"]),
    }


def _worker(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--weights-sha256", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    source_package = args.source.resolve() / "src" / "prta_cxr"
    for name in list(sys.modules):
        if name.startswith("prta_cxr.") and name != __name__:
            del sys.modules[name]
    package = sys.modules["prta_cxr"]
    package.__path__ = [str(source_package)]
    sys.path.insert(0, str(args.source.resolve() / "src"))

    from prta_cxr.training.engine import build_train_model
    from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported V2 regression checkpoint schema")
    config = dict(checkpoint["config"])
    if config.get("prta_v2_variant") != "V2":
        raise ValueError("V2 regression requires a frozen V2 checkpoint")
    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    visual, _ = load_biomedclip_visual(args.weights)
    blocks, final_norm = tail_modules(visual, start_block=4)
    model = build_train_model(blocks, final_norm, config)
    model.load_state_dict(checkpoint["model_state"], strict=True)
    model.to(device).eval()
    prior = torch.randn(1, 197, 768, generator=torch.Generator().manual_seed(args.seed))
    current = torch.randn(
        1, 197, 768, generator=torch.Generator().manual_seed(args.seed + 1)
    )
    finding = torch.randn(
        1, 512, generator=torch.Generator().manual_seed(args.seed + 2)
    )
    with torch.no_grad():
        _, logits, _ = model(prior.to(device), current.to(device), finding.to(device))
    payload = {
        "schema": "prta-cxr.ifusion-v2-regression-worker.v1",
        "checkpoint_sha256": args.checkpoint_sha256,
        "weights_sha256": args.weights_sha256,
        "seed": args.seed,
        "logits": logits.detach().cpu(),
        "trainable_parameters": sum(
            parameter.numel()
            for parameter in model.parameters()
            if parameter.requires_grad
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, args.output)
    return 0


def regress_ifusion_v2_main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "--worker":
        return _worker(raw[1:])
    parser = argparse.ArgumentParser(
        description="Verify frozen V2 old/new checkpoint-logit compatibility"
    )
    parser.add_argument("--old-source", type=Path, required=True)
    parser.add_argument("--old-source-commit", required=True)
    parser.add_argument("--new-source", type=Path, required=True)
    parser.add_argument("--new-source-commit", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(raw)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        raise FileExistsError(f"refusing existing V2 regression root: {args.output}")
    training_receipt = json.loads(args.training_receipt.read_text(encoding="utf-8"))
    if training_receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError("V2 regression training receipt is not terminal PASS")
    if training_receipt.get("protected_outcomes_opened") is not False:
        raise ValueError("V2 regression receipt reports protected outcome access")
    if training_receipt.get("internal_test_opened") is not False:
        raise ValueError("V2 regression receipt reports Internal-test access")

    args.output.mkdir(parents=True)
    script = Path(__file__).resolve().parents[2] / "scripts/79_regress_ifusion_v2.py"
    environment = os.environ.copy()
    environment[FORMAL_ENV_NAME] = FORMAL_ENV_VALUE
    checkpoint_sha256 = sha256_file(args.checkpoint)
    weights_sha256 = sha256_file(args.weights)
    payloads = {}
    for name, source in (("old", args.old_source), ("new", args.new_source)):
        output = args.output / f"{name}_worker.pt"
        command = [
            sys.executable,
            str(script),
            "--worker",
            "--source",
            str(source),
            "--checkpoint",
            str(args.checkpoint),
            "--checkpoint-sha256",
            checkpoint_sha256,
            "--weights",
            str(args.weights),
            "--weights-sha256",
            weights_sha256,
            "--device",
            args.device,
            "--output",
            str(output),
        ]
        subprocess.run(command, check=True, env=environment)
        payloads[name] = torch.load(output, map_location="cpu", weights_only=True)
    comparison = compare_logit_payloads(payloads["old"], payloads["new"])
    if not comparison["passed"] or not comparison["trainable_parameter_count_equal"]:
        raise RuntimeError("frozen V2 old/new regression failed")
    receipt = {
        "schema": "prta-cxr.ifusion-v2-regression.v1",
        "status": "PASS_IFUSION_V2_OLD_NEW_LOGIT_REGRESSION",
        "created_at": datetime.now(UTC).isoformat(),
        "old_source_commit": args.old_source_commit,
        "new_source_commit": args.new_source_commit,
        "checkpoint_sha256": checkpoint_sha256,
        "training_receipt_sha256": sha256_file(args.training_receipt),
        "weights_sha256": weights_sha256,
        "comparison": comparison,
        "synthetic_block4_batch": True,
        "real_data_opened": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    write_json_atomic(args.output / "regression_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
