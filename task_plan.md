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

- The user has now authorized the first real-data inventory and source-manifest
  preparation phase.
- Do not launch GPU training, create the full real image cache, call Luna, or
  open internal-test/protected/gold/external outcomes without a later explicit
  phase authorization.
- Structural metadata, report file existence, exclusion identifiers, source
  manifests, counts, hashes, and leakage audits may be processed now.

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

### Phase 6 - Real asset inventory and governance activation
Status: complete

- Locate all previously used CXR datasets, reports, metadata, exclusion
  registries, and BiomedCLIP assets without reading protected outcomes.
- Classify each source as eligible, auxiliary, excluded, or blocked, with
  concrete path/count/hash evidence.
- Update the source catalog only for sources whose local governance and
  longitudinal contracts can be demonstrated.

### Phase 7 - Unified source manifests and exclusion registry
Status: complete

- Build normalized source study manifests from eligible raw metadata/report
  structure without inheriting old debug rosters.
- Project historical revealed/protected/gold/external patient identifiers into
  a hash-only exclusion registry without opening outcome fields.
- Validate image/report existence, uniqueness, patient timelines, and source
  lineage; write auditable receipts.

### Phase 8 - Full candidate pair build readiness
Status: complete

- Run the locked full pair builder on the new manifests only after Phase 7
  passes.
- Audit counts, interval validity, cross-source lineage, exclusions, and disk
  requirements; stop before Luna, real image caching, or training.

### Phase 9 - Commit and local handoff
Status: complete

- Run tests/static checks, update authority/readiness documents, commit, push
  to the local-only remote, and verify local/remote equality.

## Next Step

Hold before rule/Luna label preparation until the user explicitly authorizes
that next phase; do not create a split, cache, training run, or evaluation yet.

## Decisions

| Decision | Rationale |
|---|---|
| Rebuild splits from the full authorized candidate pool | Debug-only isolation should not cap the new training scale. |
| Preserve sealed/revealed/gold/external and legal/privacy exclusions | Removing those boundaries would invalidate evaluation or data governance. |
| Patient is the indivisible split unit | Prevents longitudinal leakage across train/dev/test. |
| Code only; no real execution in this task | The user asked to start coding, not to start training. |
| Generate the text cache from frozen BiomedCLIP prototypes | Avoid a hidden manual input between image caching and training. |
| Require a separate internal-test open flag | Training completion must not silently consume the test partition. |
| Treat the new user approval as manifest-phase authority only | The preceding handoff named inventory/manifests as the next step, not training or outcome opening. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `rg` received Bash-style `**` globs as literal Windows filenames while listing current symbols | 1 | Use `rg` on directories with `-g '*.py'` or enumerate files first; the rest of the inventory completed. |
| First data validation passed 18 tests and both synthetic CLIs, but Ruff found import/line formatting and the split audit produced 28/1/1 patients instead of the configured 24/3/3 | 1 | Add exact largest-remainder patient capacities before optimizing strata, patch long lines, and apply safe import formatting. |
| First label validation reached 22/23 tests; `possible increased ...` escaped the uncertainty filter, and Ruff found import/line/unused-loop formatting | 1 | Add the `possible` lexical form to the uncertainty gate, patch explicit formatting, and apply safe import sorting. |
| First Phase-4 repository pass reached 24 tests but Ruff found one long line and three missing strict zip arguments | 1 | Reformat the mapping and bind target/prediction pairs with `strict=True`; the next pass reached 25/25. |
| First formal-entry lock-order test reached 26/28 because cache/evaluation checked `--output` before authorization | 1 | Move authorization to the first formal branch action; final suite passes 28/28 and all three formal CLIs fail closed before input checks. |
| Recursive CheXlocalize file listing emitted thousands of Grad-CAM paths and truncated tool output | 1 | Stop recursive enumeration of image-like assets; inspect only top-level inventories, receipts, counts, and named metadata files. |
| Broad `H:\Xiyao_Wang` CheXpert directory search took 25 seconds and returned many unrelated experiment-output folders with exit 1 | 1 | Use the exact discovered `H:\Xiyao_Wang\02101\data\dataset\CheXpert-Plus` candidate root and avoid further broad scans. |
| Search assumed old `configs/r29`, `r30`, and `r31` directories that do not exist | 1 | Use the concrete runtime cohort roots and builder scripts found under the old repository instead of guessing config paths. |
| R29/R30/R31 `cohort_audit.json` files unexpectedly included aggregate label counts alongside structural partition counts | 1 | Stop reading those audits; no row-level cohort/result file was opened. Build a narrow ID/partition-only projector, do not use or serialize label fields, and record this accidental aggregate-only exposure in the audit trail. |
| First focused source-builder lint found one unused `Iterable` import | 1 | Remove the import; targeted source/data tests pass 7/7 and focused Ruff is clean. |
| First combined real source build hit the 30-minute outer timeout while processing MIMIC small report files; the Python child remained alive | 1 | Formal root was never prematurely created; preserve and monitor PID 29840 without launching a duplicate, then audit its terminal output and add per-source resumability for future runs. |
| Resume completed both source manifests but exclusion projection rejected four nonnumeric legacy gold identifiers | 1 | Keep fail-closed behavior, hash those opaque identifiers as namespaced raw strings while retaining numeric normalization for MIMIC IDs, add a regression test, and reuse the completed atomic MIMIC manifest on retry. |
| First full pair build found four duplicate MIMIC patient-time rows and failed the strict increasing-time contract before writing an artifact | 1 | Audit both source manifests, then deterministically retain one frontal study per patient/time point (PA first, then stable IDs), record the dropped-row count, and keep zero-interval pairs prohibited. |
