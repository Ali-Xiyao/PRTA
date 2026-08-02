from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from prta_cxr.receipts import validate_run_receipt


@contextmanager
def _registry_lock(path: Path):
    lock_path = Path(path).with_suffix(Path(path).suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_run_registry(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def upsert_run_registry(path: Path, receipt: dict[str, Any]) -> None:
    value = validate_run_receipt(receipt)
    path = Path(path)
    with _registry_lock(path):
        rows = read_run_registry(path)
        matches = [
            index
            for index, row in enumerate(rows)
            if row["experiment_id"] == value["experiment_id"]
        ]
        if len(matches) > 1:
            raise ValueError("run registry has duplicate experiment IDs")
        if matches:
            rows[matches[0]] = value
        else:
            rows.append(value)
        rows.sort(key=lambda row: row["experiment_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                for row in rows:
                    handle.write(
                        json.dumps(row, sort_keys=True, ensure_ascii=False)
                    )
                    handle.write("\n")
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
