from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from prta_cxr.contracts import ContractError, canonical_sha256

HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PROTECTED_CATEGORIES = frozenset(
    {
        "revealed_historical_test",
        "protected_gold",
        "clinician_audit",
        "external_confirmation",
        "license_or_privacy_hold",
    }
)


def load_exclusion_registry(path: Path) -> tuple[frozenset[str], dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema") != "prta-cxr.patient-exclusions.v1":
        raise ContractError("unsupported patient exclusion registry schema")
    categories = value.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ContractError("exclusion registry requires categories")
    union: set[str] = set()
    counts = {}
    for item in categories:
        if set(item) != {"category", "patient_id_hashes"}:
            raise ContractError("exclusion category fields mismatch")
        category = str(item["category"])
        if category not in PROTECTED_CATEGORIES:
            raise ContractError(f"unknown protected category: {category}")
        patients = {str(patient).lower() for patient in item["patient_id_hashes"]}
        if any(not HASH_PATTERN.fullmatch(patient) for patient in patients):
            raise ContractError("exclusion registry requires SHA-256 patient hashes")
        counts[category] = len(patients)
        union.update(patients)
    audit = {
        "schema": "prta-cxr.patient-exclusion-audit.v1",
        "outcome_fields_read": [],
        "categories": counts,
        "union_patient_count": len(union),
        "registry_sha256": canonical_sha256(value),
    }
    return frozenset(union), audit
