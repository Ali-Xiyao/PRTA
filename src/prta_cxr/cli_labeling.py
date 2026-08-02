from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.label_batches import load_luna_output, prepare_luna_batches
from prta_cxr.label_rules import candidate_samples
from prta_cxr.labeling import merge_luna_labels

DEFAULT_PROMPT = Path("prompts/luna_label_v1.md")
DEFAULT_SCHEMA = Path("schemas/luna_label_batch.schema.json")


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def synthetic_samples() -> list[dict[str, Any]]:
    labels = ("Stable", "Improved", "Worse", "New", "Resolved")
    output = []
    for index, label in enumerate(labels):
        output.append(
            {
                "sample_id": f"synthetic-label-{index}",
                "patient_id_hash": f"synthetic-hash-{index}",
                "source": "synthetic",
                "prior_study_id": f"prior-{index}",
                "current_study_id": f"current-{index}",
                "prior_image_path": f"synthetic/prior-{index}.png",
                "current_image_path": f"synthetic/current-{index}.png",
                "prior_report": "Prior report evidence.",
                "current_report": f"Current report evidence for {label}.",
                "prior_datetime": "2025-01-01T00:00:00",
                "current_datetime": "2025-01-02T00:00:00",
                "interval_days": 1,
                "interval_basis": "calendar",
                "calendar_interval_available": True,
                "interval_semantics": "elapsed_calendar_days",
                "prior_view": "PA",
                "current_view": "PA",
                "finding": "Pleural Effusion",
                "progression_label": label,
                "label_source": "synthetic_rule",
                "label_tier": "Tier-B",
            }
        )
    return output


def synthetic_luna_rows(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sample_id": row["sample_id"],
            "finding": row["finding"],
            "verified_label": row["progression_label"],
            "decision": "accept",
            "prior_evidence": "Prior report evidence.",
            "current_evidence": "Current report evidence.",
            "comparison_evidence": "Synthetic direction evidence.",
            "comparison_matches_selected_prior": True,
            "finding_match": True,
            "negation_conflict": False,
            "uncertainty_conflict": False,
            "temporal_conflict": False,
            "reason_code": "synthetic_consistent_direction",
        }
        for row in samples
    ]


def prepare_luna_batches_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create deterministic rule candidates and de-identified Luna batches"
        )
    )
    parser.add_argument(
        "--mode", choices=("preflight", "synthetic", "formal"), default="preflight"
    )
    parser.add_argument("--pairs", type=Path)
    parser.add_argument("--candidate-output", type=Path)
    parser.add_argument("--batch-dir", type=Path)
    parser.add_argument("--receipt-output", type=Path)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        batches, receipt = prepare_luna_batches(
            synthetic_samples(),
            batch_size=args.batch_size,
            prompt_path=args.prompt,
            schema_path=args.schema,
        )
        _print(
            {
                "status": "PASS_PREPARE_LUNA_PREFLIGHT",
                "batches": len(batches),
                "receipt": receipt,
                "real_reports_opened": False,
                "external_call_made": False,
            }
        )
        return 0
    if args.mode == "formal":
        require_formal_authorization(formal_flag=args.formal)
        if not all(
            (args.pairs, args.candidate_output, args.batch_dir, args.receipt_output)
        ):
            parser.error(
                "formal mode requires --pairs, --candidate-output, --batch-dir, "
                "and --receipt-output"
            )
        pairs = read_jsonl(args.pairs)
        samples, rule_audit = candidate_samples(pairs)
        if not samples:
            raise RuntimeError("rule extraction produced zero Luna candidates")
    else:
        samples = synthetic_samples()
        rule_audit = {
            "schema": "prta-cxr.synthetic-rule-audit.v1",
            "candidate_samples": len(samples),
        }
    batches, receipt = prepare_luna_batches(
        samples,
        batch_size=args.batch_size,
        prompt_path=args.prompt,
        schema_path=args.schema,
    )
    result = {
        "status": "PASS_PREPARE_LUNA_FORMAL"
        if args.mode == "formal"
        else "PASS_PREPARE_LUNA_SYNTHETIC",
        "rule_audit": rule_audit,
        "batch_receipt": receipt,
        "external_call_made": False,
    }
    if args.candidate_output:
        write_jsonl_atomic(args.candidate_output, samples)
    if args.batch_dir:
        if args.batch_dir.exists():
            raise FileExistsError(f"refusing existing batch dir: {args.batch_dir}")
        args.batch_dir.mkdir(parents=True)
        for batch in batches:
            write_json_atomic(args.batch_dir / f"{batch['batch_id']}.json", batch)
    if args.receipt_output:
        write_json_atomic(args.receipt_output, result)
    _print(result)
    return 0


