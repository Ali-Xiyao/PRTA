from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import torch
from torch import nn

from prta_cxr.contracts import sha256_file

VISUAL_PREFIXES = ("visual.trunk.", "module.visual.trunk.")


def adapter_scope_cache_entry_block(scope: object) -> int:
    name = str(scope)
    if name in {"tail4", "last2"}:
        return 8
    if name in {"tail6", "tail8"}:
        return 4
    raise ValueError("adapter_scope must be tail4, last2, tail6, or tail8")


def _checkpoint_state(path: Path) -> dict[str, torch.Tensor]:
    value = torch.load(Path(path), map_location="cpu", weights_only=True)
    if isinstance(value, dict):
        for key in ("state_dict", "model", "model_state_dict"):
            if key in value and isinstance(value[key], dict):
                value = value[key]
                break
    if not isinstance(value, dict):
        raise ValueError("BiomedCLIP checkpoint does not contain a state dict")
    for prefix in VISUAL_PREFIXES:
        selected = {
            str(key)[len(prefix) :]: tensor
            for key, tensor in value.items()
            if str(key).startswith(prefix)
        }
        if selected:
            return selected
    raise ValueError("checkpoint lacks a visual.trunk state dictionary")


def load_biomedclip_visual(weights_path: Path) -> tuple[nn.Module, dict[str, Any]]:
    try:
        import timm
    except ImportError as error:
        raise RuntimeError(
            "formal cache/training requires the optional 'vision' dependencies"
        ) from error
    model = timm.create_model(
        "vit_base_patch16_224", pretrained=False, num_classes=0
    )
    state = _checkpoint_state(weights_path)
    incompatible = model.load_state_dict(state, strict=False)
    allowed_missing = {"head.weight", "head.bias"}
    unexpected = sorted(incompatible.unexpected_keys)
    missing = sorted(set(incompatible.missing_keys) - allowed_missing)
    if missing or unexpected:
        raise ValueError(
            f"visual checkpoint mismatch; missing={missing}, unexpected={unexpected}"
        )
    if len(model.blocks) != 12:
        raise ValueError("BiomedCLIP visual trunk must contain exactly 12 blocks")
    model.eval().requires_grad_(False)
    receipt = {
        "architecture": "vit_base_patch16_224",
        "weights_sha256": sha256_file(weights_path),
        "blocks": len(model.blocks),
        "frozen": True,
    }
    return model, receipt


class BiomedCLIPIntermediateEncoder(nn.Module):
    def __init__(self, visual: nn.Module, *, output_block: int = 8) -> None:
        super().__init__()
        if len(visual.blocks) != 12:
            raise ValueError("encoder requires a 12-block visual transformer")
        if output_block not in {4, 6, 8}:
            raise ValueError("encoder output_block must be 4, 6, or 8")
        self.visual = visual.eval().requires_grad_(False)
        self.output_block = int(output_block)

    def train(self, mode: bool = True):
        super().train(False)
        return self

    @torch.inference_mode()
    def forward(self, images: torch.Tensor) -> torch.Tensor:
        visual = self.visual
        tokens = visual.patch_embed(images)
        tokens = visual._pos_embed(tokens)
        tokens = visual.patch_drop(tokens)
        tokens = visual.norm_pre(tokens)
        for block in visual.blocks[: self.output_block]:
            tokens = block(tokens)
        if tuple(tokens.shape[1:]) != (197, 768):
            raise ValueError(
                f"unexpected Block-{self.output_block} shape: {tuple(tokens.shape)}"
            )
        return tokens


class BiomedCLIPBlock8Encoder(BiomedCLIPIntermediateEncoder):
    def __init__(self, visual: nn.Module) -> None:
        super().__init__(visual, output_block=8)


def tail_modules(
    visual: nn.Module, *, start_block: int = 8
) -> tuple[list[nn.Module], nn.Module]:
    if len(visual.blocks) != 12:
        raise ValueError("tail extraction requires a 12-block visual transformer")
    if start_block not in {4, 6, 8}:
        raise ValueError("tail start_block must be 4, 6, or 8")
    return list(visual.blocks[start_block:12]), visual.norm


def encode_image_paths(
    encoder: BiomedCLIPIntermediateEncoder,
    image_paths: Iterable[Path],
    *,
    device: torch.device,
    batch_size: int,
) -> torch.Tensor:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    try:
        from PIL import Image
        from torchvision.transforms import v2
    except ImportError as error:
        raise RuntimeError(
            "formal cache creation requires Pillow and torchvision"
        ) from error
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
    output = []
    pending = []
    for path in image_paths:
        with Image.open(path) as image:
            pending.append(transform(image.convert("RGB")))
        if len(pending) == batch_size:
            output.append(encoder(torch.stack(pending).to(device)).cpu())
            pending.clear()
    if pending:
        output.append(encoder(torch.stack(pending).to(device)).cpu())
    if not output:
        raise ValueError("no image paths were supplied to the encoder")
    return torch.cat(output)
