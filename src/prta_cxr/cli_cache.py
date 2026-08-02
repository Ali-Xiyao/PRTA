from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import torch

from prta_cxr.artifacts import write_json_atomic
from prta_cxr.authorization import require_formal_authorization
from prta_cxr.data.cache_writer import (
    synthetic_block8_features,
    unique_image_inventory,
    write_block8_cache,
)
from prta_cxr.data.token_cache import Block8CacheIndex


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--shard-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--synthetic-count", type=int, default=4)
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

    if (
        args.pair_manifest is None
        or args.weights is None
        or args.model_root is None
    ):
        parser.error(
            "formal mode requires --pair-manifest, --weights, and --model-root"
        )
    rows = _read_jsonl(args.pair_manifest)
    inventory = unique_image_inventory(rows)
    from prta_cxr.vision.biomedclip import (
        BiomedCLIPBlock8Encoder,
        encode_image_paths,
        load_biomedclip_visual,
    )

    visual, encoder_receipt = load_biomedclip_visual(args.weights)
    device = torch.device(args.device)
    features = encode_image_paths(
        BiomedCLIPBlock8Encoder(visual),
        (Path(row["image_path"]) for row in inventory),
        device=device,
        batch_size=args.batch_size,
    )
    manifest = write_block8_cache(
        args.output,
        inventory,
        features,
        shard_size=args.shard_size,
        encoder_receipt=encoder_receipt,
    )
    del features, visual
    if device.type == "cuda":
        torch.cuda.empty_cache()
    from prta_cxr.vision.text_cache import write_text_cache

    text_receipt = write_text_cache(
        args.output / "text_cache.pt",
        findings=sorted({str(row["finding"]) for row in rows}),
        model_root=args.model_root,
    )
    write_json_atomic(args.output / "text_cache_receipt.json", text_receipt)
    manifest["text_cache"] = text_receipt
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0
