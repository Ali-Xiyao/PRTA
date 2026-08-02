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

The full data-to-training code path and synthetic validation are implemented.
Formal scientific experiments have **not** been started. Data activation,
repartition, labeling, caching, training, and internal testing remain separately
gated and require explicit authorization.

## Start here

1. Read [the execution manual](docs/PRTA_CXR_最终论文实验与项目重构执行手册_CN.md).
2. Use [the experiment plan and empty result tables](docs/PRTA_CXR_实验计划与空结果表_Markdown版_CN.md).
3. Review [the migration map](docs/LEGACY_MIGRATION_MAP.md) and
   [Phase 0 status](docs/PHASE0_STATUS.md).
4. Before any real-data build, follow
   [the full-data repartition policy](docs/DATA_REPARTITION_POLICY.md).
5. Use the Chinese
   [training readiness and command runbook](docs/TRAINING_READINESS_AND_COMMANDS_CN.md)
   before allocating a GPU.

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
