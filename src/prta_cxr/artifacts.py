from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_WINDOWS_REPLACE_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)


def _replace_with_retry(temporary: Path, path: Path) -> None:
    """Retry transient Windows sharing violations without weakening atomicity."""
    for attempt, delay in enumerate(_WINDOWS_REPLACE_RETRY_DELAYS):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == len(_WINDOWS_REPLACE_RETRY_DELAYS) - 1:
                raise
            time.sleep(delay)


def _fresh_target(path: Path) -> Path:
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json_atomic(path: Path, value: Any) -> None:
    path = _fresh_target(path)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def replace_json_atomic(path: Path, value: Any) -> None:
    """Atomically replace an explicitly mutable state file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _replace_with_retry(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_jsonl_atomic(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path = _fresh_target(path)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False))
                handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
