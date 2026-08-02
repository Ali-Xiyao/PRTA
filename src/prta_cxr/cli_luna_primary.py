from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import FormalExecutionBlocked, require_formal_authorization
from prta_cxr.cli_independent_silver import synthetic_ai_rows
from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.contracts import canonical_sha256
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.independent_silver import (
    externalize_independent_batch,
    load_independent_ai_output,
)
from prta_cxr.luna_primary import (
    apply_training_patient_quarantine,
    merge_luna_primary,
    select_gold_audit_roster,
)

DEFAULT_CONFIG = Path("configs/labeling/luna_primary_full_v1.json")


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _require_fresh_outputs(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"refusing existing output artifacts: {existing}")


def _validate_full_merge_authority(
    config_path: Path,
    samples: list[dict[str, Any]],
    batch_paths: list[Path],
    output_paths: list[Path],
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("admission_policy") != (
        "retain_valid_luna_five_class_discard_unclear"
    ):
        raise FormalExecutionBlocked("config does not authorize Luna-primary merge")
    if config.get("rule_label_used_for_admission") is not False:
        raise FormalExecutionBlocked("config must prohibit rule-label admission")
    if config.get("full_candidate_rows") != len(samples):
        raise FormalExecutionBlocked("full candidate row count mismatch at merge")
    if config.get("candidate_manifest_sha256") != canonical_sha256(samples):
        raise FormalExecutionBlocked("candidate manifest hash mismatch at merge")
    batch_size = int(config["batch_size"])
    expected_batches = (len(samples) + batch_size - 1) // batch_size
    expected_names = {f"batch_{index:05d}.json" for index in range(expected_batches)}
    batch_names = {path.name for path in batch_paths}
    output_names = {path.name for path in output_paths}
    if batch_names != expected_names or output_names != expected_names:
        raise FormalExecutionBlocked(
            "full Luna input/output batch set is incomplete or contains extras"
        )
    for batch_path, output_path in zip(batch_paths, output_paths, strict=True):
        if batch_path.name != output_path.name:
            raise FormalExecutionBlocked("Luna input/output batch names differ")
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        externalize_independent_batch(batch)
        expected_ids = set(batch["sample_id_map"].values())
        rows = load_independent_ai_output(output_path)
        if {row["sample_id"] for row in rows} != expected_ids:
            raise FormalExecutionBlocked(
                f"Luna output IDs do not match input batch: {batch_path.name}"
            )
    return config


def merge_luna_primary_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge Luna-primary Silver labels")
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--batch-dir", type=Path)
    parser.add_argument("--luna-output-dir", type=Path)
    parser.add_argument("--accepted-output", type=Path)
    parser.add_argument("--discarded-output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        samples = synthetic_samples()
        accepted, discarded, audit = merge_luna_primary(
            samples, synthetic_ai_rows(samples)
        )
        _print(
            {
                "status": "PASS_LUNA_PRIMARY_MERGE_PREFLIGHT",
                "accepted": len(accepted),
                "discarded": len(discarded),
                "audit": audit,
                "real_labels_opened": False,
            }
        )
        return 0
    require_formal_authorization(formal_flag=args.formal)
    required = (
        args.candidates,
        args.batch_dir,
        args.luna_output_dir,
        args.accepted_output,
        args.discarded_output,
        args.audit_output,
    )
    if not all(required):
        parser.error("formal mode requires all input and output paths")
    _require_fresh_outputs(
        args.accepted_output, args.discarded_output, args.audit_output
    )
    samples = read_jsonl(args.candidates)
    batch_paths = sorted(args.batch_dir.glob("batch_*.json"))
    output_paths = sorted(args.luna_output_dir.glob("batch_*.json"))
    config = _validate_full_merge_authority(
        args.config, samples, batch_paths, output_paths
    )
    luna_rows = []
    for path in output_paths:
        luna_rows.extend(load_independent_ai_output(path))
    if not luna_rows:
        raise RuntimeError("no Luna-primary outputs found")
    accepted, discarded, audit = merge_luna_primary(samples, luna_rows)
    audit["config_authorized_scope"] = config["authorized_scope"]
    write_jsonl_atomic(args.accepted_output, accepted)
    write_jsonl_atomic(args.discarded_output, discarded)
    write_json_atomic(args.audit_output, audit)
    _print(audit)
    return 0


def prepare_gold_audit_roster_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare patient-quarantined Luna Silver human review roster"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--silver", type=Path)
    parser.add_argument("--roster-output", type=Path)
    parser.add_argument("--quarantine-output", type=Path)
    parser.add_argument("--training-eligible-output", type=Path)
    parser.add_argument("--quarantined-silver-output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--roster-size", type=int, default=250)
    parser.add_argument("--salt", default="prta-cxr-luna-primary-gold-audit-v1")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        rows = []
        samples = synthetic_samples()
        for source in ("mimic", "chexpert"):
            for patient in range(150):
                row = samples[patient % 5].copy()
                row["sample_id"] = f"{source}-{patient}"
                row["patient_id_hash"] = f"{source}-patient-{patient}"
                row["source"] = source
                row["progression_label"] = samples[patient % 5]["progression_label"]
                row["label_source"] = "luna_primary_report_label"
                row["label_tier"] = "Silver"
                rows.append(row)
        roster, quarantine, audit = select_gold_audit_roster(
            rows, roster_size=args.roster_size, salt=args.salt
        )
        training_eligible, quarantined_silver, quarantine_audit = (
            apply_training_patient_quarantine(rows, quarantine)
        )
        _print(
            {
                "status": "PASS_GOLD_AUDIT_ROSTER_PREFLIGHT",
                "roster": len(roster),
                "quarantine": len(quarantine),
                "audit": audit,
                "training_eligible": len(training_eligible),
                "quarantined_silver": len(quarantined_silver),
                "quarantine_audit": quarantine_audit,
                "real_labels_opened": False,
            }
        )
        return 0
    require_formal_authorization(formal_flag=args.formal)
    required = (
        args.silver,
        args.roster_output,
        args.quarantine_output,
        args.training_eligible_output,
        args.quarantined_silver_output,
        args.audit_output,
    )
    if not all(required):
        parser.error("formal mode requires all input and output paths")
    _require_fresh_outputs(
        args.roster_output,
        args.quarantine_output,
        args.training_eligible_output,
        args.quarantined_silver_output,
        args.audit_output,
    )
    rows = read_jsonl(args.silver)
    roster, quarantine, audit = select_gold_audit_roster(
        rows, roster_size=args.roster_size, salt=args.salt
    )
    training_eligible, quarantined_silver, quarantine_audit = (
        apply_training_patient_quarantine(rows, quarantine)
    )
    audit["training_quarantine"] = quarantine_audit
    write_jsonl_atomic(args.roster_output, roster)
    write_jsonl_atomic(args.quarantine_output, quarantine)
    write_jsonl_atomic(args.training_eligible_output, training_eligible)
    write_jsonl_atomic(args.quarantined_silver_output, quarantined_silver)
    write_json_atomic(args.audit_output, audit)
    _print(audit)
    return 0
