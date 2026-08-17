from __future__ import annotations

import json
import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import torch

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file

LABEL_PHRASES = {
    "Stable": "is unchanged",
    "Improved": "has improved",
    "Worse": "has worsened",
    "New": "is new",
    "Resolved": "has resolved",
}


def load_biomedclip_text_encoder(model_root: Path):
    try:
        from open_clip.model import CLIPTextCfg, CLIPVisionCfg, CustomTextCLIP
        from transformers import AutoTokenizer
    except ImportError as error:
        raise RuntimeError(
            "text caching requires open_clip_torch and transformers"
        ) from error
    model_root = Path(model_root)
    config = json.loads(
        (model_root / "open_clip_config.json").read_text(encoding="utf-8")
    )["model_cfg"]
    text_config = dict(config["text_cfg"])
    # The published OpenCLIP config names the Hub repository.  Formal servers are
    # intentionally offline, so bind both Hugging Face lookups to the audited
    # local snapshot instead of allowing an implicit network request.
    text_config["hf_model_name"] = str(model_root)
    text_config["hf_tokenizer_name"] = str(model_root)
    text_config["hf_model_pretrained"] = False
    model = CustomTextCLIP(
        embed_dim=int(config["embed_dim"]),
        vision_cfg=CLIPVisionCfg(**config["vision_cfg"]),
        text_cfg=CLIPTextCfg(**text_config),
    )
    weights = model_root / "open_clip_pytorch_model.bin"
    state = torch.load(weights, map_location="cpu", weights_only=True)
    state.pop("text.transformer.embeddings.position_ids", None)
    incompatible = model.load_state_dict(state, strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise ValueError("BiomedCLIP full checkpoint did not load strictly")
    tokenizer = AutoTokenizer.from_pretrained(model_root, local_files_only=True)
    return model.eval().requires_grad_(False), tokenizer, weights


@torch.inference_mode()
def encode_texts(model, tokenizer, texts: Iterable[str]) -> torch.Tensor:
    values = list(texts)
    encoded = tokenizer(
        values,
        padding="max_length",
        truncation=True,
        max_length=256,
        return_tensors="pt",
    )["input_ids"]
    embeddings = model.encode_text(encoded, normalize=True).cpu()
    if embeddings.shape != (len(values), 512):
        raise ValueError(f"unexpected text embedding shape: {embeddings.shape}")
    if not torch.isfinite(embeddings).all():
        raise ValueError("text embeddings contain non-finite values")
    return embeddings


def write_text_cache(
    output_path: Path,
    *,
    findings: Sequence[str],
    model_root: Path,
) -> dict[str, Any]:
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite text cache: {output_path}")
    ordered_findings = sorted(set(str(value) for value in findings))
    if not ordered_findings:
        raise ValueError("text cache requires at least one finding")
    model, tokenizer, weights = load_biomedclip_text_encoder(model_root)
    finding_prompts = {
        finding: f"chest x-ray finding: {finding}" for finding in ordered_findings
    }
    prototype_prompts = {
        f"{finding}|{label}": f"{finding} {LABEL_PHRASES[label]}"
        for finding in ordered_findings
        for label in PROGRESSION_LABELS
    }
    finding_values = encode_texts(model, tokenizer, finding_prompts.values())
    prototype_values = encode_texts(model, tokenizer, prototype_prompts.values())
    payload = {
        "schema": "prta-cxr.biomedclip-text-cache.v1",
        "finding_embeddings": dict(zip(finding_prompts, finding_values, strict=True)),
        "transition_prototypes": dict(
            zip(prototype_prompts, prototype_values, strict=True)
        ),
        "finding_prompts": finding_prompts,
        "transition_prompts": prototype_prompts,
        "encoder": {
            "name": "BiomedCLIP frozen text tower",
            "weights_sha256": sha256_file(weights),
            "frozen": True,
        },
        "contains_reports": False,
        "contains_patient_identifiers": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp.{os.getpid()}")
    try:
        torch.save(payload, temporary)
        temporary.replace(output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "schema": payload["schema"],
        "findings": len(finding_prompts),
        "transition_prototypes": len(prototype_prompts),
        "encoder": payload["encoder"],
        "contains_reports": False,
        "contains_patient_identifiers": False,
    }
