from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader
from torch.utils.flop_counter import FlopCounterMode

from prta_cxr.authorization import require_formal_authorization
from prta_cxr.cleaned_split_freeze import require_cleaned_manifest
from prta_cxr.contracts import canonical_sha256, sha256_file
from prta_cxr.data.token_cache import Block8CacheIndex
from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
from prta_cxr.provenance import resolve_source_commit
from prta_cxr.prta_v2_diagnostics import (
    _experiment_identity_matches,
    _input_hashes,
    _validate_checkpoint_input_hashes,
)
from prta_cxr.training.engine import build_train_model
from prta_cxr.vision.biomedclip import (
    adapter_scope_cache_entry_block,
    load_biomedclip_visual,
    tail_modules,
)


def _write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def parameter_inventory(model: torch.nn.Module) -> dict[str, int]:
    return {
        "total": int(sum(parameter.numel() for parameter in model.parameters())),
        "trainable": int(
            sum(
                parameter.numel()
                for parameter in model.parameters()
                if parameter.requires_grad
            )
        ),
    }


def cache_disk_inventory(cache_root: Path, text_cache: Path) -> dict[str, Any]:
    root = Path(cache_root)
    manifest_path = root / "cache_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    active_paths = [manifest_path, root / str(manifest["inventory_path"])]
    training_store = dict(manifest.get("training_store", {}))
    if training_store:
        store_path = Path(str(training_store["path"]))
        if not store_path.is_absolute():
            store_path = root / store_path
        active_paths.append(store_path)
    active_paths.append(Path(text_cache))
    active_unique = sorted({path.resolve() for path in active_paths})
    for path in active_unique:
        if not path.is_file():
            raise FileNotFoundError(f"active cache file is missing: {path}")
    archive_files = [path for path in root.rglob("*") if path.is_file()]
    text_resolved = Path(text_cache).resolve()
    if text_resolved not in {path.resolve() for path in archive_files}:
        archive_files.append(text_resolved)
    return {
        "cached_images": int(manifest["cached_image_count"]),
        "active_deployment_bytes": int(
            sum(path.stat().st_size for path in active_unique)
        ),
        "active_files": [
            {"path": str(path), "bytes": int(path.stat().st_size)}
            for path in active_unique
        ],
        "full_archival_root_bytes": int(
            sum(path.stat().st_size for path in archive_files)
        ),
        "full_archival_file_count": len(archive_files),
        "legacy_shards_retained": len(manifest.get("shards", [])),
    }


def _model_inputs(
    batch: dict[str, Any], device: torch.device
) -> tuple[torch.Tensor, ...]:
    return (
        batch["prior"].to(device),
        batch["current"].to(device),
        batch["finding_text"].to(device),
    )


@torch.no_grad()
def benchmark_forward(
    model: torch.nn.Module,
    inputs: tuple[torch.Tensor, ...],
    *,
    warmup: int,
    repeats: int,
    model_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if warmup < 1 or repeats < 2:
        raise ValueError("benchmark requires warmup >=1 and repeats >=2")
    model.eval()
    device = inputs[0].device
    kwargs = {} if model_kwargs is None else dict(model_kwargs)
    for _ in range(warmup):
        model(*inputs, **kwargs)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)
        starts = [torch.cuda.Event(enable_timing=True) for _ in range(repeats)]
        ends = [torch.cuda.Event(enable_timing=True) for _ in range(repeats)]
        for start, end in zip(starts, ends, strict=True):
            start.record()
            model(*inputs, **kwargs)
            end.record()
        torch.cuda.synchronize(device)
        elapsed_ms = np.asarray(
            [start.elapsed_time(end) for start, end in zip(starts, ends, strict=True)],
            dtype=float,
        )
        peak_memory = int(torch.cuda.max_memory_allocated(device))
    else:
        timings = []
        for _ in range(repeats):
            start = time.perf_counter()
            model(*inputs, **kwargs)
            timings.append((time.perf_counter() - start) * 1000.0)
        elapsed_ms = np.asarray(timings, dtype=float)
        peak_memory = None
    batch_size = int(inputs[0].shape[0])
    mean_ms = float(elapsed_ms.mean())
    return {
        "batch_size": batch_size,
        "warmup_iterations": warmup,
        "measured_iterations": repeats,
        "latency_ms": {
            "mean": mean_ms,
            "sd": float(elapsed_ms.std(ddof=1)),
            "p50": float(np.quantile(elapsed_ms, 0.5)),
            "p95": float(np.quantile(elapsed_ms, 0.95)),
        },
        "throughput_samples_per_second": float(batch_size * 1000.0 / mean_ms),
        "peak_allocated_memory_bytes": peak_memory,
        "scope": (
            "model_forward_on_preloaded_cached_features; host-to-device and "
            "disk I/O excluded"
        ),
    }


