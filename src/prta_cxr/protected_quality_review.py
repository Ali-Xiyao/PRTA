from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import (
    replace_json_atomic,
    write_json_atomic,
    write_jsonl_atomic,
)
from prta_cxr.cli_labeling import luna_command
from prta_cxr.contracts import (
    SAMPLE_FIELDS,
    canonical_sha256,
    sha256_file,
    validate_sample,
)
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.independent_silver import (
    AI_LABELS,
    externalize_independent_batch,
)

MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"
COHORT_ROWS = {"dev": 16666, "internal_test": 16699, "gold": 250}
QUALITY_FLAGS = (
    "REPORT_INSUFFICIENT",
    "PAIRING_ABNORMAL",
    "FINDING_NOT_JUDGEABLE",
    "TEMPORAL_DIRECTION_AMBIGUOUS",
    "NEGATION_OR_UNCERTAINTY_CONFLICT",
)
OUTPUT_FIELDS = frozenset({"sample_id", "ai_label", "quality_flags"})
DEFAULT_PROMPT = Path("prompts/protected_label_quality_review_v1.md")
DEFAULT_SCHEMA = Path("schemas/protected_label_quality_review_batch_v2.schema.json")


def _private(path: Path) -> None:
    value = str(path.resolve()).lower().replace("/", "\\")
    if "\\prta-cxr\\" in value and "\\poststop_audits\\" not in value:
        raise RuntimeError("protected row-level review output must stay outside Git")


def validate_quality_output(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"items"}:
        raise RuntimeError("quality output root must contain only items")
    rows = []
    identifiers = []
    for raw in value["items"]:
        if not isinstance(raw, dict) or set(raw) != OUTPUT_FIELDS:
            raise RuntimeError("quality output field mismatch")
        sample_id = raw["sample_id"]
        label = raw["ai_label"]
        flags = raw["quality_flags"]
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise RuntimeError("quality output sample_id is empty")
        if label not in AI_LABELS:
            raise RuntimeError("quality output label is invalid")
        if not isinstance(flags, list) or len(flags) != len(set(flags)):
            raise RuntimeError("quality flags must be a unique list")
        if any(flag not in QUALITY_FLAGS for flag in flags):
            raise RuntimeError("quality output contains an unknown flag")
        identifiers.append(sample_id.strip())
        rows.append(
            {
                "sample_id": sample_id.strip(),
                "ai_label": label,
                "quality_flags": list(flags),
            }
        )
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("quality output contains duplicate sample IDs")
    return rows


def _validate_review_sample(raw: dict[str, Any]) -> dict[str, Any]:
    if set(raw) != SAMPLE_FIELDS:
        raise RuntimeError("protected review sample field mismatch")
    if raw.get("label_tier") != "Gold":
        return validate_sample(raw)
    compatible = dict(raw)
    compatible["label_tier"] = "Silver"
    validate_sample(compatible)
    return dict(raw)


def _samples_for_split(path: Path, split: str) -> list[dict[str, Any]]:
    samples = []
    marker = f'"split": "{split}"'.encode()
    with path.open("rb") as handle:
        for raw_line in handle:
            if marker not in raw_line:
                continue
            row = json.loads(raw_line)
            sample = {field: row[field] for field in SAMPLE_FIELDS}
            samples.append(_validate_review_sample(sample))
    return samples


def _all_samples(path: Path, expected_split: str | None) -> list[dict[str, Any]]:
    samples = []
    for row in read_jsonl(path):
        if expected_split is not None and row.get("split") != expected_split:
            raise RuntimeError(f"unexpected split in {path.name}")
        sample = {field: row[field] for field in SAMPLE_FIELDS}
        samples.append(_validate_review_sample(sample))
    return samples


