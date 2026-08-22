# PRTA-CXR

PRTA-CXR is the clean, paper-facing implementation of Prior-Responsive
Temporal Adaptation for five-way longitudinal chest X-ray progression
classification:

`Stable / Improved / Worse / New / Resolved`.

The repository preserves only the final ViT-side method and reusable data,
label, evaluation, and audit contracts. Legacy VisualVIT experiment numbers,
failed routes, historical rosters, matched-representation benchmarks, and old
Qwen SFT attempts are intentionally absent.

## Current status

The final paper method is **PRTA-CXR**; `Slim-S1` is retained only as the
frozen configuration identity. Phase20-A passed its formal 88/88 finalizer,
the longitudinal comparator passed 24/24, Phase20-B1 passed 6/6, Phase20-B2
passed 28/28, and the final evidence finalizer passed without model selection.
V2 remains historical development
evidence and is not the final
paper method. See the authoritative
[Slim-S1 Phase20 protocol](docs/PRTA_CXR_Slim-S1最终主线锁定与确认实验协议_CN.md).

The focused six-job Phase20-B1 diagnostic pipeline, Phase20-B2 paired-statistics
pipeline, three authoritative finalizers, and the post-cleanup 8-system × 3-seed
comparator rebuild are complete and hash-gated. The final result package is in
[`paper/`](paper/README.md). ReXGradient/external
validation has been retired from the active paper
evidence; bidirectional MIMIC-CXR/CheXpert Plus source-held evaluation is the
active cross-source generalization experiment. It must not be described as
independent external clinical validation. Internal-test, Gold, and clinician
manual work remain excluded.

The final implementation contains only the four active optimization terms:
classification, state anchor, opposite-direction cost, and matched-hard CMCP.
Five legacy losses whose frozen weights were exactly zero were removed from the
main method and preserved only in the VisualVIT history repository. Exact final
checkpoints are local internal assets and intentionally excluded from Git; their
immutable hashes are recorded in
[`manifests/final_prta_cxr_checkpoints.json`](manifests/final_prta_cxr_checkpoints.json).

Git-safe pre-Phase20 source/config/aggregate history is frozen on
`codex/archive-v2-history-before-phase20` at
`6f471d93421b743fed446b650d7e2fd5f71ef24d`. Retired zero-weight losses,
ReXGradient execution code, and manual-review utilities are stored only in the
VisualVIT history branch `codex/prta-history-archive-20260822`. Checkpoints,
predictions, patient-level material, images, and raw logs are never stored in
ordinary Git.

## Start here

1. Read the authoritative
   [Slim-S1 Phase20 protocol](docs/PRTA_CXR_Slim-S1最终主线锁定与确认实验协议_CN.md).
2. Read the [Phase20 paper-facing rerun matrix](paper/13_PRTA-CXR-Slim-S1最终主线与重跑矩阵_CN.md).
3. Use [the final experiment and result index](paper/17_论文实验数据总表与待跑清单_CN.md).
4. Use [the final evidence narrative](paper/18_Phase20最终证据与论文叙事_CN.md)
   when drafting the paper.

## Local engineering validation

```powershell
python -m pip install -e . --no-deps
python scripts/00_preflight.py
python scripts/06_cache_vit_tokens.py --mode preflight
python scripts/07_train.py --mode preflight
python scripts/08_evaluate.py --mode preflight
python scripts/07_train.py --mode smoke --output results/smoke/checkpoint.pt
python -m pytest
ruff check .
python -m compileall -q src scripts tests
```

The smoke train uses generated tensors only. It does not open image/report
data, caches, protected outcomes, or formal output directories.

The new source catalog intentionally does not inherit old debug rosters. It
rebuilds patient-disjoint splits from all sources that pass governance and
lineage checks; revealed tests, protected gold, and external confirmation data
remain excluded.

## Formal execution lock

Formal paths require both a CLI flag and an exact environment acknowledgement:

```text
--formal
PRTA_CXR_ALLOW_FORMAL=I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN
```

This lock is an engineering safety boundary, not authorization by itself. The
user must still explicitly authorize the specific formal phase/run.
