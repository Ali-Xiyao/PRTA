from __future__ import annotations

import argparse
import io
import json
import os
from collections.abc import Sequence
from pathlib import Path

import torch

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.cache_writer import (
    finalize_streaming_block8_cache,
    prepare_streaming_block8_cache,
    write_streaming_block8_shard,
)
from prta_cxr.data.token_cache import Block8CacheIndex, image_cache_key
from prta_cxr.data.training_dataset import read_jsonl
from prta_cxr.vision.biomedclip import (
    BiomedCLIPIntermediateEncoder,
    load_biomedclip_visual,
)
from prta_cxr.vision.text_cache import encode_texts, load_biomedclip_text_encoder

SYNONYMS = {
    "atelectasis": "partial lung collapse",
    "cardiomegaly": "enlarged cardiac silhouette",
    "consolidation": "airspace opacity",
    "edema": "pulmonary fluid overload",
    "enlarged cardiomediastinum": "widened cardiomediastinal silhouette",
    "fracture": "osseous break",
    "lung lesion": "focal pulmonary lesion",
    "lung opacity": "pulmonary opacity",
    "pleural effusion": "fluid in the pleural space",
    "pleural other": "other pleural abnormality",
    "pneumonia": "pulmonary infection",
    "pneumothorax": "air in the pleural space",
    "support devices": "medical support apparatus",
}


def finding_intervention_prompts(findings: Sequence[str]) -> dict[str, dict[str, str]]:
    prompts: dict[str, dict[str, str]] = {
        name: {} for name in ("generic", "synonym", "typo", "paraphrase")
    }
    for finding in sorted(set(map(str, findings))):
        lower = finding.lower()
        typo = (
            finding
            if len(finding) < 3
            else finding[: len(finding) // 2] + finding[len(finding) // 2 + 1 :]
        )
        prompts["generic"][finding] = "chest x-ray finding"
        prompts["synonym"][finding] = SYNONYMS.get(
            lower, f"radiographic sign of {finding}"
        )
        prompts["typo"][finding] = f"chest x-ray finding: {typo}"
        prompts["paraphrase"][finding] = f"the chest radiograph demonstrates {finding}"
    return prompts


def prepare_modality_text_cache_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Encode modality interventions with the frozen BiomedCLIP text tower"
        )
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable file")
    rows = read_jsonl(args.split_manifest)
    findings = sorted({str(row["finding"]) for row in rows})
    prompts = finding_intervention_prompts(findings)
    model, tokenizer, weights = load_biomedclip_text_encoder(args.model_root)
    embeddings: dict[str, dict[str, torch.Tensor]] = {}
    for condition, condition_prompts in prompts.items():
        values = encode_texts(model, tokenizer, condition_prompts.values())
        embeddings[condition] = dict(
            zip(condition_prompts, values, strict=True)
        )
    payload = {
        "schema": "prta-cxr.modality-finding-text-cache.v1",
        "status": "PASS_MODALITY_FINDING_TEXT_REENCODED",
        "prompts": prompts,
        "embeddings": embeddings,
        "split_manifest_sha256": sha256_file(args.split_manifest),
        "encoder": {
            "name": "Microsoft BiomedCLIP frozen text tower",
            "weights_sha256": sha256_file(weights),
            "open_clip_config_sha256": sha256_file(
                args.model_root / "open_clip_config.json"
            ),
            "tokenizer_json_sha256": sha256_file(args.model_root / "tokenizer.json"),
            "config_sha256": sha256_file(args.model_root / "config.json"),
            "frozen": True,
            "actual_text_reencoding": True,
        },
        "contains_reports": False,
        "contains_patient_identifiers": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp.{os.getpid()}")
    torch.save(payload, temporary)
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "output": str(args.output),
                "sha256": sha256_file(args.output),
                "findings": len(findings),
                "conditions": sorted(embeddings),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _corrupt(image, condition: str):
    from PIL import ImageEnhance, ImageFilter

    if condition == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=2.0))
    if condition == "contrast":
        return ImageEnhance.Contrast(image).enhance(0.5)
    if condition == "jpeg":
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=20, optimize=False)
        buffer.seek(0)
        from PIL import Image

        with Image.open(buffer) as decoded:
            return decoded.convert("RGB").copy()
    raise ValueError(f"unsupported current corruption: {condition}")


