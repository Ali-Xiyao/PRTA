from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import tarfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

import zstandard as zstd

from .artifacts import write_json_atomic, write_jsonl_atomic
from .authorization import require_formal_authorization
from .contracts import canonical_sha256, sha256_file

FRONTAL_VIEWS = ("PA", "POSTERO_ANTERIOR", "AP")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ConcatenatedPartsReader(io.RawIOBase):
    """Read immutable multipart files as one stream without materializing a copy."""

    def __init__(self, parts: Sequence[Path]) -> None:
        super().__init__()
        if not parts:
            raise ValueError("at least one archive part is required")
        self.parts = [Path(path) for path in parts]
        self._index = -1
        self._handle: BinaryIO | None = None
        self._digest: hashlib._Hash | None = None
        self.part_sha256: dict[str, str] = {}
        self.part_bytes: dict[str, int] = {}
        self.total_bytes_read = 0
        self._open_next()

    def readable(self) -> bool:
        return True

    def _finish_current(self) -> None:
        if self._handle is None or self._digest is None or self._index < 0:
            return
        path = self.parts[self._index]
        self._handle.close()
        self.part_sha256[path.name] = self._digest.hexdigest()
        self._handle = None
        self._digest = None

    def _open_next(self) -> bool:
        self._finish_current()
        self._index += 1
        if self._index >= len(self.parts):
            return False
        path = self.parts[self._index]
        self._handle = path.open("rb")
        self._digest = hashlib.sha256()
        self.part_bytes[path.name] = 0
        return True

    def read(self, size: int = -1) -> bytes:
        if self._handle is None:
            return b""
        if size is None or size < 0:
            chunks = []
            while self._handle is not None:
                chunk = self.read(8 * 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        remaining = size
        chunks = []
        while remaining > 0 and self._handle is not None:
            chunk = self._handle.read(remaining)
            if chunk:
                assert self._digest is not None
                self._digest.update(chunk)
                name = self.parts[self._index].name
                self.part_bytes[name] += len(chunk)
                self.total_bytes_read += len(chunk)
                chunks.append(chunk)
                remaining -= len(chunk)
                continue
            self._open_next()
        return b"".join(chunks)

    def close(self) -> None:
        self._finish_current()
        super().close()


def _normalized_member(path: str) -> str:
    value = str(PurePosixPath(str(path).replace("\\", "/")))
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def _private_id(salt: bytes, role: str, value: str) -> str:
    return hmac.new(salt, f"{role}|{value}".encode(), hashlib.sha256).hexdigest()


def _study_date(value: object) -> datetime:
    return datetime.strptime(str(value), "%Y%m%d").replace(tzinfo=UTC)


def _frontal_images(study: Mapping[str, Any]) -> list[tuple[str, str]]:
    paths = list(study.get("ImagePath") or [])
    views = list(study.get("ImageViewPosition") or [])
    if len(paths) != len(views):
        raise ValueError("ImagePath/ImageViewPosition length mismatch")
    result = [
        (_normalized_member(str(path)), str(view))
        for path, view in zip(paths, views, strict=True)
        if str(view) in FRONTAL_VIEWS
    ]
    return sorted(result, key=lambda item: (FRONTAL_VIEWS.index(item[1]), item[0]))


def _select_images(
    prior: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[tuple[str, str], tuple[str, str]] | None:
    prior_images = _frontal_images(prior)
    current_images = _frontal_images(current)
    if not prior_images or not current_images:
        return None
    for view in FRONTAL_VIEWS:
        prior_same = [item for item in prior_images if item[1] == view]
        current_same = [item for item in current_images if item[1] == view]
        if prior_same and current_same:
            return prior_same[0], current_same[0]
    return prior_images[0], current_images[0]


def select_pairs(
    studies: Mapping[str, Mapping[str, Any]], *, split: str, salt: bytes
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if split not in {"validation", "test"}:
        raise ValueError("external split must be validation or test")
    by_patient: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for study in studies.values():
        required = {
            "PatientID",
            "StudyDate",
            "StudyInstanceUid",
            "ImagePath",
            "ImageViewPosition",
            "Findings",
            "Impression",
        }
        missing = required.difference(study)
        if missing:
            raise ValueError(f"ReXGradient study fields missing: {sorted(missing)}")
        by_patient[str(study["PatientID"])].append(study)

    rows: list[dict[str, Any]] = []
    image_members: dict[str, str] = {}
    for patient_id, patient_studies in sorted(by_patient.items()):
        ordered = sorted(
            patient_studies,
            key=lambda study: (
                _study_date(study["StudyDate"]),
                str(study["StudyInstanceUid"]),
            ),
        )
        for prior, current in zip(ordered, ordered[1:], strict=False):
            prior_date = _study_date(prior["StudyDate"])
            current_date = _study_date(current["StudyDate"])
            if prior_date >= current_date:
                continue
            selected = _select_images(prior, current)
            if selected is None:
                continue
            (prior_member, prior_view), (current_member, current_view) = selected
            for member in (prior_member, current_member):
                member_key = PurePosixPath(member).name
                image_id = _private_id(salt, "image", member_key)
                relative = f"images/{image_id}.png"
                if (
                    member_key in image_members
                    and image_members[member_key] != relative
                ):
                    raise ValueError("metadata image basename collision")
                image_members[member_key] = relative
            prior_study = str(prior["StudyInstanceUid"])
            current_study = str(current["StudyInstanceUid"])
            pair_value = f"{patient_id}|{prior_study}|{current_study}"
            rows.append(
                {
                    "schema": "prta-cxr.rexgradient-unlabeled-pair.v1",
                    "sample_id": _private_id(salt, f"pair-{split}", pair_value),
                    "source": "rexgradient_160k",
                    "external_split": split,
                    "patient_id_hash": _private_id(salt, "patient", patient_id),
                    "prior_study_id_hash": _private_id(salt, "study", prior_study),
                    "current_study_id_hash": _private_id(salt, "study", current_study),
                    "prior_image_path": image_members[PurePosixPath(prior_member).name],
                    "current_image_path": image_members[
                        PurePosixPath(current_member).name
                    ],
                    "prior_datetime": prior_date.isoformat(),
                    "current_datetime": current_date.isoformat(),
                    "interval_days": (current_date - prior_date).days,
                    "prior_view": prior_view,
                    "current_view": current_view,
                    "view_relation": (
                        "same" if prior_view == current_view else "frontal_cross_view"
                    ),
                    "prior_report": {
                        "indication": str(prior.get("Indication") or ""),
                        "comparison": str(prior.get("Comparison") or ""),
                        "findings": str(prior.get("Findings") or ""),
                        "impression": str(prior.get("Impression") or ""),
                    },
                    "current_report": {
                        "indication": str(current.get("Indication") or ""),
                        "comparison": str(current.get("Comparison") or ""),
                        "findings": str(current.get("Findings") or ""),
                        "impression": str(current.get("Impression") or ""),
                    },
                    "label_state": "UNLABELED_EXTERNAL_PENDING_FROZEN_MAPPING",
                    "progression_label": None,
                    "finding": None,
                }
            )
    rows.sort(key=lambda row: str(row["sample_id"]))
    return rows, image_members


def _load_studies(path: Path) -> dict[str, Mapping[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected study JSON object: {path}")
    if not all(isinstance(item, dict) for item in value.values()):
        raise ValueError(f"invalid study row: {path}")
    return value


def _load_expected_parts(
    path: Path, parts: Sequence[Path]
) -> dict[str, dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    files = value.get("files") if isinstance(value, dict) else None
    if not isinstance(files, dict):
        raise ValueError("part inventory must contain a files object")
    expected = {}
    for part in parts:
        item = files.get(part.name)
        if not isinstance(item, dict):
            raise ValueError(f"part missing from inventory: {part.name}")
        if int(item.get("size", -1)) != part.stat().st_size:
            raise ValueError(f"part size mismatch: {part.name}")
        digest = str(item.get("sha256", ""))
        if len(digest) != 64:
            raise ValueError(f"invalid expected SHA-256: {part.name}")
        expected[part.name] = {"size": part.stat().st_size, "sha256": digest}
    return expected


def _existing_image_inventory(
    output_root: Path, image_members: Mapping[str, str]
) -> dict[str, dict[str, Any]]:
    inventory = {}
    for member, relative in image_members.items():
        path = output_root / relative
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                raise ValueError(f"invalid resumed PNG: {relative}")
        inventory[member] = {
            "relative_path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return inventory


def stream_selected_images(
    parts: Sequence[Path],
    *,
    image_members: Mapping[str, str],
    output_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, int]]:
    inventory = _existing_image_inventory(output_root, image_members)
    missing = set(image_members).difference(inventory)
    reader = ConcatenatedPartsReader(parts)
    decompressed = zstd.ZstdDecompressor().stream_reader(
        reader,
        read_across_frames=True,
        closefd=False,
    )
    member_count = 0
    selected_seen: set[str] = set()
    try:
        with tarfile.open(fileobj=decompressed, mode="r|") as archive:
            for member in archive:
                member_count += 1
                normalized = _normalized_member(member.name)
                member_key = PurePosixPath(normalized).name
                if member_key not in image_members:
                    if member_count % 20_000 == 0:
                        print(
                            json.dumps(
                                {
                                    "archive_members_scanned": member_count,
                                    "selected_images_written": len(inventory),
                                    "selected_images_remaining": len(missing),
                                    "archive_gib_read": round(
                                        reader.total_bytes_read / 1024**3, 2
                                    ),
                                },
                                sort_keys=True,
                            ),
                            flush=True,
                        )
                    continue
                if member_key in selected_seen:
                    raise ValueError("selected archive basename is not unique")
                selected_seen.add(member_key)
                if member_key not in missing:
                    continue
                if not member.isfile():
                    raise ValueError(
                        f"selected archive member is not a file: {normalized}"
                    )
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"cannot read selected member: {normalized}")
                relative = image_members[member_key]
                destination = output_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(
                    f".{destination.name}.tmp.{os.getpid()}"
                )
                digest = hashlib.sha256()
                byte_count = 0
                with temporary.open("wb") as handle:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        byte_count += len(chunk)
                        handle.write(chunk)
                with temporary.open("rb") as handle:
                    if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                        raise ValueError(f"selected member is not PNG: {normalized}")
                temporary.replace(destination)
                inventory[member_key] = {
                    "relative_path": relative,
                    "bytes": byte_count,
                    "sha256": digest.hexdigest(),
                }
                missing.remove(member_key)
        while decompressed.read(8 * 1024 * 1024):
            pass
    finally:
        decompressed.close()
        reader.close()
    if missing:
        raise ValueError(f"selected archive members missing: {len(missing)}")
    if selected_seen != set(image_members):
        raise ValueError("selected archive member roster mismatch")
    return inventory, reader.part_sha256, reader.part_bytes


def prepare_rexgradient_external_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select and stream ReXGradient longitudinal external pairs"
    )
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--parts-root", type=Path, required=True)
    parser.add_argument("--part-inventory", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)

    parts = sorted(args.parts_root.glob("deid_png.part[0-9][0-9]"))
    if [path.name for path in parts] != [f"deid_png.part{i:02d}" for i in range(10)]:
        raise ValueError("expected exact ReXGradient part00-part09 roster")
    expected_parts = _load_expected_parts(args.part_inventory, parts)

    output_root = args.output_root
    if output_root.exists() and not args.resume:
        raise FileExistsError(f"refusing to overwrite external output: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    salt_path = output_root / "private_hmac_salt.bin"
    if salt_path.exists():
        salt = salt_path.read_bytes()
    else:
        salt = os.urandom(32)
        salt_path.write_bytes(salt)
    if len(salt) != 32:
        raise ValueError("invalid external HMAC salt")

    split_inputs = {
        "validation": args.metadata_root / "valid_metadata_view_position.json",
        "test": args.metadata_root / "test_metadata_view_position.json",
    }
    all_rows = {}
    all_members: dict[str, str] = {}
    patient_sets = {}
    for split, path in split_inputs.items():
        studies = _load_studies(path)
        patient_sets[split] = {str(study["PatientID"]) for study in studies.values()}
        rows, members = select_pairs(studies, split=split, salt=salt)
        all_rows[split] = rows
        for member, relative in members.items():
            if member in all_members and all_members[member] != relative:
                raise ValueError("image destination identity collision")
            all_members[member] = relative
    if patient_sets["validation"].intersection(patient_sets["test"]):
        raise ValueError("validation/test patient overlap")

    selection_payload = {
        "schema": "prta-cxr.rexgradient-selection.v1",
        "selection_protocol": (
            "consecutive_strict_date_frontal_same_view_preferred_v1"
        ),
        "split_pair_counts": {split: len(rows) for split, rows in all_rows.items()},
        "split_patient_counts": {
            split: len({str(row["patient_id_hash"]) for row in rows})
            for split, rows in all_rows.items()
        },
        "selected_unique_image_count": len(all_members),
        "view_relation_counts": dict(
            Counter(
                str(row["view_relation"]) for rows in all_rows.values() for row in rows
            )
        ),
        "label_state": "UNLABELED_EXTERNAL_PENDING_FROZEN_MAPPING",
        "selection_used_progression_outcomes": False,
        "raw_identifier_written_count": 0,
        "metadata_hashes": {
            name: sha256_file(path) for name, path in split_inputs.items()
        },
    }
    selection_payload["selection_sha256"] = canonical_sha256(selection_payload)
    selection_receipt = output_root / "receipts" / "selection_receipt.json"
    if selection_receipt.exists():
        existing = json.loads(selection_receipt.read_text(encoding="utf-8"))
        if existing != selection_payload:
            raise ValueError("resume selection identity drift")
    else:
        for split, rows in all_rows.items():
            write_jsonl_atomic(
                output_root / "manifests" / f"{split}_unlabeled_pairs.jsonl",
                rows,
            )
        write_json_atomic(selection_receipt, selection_payload)

    migration_receipt = output_root / "receipts" / "migration_receipt.json"
    if migration_receipt.is_file():
        existing = json.loads(migration_receipt.read_text(encoding="utf-8"))
        if existing.get("status") != "PASS_REXGRADIENT_SELECTED_SUBSET_MIGRATED":
            raise ValueError("existing migration receipt is not PASS")
        print(json.dumps(existing, indent=2, sort_keys=True))
        return 0

    inventory, part_sha256, part_bytes = stream_selected_images(
        parts,
        image_members=all_members,
        output_root=output_root,
    )
    for name, expected in expected_parts.items():
        if part_bytes.get(name) != expected["size"]:
            raise ValueError(f"archive part byte count mismatch: {name}")
        if part_sha256.get(name) != expected["sha256"]:
            raise ValueError(f"archive part SHA-256 mismatch: {name}")
    inventory_rows = [
        {
            "image_id": Path(item["relative_path"]).stem,
            "relative_path": item["relative_path"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        }
        for item in inventory.values()
    ]
    inventory_rows.sort(key=lambda row: str(row["image_id"]))
    image_inventory = output_root / "manifests" / "image_inventory.jsonl"
    write_jsonl_atomic(image_inventory, inventory_rows)
    receipt = {
        **selection_payload,
        "schema": "prta-cxr.rexgradient-migration.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "part_sha256": part_sha256,
        "image_inventory_sha256": sha256_file(image_inventory),
        "extracted_image_count": len(inventory_rows),
        "extracted_image_bytes": sum(int(row["bytes"]) for row in inventory_rows),
        "full_archive_materialized": False,
        "train_images_copied": False,
        "external_evaluation_started": False,
        "status": "PASS_REXGRADIENT_SELECTED_SUBSET_MIGRATED",
    }
    write_json_atomic(migration_receipt, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0
