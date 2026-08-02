from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prta_cxr.artifacts import write_json_atomic, write_jsonl_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.manifests import read_jsonl
from prta_cxr.human_review import finalize_human_review, read_human_review_xlsx
from prta_cxr.luna_primary import (
    apply_training_patient_quarantine,
    select_gold_audit_roster,
)


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _require_fresh_outputs(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"refusing existing output artifacts: {existing}")


def _synthetic_pool() -> list[dict[str, Any]]:
    templates = synthetic_samples()
    rows = []
    for source in ("mimic", "chexpert"):
        for patient in range(150):
            row = templates[patient % len(templates)].copy()
            row["sample_id"] = f"{source}-{patient}"
            row["patient_id_hash"] = f"{source}-patient-{patient}"
            row["source"] = source
            row["label_source"] = "luna_primary_report_label"
            row["label_tier"] = "Silver"
            rows.append(row)
    return rows


def _synthetic_responses(roster: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "case_no": index,
            "review_id": row["review_id"],
            "source": row["source"],
            "finding": row["finding"],
            "prior_report": row["prior_report"],
            "current_report": row["current_report"],
            "displayed_luna_label": row["luna_label"],
            "human_label": row["luna_label"],
            "unusable_reason": "",
            "reviewer_id": "synthetic-reviewer",
            "review_date": "2026-08-02",
            "notes_optional": "",
            "review_mode": "luna_assisted_senior_v2",
        }
        for index, row in enumerate(roster, start=1)
    ]


def finalize_human_review_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import human review, audit Luna binding, and freeze Gold"
    )
    parser.add_argument(
        "--mode", choices=("preflight", "formal"), default="preflight"
    )
    parser.add_argument("--workbook", type=Path)
    parser.add_argument("--expected-workbook-sha256")
    parser.add_argument("--roster", type=Path)
    parser.add_argument("--roster-audit", type=Path)
    parser.add_argument("--quarantine", type=Path)
    parser.add_argument("--silver", type=Path)
    parser.add_argument("--training-eligible-silver", type=Path)
    parser.add_argument("--responses-output", type=Path)
    parser.add_argument("--comparison-output", type=Path)
    parser.add_argument("--gold-output", type=Path)
    parser.add_argument("--excluded-output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight":
        pool = _synthetic_pool()
        roster, quarantine, _ = select_gold_audit_roster(
            pool, salt="synthetic-human-review"
        )
        training, _, _ = apply_training_patient_quarantine(pool, quarantine)
        outputs = finalize_human_review(
            roster,
            _synthetic_responses(roster),
            pool,
            quarantine,
            training,
            workbook_sha256="0" * 64,
        )
        _print(
            {
                "status": "PASS_HUMAN_REVIEW_FINALIZE_PREFLIGHT",
                "responses": len(outputs[0]),
                "comparisons": len(outputs[1]),
                "gold": len(outputs[2]),
                "excluded": len(outputs[3]),
                "audit": outputs[4],
                "real_human_responses_opened": False,
            }
        )
        return 0

    require_formal_authorization(formal_flag=args.formal)
    required_paths = (
        args.workbook,
        args.roster,
        args.roster_audit,
        args.quarantine,
        args.silver,
        args.training_eligible_silver,
        args.responses_output,
        args.comparison_output,
        args.gold_output,
        args.excluded_output,
        args.audit_output,
    )
    if not all(required_paths) or not args.expected_workbook_sha256:
        parser.error("formal mode requires every input/output and workbook hash")
    _require_fresh_outputs(
        args.responses_output,
        args.comparison_output,
        args.gold_output,
        args.excluded_output,
        args.audit_output,
    )
    workbook_hash = sha256_file(args.workbook)
    if workbook_hash != args.expected_workbook_sha256:
        raise RuntimeError("returned workbook hash differs from formal authority")
    roster = read_jsonl(args.roster)
    roster_audit = json.loads(args.roster_audit.read_text(encoding="utf-8"))
    if roster_audit.get("roster_sha256") != canonical_sha256(roster):
        raise RuntimeError("roster hash differs from frozen roster audit")
    responses = read_human_review_xlsx(args.workbook)
    validated_responses, comparisons, gold, excluded, audit = finalize_human_review(
        roster,
        responses,
        read_jsonl(args.silver),
        read_jsonl(args.quarantine),
        read_jsonl(args.training_eligible_silver),
        workbook_sha256=workbook_hash,
    )
    audit["roster_audit_sha256"] = sha256_file(args.roster_audit)
    audit["roster_manifest_sha256"] = canonical_sha256(roster)
    write_jsonl_atomic(args.responses_output, validated_responses)
    write_jsonl_atomic(args.comparison_output, comparisons)
    write_jsonl_atomic(args.gold_output, gold)
    write_jsonl_atomic(args.excluded_output, excluded)
    write_json_atomic(args.audit_output, audit)
    _print(audit)
    return 0
