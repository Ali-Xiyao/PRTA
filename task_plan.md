# PRTA-CXR full-data training pipeline implementation

## Goal

Turn the clean PRTA-CXR repository from an engineering scaffold into a
data-to-training implementation that can rebuild an enlarged eligible dataset,
freeze new patient-disjoint splits, prepare/cache inputs, train/evaluate PRTA,
and write auditable receipts once the user later authorizes execution.

## User decision to preserve

- Retire debugging-only small-cohort partitions and temporary development
  isolation when building the new eligible candidate pool.
- Reconsider all previously used datasets for inclusion so training scale can
  increase.
- Rebuild patient-level train/dev/internal-test partitions from scratch inside
  the new project rather than inheriting old debug rosters.
- This does not override licensing/DUA/privacy constraints and does not allow
  revealed historical test, protected gold, or external confirmation cohorts
  to enter training or development.

## Non-negotiable execution boundary

- Implement and test code only in this task.
- Do not read real reports/images/outcomes, build real caches, call Luna, or
  launch formal training/evaluation without a later explicit authorization.
- Synthetic fixtures and dry-run/preflight validation are allowed.

## Phases

### Phase 1 - Policy, source inventory contract, and gap audit
Status: complete

- Record the full-data repartition policy in durable project documentation.
- Inspect the scaffold and legacy reference implementation for reusable,
  non-R-numbered data/training components.
- Define source eligibility, exclusion reasons, and split-freeze contracts.

### Phase 2 - Dataset assembly and repartition implementation
Status: complete

- Implement source catalogs, normalized study ingestion, adjacent pairing,
  exclusion auditing, deduplication, and patient-disjoint source-aware splits.
- Replace scripts 01 and 05 dry-run stubs with real prepare/preflight modes and
  formal write gates.

### Phase 3 - Label pipeline implementation
Status: complete

- Implement candidate sample preparation, Luna batch preparation, strict batch
  validation, merge/audit, tiering, and label-manifest receipts.
- Replace scripts 02-04 dry-run stubs while keeping external calls locked.

### Phase 4 - Cache, dataloader, training, evaluation, and receipts
Status: complete

- Implement cache manifest validation, datasets/dataloaders, loss composition,
  checkpoint/resume, validation metrics, and run receipts.
- Replace scripts 06-08 with functional preflight/synthetic modes and locked
  formal execution paths.

### Phase 5 - Verification and local Git handoff
Status: complete

- Add focused tests, run repository gates and an end-to-end synthetic pipeline.
- Update readiness/HOLD documentation, commit, push to the local-only remote,
  and verify a fresh clone.

## Next Step

Await explicit authorization for the first real-data inventory/manifest build;
do not start training or open protected/internal-test outcomes automatically.

## Decisions

| Decision | Rationale |
|---|---|
| Rebuild splits from the full authorized candidate pool | Debug-only isolation should not cap the new training scale. |
| Preserve sealed/revealed/gold/external and legal/privacy exclusions | Removing those boundaries would invalidate evaluation or data governance. |
| Patient is the indivisible split unit | Prevents longitudinal leakage across train/dev/test. |
| Code only; no real execution in this task | The user asked to start coding, not to start training. |
| Generate the text cache from frozen BiomedCLIP prototypes | Avoid a hidden manual input between image caching and training. |
| Require a separate internal-test open flag | Training completion must not silently consume the test partition. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `rg` received Bash-style `**` globs as literal Windows filenames while listing current symbols | 1 | Use `rg` on directories with `-g '*.py'` or enumerate files first; the rest of the inventory completed. |
| First data validation passed 18 tests and both synthetic CLIs, but Ruff found import/line formatting and the split audit produced 28/1/1 patients instead of the configured 24/3/3 | 1 | Add exact largest-remainder patient capacities before optimizing strata, patch long lines, and apply safe import formatting. |
| First label validation reached 22/23 tests; `possible increased ...` escaped the uncertainty filter, and Ruff found import/line/unused-loop formatting | 1 | Add the `possible` lexical form to the uncertainty gate, patch explicit formatting, and apply safe import sorting. |
| First Phase-4 repository pass reached 24 tests but Ruff found one long line and three missing strict zip arguments | 1 | Reformat the mapping and bind target/prediction pairs with `strict=True`; the next pass reached 25/25. |
| First formal-entry lock-order test reached 26/28 because cache/evaluation checked `--output` before authorization | 1 | Move authorization to the first formal branch action; final suite passes 28/28 and all three formal CLIs fail closed before input checks. |
