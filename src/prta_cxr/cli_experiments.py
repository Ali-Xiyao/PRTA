from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.training_dataset import read_jsonl
from prta_cxr.experiments import (
    config_from_spec,
    initial_development_specs,
    materialize_classification_counts,
    nested_train_fraction,
)


def prepare_development_queue_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the outcome-sealed Train/Dev development queue"
    )
    parser.add_argument("--mode", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--base-config", type=Path)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        if args.formal:
            parser.error("preflight cannot carry --formal")
        print(json.dumps({"status": "PASS_DEVELOPMENT_QUEUE_PREFLIGHT"}, indent=2))
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not all((args.base_config, args.split_manifest, args.output)):
        parser.error("formal preparation requires base config, split, and output")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite queue root: {args.output}")
    base = json.loads(args.base_config.read_text(encoding="utf-8"))
    rows = read_jsonl(args.split_manifest)
    args.output.mkdir(parents=True)
    config_root = args.output / "configs"
    config_root.mkdir()
    queue = []
    audits = {}
    for spec in initial_development_specs():
        config = config_from_spec(base, spec)
        selected, audit = nested_train_fraction(
            rows,
            fraction=float(config["data"]["train_fraction"]),
            salt=str(config["data"]["fraction_salt"]),
        )
        config = materialize_classification_counts(config, selected)
        config_path = config_root / f"{spec['experiment_id']}.json"
        write_json_atomic(config_path, config)
        audits[str(spec["experiment_id"])] = audit
        queue.append(
            {
                "experiment_id": str(spec["experiment_id"]),
                "status": "PLANNED",
                "config_path": str(config_path.resolve()),
                "config_sha256": sha256_file(config_path),
                "effective_config_sha256": canonical_sha256(config),
                "train_fraction": float(spec["train_fraction"]),
                "seed": int(spec["seed"]),
                "internal_test_opened": False,
                "gold_opened": False,
            }
        )
    write_json_atomic(args.output / "run_queue.json", queue)
    receipt = {
        "schema": "prta-cxr.development-queue.v1",
        "status": "PASS_DEVELOPMENT_QUEUE_PREPARED",
        "base_config_sha256": sha256_file(args.base_config),
        "split_manifest_sha256": sha256_file(args.split_manifest),
        "experiments": len(queue),
        "queue_sha256": canonical_sha256(queue),
        "fraction_audits": audits,
        "rule_label_training": False,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    write_json_atomic(args.output / "preparation_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
