from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch

from prta_cxr.contracts import PROGRESSION_LABELS, sha256_file

EXPECTED_SEEDS = (17, 28, 43)
SELECTION_SEED = 43
SELECTION_SALT = "PRTA_ATTN_20260818"
IMPROVEMENT_LABELS = frozenset(("Improved", "Resolved"))
WORSENING_LABELS = frozenset(("Worse", "New"))


def salted_sample_hash(sample_id: str, *, salt: str = SELECTION_SALT) -> str:
    if not sample_id:
        raise ValueError("sample_id must be non-empty")
    return hashlib.sha256(f"{salt}|{sample_id}".encode()).hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _index_seed_rows(
    seed_blocks: Sequence[tuple[int, Sequence[Mapping[str, Any]]]],
) -> tuple[list[str], dict[int, dict[str, Mapping[str, Any]]]]:
    blocks = sorted((int(seed), list(rows)) for seed, rows in seed_blocks)
    if tuple(seed for seed, _ in blocks) != EXPECTED_SEEDS:
        raise ValueError("attention selection requires S17/S28/S43")
    reference_ids = [str(row["observation_id"]) for row in blocks[0][1]]
    if len(reference_ids) != len(set(reference_ids)):
        raise ValueError("duplicate observation_id in S17 prediction block")
    indexed: dict[int, dict[str, Mapping[str, Any]]] = {}
    reference_identity = {
        str(row["observation_id"]): (
            str(row["patient_id"]),
            str(row["finding"]),
            str(row["target"]),
        )
        for row in blocks[0][1]
    }
    for seed, rows in blocks:
        current = {str(row["observation_id"]): row for row in rows}
        if set(current) != set(reference_ids):
            raise ValueError("attention-selection cohort drift across seeds")
        identity = {
            sample_id: (
                str(row["patient_id"]),
                str(row["finding"]),
                str(row["target"]),
            )
            for sample_id, row in current.items()
        }
        if identity != reference_identity:
            raise ValueError("attention-selection identity drift across seeds")
        indexed[seed] = current
    return reference_ids, indexed


def _validated_confidence(row: Mapping[str, Any]) -> float:
    probabilities = np.asarray(row["probabilities"], dtype=np.float64)
    if probabilities.shape != (len(PROGRESSION_LABELS),):
        raise ValueError("attention selection requires five probabilities")
    if not np.isfinite(probabilities).all() or np.any(probabilities < 0):
        raise ValueError("invalid attention-selection probabilities")
    if not np.isclose(float(probabilities.sum()), 1.0, atol=1e-5):
        raise ValueError("attention-selection probabilities do not sum to one")
    target = str(row["target"])
    prediction = str(row["prediction"])
    if target not in PROGRESSION_LABELS or prediction not in PROGRESSION_LABELS:
        raise ValueError("unknown progression label")
    predicted_index = PROGRESSION_LABELS.index(prediction)
    confidence = float(probabilities[predicted_index])
    if not np.isclose(confidence, float(row["confidence"]), atol=1e-5):
        raise ValueError("stored confidence does not match probabilities")
    return confidence


