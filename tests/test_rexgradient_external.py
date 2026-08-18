from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import zstandard as zstd

from prta_cxr.rexgradient_external import (
    ConcatenatedPartsReader,
    select_pairs,
    stream_selected_images,
)


def _study(
    patient: str,
    uid: str,
    date: int,
    paths: list[str],
    views: list[str],
) -> dict:
    return {
        "PatientID": patient,
        "StudyInstanceUid": uid,
        "StudyDate": date,
        "ImagePath": paths,
        "ImageViewPosition": views,
        "Findings": "deidentified findings",
        "Impression": "deidentified impression",
        "Indication": "",
        "Comparison": "",
    }


def test_select_pairs_is_outcome_blind_and_prefers_same_frontal_view() -> None:
    studies = {
        "a": _study("raw-patient", "s1", 20200101, ["a.png"], ["AP"]),
        "b": _study(
            "raw-patient",
            "s2",
            20200201,
            ["b-lat.png", "b-ap.png"],
            ["LATERAL", "AP"],
        ),
        "c": _study("same-day", "s3", 20200301, ["c.png"], ["PA"]),
        "d": _study("same-day", "s4", 20200301, ["d.png"], ["PA"]),
    }
    rows, members = select_pairs(studies, split="test", salt=b"x" * 32)
    assert len(rows) == 1
    assert set(members) == {"a.png", "b-ap.png"}
    row = rows[0]
    assert row["prior_view"] == row["current_view"] == "AP"
    assert row["progression_label"] is None
    assert row["finding"] is None
    assert row["patient_id_hash"] != "raw-patient"


def test_concatenated_reader_and_selected_stream_extract(tmp_path: Path) -> None:
    image = b"\x89PNG\r\n\x1a\n" + b"payload"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo("nested/image.png")
        info.size = len(image)
        archive.addfile(info, io.BytesIO(image))
    payload = zstd.ZstdCompressor().compress(buffer.getvalue())
    split = len(payload) // 2
    parts = [tmp_path / "part00", tmp_path / "part01"]
    parts[0].write_bytes(payload[:split])
    parts[1].write_bytes(payload[split:])

    reader = ConcatenatedPartsReader(parts)
    assert reader.read() == payload
    reader.close()
    assert reader.part_sha256 == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in parts
    }

    output = tmp_path / "output"
    inventory, digests, byte_counts = stream_selected_images(
        parts,
        image_members={"image.png": "images/safe.png"},
        output_root=output,
    )
    assert (output / "images" / "safe.png").read_bytes() == image
    assert inventory["image.png"]["sha256"] == hashlib.sha256(image).hexdigest()
    assert digests == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in parts
    }
    assert byte_counts == {path.name: path.stat().st_size for path in parts}
