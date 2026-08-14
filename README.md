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

PRTA-CXR V2 is now frozen as the main method after cleaned Train/Dev-only
three-seed confirmation. Wave045 ablations and mechanism diagnostics, the
Wave046 native-baseline matrix, and the Wave047 paired bootstrap and Tail8
fairness comparison are complete. No independent untouched test has been run
for V2; the project remains
`FROZEN_MAIN_METHOD_TRAIN_DEV_CONFIRMED_PENDING_INDEPENDENT_UNTOUCHED_TEST`.
See the authoritative
[V2 final method and results report](docs/PRTA_CXR_V2_FINAL_METHOD_AND_RESULTS_CN.md).
The rule-blind Luna pilot completed 150/150 rows. A same-roster blind Sol
review found 115/124 agreement (92.74%, kappa 0.908) where both models were
decisive and favored Luna over the rule 21-to-4 in the 30 rule-Luna conflicts.
The user subsequently froze and authorized a Luna-primary labeling policy:
deterministic code constructs and audits candidates, every valid non-`Unclear`
Luna five-class output becomes Silver, and the rule label is diagnostic only.
Full labeling is now complete; see the
[Luna-primary full-labeling status](docs/LUNA_PRIMARY_FULL_LABELING_STATUS_CN.md).
The 250-row senior-physician Luna-assisted panel review is also complete:
246/250 Luna labels were confirmed, four were corrected, and all 250 decisive
consensus labels are frozen as patient-quarantined Gold. See the
[senior-panel Gold status](docs/SENIOR_LUNA_ASSISTED_GOLD_STATUS_CN.md).
The patient-disjoint cleaned split is frozen and independently audited. Any
future independent untouched evaluation remains separately gated and is not
authorized by the Train/Dev method freeze.

## Start here

1. Read the authoritative
   [V2 final method and Train/Dev results](docs/PRTA_CXR_V2_FINAL_METHOD_AND_RESULTS_CN.md).
2. Read [the execution manual](docs/PRTA_CXR_最终论文实验与项目重构执行手册_CN.md).
3. Use [the experiment plan and empty result tables](docs/PRTA_CXR_实验计划与空结果表_Markdown版_CN.md).
4. Review [the migration map](docs/LEGACY_MIGRATION_MAP.md) and
   [Phase 0 status](docs/PHASE0_STATUS.md).
5. Before any real-data build, follow
   [the full-data repartition policy](docs/DATA_REPARTITION_POLICY.md).
6. Use the Chinese
   [training readiness and command runbook](docs/TRAINING_READINESS_AND_COMMANDS_CN.md)
   before allocating a GPU.
7. Check the frozen
   [real-data preparation status](docs/REAL_DATA_PREPARATION_STATUS_CN.md) for
   current counts, hashes, and the next execution gate.
8. Review the
   [Luna pilot status](docs/LUNA_PILOT_STATUS_CN.md) before authorizing any
   historical strict label expansion.
9. Use the current
   [independent Silver pilot status](docs/INDEPENDENT_SILVER_PILOT_STATUS_CN.md)
   as the authority for future full-scale labeling decisions.
10. Review the blind [Sol-vs-Luna status](docs/SOL_BLIND_REVIEW_STATUS_CN.md)
   for the evidence supporting the frozen Luna-primary policy.
11. Use the
    [senior-panel Gold status](docs/SENIOR_LUNA_ASSISTED_GOLD_STATUS_CN.md)
    for the human confirmation/correction result and exact artifact boundary.
12. Use the
    [Train/Dev-only approximate-TracIn audit guide](docs/PRTA_CXR_TracIn只读数据审计说明_CN.md)
    for the post-STOP read-only data-quality audit; row-level outputs remain
    private and must never enter Git.
13. The active data surface is now the physician-confirmed cleaned split. See
    [physician exclusions and frozen cleaned split](docs/PRTA_CXR_医生确认排除与清洗后正式划分_CN.md).

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