@torch.inference_mode()
def _encode_corrupted(
    encoder,
    paths: Sequence[Path],
    *,
    condition: str,
    device: torch.device,
    batch_size: int,
) -> torch.Tensor:
    from PIL import Image
    from torchvision.transforms import v2

    transform = v2.Compose(
        [
            v2.Resize(224, antialias=True),
            v2.CenterCrop(224),
            v2.ToImage(),
            v2.ToDtype(torch.float32, scale=True),
            v2.Normalize(
                mean=(0.48145466, 0.4578275, 0.40821073),
                std=(0.26862954, 0.26130258, 0.27577711),
            ),
        ]
    )
    encoder.to(device)
    outputs = []
    pending = []
    for path in paths:
        with Image.open(path) as image:
            pending.append(transform(_corrupt(image.convert("RGB"), condition)))
        if len(pending) == batch_size:
            outputs.append(encoder(torch.stack(pending).to(device)).cpu())
            pending.clear()
    if pending:
        outputs.append(encoder(torch.stack(pending).to(device)).cpu())
    return torch.cat(outputs)


def build_current_corruption_cache_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a Dev current-image corruption cache"
    )
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--raw-image-root", type=Path)
    parser.add_argument(
        "--condition", choices=("blur", "contrast", "jpeg"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--shard-size", type=int, default=256)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    rows = [row for row in read_jsonl(args.split_manifest) if row.get("split") == "dev"]
    inventory_by_key = {}
    for row in rows:
        key = image_cache_key(str(row["source"]), str(row["current_image_path"]))
        image_path = (
            args.raw_image_root / f"{key}.jpg"
            if args.raw_image_root is not None
            else Path(str(row["current_image_path"]))
        )
        inventory_by_key[key] = {
            "image_key": key,
            "source": str(row["source"]),
            "image_path": str(image_path),
            "original_image_path": str(row["current_image_path"]),
        }
    inventory = [inventory_by_key[key] for key in sorted(inventory_by_key)]
    visual, encoder_receipt = load_biomedclip_visual(args.weights)
    encoder_receipt.update(
        {
            "output_block": 4,
            "modality_condition": args.condition,
            "modality_parameters": {
                "blur": {"gaussian_radius": 2.0},
                "contrast": {"factor": 0.5},
                "jpeg": {"quality": 20},
            }[args.condition],
            "split_manifest_sha256": sha256_file(args.split_manifest),
            "raw_image_root": (
                str(args.raw_image_root.resolve())
                if args.raw_image_root is not None
                else None
            ),
        }
    )
    normalized, state = prepare_streaming_block8_cache(
        args.output,
        inventory,
        shard_size=args.shard_size,
        encoder_receipt=encoder_receipt,
        resume=args.resume,
    )
    encoder = BiomedCLIPIntermediateEncoder(visual, output_block=4)
    device = torch.device(args.device)
    while int(state["completed_images"]) < len(normalized):
        start = int(state["completed_images"])
        selected = normalized[start : start + args.shard_size]
        features = _encode_corrupted(
            encoder,
            [Path(row["image_path"]) for row in selected],
            condition=args.condition,
            device=device,
            batch_size=args.batch_size,
        )
        write_streaming_block8_shard(args.output, state, features)
    manifest = finalize_streaming_block8_cache(args.output, state)
    Block8CacheIndex(args.output)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "condition": args.condition,
                "cached_images": manifest["cached_image_count"],
                "manifest_sha256": sha256_file(args.output / "cache_manifest.json"),
                "inventory_sha256": canonical_sha256(inventory),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0