def select_attention_candidates(
    seed_blocks: Sequence[tuple[int, Sequence[Mapping[str, Any]]]],
    *,
    minimum_cell_support: int = 100,
    salt: str = SELECTION_SALT,
) -> dict[str, Any]:
    if minimum_cell_support < 1:
        raise ValueError("minimum_cell_support must be positive")
    reference_ids, indexed = _index_seed_rows(seed_blocks)
    reference_rows = indexed[EXPECTED_SEEDS[0]]
    support = Counter(
        (str(row["finding"]), str(row["target"]))
        for row in reference_rows.values()
    )

    eligible: list[dict[str, Any]] = []
    for sample_id in reference_ids:
        rows = [indexed[seed][sample_id] for seed in EXPECTED_SEEDS]
        target = str(rows[0]["target"])
        predictions = tuple(str(row["prediction"]) for row in rows)
        if len(set(predictions)) != 1 or predictions[0] != target:
            continue
        finding = str(rows[0]["finding"])
        cell_support = support[(finding, target)]
        if cell_support < minimum_cell_support:
            continue
        seed43 = indexed[SELECTION_SEED][sample_id]
        confidence = _validated_confidence(seed43)
        eligible.append(
            {
                "sample_id": sample_id,
                "sample_hash": salted_sample_hash(sample_id, salt=salt),
                "finding": finding,
                "reference_progression": target,
                "predicted_progression": str(seed43["prediction"]),
                "predicted_probability": confidence,
                "probabilities": [float(value) for value in seed43["probabilities"]],
                "source": str(seed43["source"]),
                "interval_basis": str(seed43["interval_basis"]),
                "interval_days": float(seed43["interval_days"]),
                "prior_view": str(seed43["prior_view"]),
                "current_view": str(seed43["current_view"]),
                "cell_support": int(cell_support),
            }
        )

    thresholds: dict[str, dict[str, float]] = {}
    for label in PROGRESSION_LABELS:
        values = np.asarray(
            [
                row["predicted_probability"]
                for row in eligible
                if row["reference_progression"] == label
            ],
            dtype=np.float64,
        )
        if values.size:
            thresholds[label] = {
                "q10": float(np.quantile(values, 0.1)),
                "q90": float(np.quantile(values, 0.9)),
                "rows": int(values.size),
            }

    retained = []
    for row in eligible:
        threshold = thresholds[row["reference_progression"]]
        probability = row["predicted_probability"]
        if threshold["q10"] <= probability <= threshold["q90"]:
            retained.append(row)
    retained.sort(key=lambda row: row["sample_hash"])

    families = {
        "improvement": [
            row
            for row in retained
            if row["reference_progression"] in IMPROVEMENT_LABELS
        ],
        "worsening": [
            row
            for row in retained
            if row["reference_progression"] in WORSENING_LABELS
        ],
    }
    if any(not rows for rows in families.values()):
        raise ValueError("no eligible attention candidate in a required family")
    selected = {name: rows[0] for name, rows in families.items()}
    return {
        "schema": "prta-cxr.figure5-preselection.v1",
        "status": "PASS_FIGURE5_CASES_PRESELECTED",
        "selection_performed_before_image_or_attention_view": True,
        "selection_seed": SELECTION_SEED,
        "agreement_seeds": list(EXPECTED_SEEDS),
        "salt": salt,
        "minimum_cell_support": minimum_cell_support,
        "confidence_decile_definition": (
            "seed-43 predicted-class confidence within each reference "
            "progression class after support and unanimous-correct gates"
        ),
        "confidence_thresholds": thresholds,
        "eligible_before_decile_filter": len(eligible),
        "eligible_after_decile_filter": len(retained),
        "selected": selected,
        "ordered_candidate_hashes": {
            name: [row["sample_hash"] for row in rows]
            for name, rows in families.items()
        },
        "attention_opened": False,
        "images_opened": False,
    }


