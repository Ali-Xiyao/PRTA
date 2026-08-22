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
        root / "configs" / "final" / "prta_cxr_slim_s1.json",
        root / "configs" / "models" / "prta_vit_v1.json",
        root / "configs" / "training" / "prta_full_v1.json",
        root / "configs" / "training" / "smoke_v1.json",
        root / "configs" / "data" / "source_catalog_v1.json",
        root / "configs" / "data" / "pairing_v1.json",
        root / "configs" / "data" / "exclusion_sources_v1.json",
        root / "src" / "prta_cxr" / "models" / "prta.py",
        root / "src" / "prta_cxr" / "training" / "engine.py",
        root / "src" / "prta_cxr" / "training" / "losses.py",
        root / "scripts" / "07_train.py",
        root / "scripts" / "08_evaluate.py",
    ]
    missing = [
        path.relative_to(root).as_posix()
        for path in required
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(f"preflight missing required files: {missing}")

    json_files = sorted((root / "configs").rglob("*.json"))
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
        for folder in ("configs", "manifests")
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
