from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pack the frozen Phase16 Dev current-image subset"
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.receipt.exists():
        parser.error("--output and --receipt must be new immutable paths")
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    if inventory.get("schema") != "prta-cxr.phase16-dev-current-raw-inventory.v1":
        raise ValueError("unsupported Dev current-image inventory")
    items = list(inventory["items"])
    if len(items) != int(inventory["count"]):
        raise ValueError("inventory count drift")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp.{os.getpid()}")
    file_hashes: dict[str, str] = {}
    total_bytes = 0
    try:
        with tarfile.open(temporary, mode="w:gz", compresslevel=1) as archive:
            for item in items:
                source = Path(str(item["original_path"]))
                if not source.is_file():
                    raise FileNotFoundError(source)
                expected_name = f"{item['key']}.jpg"
                if str(item["name"]) != expected_name:
                    raise ValueError("inventory filename/key mismatch")
                total_bytes += source.stat().st_size
                file_hashes[expected_name] = _sha256(source)
                archive.add(source, arcname=f"images/{expected_name}", recursive=False)
        temporary.replace(args.output)
    finally:
        if temporary.exists():
            temporary.unlink()
    receipt = {
        "schema": "prta-cxr.phase16-dev-current-raw-pack.v1",
        "status": "PASS_PHASE16_DEV_CURRENT_RAW_PACKED",
        "inventory_sha256": _sha256(args.inventory),
        "archive_sha256": _sha256(args.output),
        "image_count": len(items),
        "total_uncompressed_bytes": total_bytes,
        "file_sha256": file_hashes,
        "dev_only": True,
        "internal_test_opened": False,
        "gold_opened": False,
        "protected_outcome_read_count": 0,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt_temp = args.receipt.with_name(f".{args.receipt.name}.tmp.{os.getpid()}")
    receipt_temp.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    receipt_temp.replace(args.receipt)
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in (
                    "status",
                    "archive_sha256",
                    "image_count",
                    "total_uncompressed_bytes",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
