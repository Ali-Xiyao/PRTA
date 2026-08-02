from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import (
    FormalExecutionBlocked,
    require_formal_authorization,
)
from prta_cxr.cli_labeling import luna_command, synthetic_samples
from prta_cxr.contracts import sha256_file
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.independent_silver import (
    externalize_independent_batch,
    load_independent_ai_output,
    merge_independent_silver,
    prepare_independent_ai_batches,
)
from prta_cxr.label_batches import select_stratified_pilot

DEFAULT_PROMPT = Path("prompts/independent_silver_label_v1.md")
DEFAULT_SCHEMA = Path("schemas/independent_silver_label_batch.schema.json")
DEFAULT_CONFIG = Path("configs/labeling/independent_silver_v1.json")


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _load_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "prta-cxr.independent-silver-labeling.v1":
        raise RuntimeError("unsupported independent-silver config schema")
    if value.get("rule_label_externalized") is not False:
        raise FormalExecutionBlocked("config must prohibit rule-label disclosure")
    return value


def _require_execution_enabled(
    path: Path, *, scope: str, row_count: int
) -> dict[str, Any]:
    value = _load_config(path)
    enabled_key = f"{scope}_execution_enabled"
    if value.get(enabled_key) is not True:
        raise FormalExecutionBlocked(
            f"independent-silver {scope} execution is held by the config"
        )
    if scope == "pilot" and row_count > int(value["pilot_rows_max"]):
        raise FormalExecutionBlocked("pilot input exceeds the configured row cap")
    return value


def synthetic_ai_rows(samples: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"sample_id": row["sample_id"], "ai_label": row["progression_label"]}
        for row in samples
    ]


def prepare_independent_batches_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare rule-blind independent-label batches"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--batch-dir", type=Path)
    parser.add_argument("--receipt-output", type=Path)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        samples = synthetic_samples()
    else:
        require_formal_authorization(formal_flag=args.formal)
        if not all((args.candidates, args.batch_dir, args.receipt_output)):
            parser.error("formal mode requires candidate and output paths")
        samples = read_jsonl(args.candidates)
    batches, receipt = prepare_independent_ai_batches(
        samples,
        batch_size=args.batch_size,
        prompt_path=args.prompt,
        schema_path=args.schema,
    )
    result = {
        "status": (
            "PASS_INDEPENDENT_BATCH_PREPARATION"
            if args.mode == "formal"
            else "PASS_INDEPENDENT_BATCH_PREPARATION_PREFLIGHT"
        ),
        "batch_receipt": receipt,
        "real_reports_opened": args.mode == "formal",
        "external_call_made": False,
    }
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