def luna_command(*, model: str, schema: Path, output: Path) -> list[str]:
    return [
        "codex",
        "exec",
        "-m",
        model,
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--ignore-user-config",
        "--ignore-rules",
        "--output-schema",
        str(schema),
        "-o",
        str(output),
        "-",
    ]


def run_luna_labeling_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run locked Luna labeling batches")
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--batch-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--receipt-output", type=Path)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    preview = luna_command(
        model=args.model, schema=args.schema, output=Path("OUTPUT.json")
    )
    if args.mode == "preflight":
        _print(
            {
                "status": "PASS_LUNA_RUNNER_PREFLIGHT",
                "command": preview,
                "prompt_sha256": sha256_file(args.prompt),
                "schema_sha256": sha256_file(args.schema),
                "external_call_made": False,
            }
        )
        return 0
    require_formal_authorization(formal_flag=args.formal)
    if not args.execute:
        parser.error("formal Luna mode also requires --execute")
    if not all((args.batch_dir, args.output_dir, args.receipt_output)):
        parser.error("formal mode requires batch/output dirs and receipt output")
    if args.output_dir.exists():
        raise FileExistsError(f"refusing existing output dir: {args.output_dir}")
    args.output_dir.mkdir(parents=True)
    prompt = args.prompt.read_text(encoding="utf-8")
    receipts = []
    for batch_path in sorted(args.batch_dir.glob("batch_*.json")):
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        output = args.output_dir / batch_path.name
        command = luna_command(model=args.model, schema=args.schema, output=output)
        payload = prompt + "\n\nINPUT_BATCH_JSON:\n" + json.dumps(batch)
        completed = subprocess.run(
            command,
            input=payload,
            text=True,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Luna batch failed closed: {batch_path.name}; "
                f"exit={completed.returncode}"
            )
        rows = load_luna_output(output)
        expected = {item["sample_id"] for item in batch["items"]}
        if {row["sample_id"] for row in rows} != expected:
            raise RuntimeError(f"Luna IDs mismatch for {batch_path.name}")
        receipts.append(
            {
                "batch_id": batch["batch_id"],
                "input_sha256": batch["input_sha256"],
                "output_sha256": sha256_file(output),
                "model": args.model,
                "rows": len(rows),
            }
        )
    if not receipts:
        raise RuntimeError("no Luna input batches found")
    result = {
        "status": "PASS_LUNA_BATCH_RUN",
        "external_call_made": True,
        "prompt_sha256": sha256_file(args.prompt),
        "schema_sha256": sha256_file(args.schema),
        "batches": receipts,
    }
    write_json_atomic(args.receipt_output, result)
    _print(result)
    return 0


def merge_and_audit_labels_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge and audit Luna labels")
    parser.add_argument(
        "--mode", choices=("preflight", "synthetic", "formal"), default="preflight"
    )
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--luna-output-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        samples = synthetic_samples()
        merged, counts = merge_luna_labels(samples, synthetic_luna_rows(samples))
        _print(
            {
                "status": "PASS_MERGE_LABELS_PREFLIGHT",
                "rows": len(merged),
                "tier_counts": counts,
                "real_labels_opened": False,
            }
        )
        return 0
    if args.mode == "formal":
        require_formal_authorization(formal_flag=args.formal)
        if not all(
            (args.candidates, args.luna_output_dir, args.output, args.audit_output)
        ):
            parser.error("formal mode requires candidate/input/output paths")
        samples = read_jsonl(args.candidates)
        luna_rows = []
        for path in sorted(args.luna_output_dir.glob("batch_*.json")):
            luna_rows.extend(load_luna_output(path))
    else:
        samples = synthetic_samples()
        luna_rows = synthetic_luna_rows(samples)
    merged, counts = merge_luna_labels(samples, luna_rows)
    audit = {
        "status": "PASS_LABEL_MANIFEST_AUDIT",
        "rows": len(merged),
        "tier_counts": counts,
        "sample_ids_unique": len({row["sample_id"] for row in merged})
        == len(merged),
        "label_manifest_sha256": canonical_sha256(merged),
        "manual_edits": False,
    }
    if args.output:
        write_jsonl_atomic(args.output, merged)
    if args.audit_output:
        write_json_atomic(args.audit_output, audit)
    _print(audit)
    return 0