@torch.no_grad()
def profiled_flops(
    model: torch.nn.Module,
    inputs: tuple[torch.Tensor, ...],
    *,
    model_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    model.eval()
    kwargs = {} if model_kwargs is None else dict(model_kwargs)
    with FlopCounterMode(display=False) as counter:
        model(*inputs, **kwargs)
    total = int(counter.get_total_flops())
    batch_size = int(inputs[0].shape[0])
    return {
        "batch_flops": total,
        "flops_per_sample": float(total / batch_size),
        "macs_per_sample_convention": float(total / (2 * batch_size)),
        "method": "torch.utils.flop_counter.FlopCounterMode",
        "caveat": "operator-accounted FLOPs; MACs are reported using 2 FLOPs per MAC",
    }


EFFICIENCY_SYSTEMS = ("V2", "B401", "TILA8", "IF-F01", "IF-F02")


def validate_efficiency_system(config: dict[str, Any], expected_system: str) -> str:
    family = str(dict(config.get("model", {})).get("family", ""))
    expected_family = {
        "V2": "prta",
        "B401": "current_only",
        "TILA8": "tila",
        "IF-F01": "early_concat",
        "IF-F02": "symmetric_cross_attention",
    }[expected_system]
    if family != expected_family:
        raise ValueError(
            f"efficiency system {expected_system} requires family {expected_family}"
        )
    if expected_system == "V2":
        if config.get("prta_v2_variant") != "V2":
            raise ValueError("V2 efficiency profile requires frozen V2 identity")
        scope = "candidate_v0_v2"
    elif expected_system.startswith("IF-"):
        if config.get("ifusion_variant") != expected_system:
            raise ValueError("IF efficiency profile variant mismatch")
        scope = "ifusion_final"
    else:
        if (
            expected_system == "TILA8"
            and config["model"].get("adapter_scope") != "tail8"
        ):
            raise ValueError("TILA8 efficiency comparison requires the frozen Tail8")
        scope = "formal_baseline"
    experiment_id = str(config.get("experiment_id", ""))
    if not _experiment_identity_matches(
        experiment_id, diagnostic_scope=scope, variant=expected_system
    ):
        raise ValueError("efficiency checkpoint experiment identity mismatch")
    return family


def efficiency_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Profile a frozen model on one fixed GPU"
    )
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-split-freeze", type=Path, required=True)
    parser.add_argument("--cleaned-split-platform-root", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--matched-hard-prior-map", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--label-quality-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--system", choices=EFFICIENCY_SYSTEMS, default="V2")
    parser.add_argument("--deployment-prune-state", action="store_true")
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args(argv)
    require_formal_authorization(formal_flag=args.formal)
    if args.output.exists():
        parser.error("--output must be a new immutable JSON file")
    if args.warmup < 1 or args.repeats < 2:
        parser.error("benchmark requires --warmup >=1 and --repeats >=2")

    cleaned = require_cleaned_manifest(
        args.split_manifest,
        receipt_path=args.cleaned_split_freeze,
        role="train_dev",
        portable_root=args.cleaned_split_platform_root,
    )
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported checkpoint schema")
    config = dict(checkpoint["config"])
    model_family = validate_efficiency_system(config, args.system)
    if args.deployment_prune_state and args.system != "V2":
        parser.error("--deployment-prune-state is valid only for V2")
    receipt = json.loads(args.training_receipt.read_text(encoding="utf-8"))
    if receipt.get("status") != "PASS_TRAINING_FINISHED":
        raise ValueError("training receipt is not terminal PASS")
    if receipt.get("internal_test_opened") is not False:
        raise ValueError("training receipt reports Internal-test access")
    if receipt.get("protected_outcomes_opened") is not False:
        raise ValueError("training receipt reports protected-outcome access")
    if receipt.get("config_sha256") != canonical_sha256(config):
        raise ValueError("checkpoint/training-receipt config identity mismatch")
    input_hashes = _input_hashes(args)
    checkpoint_hashes = dict(checkpoint.get("input_hashes", {}))
    _validate_checkpoint_input_hashes(checkpoint_hashes, input_hashes)
    if dict(receipt.get("input_hashes", {})) != checkpoint_hashes:
        raise ValueError("checkpoint/training-receipt input identity mismatch")

    adapter_scope = str(config["model"].get("adapter_scope", "tail4"))
    cache_entry_block = adapter_scope_cache_entry_block(adapter_scope)
    rows = read_jsonl(args.split_manifest)
    if {str(row.get("split")) for row in rows} - {"train", "dev"}:
        raise ValueError("efficiency manifest contains a non-Train/Dev split")
    visual, _ = load_biomedclip_visual(args.weights)
    blocks, final_norm = tail_modules(visual, start_block=cache_entry_block)
    model = build_train_model(blocks, final_norm, config)
    model.load_state_dict(checkpoint["model_state"])
    device = torch.device(args.device)
    model.to(device).eval()
    cache = Block8CacheIndex(args.cache_root)
    dataset = PRTAFeatureDataset(
        rows,
        cache=cache,
        text_cache_path=args.text_cache,
        split="dev",
        prior_intervention="true",
    )

    benchmarks = {}
    flops = {}
    model_kwargs = (
        {"deployment_prune_state": True} if args.deployment_prune_state else {}
    )
    for batch_size in (1, 16):
        loader = DataLoader(
            dataset, batch_size=batch_size, shuffle=False, num_workers=0
        )
        batch = next(iter(loader))
        inputs = _model_inputs(batch, device)
        flops[str(batch_size)] = profiled_flops(
            model, inputs, model_kwargs=model_kwargs
        )
        benchmarks[str(batch_size)] = benchmark_forward(
            model,
            inputs,
            warmup=args.warmup,
            repeats=args.repeats,
            model_kwargs=model_kwargs,
        )

    properties = (
        torch.cuda.get_device_properties(device) if device.type == "cuda" else None
    )
    report = {
        "schema": (
            "prta-cxr.v2-efficiency-evidence.v1"
            if args.system == "V2"
            else "prta-cxr.comparator-efficiency-evidence.v1"
        ),
        "status": (
            "PASS_V2_FIXED_HARDWARE_EFFICIENCY"
            if args.system == "V2"
            else "PASS_COMPARATOR_FIXED_HARDWARE_EFFICIENCY"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": resolve_source_commit(Path(__file__).resolve().parents[2]),
        "experiment_id": str(config["experiment_id"]),
        "system": args.system,
        "model_family": model_family,
        "adapter_scope": str(config["model"].get("adapter_scope", "tail4")),
        "deployment_state_pruned": bool(args.deployment_prune_state),
        "seed": int(config["seed"]),
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "checkpoint_bytes": int(args.checkpoint.stat().st_size),
        "training_receipt_sha256": sha256_file(args.training_receipt),
        "input_hashes": input_hashes,
        "cleaned_split_freeze_sha256": cleaned["receipt_sha256"],
        "parameters": parameter_inventory(model),
        "cache_disk": cache_disk_inventory(args.cache_root, args.text_cache),
        "hardware": {
            "device": str(device),
            "name": None if properties is None else properties.name,
            "total_memory_bytes": None
            if properties is None
            else properties.total_memory,
            "compute_capability": (
                None if properties is None else [properties.major, properties.minor]
            ),
            "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda,
        },
        "flops": flops,
        "benchmarks": benchmarks,
        "selection_performed": False,
        "internal_test_opened": False,
        "protected_outcome_read_count": 0,
    }
    _write_new_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0