def prepare_independent_pilot_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a rule-blind independent-label pilot"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--pilot-output", type=Path)
    parser.add_argument("--batch-dir", type=Path)
    parser.add_argument("--receipt-output", type=Path)
    parser.add_argument("--pilot-size", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--salt", default="prta-cxr-luna-pilot-v1")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        selected = synthetic_samples()
        batches, receipt = prepare_independent_ai_batches(
            selected,
            batch_size=args.batch_size,
            prompt_path=args.prompt,
            schema_path=args.schema,
        )
        _print(
            {
                "status": "PASS_INDEPENDENT_PILOT_PREFLIGHT",
                "batches": len(batches),
                "batch_receipt": receipt,
                "real_reports_opened": False,
                "external_call_made": False,
            }
        )
        return 0

    require_formal_authorization(formal_flag=args.formal)
    required = (
        args.candidates,
        args.pilot_output,
        args.batch_dir,
        args.receipt_output,
    )
    if not all(required):
        parser.error("formal mode requires all candidate/output paths")
    if not 100 <= args.pilot_size <= 200:
        parser.error("pilot-size must be within [100, 200]")
    samples = read_jsonl(args.candidates)
    selected, selection_audit = select_stratified_pilot(
        samples, pilot_size=args.pilot_size, salt=args.salt
    )
    batches, batch_receipt = prepare_independent_ai_batches(
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
        "status": "PASS_INDEPENDENT_PILOT_PREPARATION",
        "selection_audit": selection_audit,
        "batch_receipt": batch_receipt,
        "external_call_made": False,
    }
    write_json_atomic(args.receipt_output, result)
    _print(result)
    return 0


def run_independent_ai_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run rule-blind independent AI label batches"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--scope", choices=("pilot", "full"), default="pilot")
    parser.add_argument("--batch-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--receipt-output", type=Path)
    parser.add_argument("--preparation-receipt", type=Path)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=2.0)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--start-batch", type=int, default=0)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    preview = luna_command(
        model=args.model, schema=args.schema, output=Path("OUTPUT.json")
    )
    if args.mode == "preflight":
        config = _load_config(args.config)
        _print(
            {
                "status": "PASS_INDEPENDENT_AI_RUNNER_PREFLIGHT",
                "command": preview,
                "prompt_sha256": sha256_file(args.prompt),
                "schema_sha256": sha256_file(args.schema),
                "pilot_execution_enabled": config["pilot_execution_enabled"],
                "full_execution_enabled": config["full_execution_enabled"],
                "external_call_made": False,
            }
        )
        return 0

    require_formal_authorization(formal_flag=args.formal)
    if not args.execute:
        parser.error("formal independent-AI mode also requires --execute")
    if not all((args.batch_dir, args.output_dir, args.receipt_output)):
        parser.error("formal mode requires batch/output dirs and receipt output")
    all_batch_paths = sorted(args.batch_dir.glob("batch_*.json"))
    if not all_batch_paths:
        raise RuntimeError("no independent AI input batches found")
    authority_row_count = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["items"])
        for path in all_batch_paths
    )
    batch_paths = all_batch_paths
    if args.start_batch < 0:
        parser.error("start-batch must be non-negative")
    batch_paths = batch_paths[args.start_batch :]
    if args.max_batches is not None:
        if args.max_batches < 1:
            parser.error("max-batches must be positive")
        batch_paths = batch_paths[: args.max_batches]
    if not batch_paths:
        raise RuntimeError("batch selection is empty")
    input_batches = [
        json.loads(path.read_text(encoding="utf-8")) for path in batch_paths
    ]
    row_count = sum(len(batch["items"]) for batch in input_batches)
    config = _require_execution_enabled(
        args.config, scope=args.scope, row_count=authority_row_count
    )
    expected_candidate_hash = config.get("candidate_manifest_sha256")
    if expected_candidate_hash:
        if args.preparation_receipt is None:
            raise FormalExecutionBlocked(
                "config-pinned candidate hash requires --preparation-receipt"
            )
        preparation = json.loads(
            args.preparation_receipt.read_text(encoding="utf-8")
        )
        batch_receipt = preparation.get("batch_receipt", {})
        if batch_receipt.get("candidate_manifest_sha256") != expected_candidate_hash:
            raise FormalExecutionBlocked("candidate manifest hash mismatch")
        if batch_receipt.get("samples") != authority_row_count:
            raise FormalExecutionBlocked("candidate row count mismatch")
        if config.get("full_candidate_rows") != authority_row_count:
            raise FormalExecutionBlocked("configured full candidate count mismatch")
    if args.model != config.get("model"):
        raise FormalExecutionBlocked(
            "requested model does not match the independent-label config"
        )
    prompt_hash = sha256_file(args.prompt)
    schema_hash = sha256_file(args.schema)
    for batch_path, batch in zip(batch_paths, input_batches, strict=True):
        if batch.get("prompt_sha256") != prompt_hash:
            raise FormalExecutionBlocked(
                f"prompt hash mismatch for {batch_path.name}"
            )
        if batch.get("output_schema_sha256") != schema_hash:
            raise FormalExecutionBlocked(
                f"schema hash mismatch for {batch_path.name}"
            )
    if args.timeout_seconds < 1:
        parser.error("timeout-seconds must be positive")
    if args.max_attempts < 1:
        parser.error("max-attempts must be positive")
    if args.retry_delay_seconds < 0:
        parser.error("retry-delay-seconds must be non-negative")
    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(f"refusing existing output dir: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    prompt = args.prompt.read_text(encoding="utf-8")
    receipts = []
    for batch_path, batch in zip(batch_paths, input_batches, strict=True):
        if batch.get("schema") != "prta-cxr.independent-ai-input-batch.v1":
            raise RuntimeError(f"unsupported input batch: {batch_path.name}")
        output = args.output_dir / batch_path.name
        timing_receipt = output.with_name(f".{output.name}.timing-receipt")
        expected_external = {item["sample_id"] for item in batch["items"]}
        sample_id_map = batch.get("sample_id_map", {})
        if (
            set(sample_id_map) != expected_external
            or len(set(sample_id_map.values())) != len(sample_id_map)
        ):
            raise RuntimeError(f"invalid sample_id_map for {batch_path.name}")
        expected_final = set(sample_id_map.values())
        reused = output.exists()
        if not reused:
            started_at = datetime.now(UTC).isoformat()
            started_clock = time.perf_counter()
            external_batch = externalize_independent_batch(batch)
            payload = (
                prompt
                + "\n\nINPUT_BATCH_JSON:\n"
                + json.dumps(external_batch, ensure_ascii=False)
            )
            attempt_errors = []
            for attempt in range(1, args.max_attempts + 1):
                temporary = output.with_name(
                    f".{output.name}.tmp.{os.getpid()}.{attempt}"
                )
                command = luna_command(
                    model=args.model, schema=args.schema, output=temporary
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
                            f"exit={completed.returncode}; "
                            f"stderr_tail={completed.stderr[-500:]!r}"
                        )
                    rows = load_independent_ai_output(temporary)
                    if {row["sample_id"] for row in rows} != expected_external:
                        raise RuntimeError(
                            "external sample IDs are incomplete or mismatched"
                        )
                    restored = [
                        row | {"sample_id": sample_id_map[row["sample_id"]]}
                        for row in rows
                    ]
                    rows = restored
                    temporary.write_text(
                        json.dumps(
                            {"items": restored},
                            indent=2,
                            sort_keys=True,
                            ensure_ascii=False,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    temporary.replace(output)
                    timing = {
                        "started_at_utc": started_at,
                        "completed_at_utc": datetime.now(UTC).isoformat(),
                        "elapsed_seconds": round(
                            time.perf_counter() - started_clock, 3
                        ),
                        "attempts_used": attempt,
                        "failed_attempts": attempt - 1,
                    }
                    write_json_atomic(timing_receipt, timing)
                    break
                except Exception as error:
                    attempt_errors.append(str(error))
                    failed = output.with_name(
                        f".{output.name}.failed.{os.getpid()}."
                        f"{time.time_ns()}.json"
                    )
                    if temporary.exists():
                        temporary.replace(failed)
                    if attempt == args.max_attempts:
                        raise RuntimeError(
                            f"independent AI batch failed after "
                            f"{args.max_attempts} attempts: {batch_path.name}; "
                            f"last_error={attempt_errors[-1]}"
                        ) from error
                    time.sleep(args.retry_delay_seconds)
                finally:
                    if temporary.exists():
                        temporary.unlink()
        else:
            rows = load_independent_ai_output(output)
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
            raise RuntimeError(f"independent AI IDs mismatch for {batch_path.name}")
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
    result = {
        "status": "PASS_INDEPENDENT_AI_BATCH_RUN",
        "scope": args.scope,
        "rows": row_count,
        "external_call_made": True,
        "rule_label_in_external_payload": False,
        "prompt_sha256": prompt_hash,
        "schema_sha256": schema_hash,
        "config_authorized_scope": config["authorized_scope"],
        "batches": receipts,
    }
    write_json_atomic(args.receipt_output, result)
    _print(result)
    return 0


def merge_independent_silver_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Intersect local rule and rule-blind AI labels"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--ai-output-dir", type=Path)
    parser.add_argument("--accepted-output", type=Path)
    parser.add_argument("--excluded-output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        samples = synthetic_samples()
        accepted, excluded, audit = merge_independent_silver(
            samples, synthetic_ai_rows(samples)
        )
        _print(
            {
                "status": "PASS_INDEPENDENT_SILVER_MERGE_PREFLIGHT",
                "accepted": len(accepted),
                "excluded": len(excluded),
                "audit": audit,
                "real_labels_opened": False,
            }
        )
        return 0

    require_formal_authorization(formal_flag=args.formal)
    required = (
        args.candidates,
        args.ai_output_dir,
        args.accepted_output,
        args.excluded_output,
        args.audit_output,
    )
    if not all(required):
        parser.error("formal mode requires all input/output paths")
    samples = read_jsonl(args.candidates)
    ai_rows = []
    for path in sorted(args.ai_output_dir.glob("batch_*.json")):
        ai_rows.extend(load_independent_ai_output(path))
    if not ai_rows:
        raise RuntimeError("no independent AI outputs found")
    accepted, excluded, audit = merge_independent_silver(samples, ai_rows)
    write_jsonl_atomic(args.accepted_output, accepted)
    write_jsonl_atomic(args.excluded_output, excluded)
    write_json_atomic(args.audit_output, audit)
    _print(audit)
    return 0
