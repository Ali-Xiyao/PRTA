from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from prta_cxr.contracts import (
    PROGRESSION_LABELS,
    ContractError,
    canonical_sha256,
    validate_sample,
)
from prta_cxr.independent_silver import validate_independent_ai_batch


def merge_luna_primary(
    samples: Sequence[Mapping[str, Any]],
    luna_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    validated_samples = [validate_sample(row) for row in samples]
    validated_luna = validate_independent_ai_batch(luna_rows)
    sample_by_id = {row["sample_id"]: row for row in validated_samples}
    luna_by_id = {row["sample_id"]: row["ai_label"] for row in validated_luna}
    if len(sample_by_id) != len(validated_samples):
        raise ContractError("duplicate sample_id in Luna-primary candidates")
    if set(luna_by_id) != set(sample_by_id):
        missing = len(set(sample_by_id) - set(luna_by_id))
        extra = len(set(luna_by_id) - set(sample_by_id))
        raise ContractError(
            f"Luna-primary IDs mismatch; missing={missing}, extra={extra}"
        )

    accepted = []
    discarded = []
    diagnostics = []
    for sample_id in sorted(sample_by_id):
        sample = sample_by_id[sample_id]
        luna_label = luna_by_id[sample_id]
        diagnostic = {
            "sample_id": sample_id,
            "source": sample["source"],
            "finding": sample["finding"],
            "rule_label": sample["progression_label"],
            "luna_label": luna_label,
            "rule_luna_exact": sample["progression_label"] == luna_label,
        }
        diagnostics.append(diagnostic)
        if luna_label == "Unclear":
            discarded.append(
                diagnostic | {"discard_reason": "luna_unclear"}
            )
            continue
        accepted.append(
            sample
            | {
                "progression_label": luna_label,
                "label_source": "luna_primary_report_label",
                "label_tier": "Silver",
            }
        )

    sources = sorted({row["source"] for row in diagnostics})
    audit = {
        "schema": "prta-cxr.luna-primary-merge-audit.v1",
        "status": "PASS_LUNA_PRIMARY_SILVER_MERGE",
        "candidate_rows": len(diagnostics),
        "accepted_silver_rows": len(accepted),
        "discarded_unclear_rows": len(discarded),
        "retention_rate": (
            len(accepted) / len(diagnostics) if diagnostics else 0.0
        ),
        "luna_label_counts": dict(
            sorted(Counter(row["luna_label"] for row in diagnostics).items())
        ),
        "accepted_by_source": {
            source: sum(row["source"] == source for row in accepted)
            for source in sources
        },
        "discarded_by_source": {
            source: sum(row["source"] == source for row in discarded)
            for source in sources
        },
        "accepted_by_finding": dict(
            sorted(Counter(row["finding"] for row in accepted).items())
        ),
        "rule_luna_exact_diagnostic": sum(
            row["rule_luna_exact"] for row in diagnostics
        ),
        "rule_label_used_for_admission": False,
        "manual_label_edits": False,
        "agreement_is_ground_truth": False,
        "human_accuracy_audit": {
            "required": True,
            "rows": 250,
            "stratification": "source_x_luna_five_label",
            "completed": False,
        },
        "gold_status": "GOLD_PENDING_HUMAN_REVIEW",
        "formal_training_authorized": False,
        "paper_use_authorized": False,
        "accepted_manifest_sha256": canonical_sha256(accepted),
        "discarded_manifest_sha256": canonical_sha256(discarded),
        "diagnostic_manifest_sha256": canonical_sha256(diagnostics),
    }
    return accepted, discarded, audit


def select_gold_audit_roster(
    silver_rows: Sequence[Mapping[str, Any]],
    *,
    roster_size: int = 250,
    salt: str = "prta-cxr-luna-primary-gold-audit-v1",
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    validated = [validate_sample(row) for row in silver_rows]
    sources = sorted({row["source"] for row in validated})
    strata = [(source, label) for source in sources for label in PROGRESSION_LABELS]
    if not strata or roster_size < len(strata) or roster_size % len(strata):
        raise ContractError("roster_size must divide evenly across source-label strata")
    per_stratum = roster_size // len(strata)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in validated:
        grouped[(row["source"], row["progression_label"])].append(row)

    def rank(value: str) -> str:
        return hashlib.sha256(f"{salt}|{value}".encode()).hexdigest()

    selected = []
    selected_patients: set[str] = set()
    for stratum in strata:
        rows = sorted(grouped[stratum], key=lambda row: rank(row["sample_id"]))
        chosen = []
        for row in rows:
            if row["patient_id_hash"] in selected_patients:
                continue
            chosen.append(row)
            selected_patients.add(row["patient_id_hash"])
            if len(chosen) == per_stratum:
                break
        if len(chosen) != per_stratum:
            raise ContractError(f"insufficient unique patients for stratum: {stratum}")
        selected.extend(chosen)
    selected.sort(key=lambda row: rank(row["sample_id"]))
    roster = [
        {
            "review_id": f"review_{index:04d}",
            "sample_id": row["sample_id"],
            "patient_id_hash": row["patient_id_hash"],
            "source": row["source"],
            "finding": row["finding"],
            "prior_report": row["prior_report"],
            "current_report": row["current_report"],
            "luna_label": row["progression_label"],
            "clinician_label": None,
            "review_status": "PENDING_HUMAN_REVIEW",
        }
        for index, row in enumerate(selected)
    ]
    quarantine = [
        {"patient_id_hash": patient, "reason": "gold_audit_pending_human_review"}
        for patient in sorted(selected_patients)
    ]
    audit = {
        "schema": "prta-cxr.gold-audit-roster.v1",
        "status": "GOLD_PENDING_HUMAN_REVIEW",
        "rows": len(roster),
        "unique_patients": len(selected_patients),
        "rows_per_source_label_stratum": per_stratum,
        "strata": {
            f"{source}|{label}": sum(
                row["source"] == source and row["luna_label"] == label
                for row in roster
            )
            for source, label in strata
        },
        "all_rows_human_confirmed": False,
        "gold_rows": 0,
        "training_quarantine_required": True,
        "roster_sha256": canonical_sha256(roster),
        "quarantine_sha256": canonical_sha256(quarantine),
        "salt": salt,
    }
    return roster, quarantine, audit


def apply_training_patient_quarantine(
    silver_rows: Sequence[Mapping[str, Any]],
    quarantine_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    validated = [validate_sample(row) for row in silver_rows]
    quarantine_patients = [
        str(row.get("patient_id_hash", "")).strip() for row in quarantine_rows
    ]
    if any(not patient for patient in quarantine_patients):
        raise ContractError("quarantine rows require patient_id_hash")
    if len(set(quarantine_patients)) != len(quarantine_patients):
        raise ContractError("duplicate patient_id_hash in quarantine")
    quarantine_set = set(quarantine_patients)
    training_eligible = [
        row for row in validated if row["patient_id_hash"] not in quarantine_set
    ]
    quarantined = [
        row for row in validated if row["patient_id_hash"] in quarantine_set
    ]
    observed = {row["patient_id_hash"] for row in quarantined}
    if observed != quarantine_set:
        raise ContractError("quarantine contains patients absent from Silver")
    audit = {
        "schema": "prta-cxr.training-patient-quarantine-audit.v1",
        "status": "PASS_GOLD_AUDIT_PATIENT_QUARANTINE",
        "input_silver_rows": len(validated),
        "quarantined_patients": len(quarantine_set),
        "quarantined_silver_rows": len(quarantined),
        "training_eligible_silver_rows": len(training_eligible),
        "patient_overlap": len(
            {row["patient_id_hash"] for row in training_eligible}
            & {row["patient_id_hash"] for row in quarantined}
        ),
        "training_eligible_manifest_sha256": canonical_sha256(training_eligible),
        "quarantined_manifest_sha256": canonical_sha256(quarantined),
    }
    return training_eligible, quarantined, audit
