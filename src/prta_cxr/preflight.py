from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .contracts import sha256_file

WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[\"'])(?:[a-z]:\\\\)")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_preflight(root: Path | None = None) -> dict[str, Any]:
    root = project_root() if root is None else Path(root).resolve()
    required = [
        root / "pyproject.toml",
        root / "src" / "prta_cxr" / "models" / "prta.py",
        root / "schemas" / "luna_label_batch.schema.json",
        root / "prompts" / "luna_label_v1.md",
        root / "prompts" / "luna_verify_v1.md",
        root / "schemas" / "independent_silver_label_batch.schema.json",
        root / "prompts" / "independent_silver_label_v1.md",
        root / "configs" / "labeling" / "independent_silver_v1.json",
        root / "configs" / "labeling" / "sol_blind_review_v1.json",
        root / "configs" / "labeling" / "luna_primary_full_v1.json",
    ]
    missing = [
        path.relative_to(root).as_posix()
        for path in required
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(f"preflight missing required files: {missing}")

    json_files = sorted((root / "configs").rglob("*.json")) + sorted(
        (root / "schemas").rglob("*.json")
    )
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))

    scan_files = sorted((root / "src").rglob("*.py")) + sorted(
        (root / "configs").rglob("*.json")
    )
    absolute_path_hits = []
    for path in scan_files:
        if WINDOWS_ABSOLUTE.search(path.read_text(encoding="utf-8")):
            absolute_path_hits.append(path.relative_to(root).as_posix())
    if absolute_path_hits:
        raise ValueError(f"hard-coded Windows paths: {absolute_path_hits}")

    authority = sorted(
        path
        for folder in ("configs", "prompts", "schemas")
        for path in (root / folder).rglob("*")
        if path.is_file()
    )
    return {
        "status": "PASS_PRTA_CXR_ENGINEERING_PREFLIGHT",
        "formal_experiment_started": False,
        "real_data_opened": False,
        "protected_outcomes_opened": False,
        "required_files": len(required),
        "json_files_validated": len(json_files),
        "authority_hashes": {
            path.relative_to(root).as_posix(): sha256_file(path) for path in authority
        },
        "absolute_path_hits": [],
    }