def _write_batches(
    samples: list[dict[str, Any]],
    *,
    cohort: str,
    root: Path,
    batch_size: int,
    prompt: Path,
    schema: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    candidate = root / "private" / "candidates" / f"{cohort}.jsonl"
    batch_dir = root / "private" / "batches" / cohort
    _private(candidate)
    _private(batch_dir)
    write_jsonl_atomic(candidate, samples)
    if batch_size < 1 or batch_size > 30:
        raise RuntimeError("protected quality batch_size must be within [1, 30]")
    validated = [_validate_review_sample(row) for row in samples]
    identifiers = [row["sample_id"] for row in validated]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("protected candidate sample IDs must be unique")
    prompt_hash = sha256_file(prompt)
    schema_hash = sha256_file(schema)
    batches = []
    for batch_index, start in enumerate(range(0, len(validated), batch_size)):
        selected = validated[start : start + batch_size]
        sample_id_map = {
            f"s{batch_index:05d}_{offset:02d}": row["sample_id"]
            for offset, row in enumerate(selected)
        }
        items = [
            {
                "sample_id": alias,
                "finding": row["finding"],
                "prior_report": row["prior_report"],
                "current_report": row["current_report"],
            }
            for alias, row in zip(sample_id_map, selected, strict=True)
        ]
        batches.append(
            {
                "schema": "prta-cxr.independent-ai-input-batch.v1",
                "batch_id": f"batch_{batch_index:05d}",
                "prompt_sha256": prompt_hash,
                "output_schema_sha256": schema_hash,
                "items": items,
                "sample_id_map": sample_id_map,
                "input_sha256": canonical_sha256(items),
            }
        )
    receipt = {
        "schema": "prta-cxr.protected-quality-batch-preparation.v1",
        "samples": len(validated),
        "batches": len(batches),
        "batch_size": batch_size,
        "prompt_sha256": prompt_hash,
        "output_schema_sha256": schema_hash,
        "external_item_fields": [
            "current_report",
            "finding",
            "prior_report",
            "sample_id",
        ],
        "labels_in_external_payload": False,
        "patient_identifiers_in_external_payload": False,
        "alias_map_in_external_payload": False,
        "candidate_manifest_sha256": canonical_sha256(validated),
    }
    if batch_dir.exists():
        raise FileExistsError(f"refusing existing batch dir: {batch_dir}")
    batch_dir.mkdir(parents=True)
    for batch in batches:
        write_json_atomic(batch_dir / f"{batch['batch_id']}.json", batch)
    return candidate, batch_dir, receipt


def prepare_protected_quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare protected blind quality rosters"
    )
    parser.add_argument("--train-dev", type=Path, required=True)
    parser.add_argument("--internal-test", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args(argv)
    _private(args.output_root)
    if args.output_root.exists():
        raise FileExistsError(f"refusing existing output root: {args.output_root}")
    args.output_root.mkdir(parents=True)

    input_hashes = {
        "train_dev": sha256_file(args.train_dev),
        "internal_test": sha256_file(args.internal_test),
        "gold": sha256_file(args.gold),
    }
    preopen = {
        "schema": "prta-cxr.protected-quality-preopen.v1",
        "status": "AUTHORIZED_PROTECTED_LABEL_QUALITY_ACCESS",
        "authorization_date": "2026-08-04",
        "authority": "explicit_user_request",
        "authorized_cohorts": ["dev", "internal_test", "gold"],
        "input_hashes": input_hashes,
        "labels_externalized": False,
        "prta_model_inference_authorized": False,
        "sol_label_review_authorized": True,
        "label_mutation_authorized": False,
        "future_scientific_disclosure_required": True,
    }
    write_json_atomic(args.output_root / "preopen_receipt.json", preopen)

    cohorts = {
        "dev": _samples_for_split(args.train_dev, "dev"),
        "internal_test": _all_samples(args.internal_test, "internal_test"),
        "gold": _all_samples(args.gold, None),
    }
    for cohort, expected in COHORT_ROWS.items():
        rows = cohorts[cohort]
        if len(rows) != expected or len({row["sample_id"] for row in rows}) != expected:
            raise RuntimeError(
                f"{cohort} row count/uniqueness mismatch"
            )

    preparation: dict[str, Any] = {}
    candidate_hashes: dict[str, str] = {}
    for cohort, samples in cohorts.items():
        candidate, _, batch_receipt = _write_batches(
            samples,
            cohort=cohort,
            root=args.output_root,
            batch_size=args.batch_size,
            prompt=args.prompt,
            schema=args.schema,
        )
        candidate_hashes[cohort] = sha256_file(candidate)
        preparation[cohort] = batch_receipt
    config = {
        "schema": "prta-cxr.protected-quality-review-config.v1",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "authorized_scope": "dev_internal_test_gold_full_blind_quality_review",
        "execution_enabled": True,
        "cohort_rows": COHORT_ROWS,
        "candidate_file_hashes": candidate_hashes,
        "candidate_manifest_hashes": {
            cohort: value["candidate_manifest_sha256"]
            for cohort, value in preparation.items()
        },
        "prompt_sha256": sha256_file(args.prompt),
        "schema_sha256": sha256_file(args.schema),
        "labels_externalized": False,
        "training_or_mutation_authorized": False,
    }
    write_json_atomic(args.output_root / "private" / "config.json", config)
    receipt = {
        "schema": "prta-cxr.protected-quality-preparation.v1",
        "status": "PASS_PROTECTED_BLIND_ROSTERS_PREPARED",
        "input_hashes": input_hashes,
        "cohort_rows": COHORT_ROWS,
        "total_rows": sum(COHORT_ROWS.values()),
        "total_batches": sum(value["batches"] for value in preparation.values()),
        "preparation": preparation,
        "external_item_fields": [
            "sample_id",
            "finding",
            "prior_report",
            "current_report",
        ],
        "labels_or_risk_externalized": False,
        "training_or_mutation_performed": False,
    }
    write_json_atomic(args.output_root / "preparation_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def run_protected_quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run protected blind quality batches")
    parser.add_argument("--cohort", choices=tuple(COHORT_ROWS), required=True)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--reasoning-effort", default=REASONING_EFFORT)
    parser.add_argument("--start-batch", type=int, default=0)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    for path in (args.output_dir, args.receipt_output):
        _private(path)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("schema") != "prta-cxr.protected-quality-review-config.v1":
        raise RuntimeError("unsupported protected-quality config")
    if config.get("execution_enabled") is not True:
        raise RuntimeError("protected-quality execution is closed")
    if (
        args.model != config["model"]
        or args.reasoning_effort != config["reasoning_effort"]
    ):
        raise RuntimeError("model/reasoning effort differs from authority")
    prompt_hash = sha256_file(args.prompt)
    schema_hash = sha256_file(args.schema)
    if prompt_hash != config["prompt_sha256"] or schema_hash != config["schema_sha256"]:
        raise RuntimeError("prompt/schema differs from authority")
    all_paths = sorted(args.batch_dir.glob("batch_*.json"))
    if len(all_paths) == 0:
        raise RuntimeError("no quality input batches")
    paths = all_paths[args.start_batch :]
    if args.max_batches is not None:
        paths = paths[: args.max_batches]
    if not paths:
        raise RuntimeError("empty quality batch selection")
    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(f"refusing existing output dir: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    prompt = args.prompt.read_text(encoding="utf-8")
    receipts = []
    for batch_path in paths:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        if (
            batch["prompt_sha256"] != prompt_hash
            or batch["output_schema_sha256"] != schema_hash
        ):
            raise RuntimeError("batch prompt/schema hash mismatch")
        external = externalize_independent_batch(batch)
        expected_aliases = {row["sample_id"] for row in batch["items"]}
        mapping = batch["sample_id_map"]
        output = args.output_dir / batch_path.name
        timing_path = output.with_name(f".{output.name}.timing-receipt")
        reused = output.exists()
        if not reused:
            payload = (
                prompt
                + "\n\nINPUT_BATCH_JSON:\n"
                + json.dumps(external, ensure_ascii=False)
            )
            started_at = datetime.now(UTC).isoformat()
            clock = time.perf_counter()
            errors = []
            for attempt in range(1, args.max_attempts + 1):
                temporary = output.with_name(
                    f".{output.name}.tmp.{os.getpid()}.{attempt}"
                )
                command = luna_command(
                    model=args.model,
                    schema=args.schema,
                    output=temporary,
                    reasoning_effort=args.reasoning_effort,
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
                        tail = completed.stderr[-500:]
                        raise RuntimeError(
                            f"exit={completed.returncode}; stderr={tail!r}"
                        )
                    rows = validate_quality_output(temporary)
                    if {row["sample_id"] for row in rows} != expected_aliases:
                        raise RuntimeError("quality alias set mismatch")
                    restored = [
                        row | {"sample_id": mapping[row["sample_id"]]}
                        for row in rows
                    ]
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
                        "elapsed_seconds": round(time.perf_counter() - clock, 3),
                        "attempts_used": attempt,
                        "failed_attempts": attempt - 1,
                    }
                    write_json_atomic(timing_path, timing)
                    break
                except Exception as error:
                    errors.append(str(error))
                    if temporary.exists():
                        failed = output.with_name(
                            f".{output.name}.failed.{os.getpid()}.{time.time_ns()}.json"
                        )
                        temporary.replace(failed)
                    if attempt == args.max_attempts:
                        raise RuntimeError(
                            f"quality batch failed: {batch_path.name}; {errors[-1]}"
                        ) from error
                    time.sleep(3)
                finally:
                    if temporary.exists():
                        temporary.unlink()
        rows = validate_quality_output(output)
        expected_ids = set(mapping.values())
        if {row["sample_id"] for row in rows} != expected_ids:
            raise RuntimeError("restored quality ID set mismatch")
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        receipts.append(
            {
                "batch_id": batch["batch_id"],
                "rows": len(rows),
                "model": args.model,
                "reasoning_effort": args.reasoning_effort,
                "input_sha256": batch["input_sha256"],
                "output_sha256": sha256_file(output),
                "reused_existing_output": reused,
                **timing,
            }
        )
    result = {
        "schema": "prta-cxr.protected-quality-run-receipt.v1",
        "status": "PASS_PROTECTED_QUALITY_BATCH_RUN",
        "cohort": args.cohort,
        "rows": sum(row["rows"] for row in receipts),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "labels_or_risk_externalized": False,
        "batches": receipts,
    }
    write_json_atomic(args.receipt_output, result)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def shard_ranges(total: int, workers: int) -> list[tuple[int, int]]:
    if total < 1 or workers < 1:
        raise ValueError("total and workers must be positive")
    width = math.ceil(total / workers)
    return [
        (start, min(width, total - start))
        for start in range(0, total, width)
    ]


def launch_protected_quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Launch disjoint protected-quality review shards"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dev-workers", type=int, default=14)
    parser.add_argument("--internal-test-workers", type=int, default=14)
    parser.add_argument("--gold-workers", type=int, default=2)
    args = parser.parse_args(argv)
    _private(args.output_root)
    registry_path = args.output_root / "launch_registry.json"
    if registry_path.exists():
        raise FileExistsError(f"refusing existing launch registry: {registry_path}")
    config = args.output_root / "private" / "config.json"
    if not config.is_file():
        raise FileNotFoundError(f"missing review config: {config}")
    worker_counts = {
        "dev": args.dev_workers,
        "internal_test": args.internal_test_workers,
        "gold": args.gold_workers,
    }
    repo_root = Path(__file__).resolve().parents[2]
    runner = repo_root / "scripts" / "25_run_protected_quality_review.py"
    logs = args.output_root / "private" / "logs"
    logs.mkdir(parents=True, exist_ok=False)
    children = []
    for cohort, workers in worker_counts.items():
        batch_dir = args.output_root / "private" / "batches" / cohort
        total = len(list(batch_dir.glob("batch_*.json")))
        expected = math.ceil(COHORT_ROWS[cohort] / 20)
        if total != expected:
            raise RuntimeError(f"{cohort} batch count mismatch")
        for index, (start, count) in enumerate(shard_ranges(total, workers)):
            output_dir = args.output_root / "private" / "outputs" / cohort
            receipt = (
                args.output_root
                / "receipts"
                / f"full_{cohort}_{index:02d}.json"
            )
            stdout_path = logs / f"full_{cohort}_{index:02d}.stdout.log"
            stderr_path = logs / f"full_{cohort}_{index:02d}.stderr.log"
            command = [
                sys.executable,
                str(runner),
                "--cohort",
                cohort,
                "--batch-dir",
                str(batch_dir),
                "--output-dir",
                str(output_dir),
                "--config",
                str(config),
                "--receipt-output",
                str(receipt),
                "--start-batch",
                str(start),
                "--max-batches",
                str(count),
                "--resume",
            ]
            with stdout_path.open("w", encoding="utf-8") as stdout_handle:
                with stderr_path.open("w", encoding="utf-8") as stderr_handle:
                    process = subprocess.Popen(
                        command,
                        cwd=repo_root,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
            children.append(
                {
                    "cohort": cohort,
                    "shard": index,
                    "start_batch": start,
                    "max_batches": count,
                    "pid": process.pid,
                    "stdout": str(stdout_path),
                    "stderr": str(stderr_path),
                    "receipt": str(receipt),
                }
            )
    registry = {
        "schema": "prta-cxr.protected-quality-launch.v1",
        "status": "RUNNING_FULL_BLIND_REVIEW",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "workers": len(children),
        "children": children,
        "training_or_mutation_started": False,
    }
    write_json_atomic(registry_path, registry)
    print(json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _load_completed_outputs(
    output_dir: Path,
    expected_batches: int,
) -> dict[str, dict[str, Any]]:
    paths = sorted(output_dir.glob("batch_*.json"))
    if len(paths) != expected_batches:
        raise RuntimeError(
            f"incomplete outputs in {output_dir}: {len(paths)}/{expected_batches}"
        )
    rows = [row for path in paths for row in validate_quality_output(path)]
    by_id = {row["sample_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise RuntimeError(f"duplicate restored IDs in {output_dir}")
    return by_id


def _cohen_kappa(rows: list[dict[str, Any]]) -> float | None:
    decisive = [row for row in rows if row["sol_label"] != "Unclear"]
    if not decisive:
        return None
    total = len(decisive)
    observed = sum(row["exact_current"] for row in decisive) / total
    current = Counter(row["current_label"] for row in decisive)
    sol = Counter(row["sol_label"] for row in decisive)
    expected = sum(current[label] * sol[label] for label in AI_LABELS[:-1])
    expected /= total * total
    if expected == 1:
        return 1.0 if observed == 1 else None
    return round((observed - expected) / (1 - expected), 6)


def _group_summary(
    rows: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(str(row[field]) for field in fields)
        groups.setdefault(key, []).append(row)
    output = []
    for key, selected in sorted(groups.items()):
        decisive = [row for row in selected if not row["sol_unclear"]]
        exact = sum(row["exact_current"] for row in decisive)
        item = {field: value for field, value in zip(fields, key, strict=True)}
        item.update(
            {
                "rows": len(selected),
                "sol_unclear": sum(row["sol_unclear"] for row in selected),
                "quality_flagged": sum(
                    bool(row["quality_flags"]) for row in selected
                ),
                "decisive_rows": len(decisive),
                "decisive_exact": exact,
                "decisive_disagreement": len(decisive) - exact,
                "decisive_agreement_rate": (
                    round(exact / len(decisive), 6) if decisive else None
                ),
                "cohen_kappa": _cohen_kappa(selected),
            }
        )
        output.append(item)
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({field for row in rows for field in row})
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: (
                            "|".join(str(value) for value in item)
                            if isinstance(item, list)
                            else item
                        )
                        for key, item in row.items()
                    }
                )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def compare_protected_quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare completed blind quality labels without mutation"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dev-risk", type=Path, required=True)
    parser.add_argument("--gold-original", type=Path, required=True)
    parser.add_argument("--train-dev", type=Path, required=True)
    parser.add_argument("--internal-test", type=Path, required=True)
    args = parser.parse_args(argv)
    _private(args.output_root)
    analysis_dir = args.output_root / "private" / "analysis"
    if analysis_dir.exists():
        raise FileExistsError(f"refusing existing analysis dir: {analysis_dir}")

    preparation = json.loads(
        (args.output_root / "preparation_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    before_hashes = preparation["input_hashes"]
    current_hashes = {
        "train_dev": sha256_file(args.train_dev),
        "internal_test": sha256_file(args.internal_test),
        "gold": sha256_file(args.gold_original),
    }
    if current_hashes != before_hashes:
        raise RuntimeError("protected source hash changed before comparison")

    candidates = {
        cohort: read_jsonl(
            args.output_root / "private" / "candidates" / f"{cohort}.jsonl"
        )
        for cohort in COHORT_ROWS
    }
    outputs = {
        cohort: _load_completed_outputs(
            args.output_root / "private" / "outputs" / cohort,
            preparation["preparation"][cohort]["batches"],
        )
        for cohort in COHORT_ROWS
    }

    with args.dev_risk.open("r", encoding="utf-8-sig", newline="") as handle:
        dev_risk_rows = list(csv.DictReader(handle))
    dev_risk = {row["sample_id"]: row for row in dev_risk_rows}
    if len(dev_risk) != COHORT_ROWS["dev"]:
        raise RuntimeError("Dev risk rows are incomplete or duplicated")
    gold_original = {row["sample_id"]: row for row in read_jsonl(args.gold_original)}
    if len(gold_original) != COHORT_ROWS["gold"]:
        raise RuntimeError("Gold original rows are incomplete or duplicated")

    results = []
    for cohort in COHORT_ROWS:
        candidate_ids = {row["sample_id"] for row in candidates[cohort]}
        if candidate_ids != set(outputs[cohort]):
            raise RuntimeError(f"{cohort} candidate/output ID mismatch")
        if len(candidate_ids) != COHORT_ROWS[cohort]:
            raise RuntimeError(f"{cohort} candidate count mismatch")
        for sample in candidates[cohort]:
            sample_id = sample["sample_id"]
            sol = outputs[cohort][sample_id]
            current_label = sample["progression_label"]
            exact = sol["ai_label"] == current_label
            risk = dev_risk.get(sample_id) if cohort == "dev" else None
            high_risk_agree = bool(
                risk
                and risk["risk_tier"] != "Context"
                and exact
                and sol["ai_label"] != "Unclear"
            )
            buckets = []
            if sol["ai_label"] == "Unclear":
                buckets.append("SOL_UNCLEAR")
            elif not exact:
                buckets.append("SOL_DISAGREEMENT")
            if sol["quality_flags"]:
                buckets.append("QUALITY_FLAG")
            if high_risk_agree:
                buckets.append("DEV_HIGH_RISK_SOL_AGREES")
            gold_row = gold_original.get(sample_id)
            result = dict(sample)
            result.update(
                {
                    "cohort": cohort,
                    "current_label": current_label,
                    "current_label_source": sample["label_source"],
                    "sol_label": sol["ai_label"],
                    "sol_unclear": sol["ai_label"] == "Unclear",
                    "exact_current": exact,
                    "quality_flags": sol["quality_flags"],
                    "review_buckets": buckets,
                    "dev_risk_tier": risk["risk_tier"] if risk else "",
                    "dev_selection_reasons": (
                        risk["selection_reasons"] if risk else ""
                    ),
                    "dev_wrong_seed_count": (
                        risk["wrong_seed_count"] if risk else ""
                    ),
                    "dev_seed_disagreement": (
                        risk["seed_disagreement"] if risk else ""
                    ),
                    "dev_mean_nll": risk["mean_nll"] if risk else "",
                    "gold_luna_label": gold_row.get("luna_label", "")
                    if gold_row
                    else "",
                    "sol_vs_gold_luna_exact": (
                        sol["ai_label"] == gold_row.get("luna_label")
                        if gold_row and sol["ai_label"] != "Unclear"
                        else ""
                    ),
                }
            )
            results.append(result)

    flagged = [
        row
        for row in results
        if any(
            bucket in row["review_buckets"]
            for bucket in ("SOL_UNCLEAR", "SOL_DISAGREEMENT", "QUALITY_FLAG")
        )
    ]
    difficult = [
        row
        for row in results
        if "DEV_HIGH_RISK_SOL_AGREES" in row["review_buckets"]
    ]
    confusion = Counter(
        (row["cohort"], row["current_label"], row["sol_label"])
        for row in results
    )
    summary = {
        "schema": "prta-cxr.protected-quality-summary.v1",
        "status": "PASS_READ_ONLY_LABEL_QUALITY_COMPARISON",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "total_rows": len(results),
        "flagged_union_rows": len(flagged),
        "dev_high_risk_sol_agrees": len(difficult),
        "overall": _group_summary(results, ("cohort",)),
        "by_source": _group_summary(results, ("cohort", "source")),
        "by_current_label": _group_summary(
            results, ("cohort", "current_label")
        ),
        "by_finding": _group_summary(results, ("cohort", "finding")),
        "confusion": [
            {
                "cohort": cohort,
                "current_label": current,
                "sol_label": sol,
                "rows": count,
            }
            for (cohort, current, sol), count in sorted(confusion.items())
        ],
        "quality_flag_counts": dict(
            sorted(
                Counter(
                    flag for row in results for flag in row["quality_flags"]
                ).items()
            )
        ),
        "labels_modified": 0,
        "samples_deleted": 0,
        "splits_modified": 0,
        "training_started": False,
        "post_relabel_metrics_computed": False,
    }
    analysis_dir.mkdir(parents=True)
    all_jsonl = analysis_dir / "all_review_results.jsonl"
    flagged_csv = analysis_dir / "all_flagged_for_review.csv"
    difficult_csv = analysis_dir / "dev_high_risk_sol_agrees.csv"
    summary_json = analysis_dir / "aggregate_summary.json"
    write_jsonl_atomic(all_jsonl, results)
    _write_csv(flagged_csv, flagged)
    _write_csv(difficult_csv, difficult)
    write_json_atomic(summary_json, summary)
    report = analysis_dir / "PRTA_CXR_受保护标签质量复核.md"
    lines = [
        "# PRTA-CXR Dev / Internal-test / Gold 标签质量复核",
        "",
        "> 只读审计：不改标签、不删除样本、不调整划分、不训练模型，"
        "不计算改标后指标。Sol 结果是独立自动复核意见，不是医学 Gold。",
        "",
        f"- 全量覆盖：{len(results):,}",
        f"- 不一致/Unclear/质量标志并集：{len(flagged):,}",
        f"- Dev 高风险但 Sol 同意当前标签：{len(difficult):,}",
        "",
        "逐样本完整记录见 `all_review_results.jsonl`，所有需复核记录见 "
        "`all_flagged_for_review.csv`，Dev 困难一致样本见 "
        "`dev_high_risk_sol_agrees.csv`。",
        "",
        "## 分队列概览",
        "",
    ]
    for item in summary["overall"]:
        lines.append(
            "- {cohort}: rows={rows:,}, decisive_agreement={rate}, "
            "Unclear={unclear:,}, quality_flagged={flagged:,}, kappa={kappa}".format(
                cohort=item["cohort"],
                rows=item["rows"],
                rate=item["decisive_agreement_rate"],
                unclear=item["sol_unclear"],
                flagged=item["quality_flagged"],
                kappa=item["cohen_kappa"],
            )
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    final_hashes = {
        "train_dev": sha256_file(args.train_dev),
        "internal_test": sha256_file(args.internal_test),
        "gold": sha256_file(args.gold_original),
    }
    if final_hashes != before_hashes:
        raise RuntimeError("protected source hash changed during comparison")
    receipt = {
        "schema": "prta-cxr.protected-quality-final-receipt.v1",
        "status": "PASS_READ_ONLY_PROTECTED_LABEL_QUALITY_AUDIT",
        "input_hashes_before": before_hashes,
        "input_hashes_after": final_hashes,
        "dev_risk_sha256": sha256_file(args.dev_risk),
        "row_counts": {cohort: len(candidates[cohort]) for cohort in COHORT_ROWS},
        "total_rows": len(results),
        "output_hashes": {
            path.name: sha256_file(path)
            for path in (
                all_jsonl,
                flagged_csv,
                difficult_csv,
                summary_json,
                report,
            )
        },
        "labels_modified": 0,
        "training_or_model_metric_computation_started": False,
    }
    write_json_atomic(args.output_root / "final_audit_receipt.json", receipt)
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def finalize_protected_quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Wait for protected review and run read-only finalization"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dev-risk", type=Path, required=True)
    parser.add_argument("--gold-original", type=Path, required=True)
    parser.add_argument("--train-dev", type=Path, required=True)
    parser.add_argument("--internal-test", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=10800)
    args = parser.parse_args(argv)
    _private(args.output_root)
    preparation = json.loads(
        (args.output_root / "preparation_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        cohort: preparation["preparation"][cohort]["batches"]
        for cohort in COHORT_ROWS
    }
    state_path = args.output_root / "keeper_state.json"
    if state_path.exists():
        raise FileExistsError(f"refusing existing keeper state: {state_path}")
    started = time.monotonic()
    while True:
        counts = {
            cohort: len(
                list(
                    (
                        args.output_root
                        / "private"
                        / "outputs"
                        / cohort
                    ).glob("batch_*.json")
                )
            )
            for cohort in COHORT_ROWS
        }
        if any(counts[key] > expected[key] for key in counts):
            raise RuntimeError("output batch count exceeds frozen expectation")
        elapsed = round(time.monotonic() - started, 3)
        state = {
            "schema": "prta-cxr.protected-quality-keeper.v1",
            "status": "WAITING_FOR_FULL_BLIND_REVIEW",
            "pid": os.getpid(),
            "updated_at_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": elapsed,
            "batch_counts": counts,
            "expected_batches": expected,
            "training_or_mutation_started": False,
        }
        replace_json_atomic(state_path, state)
        if counts == expected:
            compare_args = [
                "--output-root",
                str(args.output_root),
                "--dev-risk",
                str(args.dev_risk),
                "--gold-original",
                str(args.gold_original),
                "--train-dev",
                str(args.train_dev),
                "--internal-test",
                str(args.internal_test),
            ]
            compare_protected_quality_main(compare_args)
            state.update(
                {
                    "status": "PASS_FULL_REVIEW_AND_COMPARISON_COMPLETE",
                    "updated_at_utc": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            replace_json_atomic(state_path, state)
            return 0
        if elapsed >= args.timeout_seconds:
            state.update(
                {
                    "status": "HOLD_INCOMPLETE_REVIEW_TIMEOUT",
                    "updated_at_utc": datetime.now(UTC).isoformat(),
                }
            )
            replace_json_atomic(state_path, state)
            return 2
        time.sleep(args.poll_seconds)
