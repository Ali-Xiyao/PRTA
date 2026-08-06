from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

SOURCE_COMMIT_ENV = "PRTA_CXR_SOURCE_COMMIT"
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40,64}")


def resolve_source_commit(repo_root: Path) -> str:
    """Resolve source identity from Git or an explicit archive provenance pin."""
    try:
        value = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(repo_root),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        value = os.environ.get(SOURCE_COMMIT_ENV, "").strip().lower()
    if not _COMMIT_PATTERN.fullmatch(value):
        raise RuntimeError(
            "source provenance is unavailable; run inside a Git checkout or set "
            f"{SOURCE_COMMIT_ENV} to the exact deployed commit"
        )
    return value
