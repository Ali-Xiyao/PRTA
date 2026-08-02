from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prta_cxr.contracts import ContractError, canonical_sha256

SOURCE_STATUSES = frozenset(
    {
        "eligible_candidate",
        "debug_only_legacy",
        "revealed_test",
        "protected_gold",
        "external_confirmation",
        "governance_hold",
    }
)
BLOCKED_STATUSES = frozenset(
    {
        "revealed_test",
        "protected_gold",
        "external_confirmation",
        "governance_hold",
    }
)


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    patient_namespace: str
    manifest_env: str
    status: str
    allowed_official_splits: tuple[str, ...]
    longitudinal_reports: bool
    license_verified: bool
    deidentified: bool
    processing_allowed: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SourceSpec:
        required = {
            "source_id",
            "patient_namespace",
            "manifest_env",
            "status",
            "allowed_official_splits",
            "longitudinal_reports",
            "license_verified",
            "deidentified",
            "processing_allowed",
        }
        if set(value) != required:
            raise ContractError(
                "source fields mismatch; "
                f"missing={sorted(required - set(value))}, "
                f"extra={sorted(set(value) - required)}"
            )
        status = str(value["status"])
        if status not in SOURCE_STATUSES:
            raise ContractError(f"unknown source status: {status}")
        splits = tuple(str(item) for item in value["allowed_official_splits"])
        if not splits:
            raise ContractError("allowed_official_splits cannot be empty")
        booleans = (
            "longitudinal_reports",
            "license_verified",
            "deidentified",
            "processing_allowed",
        )
        if any(type(value[key]) is not bool for key in booleans):
            raise ContractError("source governance flags must be booleans")
        return cls(
            source_id=str(value["source_id"]),
            patient_namespace=str(value["patient_namespace"]),
            manifest_env=str(value["manifest_env"]),
            status=status,
            allowed_official_splits=splits,
            longitudinal_reports=bool(value["longitudinal_reports"]),
            license_verified=bool(value["license_verified"]),
            deidentified=bool(value["deidentified"]),
            processing_allowed=bool(value["processing_allowed"]),
        )

    def activation_reasons(self) -> list[str]:
        reasons = []
        if self.status in BLOCKED_STATUSES:
            reasons.append(f"blocked_status:{self.status}")
        if not self.longitudinal_reports:
            reasons.append("no_longitudinal_reports")
        if not self.license_verified:
            reasons.append("license_not_verified")
        if not self.deidentified:
            reasons.append("not_deidentified")
        if not self.processing_allowed:
            reasons.append("processing_not_allowed")
        return reasons

    @property
    def eligible_for_repartition(self) -> bool:
        return self.status in {"eligible_candidate", "debug_only_legacy"} and not (
            self.activation_reasons()
        )

    def manifest_path(self) -> Path:
        raw = os.environ.get(self.manifest_env, "").strip()
        if not raw:
            raise ContractError(
                f"source {self.source_id} requires environment {self.manifest_env}"
            )
        return Path(raw)


@dataclass(frozen=True)
class SourceCatalog:
    schema: str
    policy: str
    debug_only_isolation_retired: bool
    split_fractions: dict[str, float]
    sources: tuple[SourceSpec, ...]

    def audit(self) -> dict[str, Any]:
        entries = []
        for source in self.sources:
            reasons = source.activation_reasons()
            entries.append(
                {
                    "source_id": source.source_id,
                    "status": source.status,
                    "eligible_for_repartition": source.eligible_for_repartition,
                    "debug_only_reactivated": source.status == "debug_only_legacy"
                    and source.eligible_for_repartition,
                    "hold_reasons": reasons,
                    "manifest_env": source.manifest_env,
                    "manifest_env_set": bool(
                        os.environ.get(source.manifest_env, "").strip()
                    ),
                }
            )
        return {
            "schema": "prta-cxr.source-catalog-audit.v1",
            "policy": self.policy,
            "debug_only_isolation_retired": self.debug_only_isolation_retired,
            "sources": entries,
            "eligible_source_count": sum(
                item["eligible_for_repartition"] for item in entries
            ),
            "catalog_sha256": canonical_sha256(self.to_dict()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy": self.policy,
            "debug_only_isolation_retired": self.debug_only_isolation_retired,
            "default_split_fractions": self.split_fractions,
            "sources": [
                {
                    "source_id": item.source_id,
                    "patient_namespace": item.patient_namespace,
                    "manifest_env": item.manifest_env,
                    "status": item.status,
                    "allowed_official_splits": list(
                        item.allowed_official_splits
                    ),
                    "longitudinal_reports": item.longitudinal_reports,
                    "license_verified": item.license_verified,
                    "deidentified": item.deidentified,
                    "processing_allowed": item.processing_allowed,
                }
                for item in self.sources
            ],
        }


def load_source_catalog(path: Path) -> SourceCatalog:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema") != "prta-cxr.source-catalog.v1":
        raise ContractError("unsupported source catalog schema")
    fractions = {
        str(key): float(amount)
        for key, amount in value["default_split_fractions"].items()
    }
    if set(fractions) != {"train", "dev", "internal_test"}:
        raise ContractError("split fractions must define train/dev/internal_test")
    if abs(sum(fractions.values()) - 1.0) > 1e-9 or any(
        amount <= 0 for amount in fractions.values()
    ):
        raise ContractError("split fractions must be positive and sum to one")
    sources = tuple(SourceSpec.from_mapping(item) for item in value["sources"])
    identifiers = [item.source_id for item in sources]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("source_id values must be unique")
    if not value.get("debug_only_isolation_retired"):
        raise ContractError("new catalog must retire debug-only isolation")
    return SourceCatalog(
        schema=str(value["schema"]),
        policy=str(value["policy"]),
        debug_only_isolation_retired=True,
        split_fractions=fractions,
        sources=sources,
    )
