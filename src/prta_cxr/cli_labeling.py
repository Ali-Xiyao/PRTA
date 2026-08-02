from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import FormalExecutionBlocked, require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.label_batches import (
    load_luna_output,
    prepare_luna_batches,
    select_stratified_pilot,
)
from prta_cxr.label_rules import candidate_samples
from prta_cxr.labeling import merge_luna_labels

DEFAULT_PROMPT = Path("prompts/luna_label_v1.md")
DEFAULT_SCHEMA = Path("schemas/luna_label_batch.schema.json")
DEFAULT_LABEL_CONFIG = Path("configs/labeling/luna_v1.json")


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _require_luna_execution_enabled(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "prta-cxr.luna-labeling.v1":
        raise RuntimeError("unsupported Luna labeling config schema")
    if value.get("formal_execution_enabled") is not True:
        raise FormalExecutionBlocked(
            "full Luna execution is held by the labeling config; "
            "a new explicit authorization and config update are required"
        )
    return value


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
            "prior_evidence": row["prior_report"],
            "current_evidence": row["current_report"],
            "comparison_evidence": "Current report evidence",
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
    executable = (
        shutil.which("codex.cmd") if os.name == "nt" else shutil.which("codex")
    )
    if not executable:
        raise RuntimeError("Codex CLI executable was not found")
    return [
        executable,
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


def prepare_luna_pilot_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select and prepare a deterministic stratified Luna pilot"
    )
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--pilot-output", type=Path, required=True)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--pilot-size", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--salt", default="prta-cxr-luna-pilot-v1")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if not 100 <= args.pilot_size <= 200:
        parser.error("pilot-size must be within the frozen [100, 200] gate")
    samples = read_jsonl(args.candidates)
    selected, selection_audit = select_stratified_pilot(
        samples, pilot_size=args.pilot_size, salt=args.salt
    )
    batches, batch_receipt = prepare_luna_batches(
        selected,
        batch_size=args.batch_size,
        prompt_path=args.prompt,
        schema_path=args.schema,
    )
    write_jsonl_atomic(args.pilot_output, selected)
    if args.batch_dir.exists():
        raise FileExistsError(f"refusing existing batch dir: {args.batch_dir}")
    args.batch_dir.mkdir(parents=True)
    for batch in batches:
        write_json_atomic(args.batch_dir / f"{batch['batch_id']}.json", batch)
    result = {
        "status": "PASS_STRATIFIED_LUNA_PILOT_PREPARATION",
        "selection_audit": selection_audit,
        "batch_receipt": batch_receipt,
        "external_call_made": False,
    }
    write_json_atomic(args.receipt_output, result)
    _print(result)
    return 0


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
    parser.add_argument("--config", type=Path, default=DEFAULT_LABEL_CONFIG)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    preview = luna_command(
        model=args.model, schema=args.schema, output=Path("OUTPUT.json")
    )
    if args.mode == "preflight":
        config = json.loads(args.config.read_text(encoding="utf-8"))
        _print(
            {
                "status": "PASS_LUNA_RUNNER_PREFLIGHT",
                "command": preview,
                "prompt_sha256": sha256_file(args.prompt),
                "schema_sha256": sha256_file(args.schema),
                "external_call_made": False,
                "formal_execution_enabled": config.get(
                    "formal_execution_enabled", False
                ),
                "pilot_status": config.get("pilot_status", "not_recorded"),
            }
        )
        return 0
    require_formal_authorization(formal_flag=args.formal)
    _require_luna_execution_enabled(args.config)
    if not args.execute:
        parser.error("formal Luna mode also requires --execute")
    if not all((args.batch_dir, args.output_dir, args.receipt_output)):
        parser.error("formal mode requires batch/output dirs and receipt output")
    if args.timeout_seconds < 1:
        parser.error("timeout-seconds must be positive")
    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(f"refusing existing output dir: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    prompt = args.prompt.read_text(encoding="utf-8")
    receipts = []
    for batch_path in sorted(args.batch_dir.glob("batch_*.json")):
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        output = args.output_dir / batch_path.name
        timing_receipt = output.with_name(f".{output.name}.timing-receipt")
        expected_external = {item["sample_id"] for item in batch["items"]}
        sample_id_map = batch.get("sample_id_map", {})
        if sample_id_map and (
            set(sample_id_map) != expected_external
            or len(set(sample_id_map.values())) != len(sample_id_map)
        ):
            raise RuntimeError(f"invalid sample_id_map for {batch_path.name}")
        expected_final = (
            set(sample_id_map.values()) if sample_id_map else expected_external
        )
        reused = output.exists()
        if not reused:
            batch_started_at = datetime.now(UTC).isoformat()
            batch_started_clock = time.perf_counter()
            temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
            command = luna_command(
                model=args.model, schema=args.schema, output=temporary
            )
            external_batch = {
                key: value for key, value in batch.items() if key != "sample_id_map"
            }
            payload = (
                prompt + "\n\nINPUT_BATCH_JSON:\n" + json.dumps(external_batch)
            )
            try:
                completed = subprocess.run(
                    command,
                    input=payload,
                    text=True,
                    check=False,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=args.timeout_seconds,
                )
                if completed.returncode != 0:
                    raise RuntimeError(
                        f"Luna batch failed closed: {batch_path.name}; "
                        f"exit={completed.returncode}; "
                        f"stderr_tail={completed.stderr[-500:]!r}"
                    )
                try:
                    rows = load_luna_output(temporary)
                    if {row["sample_id"] for row in rows} != expected_external:
                        raise RuntimeError(
                            f"Luna IDs mismatch for {batch_path.name}"
                        )
                    if sample_id_map:
                        rows = [
                            row | {"sample_id": sample_id_map[row["sample_id"]]}
                            for row in rows
                        ]
                        temporary.write_text(
                            json.dumps(
                                {"items": rows},
                                indent=2,
                                sort_keys=True,
                                ensure_ascii=False,
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                except Exception:
                    failed = output.with_name(
                        f".{output.name}.failed.{os.getpid()}.json"
                    )
                    temporary.replace(failed)
                    raise
                temporary.replace(output)
                timing = {
                    "started_at_utc": batch_started_at,
                    "completed_at_utc": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": round(
                        time.perf_counter() - batch_started_clock, 3
                    ),
                }
                write_json_atomic(timing_receipt, timing)
            finally:
                if temporary.exists():
                    temporary.unlink()
        else:
            rows = load_luna_output(output)
            timing = (
                json.loads(timing_receipt.read_text(encoding="utf-8"))
                if timing_receipt.exists()
                else {
                    "started_at_utc": None,
                    "completed_at_utc": datetime.fromtimestamp(
                        output.stat().st_mtime, UTC
                    ).isoformat(),
                    "elapsed_seconds": None,
                }
            )
        if {row["sample_id"] for row in rows} != expected_final:
            raise RuntimeError(f"Luna IDs mismatch for {batch_path.name}")
        receipts.append(
            {
                "batch_id": batch["batch_id"],
                "input_sha256": batch["input_sha256"],
                "output_sha256": sha256_file(output),
                "model": args.model,
                "rows": len(rows),
                "reused_existing_output": reused,
                "prior_failed_attempts": len(
                    list(args.output_dir.glob(f".{output.name}.failed.*.json"))
                ),
                **timing,
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
        "deterministic_reject_reasons": {
            reason: sum(
                row.get("label_gate", {}).get("deterministic_reject_reason")
                == reason
                for row in merged
            )
            for reason in (
                "accept_with_conflict",
                "accept_with_mismatch",
                "non_extractive_evidence",
            )
        },
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
