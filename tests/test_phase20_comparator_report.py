from __future__ import annotations

import json
from pathlib import Path

import pytest

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file
from prta_cxr.phase20_comparator_program import COMPARATOR_SPECS, COMPARATOR_STATUS
from prta_cxr.phase20_comparator_report import (
    _job_identity,
    merge_interim_host_snapshots,
    render_interim_markdown,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _cell(method: str, seed: int) -> dict[str, object]:
    score = 0.5 + seed / 1000
    return {
        "job_id": f"train-P20-REBUILD-{method}-S{seed}",
        "experiment_id": f"P20-REBUILD-{method}-S{seed}",
        "method": method,
        "seed": seed,
        "hardware_class": "A800-80GB",
        "best_epoch": 1,
        "completed_epochs": 2,
        "duration_seconds": 100,
        "metrics": {
            "macro_f1": score,
            "balanced_accuracy": score,
            "min_class_recall": score,
            "opposite_direction_error_rate": 0.01,
            "nll": 1.0,
            "brier": 0.5,
        },
        "ordinary": {
            "per_class_recall": {label: score for label in PROGRESSION_LABELS},
            "per_class_f1": {label: score for label in PROGRESSION_LABELS},
        },
        "parameter_audit": {"total_parameters": 10, "trainable_parameters": 5},
        "method_provenance": COMPARATOR_SPECS[method]["method_provenance"],
        "comparison_protocol": "test",
        "official_implementation": False,
        "official_checkpoint": False,
        "checkpoint_sha256": "a" * 64,
        "training_receipt_sha256": "b" * 64,
    }


def test_interim_merge_reports_complete_and_pending_methods(tmp_path: Path) -> None:
    program = tmp_path / "program"
    jobs = []
    for index, method in enumerate(COMPARATOR_SPECS):
        for seed in (17, 28, 43):
            jobs.append(
                {
                    "job_id": f"train-P20-REBUILD-{method}-S{seed}",
                    "host": "server" if index % 2 == 0 else "local",
                }
            )
    _write(program / "job_registry.json", {"jobs": jobs})
    _write(
        program / "preparation_receipt.json",
        {"status": COMPARATOR_STATUS, "source_commit": "c" * 40},
    )
    snapshots = []
    for host in ("server", "local"):
        selected = [job for job in jobs if job["host"] == host]
        cells = []
        statuses = []
        for job in selected:
            _, rest = str(job["job_id"]).split("REBUILD-", 1)
            method, seed_text = rest.rsplit("-S", 1)
            seed = int(seed_text)
            complete = method == "V2" or seed == 17
            status = "PASS" if complete else "PENDING"
            statuses.append(
                {
                    "job_id": job["job_id"],
                    "method": method,
                    "seed": seed,
                    "lane": "a800_3066",
                    "status": status,
                }
            )
            if complete:
                cells.append(_cell(method, seed))
        snapshots.append(
            {
                "schema": "prta-cxr.phase20-comparator-interim-host.v1",
                "status": "PHASE20_COMPARATOR_INTERIM_HOST_SNAPSHOT_VALIDATED",
                "host": host,
                "program_preparation_sha256": sha256_file(
                    program / "preparation_receipt.json"
                ),
                "source_commit": "c" * 40,
                "job_status": statuses,
                "cells": cells,
                "external_evaluation_included": False,
                "internal_test_opened": False,
                "gold_opened": False,
                "protected_outcome_read_count": 0,
            }
        )
    result = merge_interim_host_snapshots(program, snapshots)
    assert result["counts"]["PASS"] == 10
    assert result["methods"]["V2"]["status"] == "COMPLETE_THREE_SEED"
    assert result["methods"]["B401"]["status"] == "PENDING_THREE_SEED"
    assert result["methods"]["B401"]["pending_seeds"] == [28, 43]
    markdown = render_interim_markdown(result)
    assert "待跑/待汇总" in markdown
    assert "24/24 正式 finalizer" in markdown


def test_interim_merge_rejects_missing_job(tmp_path: Path) -> None:
    program = tmp_path / "program"
    _write(program / "job_registry.json", {"jobs": [{"job_id": "a"}]})
    _write(
        program / "preparation_receipt.json",
        {"status": COMPARATOR_STATUS, "source_commit": "c" * 40},
    )
    base = {
        "status": "PHASE20_COMPARATOR_INTERIM_HOST_SNAPSHOT_VALIDATED",
        "program_preparation_sha256": sha256_file(program / "preparation_receipt.json"),
        "source_commit": "c" * 40,
        "job_status": [],
        "cells": [],
        "external_evaluation_included": False,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    with pytest.raises(ValueError, match="duplicate or missing jobs"):
        merge_interim_host_snapshots(
            program,
            [{**base, "host": "server"}, {**base, "host": "local"}],
        )


def test_job_identity_is_resolved_from_frozen_config(tmp_path: Path) -> None:
    program = tmp_path / "program"
    _write(
        program / "configs" / "P20-REBUILD-B401-S17.json",
        {"phase20_role": "B401", "seed": 17},
    )
    assert _job_identity(program, {"job_id": "train-P20-REBUILD-B401-S17"}) == (
        "B401",
        17,
    )