def capture_true_attention(
    model: torch.nn.Module,
    *,
    prior: torch.Tensor,
    current: torch.Tensor,
    finding_text: torch.Tensor,
    replay_atol: float = 1e-6,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Capture the two genuine post-softmax attention tensors.

    The scientific forward is executed unchanged. Pre-hooks retain the exact
    normalized Q/K/V tensors supplied to each MultiheadAttention module. After
    the forward hooks are removed, each module is replayed with weights enabled
    and its output is checked against the original output.
    """

    adapter = getattr(model, "adapter", None)
    if adapter is None or not bool(getattr(adapter, "cross_time_alignment", False)):
        raise ValueError("attention export requires cross-time alignment")
    modules = {
        "align": adapter.cross_time,
        "transition": adapter.transition_resampler.attention,
    }
    captured: dict[str, dict[str, Any]] = {}
    handles = []

    def pre_hook(name: str):
        def hook(module, args, kwargs):
            del module
            if len(args) < 3:
                raise RuntimeError(f"{name} attention did not receive Q/K/V")
            captured[name] = {
                "qkv": tuple(value.detach() for value in args[:3]),
                "kwargs": dict(kwargs),
            }

        return hook

    def forward_hook(name: str):
        def hook(module, args, kwargs, output):
            del module, args, kwargs
            if name not in captured:
                raise RuntimeError(f"{name} attention pre-hook did not run")
            captured[name]["output"] = output[0].detach()

        return hook

    for name, module in modules.items():
        handles.append(
            module.register_forward_pre_hook(pre_hook(name), with_kwargs=True)
        )
        handles.append(
            module.register_forward_hook(forward_hook(name), with_kwargs=True)
        )
    try:
        model.eval()
        with torch.no_grad():
            _, logits, _ = model(prior, current, finding_text)
    finally:
        for handle in handles:
            handle.remove()

    weights = {}
    with torch.no_grad():
        for name, module in modules.items():
            q, k, v = captured[name]["qkv"]
            replay, attention = module(
                q,
                k,
                v,
                need_weights=True,
                average_attn_weights=False,
            )
            if not torch.allclose(
                replay,
                captured[name]["output"],
                atol=replay_atol,
                rtol=0.0,
            ):
                maximum = float(
                    (replay - captured[name]["output"]).abs().max().item()
                )
                raise ValueError(
                    f"{name} attention replay drift; maximum_abs={maximum}"
                )
            weights[name] = attention.detach()
    if tuple(weights["align"].shape[1:]) != (12, 197, 197):
        raise ValueError("W_align must have shape [B,12,197,197]")
    if tuple(weights["transition"].shape[1:]) != (12, 20, 197):
        raise ValueError("W_trans must have shape [B,12,20,197]")
    return logits.detach(), weights["align"], weights["transition"]


def patch_attention_flow(
    w_align: np.ndarray,
    w_trans: np.ndarray,
) -> dict[str, np.ndarray]:
    align = np.asarray(w_align, dtype=np.float64)
    transition = np.asarray(w_trans, dtype=np.float64)
    if align.shape != (12, 197, 197):
        raise ValueError("W_align must have shape [12,197,197]")
    if transition.shape != (12, 20, 197):
        raise ValueError("W_trans must have shape [12,20,197]")
    if not np.isfinite(align).all() or not np.isfinite(transition).all():
        raise ValueError("attention tensors must be finite")
    align_patch = align[:, 1:, 1:]
    transition_patch = transition[:, :, 1:]
    align_denominator = align_patch.sum(axis=-1, keepdims=True)
    transition_denominator = transition_patch.sum(axis=-1, keepdims=True)
    if np.any(align_denominator <= 0) or np.any(transition_denominator <= 0):
        raise ValueError("patch attention has a non-positive normalization sum")
    align_patch = align_patch / align_denominator
    transition_patch = transition_patch / transition_denominator
    a_bar = align_patch.mean(axis=0)
    r_current = transition_patch.mean(axis=(0, 1))
    r_current = r_current / r_current.sum()
    r_prior = r_current @ a_bar
    r_prior = r_prior / r_prior.sum()
    edge = r_current[:, None] * a_bar
    return {
        "A_bar": a_bar,
        "r_current": r_current,
        "r_prior": r_prior,
        "edge": edge,
    }


def strongest_routes(
    edge: np.ndarray,
    *,
    maximum_routes: int = 6,
    nms_radius: int = 1,
) -> list[dict[str, Any]]:
    values = np.asarray(edge, dtype=np.float64)
    if values.shape != (196, 196):
        raise ValueError("edge must have shape [196,196]")
    if maximum_routes < 1 or nms_radius < 0:
        raise ValueError("invalid route-selection parameters")

    def position(index: int) -> tuple[int, int]:
        return divmod(index, 14)

    def suppressed(index: int, selected: list[int]) -> bool:
        row, column = position(index)
        return any(
            max(abs(row - old_row), abs(column - old_column)) <= nms_radius
            for old_row, old_column in (position(value) for value in selected)
        )

    flat_order = np.argsort(values, axis=None)[::-1]
    current_selected: list[int] = []
    prior_selected: list[int] = []
    routes = []
    for flat_index in flat_order:
        current_index, prior_index = np.unravel_index(flat_index, values.shape)
        current_index = int(current_index)
        prior_index = int(prior_index)
        if suppressed(current_index, current_selected) or suppressed(
            prior_index, prior_selected
        ):
            continue
        current_selected.append(current_index)
        prior_selected.append(prior_index)
        routes.append(
            {
                "current_patch": current_index,
                "current_row": position(current_index)[0],
                "current_column": position(current_index)[1],
                "prior_patch": prior_index,
                "prior_row": position(prior_index)[0],
                "prior_column": position(prior_index)[1],
                "weight": float(values[current_index, prior_index]),
            }
        )
        if len(routes) == maximum_routes:
            break
    return routes


def shared_attention_clip(flows: Sequence[Mapping[str, np.ndarray]]) -> float:
    values = np.concatenate(
        [
            np.asarray(flow[name], dtype=np.float64).reshape(-1)
            for flow in flows
            for name in ("r_prior", "r_current")
        ]
    )
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("attention maps are empty or non-finite")
    return float(np.quantile(values, 0.99))


def _interval_bucket(row: Mapping[str, Any]) -> str:
    if not bool(row.get("calendar_interval_available", False)):
        return "ordinal"
    value = float(row["interval_days"])
    for bound in (7, 30, 90, 365):
        if value <= bound:
            return f"le_{bound}_days"
    return "gt_365_days"


def _private_to_public_case(
    case: Mapping[str, Any],
    *,
    tensor_sha256: str,
) -> dict[str, Any]:
    forbidden = {
        "sample_id",
        "patient_id",
        "patient_id_hash",
        "prior_image_path",
        "current_image_path",
    }
    overlap = forbidden.intersection(case)
    if overlap:
        raise ValueError(f"public attention case contains private fields: {overlap}")
    result = dict(case)
    result["tensor_bundle_sha256"] = tensor_sha256
    return result


def attention_export_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export genuine seed-43 attention for frozen Figure 5 cases."
    )
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--text-cache", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--preselection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args(argv)

    from prta_cxr.data.token_cache import Block8CacheIndex
    from prta_cxr.data.training_dataset import PRTAFeatureDataset, read_jsonl
    from prta_cxr.training.engine import build_train_model
    from prta_cxr.vision.biomedclip import load_biomedclip_visual, tail_modules

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "prta-cxr.checkpoint.v1":
        raise ValueError("unsupported attention-export checkpoint schema")
    config = checkpoint["config"]
    if int(config.get("seed", -1)) != SELECTION_SEED:
        raise ValueError("Figure 5 requires the frozen seed-43 checkpoint")
    expected = checkpoint["input_hashes"]
    actual = {
        "split_manifest": sha256_file(args.split_manifest),
        "cache_manifest": sha256_file(args.cache_root / "cache_manifest.json"),
        "text_cache": sha256_file(args.text_cache),
        "weights": sha256_file(args.weights),
    }
    if {key: expected.get(key) for key in actual} != actual:
        raise ValueError("attention-export inputs do not match S43 hashes")

    preselection = json.loads(args.preselection.read_text(encoding="utf-8"))
    if preselection.get("status") != "PASS_FIGURE5_CASES_PRESELECTED":
        raise ValueError("Figure 5 preselection is not terminal PASS")
    if not preselection.get("selection_performed_before_image_or_attention_view"):
        raise ValueError("Figure 5 cases were not selected before viewing")
    if preselection.get("attention_opened") or preselection.get("images_opened"):
        raise ValueError("Figure 5 preselection reports premature qualitative access")
    selected = dict(preselection["selected"])
    selected_ids = {
        family: str(row["sample_id"]) for family, row in selected.items()
    }
    if set(selected_ids) != {"improvement", "worsening"}:
        raise ValueError("Figure 5 requires improvement and worsening cases")

    rows_by_id = {
        str(row["sample_id"]): row for row in read_jsonl(args.split_manifest)
    }
    missing = [value for value in selected_ids.values() if value not in rows_by_id]
    if missing:
        raise ValueError("a frozen Figure 5 case is absent from Train/Dev manifest")
    selected_rows = [rows_by_id[selected_ids[name]] for name in selected_ids]
    if any(str(row.get("split")) != "dev" for row in selected_rows):
        raise ValueError("Figure 5 selection is not confined to Dev")

    cache = Block8CacheIndex(args.cache_root)
    dataset = PRTAFeatureDataset(
        selected_rows,
        cache=cache,
        text_cache_path=args.text_cache,
        split="dev",
    )
    visual, _ = load_biomedclip_visual(args.weights)
    start_block = int(config.get("cache_entry_block", 8))
    frozen_tail, final_norm = tail_modules(visual, start_block=start_block)
    model = build_train_model(frozen_tail, final_norm, config)
    model.load_state_dict(checkpoint["model_state"])
    device = torch.device(args.device)
    model.to(device).eval()

    arrays: dict[str, np.ndarray] = {}
    private_cases = []
    public_cases = []
    flows = []
    for family, sample_id in selected_ids.items():
        dataset_index = dataset.sample_indices[sample_id]
        item = dataset[dataset_index]
        logits, w_align, w_trans = capture_true_attention(
            model,
            prior=item["prior"].unsqueeze(0).to(device),
            current=item["current"].unsqueeze(0).to(device),
            finding_text=item["finding_text"].unsqueeze(0).to(device),
        )
        probabilities = torch.softmax(logits.float(), dim=-1)[0].cpu().numpy()
        expected_probabilities = np.asarray(
            selected[family]["probabilities"], dtype=np.float64
        )
        if not np.allclose(probabilities, expected_probabilities, atol=2e-5, rtol=0):
            maximum = float(np.max(np.abs(probabilities - expected_probabilities)))
            raise ValueError(
                f"{family} probability replay drift; maximum_abs={maximum}"
            )
        align = w_align[0].float().cpu().numpy()
        transition = w_trans[0].float().cpu().numpy()
        flow = patch_attention_flow(align, transition)
        routes = strongest_routes(flow["edge"])
        flows.append(flow)
        prefix = family
        arrays[f"{prefix}_W_align"] = align.astype(np.float32)
        arrays[f"{prefix}_W_trans"] = transition.astype(np.float32)
        for name in ("A_bar", "r_current", "r_prior", "edge"):
            arrays[f"{prefix}_{name}"] = flow[name].astype(np.float32)
        prediction_index = int(probabilities.argmax())
        private_cases.append(
            {
                "family": family,
                "sample_id": sample_id,
                "sample_hash": selected[family]["sample_hash"],
                "prior_image_path": str(item["prior_image_path"]),
                "current_image_path": str(item["current_image_path"]),
                "finding": str(item["finding"]),
                "reference_progression": PROGRESSION_LABELS[int(item["target"])],
                "predicted_progression": PROGRESSION_LABELS[prediction_index],
                "probabilities": probabilities.astype(float).tolist(),
                "source": str(item["source"]),
                "interval_bucket": _interval_bucket(item),
                "prior_view": str(item["prior_view"]),
                "current_view": str(item["current_view"]),
                "routes": routes,
            }
        )

    clip = shared_attention_clip(flows)
    args.output.mkdir(parents=True, exist_ok=False)
    tensor_path = args.output / "attention_tensors.private.npz"
    np.savez_compressed(tensor_path, **arrays)
    tensor_sha = sha256_file(tensor_path)
    for case in private_cases:
        public_cases.append(
            _private_to_public_case(
                {
                    key: value
                    for key, value in case.items()
                    if key
                    not in {"sample_id", "prior_image_path", "current_image_path"}
                },
                tensor_sha256=tensor_sha,
            )
        )
    checkpoint_sha = sha256_file(args.checkpoint)
    private_manifest = {
        "schema": "prta-cxr.figure5-attention-export.private.v1",
        "status": "PASS_FIGURE5_TRUE_ATTENTION_EXPORTED",
        "source_commit": args.source_commit,
        "checkpoint_sha256": checkpoint_sha,
        "checkpoint_seed": SELECTION_SEED,
        "preselection_sha256": sha256_file(args.preselection),
        "input_sha256": actual,
        "tensor_bundle": {
            "path": tensor_path.name,
            "sha256": tensor_sha,
            "arrays": {name: list(value.shape) for name, value in arrays.items()},
        },
        "shared_p99_clip": clip,
        "cases": private_cases,
        "selection_performed_before_image_or_attention_view": True,
        "images_opened": False,
        "attention_opened_only_after_selection_lock": True,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    public_manifest = {
        "schema": "prta-cxr.figure5-attention-export.public.v1",
        "status": "PASS_FIGURE5_TRUE_ATTENTION_EXPORTED_GIT_SAFE",
        "source_commit": args.source_commit,
        "checkpoint_sha256": checkpoint_sha,
        "checkpoint_seed": SELECTION_SEED,
        "preselection_sha256": sha256_file(args.preselection),
        "tensor_shapes": {
            "W_align": [12, 197, 197],
            "W_trans": [12, 20, 197],
            "A_bar": [196, 196],
            "r_current": [196],
            "r_prior": [196],
            "edge": [196, 196],
        },
        "shared_p99_clip": clip,
        "cases": public_cases,
        "selection_performed_before_image_or_attention_view": True,
        "attention_method": "native post-softmax MHA weights",
        "need_weights": True,
        "average_attn_weights": False,
        "cls_removed_and_patch_renormalized": True,
        "raw_cxr_redistributed": False,
        "raw_attention_tensors_redistributed": False,
        "internal_test_opened": False,
        "gold_opened": False,
    }
    (args.output / "attention_export_manifest.private.json").write_text(
        json.dumps(private_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output / "attention_export_manifest.json").write_text(
        json.dumps(public_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(public_manifest, indent=2, sort_keys=True))
    return 0


def attention_preselection_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze Figure 5 cases before any image/attention view."
    )
    for seed in EXPECTED_SEEDS:
        parser.add_argument(f"--s{seed}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-cell-support", type=int, default=100)
    args = parser.parse_args(argv)
    paths = {seed: getattr(args, f"s{seed}") for seed in EXPECTED_SEEDS}
    report = select_attention_candidates(
        [(seed, _load_jsonl(path)) for seed, path in paths.items()],
        minimum_cell_support=args.minimum_cell_support,
    )
    report["input_sha256"] = {
        f"S{seed}": sha256_file(path) for seed, path in paths.items()
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0
