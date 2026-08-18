from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import torch

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.cache_writer import (
    finalize_streaming_block8_cache,
    prepare_streaming_block8_cache,
    replace_cache_manifest,
    synthetic_block8_features,
    unique_image_inventory,
    write_block8_cache,
    write_streaming_block8_shard,
)
from prta_cxr.data.token_cache import Block8CacheIndex


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _bind_image_root(
    rows: list[dict[str, object]], image_root: Path | None
) -> list[dict[str, object]]:
    if image_root is None:
        return rows
    root = image_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"image root is missing: {root}")
    bound = []
    for raw in rows:
        row = dict(raw)
        for key in ("prior_image_path", "current_image_path"):
            value = Path(str(row[key]))
            path = value.resolve() if value.is_absolute() else (root / value).resolve()
            try:
                path.relative_to(root)
            except ValueError as error:
                raise ValueError(f"image path escapes image root: {key}") from error
            if not path.is_file():
                raise FileNotFoundError(f"manifest image is missing: {key}")
            row[key] = str(path)
        bound.append(row)
    return bound


def _synthetic_inventory(count: int) -> list[dict[str, str]]:
    rows = []
    for index in range(count):
        rows.append(
            {
                "source": "synthetic",
                "prior_image_path": f"prior/{index}.png",
                "current_image_path": f"current/{index}.png",
            }
        )
    return unique_image_inventory(rows)


def cache_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the frozen Block-8 cache")
    parser.add_argument(
        "--mode", choices=("preflight", "synthetic", "formal"), default="preflight"
    )
    parser.add_argument(
        "--sample-manifest", "--pair-manifest", dest="pair_manifest", type=Path
    )
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--image-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--shard-size", type=int, default=256)
    parser.add_argument("--output-block", type=int, choices=(2, 4, 6, 8), default=8)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--synthetic-count", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)

    if args.mode == "preflight":
        if args.formal:
            parser.error("--formal cannot be used in preflight mode")
        print(
            json.dumps(
                {
                    "status": "PASS_CACHE_PREFLIGHT",
                    "formal_experiment_started": False,
                    "real_images_opened": False,
                    "output_requested": args.output is not None,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.mode == "formal":
        require_formal_authorization(formal_flag=args.formal)
    if args.output is None:
        parser.error("--output is required outside preflight mode")
    if args.mode == "synthetic":
        if args.formal:
            parser.error("--formal cannot be used in synthetic mode")
        if args.resume:
            parser.error("--resume cannot be used in synthetic mode")
        inventory = _synthetic_inventory(args.synthetic_count)
        features = synthetic_block8_features(len(inventory), seed=args.seed)
        manifest = write_block8_cache(
            args.output,
            inventory,
            features,
            shard_size=args.shard_size,
            encoder_receipt={"synthetic": True, "seed": args.seed},
        )
        check = Block8CacheIndex(args.output)
        check.get_many([str(row["image_key"]) for row in inventory])
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    if args.pair_manifest is None or args.weights is None or args.model_root is None:
        parser.error(
            "formal mode requires --pair-manifest, --weights, and --model-root"
        )
    rows = _bind_image_root(_read_jsonl(args.pair_manifest), args.image_root)
    inventory = unique_image_inventory(rows)
    from prta_cxr.vision.biomedclip import (
        BiomedCLIPIntermediateEncoder,
        encode_image_paths,
        load_biomedclip_visual,
    )

    visual, encoder_receipt = load_biomedclip_visual(args.weights)
    encoder_receipt["output_block"] = int(args.output_block)
    device = torch.device(args.device)
    normalized, state = prepare_streaming_block8_cache(
        args.output,
        inventory,
        shard_size=args.shard_size,
        encoder_receipt=encoder_receipt,
        resume=args.resume,
    )
    encoder = BiomedCLIPIntermediateEncoder(visual, output_block=args.output_block)
    while int(state["completed_images"]) < len(normalized):
        start = int(state["completed_images"])
        selected = normalized[start : start + args.shard_size]
        features = encode_image_paths(
            encoder,
            (Path(row["image_path"]) for row in selected),
            device=device,
            batch_size=args.batch_size,
        )
        write_streaming_block8_shard(args.output, state, features)
        del features
    manifest = finalize_streaming_block8_cache(args.output, state)
    del encoder, visual
    if device.type == "cuda":
        torch.cuda.empty_cache()
    from prta_cxr.vision.text_cache import write_text_cache

    findings = sorted({str(row["finding"]) for row in rows})
    text_path = args.output / "text_cache.pt"
    text_receipt_path = args.output / "text_cache_receipt.json"
    if text_path.exists() or text_receipt_path.exists():
        if (
            not args.resume
            or not text_path.is_file()
            or not text_receipt_path.is_file()
        ):
            raise FileExistsError("incomplete or unauthorized text-cache resume")
        text_receipt = json.loads(text_receipt_path.read_text(encoding="utf-8"))
        if text_receipt["encoder"]["weights_sha256"] != sha256_file(args.weights):
            raise ValueError("resumed text cache uses different visual/text weights")
        if int(text_receipt["findings"]) != len(findings):
            raise ValueError("resumed text cache uses a different finding set")
        if int(text_receipt["transition_prototypes"]) != 5 * len(findings):
            raise ValueError("resumed text cache has incomplete prototypes")
    else:
        text_receipt = write_text_cache(
            text_path,
            findings=findings,
            model_root=args.model_root,
        )
        write_json_atomic(text_receipt_path, text_receipt)
    manifest["text_cache"] = text_receipt
    manifest["formal_input"] = {
        "sample_manifest_sha256": canonical_sha256(rows),
        "sample_manifest_file_sha256": sha256_file(args.pair_manifest),
        "model_config_sha256": sha256_file(args.model_root / "open_clip_config.json"),
        "weights_sha256": sha256_file(args.weights),
        "image_root_bound": args.image_root is not None,
    }
    replace_cache_manifest(args.output, manifest)
    Block8CacheIndex(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0
