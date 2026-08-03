# Progress - full-data training pipeline

## 2026-08-02 - Luna-primary full-run concurrency qualification

- Prepared 7,440 rule-blind batches for all 148,798 frozen candidates; the
  preparation receipt reproduces candidate hash
  `29ceedb0719d9c04476d5aa157da937147acb2314cb9f7c4b1d571b9b9d7e81e`.
- Independent batch audit: 148,798 unique restored IDs, exact four external
  fields, no rule label or patient identifier, final batch size 18, and zero
  schema/field/map errors.
- Four-worker qualification initially exposed one 19/20-ID Luna response. The
  runner failed closed; bounded retries were added and the malformed response
  was preserved.
- Qualification resume passed: 40/40 batches, 800/800 unique IDs, four PASS
  receipts, no unresolved batch failure. Safe expansion is eight disjoint
  shards over batches 40-7439 with resume enabled.
- Concurrency was subsequently qualified at 8, 16, 32, then 64 disjoint workers.
  Each scale-up stopped exact prior PIDs, preserved valid outputs, verified
  remaining ranges were contiguous, and restarted from the first missing batch.
- The final 64-worker command-line audit covers 6,231 then-missing batches
  exactly once (overlap 0; shard sizes 16-174); completed outputs remain outside
  those ranges and are reused rather than overwritten.
- Gold-audit preparation now also writes a training-eligible Silver manifest
  that removes all rows belonging to the 250 selected patients; focused tests
  prove zero patient overlap with the quarantined manifest.

## 2026-08-02

- Received authorization to begin coding, but not to begin training.
- Recorded the decision to retire debugging-only dataset isolation, reconsider
  all previously used datasets, increase eligible data scale, and rebuild
  patient-level splits from scratch.
- Preserved non-debug boundaries for licensing/privacy, revealed historical
  tests, protected gold, external confirmation, and patient leakage.
- Started Phase 1 policy/interface audit.
- Audited the current 00-11 wrappers and legacy data, labeling, cache, and
  formal-pipeline implementations. Identified generic algorithms to migrate and
  R-number/path/roster assumptions to discard.
- Added and linked `docs/DATA_REPARTITION_POLICY.md`, plus a source-catalog
  template that names MIMIC-CXR-JPG and CheXpert Plus as candidates while
  leaving governance activation false until runtime evidence is supplied.
- Implemented source catalog/audit, hashed exclusion registries, source study
  normalization, one-frontal selection, protected/dedup filtering, full
  adjacent-pair assembly, and source/label/finding-aware patient splits.
- Replaced scripts 01 and 05 with functional preflight, synthetic, and locked
  formal modes. Phase 1 is complete; Phase 2 now needs tests and correction.
- Added four focused data-policy tests; the first pass reached 18/18 tests and
  both synthetic CLIs. The audit exposed an important balancing defect: the
  unconstrained greedy split produced 28/1/1 patients. Added exact
  largest-remainder patient capacities so 80/10/10 is enforced before
  optimizing source/finding/label balance.
- Implemented clean deterministic report-rule extraction, candidate samples,
  de-identified Luna batches, external command construction, strict output
  validation, and Tier merge/audit; scripts 02-04 now have functional
  preflight/synthetic/locked-formal modes.
- The first label pass reached 22/23 tests and found that `possible` was absent
  while `possibly` was covered. Added the missing uncertainty form so that
  ambiguous direction fails closed.
- Corrected label pipeline passes 23/23 tests. Phases 2 and 3 are complete;
  Phase 4 starts with the cache format and model/data loading contract.
- Added a clean direct Block-8 cache format with SHA-256 image keys, FP16
  shards, manifest hashes, finite/shape checks, LRU loading, and backward
  compatibility for the migrated legacy cache schema.
- Added a local BiomedCLIP visual loader, exact Blocks 1-8 encoder, frozen
  Blocks 9-12 tail adapter, and a frozen text-tower cache for finding and
  finding-by-progression prototypes. Optional vision dependencies remain lazy.
- Added the feature dataset, full multi-loss PRTA training engine, H0/H1 heads,
  deterministic loaders, gradient clipping, checkpoint/resume, best-dev
  selection, receipts, and checkpoint-bound input hashes.
- Replaced scripts 06-08 with functional preflight/synthetic/formal paths.
  Internal-test evaluation needs a separate open flag and never reads protected
  outcomes.
- Phase-4 validation reached 25/25 tests, Ruff clean, and successful synthetic
  cache/train/evaluation CLIs. No real image, report, labeler, training, or test
  data was opened.
- Added a Chinese readiness/run-command document that makes clear a GPU alone
  is insufficient until source governance, manifests, new split, labels, and
  caches are ready and separately authorized.
- Final lock-order tests initially exposed two CLIs that validated `--output`
  before the formal environment lock. Reordered cache/evaluation authorization
  to be the first formal action; all 28 tests now pass.
- Read-only local asset validation strictly loaded the existing BiomedCLIP
  checkpoint, produced finite dummy Block-8/text representations, and produced
  finite full-size PRTA five-class logits. No real image/report or optimizer
  step was used.
- Committed the implementation as `b3c4249` and pushed `main` only to the
  local bare remote `PRTA-CXR-local.git`; no cloud remote exists or was used.

## 2026-08-02 real-data preparation authorization

- The user approved starting the next step named in the handoff: real asset
  inventory and unified source-manifest preparation.
- Training, Luna, real image caching, internal-test opening, and protected
  outcome access remain outside this phase.
- Started Phase 6 inventory and governance evidence collection.
- Confirmed MIMIC official-train and CheXpert Plus train as the two local
  longitudinal report sources; classification/localization-only CXR datasets
  remain auxiliary or blocked for the primary progression pool.
- Added a fresh-only real source builder for MIMIC and CheXpert Plus, plus an
  ID/partition-only historical exclusion projector covering R24-R32 while
  deliberately reactivating old train-only membership.
- Added three focused source-builder tests; the targeted source/data suite
  passes 7/7 and focused Ruff passes.
- Launched the authorized fresh real source build under PID 29840. The outer
  command reached its 30-minute limit, but process inspection confirmed the
  child remained alive with increasing CPU and I/O counters; no duplicate was
  launched and no formal directory was prematurely accepted.
- At the first staging audit, the atomic MIMIC temp JSONL had 176,745 readable
  lines and later 199,452,548 bytes. The process remains I/O-active; CheXpert,
  exclusions, pair construction, cache, and training have not started.
- After confirming sustained but very low disk throughput, stopped only the
  orphaned builder PID 29840; the formal output never existed and staging was
  preserved. The final partial audit found 206,724 complete, valid, unique
  MIMIC JSONL rows, zero duplicate image IDs, and no malformed tail.
- The first resume completed atomic MIMIC and CheXpert source JSONLs in staging
  but stopped at the exclusion projector because four gold identifiers had no
  numeric component. Added a namespaced opaque-ID hash fallback with a receipt
  counter; regression tests remain 3/3 and Ruff clean.
- The corrected retry atomically completed `sources_v1`: MIMIC 213,365 studies
  and CheXpert Plus 187,474 studies, plus a 3,750-patient hash-only exclusion
  registry. Independent full parsing verified row/key/time-basis/report
  integrity and confirmed all protected execution flags remained false.
- Closed Phases 6 and 7. Added explicit pair-level calendar-versus-ordinal
  semantics and regression coverage; the focused data suite passes 10/10 and
  Ruff is clean. Phase 8 is now building the full candidate pair manifest.
- The first full pair attempt failed closed before writing files on four
  duplicate MIMIC patient-time rows. Added deterministic timepoint
  deduplication plus a regression test; zero-interval transitions remain
  prohibited.
- The corrected full build produced 238,511 adjacent pairs from 362,593
  normalized studies. Independent streaming validation reproduced the
  canonical hash and found zero excluded patients, raw patient fields,
  nonpositive intervals, time-basis conflicts, pair-ID mismatches, duplicate
  edges, or non-adjacent chains.
- Added `docs/REAL_DATA_PREPARATION_STATUS_CN.md` and refreshed README/readiness
  status so the repository now identifies the exact artifact boundary and the
  next label-review gate. The two supplied authority documents remain
  byte-identical to their originals.
- Final repository validation passes 34/34 tests, Ruff, compileall, the main
  preflight, every scripts/00-08 preflight, and `git diff --check`. No formal
  experiment, cache, Luna call, internal-test opening, or GPU training was
  triggered by these verification gates.

## 2026-08-02 labeling authorization

- The user explicitly authorized the next named phase: rule candidate
  generation and Luna label review. Split freeze, cache generation, GPU
  training, and evaluation remain outside this authorization.
- Activated the labeling config only for that scope and amended the Luna prompt
  so within-patient ordinal metadata cannot be interpreted as calendar dates
  or elapsed days.
- Generated and independently verified 148,798 rule candidates in 5,952
  reusable batches. Froze a 150-patient stratified pilot spanning 118 strata,
  with exact 75/75 source and calendar/ordinal balance.
- The first pilot invocation failed before any external call because Windows
  exposed `codex` as a PowerShell wrapper to Python subprocess. Added explicit
  `codex.cmd` resolution plus atomic per-batch output, timeout, and resume
  support; the empty pilot output directory is safe to reuse.
- Three pilot batches (75 rows) completed under the first authority, but the
  fourth returned `accept` with a conflict flag and correctly failed the
  runtime Tier-A contract. Those first outputs are retained as invalidated
  runner evidence and will not be merged. Strengthened the prompt and output
  schema so acceptance logically implies matching finding/comparison, no
  conflict flags, and non-empty comparison evidence; the full 150-row pilot
  must be regenerated and rerun under the new single authority hash.
- The v2 canary was rejected server-side before output generation because the
  Structured Outputs subset disallows `allOf` at the item schema. Removed that
  unsupported keyword while retaining the explicit prompt rule and strict
  runtime validator; v2 is invalidated and v3 will be the next authority.
- The v3 pilot completed 150/150 structurally valid rows and merged to 74
  Tier-A / 76 Reject, with rule/Luna label agreement 143/150. However, only
  48/74 Tier-A rows had all three evidence fields as contiguous token spans in
  the corresponding reports, below the >=98% pilot target. Full expansion is
  held. Added an extractive-evidence merge gate and a prompt prohibition on
  paraphrase/non-contiguous evidence; the same frozen pilot will rerun as v4.
- The first v4 canary failed the exact-ID set gate before formal output. Its
  temporary output was not preserved because the mismatch check was one block
  outside the preservation handler; corrected that runner defect. No v4 row
  was accepted or merged, and the unchanged v4 authority can be retried.
- The v4 retry failed the same ID gate. The now-preserved rejected output had
  23 unique expected IDs, two missing, no extras, and no duplicates. Full
  expansion remains held. Added an exact one-output-per-input instruction and
  reduced standard batch size to 20 for v5; the ID contract is unchanged.
- The v5 canary returned 20 unique rows but transcribed one long sample hash
  incorrectly (one missing and one extra ID). Added short batch-local aliases;
  the private alias map is removed from the external payload, exact aliases are
  checked, and original IDs are restored locally before atomic output. v6 will
  use this traceable interface without relaxing the ID contract.
- The v6 alias canary passed 20/20 ID/schema gates. One of 14 accepted rows had
  non-extractive current/comparison evidence, so the merge policy now
  deterministically demotes such records to Reject while preserving the raw
  Luna record and recording `non_extractive_evidence`. Tier-A therefore
  requires 100% extractive evidence by code, without manual label repair.
- The sixth v6 batch twice returned an accept/flag contradiction. Refactored
  the gate so Luna rows are structurally preserved while deterministic label
  admission demotes accept+conflict, accept+mismatch, and non-extractive
  accepts to explicitly audited Rejects. This stops stochastic retries without
  weakening Tier-A or editing raw model output.
- Completed the final v6 pilot: 150 unique rows, 45 Tier-A, 105 Reject, zero
  Tier-B, 142/150 rule/Luna label agreement, and one non-extractive accept
  deterministically rejected. Final Tier-A extractive evidence is 45/45.
- The pilot places full expansion on HOLD: strict batch-attempt failure was
  2/10, MIMIC Tier-A was 35/75 versus CheXpert Plus 10/75, and observed
  sequential throughput projects roughly 9-10 days for all 148,798 candidates.
  Added `docs/LUNA_PILOT_STATUS_CN.md`; no split/cache/train/test was opened.
- Wrote the real pilot results and eight v6 batch rows back into the active
  experiment-plan table, disabled formal full-Luna execution in config and
  enforced that HOLD in the runner. Final repository gates pass 37/37 tests,
  Ruff, compileall, diff-check, main preflight, and downstream split/cache/train/
  evaluation preflights without opening any protected surface.

## 2026-08-02 independent-silver protocol authorization

- The user replaced the proposed full-scale strict evidence workflow with a
  rule-blind independent-intersection protocol and asked for a trial.
- The external AI request will contain no rule label, confidence, rationale,
  evidence quotation, patient identifier, or private alias mapping. Its only
  per-row output is `sample_id` plus one of the five progression labels or
  `Unclear`.
- Exact rule/AI agreement is admitted as silver; mismatch and `Unclear` are
  excluded. Agreement is explicitly not treated as ground truth.
- Source-specific agreement is mandatory. A later 200-300-row stratified human
  accuracy audit remains a hard prerequisite for formal training or paper use.
- Started Phase 13. Full labeling, split, cache, training, and evaluation are
  not authorized by this trial.
- Added separate prompt/schema/config, batch preparation, resume-safe runner,
  exact-intersection merge, exclusion manifest, source/label audits, and a
  formal training gate that requires a completed 200-300-row human audit
  receipt.
- Reused the exact historical 150-row selection (`c7a44d86...858f9`) while
  keeping all historical strict outputs immutable. The new external payload
  contained only short aliases, finding, and prior/current reports.
- Completed the independent AI pilot 150/150 in eight batches with zero failed
  outputs or retries. Total external time was 344.991 seconds.
- The local intersection admitted 103/150 Silver rows, excluded 30 mismatches
  and 17 `Unclear` rows. MIMIC retained 52/75 (69.33%) and CheXpert Plus 51/75
  (68.00%); `Worse` was the lowest rule stratum at 17/30 (56.67%).
- Disabled both repeated pilot execution and full execution in the frozen
  config. No full label expansion, split, cache, training, test, gold, or
  external-confirmation surface was opened.
- Updated both supplied authority documents, README, readiness commands,
  migration map, and the new pilot status receipt. Final validation passes
  49/49 tests, Ruff, compileall, all relevant preflights, runtime artifact
  re-audit, and `git diff --check`.

## 2026-08-02 Sol blind-review authorization

- The user authorized a Sol blind review of the same frozen 150 rows after
  explicitly separating AI-AI agreement from medical accuracy.
- Sol will receive the same short alias, finding, prior report, and current
  report only. Rule and Luna labels remain local.
- This scope authorizes only the 150-row Sol review and three-way audit. Full
  labeling, split, cache, training, and all outcome surfaces remain closed.
- Started Phase 16 with one-canary-then-resume and fail-closed ID/schema gates.
- Added a model/config/hash-pinned Sol authority and deterministic three-way
  audit with Wilson intervals, six-class and decisive five-class agreement,
  Cohen's kappa, confusion matrices, source/label strata, and focused mismatch
  accounting. Focused tests and Ruff passed before the external call.
- Rebuilt the same 150-row roster at the identical candidate hash and ran
  `gpt-5.6-sol`: 8/8 batches and 150/150 IDs passed with zero failed outputs
  and zero retries. Total Sol external time was 378.974 seconds.
- Luna-Sol agreement was 121/150 (80.67%, six-class including `Unclear`,
  kappa 0.765). On the 124 rows where both models were decisive, agreement was
  115/124 (92.74%, kappa 0.908).
- Decisive agreement was 57/63 (90.48%) for CheXpert Plus and 58/61 (95.08%)
  for MIMIC. By Luna label it was Improved 95.83%, New 85.71%, Resolved 95%,
  Stable 96%, and Worse 95%.
- Within the 30 rule-Luna mismatches, Sol supported Luna 21 times, the rule 4
  times, a third label once, and returned `Unclear` 4 times. This pilot favors
  removing rule-label agreement as an admission requirement, but does not
  estimate medical accuracy or authorize the policy switch/full expansion.
- Froze the completed Sol pilot config with both pilot and full execution
  disabled. No split, cache, training, test, gold, or external outcome opened.
- Added `docs/SOL_BLIND_REVIEW_STATUS_CN.md` and synchronized README, readiness,
  the experiment plan, execution manual, legacy map, and the earlier
  independent-pilot status without silently activating Luna-primary admission.
- Final validation passes 52/52 tests, Ruff, compileall, main/Sol/downstream
  preflights, and `git diff --check`. Independent runtime re-audit confirmed
  identical Luna/Sol input hashes, four allowed external fields, 150 unique
  two-field Sol outputs, zero failed files, and a comparison hash matching the
  frozen v2 audit.

## 2026-08-02 Luna-primary full-labeling authorization

- The user explicitly selected Luna as the sole five-class label generator and
  asked to complete full labeling. Rule-Luna agreement is no longer an
  admission criterion; Luna `Unclear`/unusable rows must be discarded.
- Structural automation remains in scope for candidate pairing, target finding,
  uncertainty/structure filtering, de-duplication, ID/source/patient audit,
  batching, resumability, and receipts. It does not choose the final class.
- A Luna-prelabeled test subset may become Gold only after every selected row
  is human-confirmed and patient-quarantined. The 200-300-row sampled review
  remains a Silver accuracy audit and cannot make unreviewed rows Gold.
- Started Phase 19. This authorization covers labeling and roster preparation,
  not GPU training, cache generation, internal-test opening, or paper claims.

## 2026-08-02 blind human-review handoff

- Added `docs/PRTA_CXR_Gold人工盲审规则_CN.md` with label definitions,
  boundary cases, unusable reasons, blinding requirements, and completion gates.
- Exported 250 cases to
  `outputs/gold_human_review_20260802/PRTA_CXR_Gold人工盲审表_v1.xlsx` after a
  stable blind shuffle. The workbook contains only review alias, source,
  target finding, PRIOR/CURRENT reports, and reviewer-entry fields.
- Workbook re-import checks confirmed 250 rows, 125 rows per source, valid QC
  formulas, and zero occurrences of `luna_label`, `patient_id_hash`,
  `sample_id`, or `clinician_label`. All four sheets passed rendered visual QA.
- Human responses, deblinding, Gold freeze, split, cache, and training remain
  pending; no scientific outcome gate was opened.
- Packaged the reviewer-facing protocol and blind workbook only as
  `outputs/gold_human_review_20260802/PRTA_CXR_Gold_Human_Review_Package_v1.zip`
  for direct offline handoff; no Luna mapping or project runtime artifact is
  included.

## 2026-08-02 first review withdrawn and senior review repackaged

- The user questioned the first reviewer's reliability and explicitly asked to
  delete the first-round result. Restored the tracked v1 workbook to its
  original empty Git blob (`6665f27c...acf4c`) using a byte-identical verified
  backup.
- Deleted the two derived runtime result directories
  `human_review_complete_v1` and `human_review_complete_v2`; the verified
  remaining count is zero. Luna outputs, the frozen 250-row roster, patient
  quarantine, and labeling code were preserved.
- The user changed the second review from blind to Luna-assisted. Generated a
  newly shuffled 250-row workbook that exposes `Luna标签` and leaves every
  senior-doctor response field empty. It contains 125 rows per source and 50
  rows per Luna five-class label; no first-review answer field was found.
- Rendered and visually checked all four workbook sheets. Packaged only the new
  workbook, assisted-review instructions, and v2 label rules in
  `outputs/gold_human_review_senior_20260802/PRTA_CXR_Gold_Senior_Doctor_Luna_Assisted_Review_Package_v2.zip`.
- Workbook SHA-256 is `2e823b7154d0cf92560c1cd2f4a7d853fd61f3589f9291fb2bf6f09047547e07`;
  package SHA-256 is `536bc5225cc7543ced4ffbe050f353435beea1e0afa0d6da69020c5a6ee69e2b`.
- Upgraded the importer to recognize both the legacy blind schema and the new
  Luna-assisted senior schema, including exact verification of the displayed
  Luna label against the frozen roster. Final validation passes 64 tests,
  Ruff, compileall, formalizer preflight, direct parse of the new workbook, and
  `git diff --check`.
- Gold freeze, split, cache, internal test, and GPU training remain closed.

## 2026-08-03 senior-consensus Gold import authorization

- The user authorized formal import and Gold freeze from the returned workbook
  at `outputs/PRTA_CXR_Gold资深医生_Luna辅助复核表_v2.xlsx`.
- Read-only artifact inspection found a compact A-H return: the doctors removed
  the unused trailing columns and filled exactly one `资深医生标签` column.
  All 250 labels are valid and decisive; 250 review IDs are unique; source,
  finding, prior/current reports, and displayed Luna labels bind exactly to the
  frozen roster with zero mismatches.
- User-attested provenance: two physicians, each with more than five years of
  clinical experience, produced the single result column. This will be recorded
  as Luna-assisted panel consensus, not two independent annotations.
- Started Phase 28. Split, cache, internal test, and GPU training remain closed.
- Added explicit compact A-H workbook schema support and a separate
  `senior-review-provenance.v1` authority recording two reviewers, >5 years of
  experience each, Luna-visible single-column consensus, and absence of
  row-level identities/dates. The original returned workbook remains unedited.
- Extended the Gold finalizer to require that provenance for compact returns,
  verify the displayed Luna label against the frozen roster, and mark outputs
  as panel consensus rather than independent review. Seven focused tests,
  focused Ruff/compileall, the compact synthetic preflight, and diff-check pass.
- Full validation then passed 67 tests, repository-wide Ruff/compileall, direct
  parsing of the real returned workbook, and workbook hash pinning at
  `b2caf748...c429`.
- Formally froze `senior_panel_gold_v1`: 250/250 decisive Gold rows, 250 unique
  patients, 246/250 Luna confirmations (98.4%), four physician corrections,
  zero exclusions, 2,297 quarantined Silver rows, 124,430 training-eligible
  Silver rows, and zero Gold/training patient overlap.
- Independent re-read reproduced all four canonical manifest hashes. The Gold
  manifest hash is `564d9b38...8bcad`; the audit file SHA-256 is
  `26f4f2e5...9b10b`. No split, cache, internal test, or training was started.
- Synchronized the README, Luna status, training-readiness guide, both paper
  authority documents, and a dedicated senior-panel Gold status page with the
  final counts, four corrections, terminology boundary, and frozen hashes.
- Final repository validation passed 67 tests, repository-wide Ruff,
  compileall, compact human-review preflight, split preflight, and
  `git diff --check`. A fresh runtime re-read reconfirmed 250 Gold rows, 246
  confirmations, four corrections, zero exclusions, zero Gold/training patient
  overlap, 2,297 quarantined Silver rows, and 124,430 training-eligible Silver
  rows. The formal split/cache/training flag remains false.
- Committed the frozen package as `25cfc91` and pushed it only to the local bare
  remote `E:\Xiyaowang\050_VisualVIT\PRTA-CXR-local.git`; local `main` and the
  local remote `main` were byte-identical at verification time. No cloud remote
  exists in this clean project.

## 2026-08-03 full formal-program authorization

- The user authorized implementation and formal execution of the complete
  program in the two Chinese paper authority documents and requested a
  20-minute recurring monitor until terminal completion.
- Expanded the persistent plan through split freeze, cache, Train/Dev
  development, protocol freeze, formal baselines/ablations, one-time
  Internal-test/Gold evaluation, trust/calibration/subgroups, figures, the VLM
  appendix, and final paper/local handoff.
- Preserved the authority documents' order: the authorization enables the
  stages but does not permit test-driven tuning or premature Gold/Test access.
- One command-inventory search failed because a pattern beginning with
  `--mode` was parsed as an option; recorded the issue and will use `rg --`.
- The first 20-minute heartbeat request was rejected because a local
  destination requires an explicit target thread. No automation was created;
  the retry will use the app's current-thread destination.
- Created and activated the current-thread heartbeat
  `prta-cxr-formal-program-monitor` at a 20-minute cadence with the two paper
  documents, planning files, stage order, one-time test boundary, resume rules,
  and local-only push policy embedded in its task prompt.
- Phase-30 resource audit found two idle RTX 3090 24 GB GPUs, no competing PRTA
  processes, and sufficient immediate free space on H: for split and initial
  preparation. The paper experiment config directories are still placeholders,
  so formal matrix implementation must proceed alongside the first split/cache
  stages rather than pretending the repository is already paper-complete.
- A split-code inspection used two guessed legacy-style filenames that are not
  present. The file inventory identifies `src/prta_cxr/data/splitting.py` plus
  the thin `scripts/05_freeze_splits.py` entrypoint as the correct surfaces.
- Committed the full-program authority/monitor plan as `0eb29b6` and pushed it
  to the local-only bare remote before formal execution.
- Formally froze `formal_program_v1/splits/full_repartition_v1.jsonl` in 22.8
  seconds. The built-in audit passed with 32,557 patients at exact 80/10/10
  capacities and zero patient overlap.
- A separate full JSONL audit passed: all 124,430 input sample IDs are preserved
  exactly once; Train/Dev/Internal-test and the 250-patient Gold set are pairwise
  disjoint; all sources and five labels remain supported; the canonical
  manifest hash exactly reproduces the formal audit. No GPU, cache, training,
  or outcome read occurred.
- Pinned the strictly loadable local BiomedCLIP assets and their hashes. Cache
  source inspection exposed a scale blocker before GPU launch: the current CLI
  accumulates the entire feature tensor before writing, so it is unsuitable for
  the full manifest. No cache was started; implementation will be repaired to
  stream/resume atomically first.
- Implemented bounded-memory streaming cache primitives, atomic per-shard
  state, strict resume identity, final manifest validation, CLI `--resume`, and
  formal input/model hashes. The first focused check exposed only a missing
  test import and two Ruff formatting findings; recorded and corrected them.
- Focused cache tests (9), Ruff, and compileall pass after the repair. A full
  frozen-path audit found 146,110 unique images, 12 findings, zero missing
  image files, and an estimated 41.175 GiB/571-shard FP16 cache footprint.
- Full repository verification passed 69 tests, Ruff, compileall, and diff
  checks. Committed the frozen split documentation plus resume-safe cacher as
  `b691041` and pushed it to the local-only remote.
- Launched the formal full cache on GPU 0 as PID 25880 with batch size 32 and
  shard size 256. The first atomic shard completed successfully; build state is
  `IN_PROGRESS` at 256/146,110 images with no stderr, and GPU 1 remains free.
- Began the parallel Phase-33 code audit while caching. Confirmed that the
  existing generic trainer is only a basic PRTA H0/H1 path and that the formal
  evaluator contains a deterministic input-hash mismatch; trust/figure/VLM
  scripts remain unimplemented gates. None of these surfaces will be allowed to
  reach test data until repaired and frozen.
- Two read-only test inventory commands returned nonzero for guessed/missing
  test filenames and an empty `rg` match. Located the actual core test file;
  neither command changed code or runtime state.
- Added the H2 query-attentive native head and all three registered imbalance
  losses with gradient tests. Seven focused tests pass; corrected the two Ruff
  import-only findings from the first pass.
- At 20 completed cache shards, detected a pre-freeze isolation defect: the
  cache source JSONL carried unused Internal-test labels. Registered the issue
  before protocol freeze and will stop only PID 25880, preserving completed
  atomic shards and logs. No optimizer, prediction, metric, or test-driven
  decision has occurred.
- Stopped only PID 25880 at a clean recorded boundary: 13,312 images / 52
  shards, zero temporary files, zero stderr. Added a formal split-surface
  sealing CLI with exact ID conservation and a minimal outcome-free cache
  schema. Eleven focused tests and preflight pass; corrected the first Ruff
  pass's line/import-only findings.
- Formally generated and independently audited the outcome-separated split
  surfaces. The cache-input manifest contains exactly six approved fields,
  zero forbidden outcome/patient fields, and reproduces the existing cache
  inventory hash, so all 13,312 completed images can be resumed without
  rewriting or changing cache identity.
- Implemented H2, the three imbalance losses, Current-only/Siamese-Diff/TILA
  native model families, PRTA component switches, richer Dev metrics, and the
  evaluation input-hash repair. Full repository gates now pass 78 tests, Ruff,
  compileall, and diff checks. Registered the pre-freeze cache-input issue as
  `DEV-001` in the paper experiment record before resuming.
- Resumed the identical outcome-free cache as PID 30444. A fresh audit found
  17,408/146,110 images in 68 atomic shards, an active process, zero stderr,
  and GPU 1 still idle.
- Added explicit `tail4` versus `last2` adapter placement and a deterministic
  derivation of the 250-row human Silver quality gate. Focused tests and Ruff
  pass after correcting stale guessed test paths.
- Formally wrote
  `formal_program_v1/receipts/human_silver_accuracy_audit.json`: 250 reviewed
  rows, 0.984 overall and for each source, all five label strata present,
  `training_gate_passed=true`, and explicit Luna-assisted/not-blind wording.
  The receipt file SHA-256 is
  `b6c7d4cc1784deef5e45640d0c0151b68504a51f7f70b5b922ef67eba034b2c9`.
- Replaced the stale Rule-only D0-D3 development surface with five nested
  patient-level Luna-primary fractions (10/25/50/75/100%) and marked A507
  `N/A_POLICY_RETIRED`, preserving the user's later label authority.
- Implemented deterministic patient-level scaling, effective class-count
  materialization, a mutable atomic Run Registry, live training progress,
  epoch-level identity-checked resume, and a frozen early-stopping rule.
- Formally prepared the seven-run initial Train/Dev queue: D201-D205 plus
  M301-H1/H2 (M301-H0 reuses D205). All five labels and both sources remain in
  every fraction; Dev stays fixed at 16,666 rows; no test or Gold outcome was
  opened. Queue hash is
  `84086d0ce7fa3b3c465513a51af4c92935998d32e6244cdf186d78a06582f60b`.
- Added a verified contiguous FP16 training store derived shard-by-shard from
  the completed cache. `Block8CacheIndex` will prefer this memory-mapped access
  surface, avoiding random whole-shard reads while preserving identical
  features and inventory order.
- Added a fail-closed two-GPU queue keeper. It waits for the final cache and
  text cache, builds/validates the training store, runs only the seven frozen
  Train/Dev configs, honors D205 before M301-H1/H2, updates a locked registry,
  and enters HOLD on any missing receipt. It has not yet been launched.
- Full repository validation now passes 85 tests, Ruff, compileall, and diff
  checks. The original cache process remains healthy at 42,752/146,110 images
  (167 shards, 29.26%) with empty stderr.
- Launched the committed development keeper as PID 25716. It is healthy and
  explicitly waiting for the cache/training-store gate; zero training runs
  have started.
- Added a deterministic Dev matched-wrong PRIOR dataset matched in descending
  strictness by source/finding/view/interval and always drawn from a different
  patient. Each run evaluates this intervention once on its best Dev-selected
  checkpoint and records True-minus-Wrong Macro-F1 without opening test/Gold.
- Full gates now pass 86 tests. Cache progress is 50,944/146,110 images (199
  shards, 34.87%), while the keeper remains at 0/7 and stderr is empty.
- Implemented the Dev-only stage selector for Head, Loss, Adapter scope, and
  three-seed confirmation. Equivalent WCE/tail4/seed-17 runs are reused; only
  the two alternative losses, one last2 scope, and seeds 29/43 are newly queued.
- Ran one synthetic GPU1 forward/backward engineering step with batch 16 and
  the real frozen BiomedCLIP tail: PASS, logits `[16,5]`, peak allocated 3.718
  GiB and reserved 3.969 GiB. It read no real outcomes and is not a paper run.
- Registered `DEV-002` after one already-frozen Gold row was accidentally
  re-read during a structure check; it had no scientific downstream use.
- Formally derived a six-field, 250-row Gold-candidate cache input from the
  pending pre-human roster and Silver image lineage. It contains zero human
  outcomes, Luna labels, or patient identifiers; manifest hash is
  `58551698e0bf68833c3f44edb26ba8fd7b23173f221e1bf3b4df2589709547aa`.
- Built the independent Gold-candidate cache on GPU1: 500/500 images completed
  while the main cache reached 65,280/146,110 images. No Gold outcome was
  opened by the cache process.
- Gold-candidate cache fully closed with 500 images, 2 verified shards, 11
  finding embeddings, and `PASS_PRTA_CXR_BLOCK8_CACHE`; its process exited with
  empty stderr.
- Implemented the final Dev baseline gate and formal matrix preparation. GO
  requires mean three-seed F1 >=0.52, Seed-17 gain >=3pp over the strongest
  temporal baseline, mean min recall >=0.20, non-worse ODER, positive prior
  gaps, no seed below 0.48, and <=0.10 seed range. HOLD/STOP fail closed.
- A GO gate will generate 9 B401-B403 runs and 18 A501-A506 runs. B404/A500
  alias the identical frozen PRTA three-seed checkpoints; B405/A507 are explicit
  N/A. Full gates now pass 91 tests, Ruff, compileall, and diff checks.
- Added tracked formal protocol, trust, calibration, bootstrap, subgroup, and
  outcome-independent case-selection configs plus a clean-worktree
  protocol-freeze receipt builder. It hashes sealed outcome files without
  parsing them and cannot run before a GO gate/formal matrix.
- Implemented Dev-only scalar temperature fitting, 15-bin ECE, NLL, Brier,
  AURC/risk-at-coverage, and all registered PRIOR/query dataset interventions.
  Main cache progress is 78,592/146,110 (53.79%); keeper remains 0/7 waiting.
- Upgraded prediction artifacts to retain calibrated five-class probabilities,
  patient/sample identity, source, finding, views, interval, query, and PRIOR
  condition. Implemented real trust reporting for calibration, risk coverage,
  interventions, and four subgroup axes.
- Implemented a resumable one-time formal outcome session. It fits all main
  temperatures on Dev before opening, writes an immutable protocol-bound open
  marker, evaluates 30 unique Internal-test checkpoints, main-method Gold, and
  six PRTA interventions, and forbids a changed restart.
- Full gates pass 98 tests. Main cache is 90,368/146,110 images (353 shards,
  61.85%); development remains 0/7 behind the cache/store gate.
- Completed the formal bootstrap/significance surface: four main methods and
  seven PRTA input conditions are evaluated as fully crossed patient-weighted
  blocks across seeds 17/29/43, using the frozen 10,000-replicate protocol,
  empirical two-sided p-values, and a joint Benjamini-Hochberg correction.
- Full repository gates now pass 99 tests, Ruff, compileall, and diff checks.
  The main cache remains healthy at 98,048/146,110 images (383 atomic shards,
  67.11%); both cache and queue-keeper stderr files are empty, and training
  remains 0/7 behind the cache/training-store gate.
- Replaced both remaining paper-output placeholders. V701-V708 now have a
  formal outcome-locked generator with deterministic failure-inclusive case
  selection; X801-X806 have a single exact-64 projector-only Qwen3-VL path with
  resumable training, frozen model auditing, structured Gold evaluation, and a
  pre-frozen omit-without-changing-PRTA gate.
- Hardened protocol freeze to hash the figure implementations, the complete VLM
  implementation, the portable VLM protocol, local model config/index, every
  referenced safetensors shard, and tokenizer assets. Full gates pass 104 tests,
  Ruff, compileall, repository preflight, and diff checks.
- Main cache progress reached 123,392/146,110 images (482 atomic shards,
  84.45%). Cache and queue-keeper stderr remain empty; the initial development
  queue remains 0/7 behind the completed-cache and training-store gate.
- Added an outcome-locked paper finalizer that automatically recomputes Table
  1-8, the Expert Gold appendix, the Dev-selected strongest baseline, and all
  artifact hashes. It emits explicit N/A provenance and records that neither
  test nor Gold selected a model and that Rule labels never entered training.
- Main cache subsequently reached 131,840/146,110 images (515 atomic shards,
  90.23%); training remains 0/7 behind the unchanged cache/store gate.
- Added the formal-program keeper for automatic Loss, Adapter, three-seed,
  Dev-baseline, development-gate, formal-matrix, protocol-freeze, one-time
  outcome, trust, figure, VLM, and table stages. It reuses the existing initial
  queue process, stops outcome-closed on non-GO, and has a resume-safe pre-open
  identity for the formal outcome session.
- Launched the committed formal-program keeper as PID 40932 after safely
  replacing the still-waiting pre-hardening PID 39208. Its state is
  `WAITING_INITIAL_DEVELOPMENT_QUEUE`, it points to the frozen senior-consensus
  Gold JSONL and local hashed Qwen assets, and both stdout/stderr are empty. It
  is waiting on the existing PID 25716 rather than launching a duplicate queue.
- Live continuation audit at 2026-08-03 02:44 CST confirmed all 146,110 images
  are present in 571 atomic Block-8 shards. Cache PID 30444 remains healthy
  during full-shard validation (CPU advanced by 58.8 seconds over 41 seconds,
  working set about 1.14 GiB, stderr empty); the manifest/text-cache gate has
  not yet closed. Development keeper PID 25716 and formal keeper PID 40932 are
  both alive, the frozen initial queue remains 0/7, both GPUs are idle, and H:
  retains 466.9 GiB free for the planned 41.175 GiB contiguous training store.
- Closed Phase 32 without bypassing validation. The main cache now records
  `PASS_PRTA_CXR_BLOCK8_CACHE` for 146,110 images in 571 shards, plus 12 frozen
  finding embeddings and 60 transition prototypes; cache PID 30444 exited with
  empty stderr. The queue keeper then atomically built and bound a 41.175 GiB,
  146,110-row FP16 training store with SHA-256
  `050a4837dbff14f39cab75e9438c3bf7b86776583a06d12b68b1308fca44e540`.
- Phase 33 began automatically at 03:07:53 CST. D201 runs on GPU0 as PID 14772
  and D202 runs on GPU1 as PID 17960; both reached their first 100-batch
  progress marker with about 4.48 GiB GPU memory each. Initial observed losses
  were 1.6215 and 1.7698, respectively. The initial queue is 0/7 complete and
  2/7 running; Internal-test and Gold remain sealed.
- The 03:17 CST heartbeat found Phase 33 healthy and outcome-closed. D201 has
  completed all 581 training batches of epoch 0 and is evaluating the fixed
  Dev set; D202 has completed 1,100/1,441 training batches of epoch 0. Both
  child PIDs and both keepers remain alive, GPU memory is about 4.48 GiB per
  device, temperatures are 71/77 C, both keeper stderr logs are empty, and H:
  has 425.7 GiB free. No checkpoint or run receipt is expected until the first
  Dev pass closes; the seven-run initial queue remains 0 complete, 2 running,
  and 5 planned. Total Phase-33 duration remains multi-hour and is bounded by
  the frozen 6-epoch minimum / 20-epoch maximum early-stopping protocol.
- The 03:35 CST heartbeat confirmed continued healthy Phase-33 training. D201
  is at epoch 3, batch 500/581 with best fixed-Dev Macro-F1 0.3839 at epoch 2;
  D202 is at epoch 2, batch 200/1,441 with best fixed-Dev Macro-F1 0.4034 at
  epoch 1. Each run has an atomic `best.pt`; no final receipt exists yet. Both
  GPUs are active at about 4.48 GiB, 78/76 C, all four expected PIDs are alive,
  keeper stderr remains empty, and H: has 424.6 GiB free. The initial queue is
  still 0 complete, 2 running, and 5 planned; protected outcome-open/protocol-
  freeze markers remain absent, so Internal-test and Gold are still sealed.
- The 03:55 CST heartbeat found D201 at the end of epoch 6 (581/581 batches)
  entering fixed-Dev evaluation, with best Dev Macro-F1 0.4045 at epoch 4.
  D202 is at the end of epoch 3 (1,441/1,441 batches), with best Dev Macro-F1
  0.4430 at epoch 2. Both atomic best checkpoints remain present; no final run
  receipt exists because neither frozen early-stopping decision has closed.
  GPUs remain healthy at about 4.48 GiB and 75/73 C, both training children and
  both keepers are alive, stderr logs are empty, and H: has 424.6 GiB free.
  The queue remains 0 complete, 2 running, and 5 planned, with no protected
  outcome-open or protocol-freeze marker.
- D201 formally closed at 04:14:57 CST with `PASS_TRAINING_FINISHED`, frozen
  early stopping after epoch 8, and best fixed-Dev Macro-F1 0.4045 at epoch 4.
  Its receipt confirms Internal-test and protected outcomes were not opened.
  The original Windows keeper did not reconcile the exited child because
  `os.kill(pid, 0)` is not a reliable exit-state probe on this host. Replaced
  it with native `GetExitCodeProcess` detection, added a live/dead child
  regression test, and passed the full 109-test suite, Ruff, compileall, and
  diff checks in commit `55fd22c`.
- Restarted only the queue keeper, preserving D202 PID 17960 and all artifacts.
  The first restart failed closed before queue access because the formal
  authorization environment variable was absent; the authorized retry is
  healthy as PID 10548 with empty stderr. It reconciled D201 and launched D203
  on GPU0 as PID 6780 while D202 continues on GPU1. The queue is now 1/7
  complete, 2/7 running, and 4/7 planned; no protected outcome was opened.
- Because the long-lived formal-program keeper had imported the same pre-fix
  Windows liveness function, safely replaced it only while its durable state
  was `WAITING_INITIAL_DEVELOPMENT_QUEUE`. The patched keeper is PID 37228,
  retains that exact waiting state, sees the queue as 1 complete / D202+D203
  running / 4 planned, and has empty stdout/stderr. Queue keeper PID 10548 and
  both training children remained alive through the restart.
- The 04:35 CST heartbeat confirmed the repaired queue remains healthy. D202
  completed all 1,441 training batches of epoch 6 and entered fixed-Dev
  evaluation; its best Dev Macro-F1 remains 0.4430 at epoch 2, so the frozen
  patience rule will decide closeout after this Dev pass. D203 completed all
  2,868 training batches of epoch 0 and entered its first fixed-Dev evaluation.
  Both GPUs are active at about 4.48 GiB and 75/75 C; both training children,
  queue keeper PID 10548, and formal keeper PID 37228 are alive with zero-byte
  stderr logs. The queue is 1 complete, 2 running, and 4 planned; H: has
  424.6 GiB free, and no outcome-open/protocol-freeze marker exists.
- D202 formally closed at 04:37:03 CST with `PASS_TRAINING_FINISHED`, frozen
  early stopping after epoch 6, and best fixed-Dev Macro-F1 0.4430 at epoch 2;
  its receipt and registry row confirm protected outcomes remained sealed. The
  repaired queue reconciled it immediately and launched D204 on GPU1 as PID
  24720. At the 04:55 CST heartbeat, D203 had completed epoch 1 with best Dev
  Macro-F1 0.4368 and was in fixed-Dev evaluation, while D204 had completed
  3,300/4,293 batches of epoch 0. Queue status is 2/7 complete, D203+D204
  running, and 3 planned. Both keepers and training children are alive, all
  relevant stderr logs are empty, GPU memory is about 4.48 GiB per device,
  temperatures are 56/74 C, H: has 424.0 GiB free, and no protected marker
  exists.
- The 05:15 CST heartbeat found D203 at epoch 3, batch 400/2,868 with best
  fixed-Dev Macro-F1 0.4392 at epoch 2. D204 is at epoch 1, batch 2,000/4,293
  with best fixed-Dev Macro-F1 0.4135 after epoch 0. Both atomic best
  checkpoints exist; neither run has reached its frozen early-stopping close.
  Queue state remains 2/7 complete, D203+D204 running, and 3 planned. Both
  training children and the patched keepers are alive, all relevant stderr
  logs remain empty, GPU memory is about 4.48 GiB per device at 78/76 C, H:
  has 423.4 GiB free, and protected outcome/protocol-freeze markers are absent.
- The 05:35 CST heartbeat found D203 at epoch 4, batch 800/2,868. Its best
  fixed-Dev Macro-F1 remains 0.4392 at epoch 2; the latest 0.4395 change is
  below the frozen 0.001 improvement threshold and therefore correctly did not
  reset patience. D204 is at epoch 2, batch 700/4,293 with best Dev Macro-F1
  0.4135 at epoch 0. Queue state remains 2/7 complete, D203+D204 running, and
  3 planned. Both children and keepers are alive, stderr logs are empty, GPU
  memory is about 4.48 GiB at 78/75 C, H: has 423.4 GiB free, and no protected
  marker exists.
- The 05:55 CST heartbeat found D203 at epoch 5, batch 1,500/2,868 with best
  fixed-Dev Macro-F1 0.4392 at epoch 2 and latest completed-epoch Macro-F1
  0.4394. D204 completed all 4,293 training batches of epoch 2 and entered its
  fixed-Dev evaluation; its best Dev Macro-F1 remains 0.4135 at epoch 0.
  Queue state remains 2/7 complete, D203+D204 running, and 3 planned. Both
  children and patched keepers are alive, current stderr logs are empty, GPU
  memory is about 4.48 GiB per device at 75/74 C, H: has 423.4 GiB free, and
  no protected outcome/protocol-freeze marker exists.
- The 06:15 CST heartbeat found D203 at epoch 6, batch 1,700/2,868; its best
  fixed-Dev Macro-F1 remains 0.4392 at epoch 2 and its latest completed epoch
  scored 0.4386. At its present rate it should reach the next frozen Dev and
  early-stopping decision in roughly 20-30 minutes. D204 is at epoch 3, batch
  3,100/4,293 and improved its best Dev Macro-F1 to 0.4214 at epoch 2. Queue
  state remains 2/7 complete, D203+D204 running, and 3 planned. Both training
  children and keepers are alive, checkpoints are current, stderr logs are
  empty, GPU memory is about 4.48 GiB per device at 78/75 C, H: has 423.4 GiB
  free, registry state is consistent, and no protected outcome/protocol-freeze
  marker exists.
- D203 formally closed at 06:27:35 CST with `PASS_TRAINING_FINISHED`, frozen
  early stopping after 7 completed epochs, and best fixed-Dev Macro-F1 0.4392
  at epoch 2. Its receipt hash begins `c0a82ddd00d5f9a7` and confirms protected
  outcomes were not opened. The queue reconciled the run and immediately
  launched full-data D205 on GPU0 as PID 14248. At the 06:35 CST heartbeat,
  D205 was at epoch 0, batch 1,400/5,692 and should reach its first Dev pass in
  roughly 25-35 minutes. D204 was at epoch 4, batch 1,800/4,293 after improving
  best Dev Macro-F1 to 0.4229 at epoch 3. Queue state is now 3/7 complete,
  D204+D205 running, and two M301 head variants planned. Both children and
  keepers are alive, checkpoints and registry rows are current, active stderr
  logs are empty, GPU memory is about 4.48 GiB per device at 78/76 C, H: has
  423.4 GiB free, and no protected outcome/protocol-freeze marker exists.
- The 06:55 CST heartbeat found D204 through all 4,293 batches of epoch 4 and
  in its fixed-Dev evaluation, with best Dev Macro-F1 0.4229 at epoch 3. D205
  reached batch 5,400/5,692 of its first full-data epoch. Both should emit
  their next fixed-Dev result within roughly 5-15 minutes. Queue state remains
  3/7 complete, D204+D205 running, and two M301 variants planned. Both training
  children and keepers are alive, artifact timestamps and registry rows are
  current, active stderr logs are empty, GPU memory is about 4.48 GiB per
  device at 75/57 C, H: has 423.4 GiB free, and protected outcome/protocol-
  freeze markers remain absent.
- The 07:15 CST audit found that the queue keeper had exited at 07:09:26 after
  a transient Windows WinError 5 while atomically replacing only
  `scheduler_state.json`; D204 and D205 continued training normally, and the
  queue manifest was not damaged. Added bounded PermissionError retries to
  mutable JSON atomic replacement, with 110 tests, Ruff, and compileall all
  passing. After commit `8a6eef9`, both operational keepers were restarted
  against the unchanged queue as PIDs 27740 and 38596; their stderr logs are
  empty and both report 3/7 complete with D204+D205 running. No training child,
  data identity, seed, method, or budget changed. At inspection D204 was at
  epoch 5, batch 3,400/4,293 with best Dev Macro-F1 0.4331 at epoch 4; D205 was
  at epoch 1, batch 3,100/5,692 with first-pass Dev Macro-F1 0.4112. Protected
  outcomes remain sealed.
- The 07:35 CST heartbeat confirmed the recovered keepers remain healthy and
  their bounded atomic-state retry has not recurred. D204 is at epoch 6, batch
  2,100/4,293; its latest Dev Macro-F1 0.4333 is below the frozen 0.001
  improvement threshold over best 0.4331, so the best checkpoint correctly
  remains epoch 4. D205 is at epoch 2, batch 500/5,692 after improving best Dev
  Macro-F1 to 0.4430 at epoch 1. D204 should reach its next Dev decision in
  roughly 15-25 minutes and D205 in roughly 30-40 minutes. Queue state remains
  3/7 complete with both training runs active and two M301 variants planned.
  All four processes are alive, current stderr logs are empty, checkpoints and
  registry rows are consistent, GPU memory is about 4.48 GiB per device at
  77/76 C, H: has 422.8 GiB free, and protected markers remain absent.
- The 07:55 CST heartbeat found D204 at epoch 7, batch 700/4,293. Its latest
  completed Dev Macro-F1 was 0.4173 at epoch 6, while the frozen best remains
  0.4331 at epoch 4. D205 reached epoch 2, batch 4,600/5,692 with best Dev
  Macro-F1 0.4430 at epoch 1 and should enter its next fixed-Dev pass in about
  10-20 minutes. Queue state remains 3/7 complete with both runs active and
  two M301 variants planned. Both children and the recovered keepers are
  alive, active stderr logs remain empty, checkpoint and registry identities
  are consistent, GPU memory is about 4.48 GiB per device at 78/71 C, H: has
  422.8 GiB free, and protected outcome/protocol-freeze markers are absent.
- The 08:15 CST heartbeat found D204 through all 4,293 batches of epoch 7 and
  entering its fixed-Dev evaluation, so its next frozen early-stopping decision
  is expected within roughly 5-15 minutes. Best Dev Macro-F1 remains 0.4331 at
  epoch 4. D205 is at epoch 3, batch 2,200/5,692; its epoch-2 Dev Macro-F1 was
  0.4406 and the best remains 0.4430 at epoch 1, with the next Dev pass expected
  in roughly 20-30 minutes. Queue state remains 3/7 complete, D204+D205 running,
  and two M301 variants planned. Both children and keepers are alive, active
  stderr logs are empty, checkpoint and registry artifacts are current, GPU
  memory is about 4.48 GiB per device at 77/72 C, H: has 422.8 GiB free, and
  protected outcome/protocol-freeze markers remain absent.
- The 08:35 CST heartbeat found D204 at epoch 8, batch 3,200/4,293 after its
  epoch-7 Dev Macro-F1 improved to 0.4377, exceeding the frozen minimum-delta
  rule and correctly advancing the best checkpoint from epoch 4 to epoch 7.
  Its next Dev pass is expected in roughly 10-20 minutes. D205 completed all
  5,692 batches of epoch 3 and entered fixed-Dev evaluation; best Dev Macro-F1
  remains 0.4430 at epoch 1, with the next result expected in roughly 5-15
  minutes. Queue state remains 3/7 complete with two M301 variants planned.
  Both children and keepers are alive, active stderr logs are empty, artifact
  and registry identities are current, GPU memory is about 4.48 GiB per device
  at 68/76 C, H: has 422.8 GiB free, and protected markers remain absent.
- The 08:55 CST heartbeat found D204 at epoch 9, batch 1,900/4,293; its
  epoch-8 Dev Macro-F1 was 0.4306 and the frozen best remains 0.4377 at epoch
  7. D205 is at epoch 4, batch 3,700/5,692 after epoch-3 Dev Macro-F1 0.4257;
  its frozen best remains 0.4430 at epoch 1. Their next Dev passes are expected
  in roughly 10-25 minutes. Queue state remains 3/7 complete with two M301
  variants planned. Both training children and keepers are alive, stderr logs
  are empty, checkpoints and registry rows are current, GPU memory is about
  4.48 GiB per device at 78/76 C, H: has 422.8 GiB free, and no protected
  outcome/protocol-freeze marker exists.
- The 09:15 CST heartbeat found D204 at epoch 10, batch 600/4,293 after
  epoch-9 Dev Macro-F1 0.4267; its frozen best remains 0.4377 at epoch 7.
  D205 is at epoch 5, batch 1,300/5,692 after epoch-4 Dev Macro-F1 0.4368;
  its frozen best remains 0.4430 at epoch 1. The next Dev/early-stopping
  decisions are expected in roughly 20-35 minutes. Queue state remains 3/7
  complete with D204+D205 running and two M301 variants planned. All processes
  remain alive, active stderr logs are empty, checkpoints and registry rows
  are consistent, GPU memory is about 4.48 GiB per device at 78/75 C, H: has
  422.8 GiB free, and protected outcome/protocol-freeze markers are absent.
- The 09:35 CST heartbeat found D204 through all 4,293 batches of epoch 10 and
  entering fixed-Dev evaluation, with best Dev Macro-F1 0.4377 at epoch 7.
  D205 reached epoch 5, batch 5,400/5,692 with best Dev Macro-F1 0.4430 at
  epoch 1. Both should emit their next frozen Dev/early-stopping decisions in
  roughly 5-15 minutes. Queue state remains 3/7 complete with two M301
  variants planned. Both training children and keepers are alive, active
  stderr logs are empty, checkpoints and registry rows are current, GPU memory
  is about 4.48 GiB per device at 77/45 C, H: has 422.8 GiB free, and no
  protected outcome/protocol-freeze marker exists.
- D205 formally closed at 09:44:08 CST with `PASS_TRAINING_FINISHED`, frozen
  early stopping after 6 epochs, and best fixed-Dev Macro-F1 0.4430 at epoch
  1. Its receipt hash begins `d0372f4e20d0caca` and confirms protected
  outcomes remained sealed. The queue immediately launched M301-H1 on GPU0 as
  PID 39688. At the 09:55 CST heartbeat, M301-H1 was at epoch 0, batch
  2,100/5,692 and should reach its first fixed-Dev pass in roughly 20-30
  minutes. D204 was at epoch 11, batch 2,700/4,293 after epoch-10 Dev Macro-F1
  0.4215, with best 0.4377 at epoch 7 and its next Dev decision expected in
  about 10-20 minutes. Queue state is 4/7 complete, D204+M301-H1 running, and
  M301-H2 planned. Both children and keepers are alive, active stderr logs are
  empty, checkpoints and registry rows are current, GPU memory is about
  4.55/4.48 GiB at 78/75 C, H: has 422.8 GiB free, and protected markers are
  absent.
- D204 formally closed at 10:11:13 CST with `PASS_TRAINING_FINISHED`, frozen
  early stopping after 12 epochs, and best fixed-Dev Macro-F1 0.4377 at epoch
  7. Its receipt hash begins `f89e4c9f66596631` and confirms protected
  outcomes remained sealed. The queue immediately launched M301-H2 on GPU1 as
  PID 37076. At the 10:15 CST heartbeat, M301-H1 had completed all 5,692
  batches of epoch 0 and entered its first fixed-Dev evaluation, while M301-H2
  was at epoch 0, batch 600/5,692 and should reach its first Dev pass in roughly
  30-40 minutes. Queue state is now 5/7 complete with both head variants
  running. Both children and keepers are alive, active stderr logs are empty,
  artifact and registry identities are current, GPU memory is about 4.55/4.58
  GiB at 76/75 C, H: has 422.8 GiB free, and protected markers remain absent.
- The 10:35 CST heartbeat found M301-H1 at epoch 1, batch 3,400/5,692 after a
  first fixed-Dev Macro-F1 of 0.4054 at epoch 0. M301-H2 reached epoch 0, batch
  4,300/5,692 and should enter its first fixed-Dev pass in roughly 10-20
  minutes. Queue state remains 5/7 complete with both head variants running.
  Both children and keepers are alive, M301-H1 has a current best checkpoint,
  stderr logs are empty, registry identities are consistent, GPU memory is
  about 4.55/4.58 GiB at 75/74 C, H: has 422.2 GiB free, and protected
  outcome/protocol-freeze markers remain absent.
- The 10:55 CST heartbeat found M301-H1 at epoch 2, batch 1,000/5,692 after
  improving best fixed-Dev Macro-F1 to 0.4295 at epoch 1. M301-H2 is at epoch
  1, batch 900/5,692 after a first fixed-Dev Macro-F1 of 0.4002 at epoch 0.
  Both next Dev passes are expected in roughly 25-35 minutes. Queue state
  remains 5/7 complete with both head variants running. Both children and
  keepers are alive, atomic checkpoints exist for both runs, stderr logs are
  empty, registry identities are consistent, GPU memory is about 4.55/4.58 GiB
  at 78/74 C, H: has 421.5 GiB free, and protected outcome/protocol-freeze
  markers remain absent.
- The 11:15 CST heartbeat found M301-H1 at epoch 2, batch 4,600/5,692 with
  best fixed-Dev Macro-F1 0.4295 at epoch 1, and M301-H2 at epoch 1, batch
  4,400/5,692 with best Dev Macro-F1 0.4002 at epoch 0. Both should enter their
  next fixed-Dev passes in roughly 10-20 minutes. Queue state remains 5/7
  complete with both head variants running. Both children and keepers are
  alive, checkpoints and registry rows are current, stderr logs are empty, GPU
  memory is about 4.55/4.58 GiB at 75/68 C, H: has 421.5 GiB free, and no
  protected outcome/protocol-freeze marker exists.
- The 11:35 CST heartbeat found both head variants improved on fixed Dev.
  M301-H1 is at epoch 3, batch 1,200/5,692 with best Macro-F1 0.4485 at epoch
  2, while M301-H2 is at epoch 2, batch 1,100/5,692 with best Macro-F1 0.4430
  at epoch 1. Their next Dev passes are expected in roughly 25-35 minutes.
  Queue state remains 5/7 complete with both runs active. Both children and
  keepers are alive, atomic best/last checkpoints are current, stderr logs are
  empty, registry identities are consistent, GPU memory is about 4.55/4.58 GiB
  at 78/74 C, H: has 421.5 GiB free, and protected outcome/protocol-freeze
  markers remain absent.
- The 11:55 CST heartbeat found M301-H1 at epoch 3, batch 5,100/5,692 with
  best fixed-Dev Macro-F1 0.4485 at epoch 2, and M301-H2 at epoch 2, batch
  4,700/5,692 with best Macro-F1 0.4430 at epoch 1. Both should enter their
  next Dev passes in roughly 5-15 minutes. Queue state remains 5/7 complete
  with both head variants active. Both children and keepers are alive, stderr
  logs are empty, checkpoints and registry identities are current, GPU memory
  is about 4.55/4.58 GiB at 77/74 C, H: has 421.5 GiB free, and no protected
  outcome/protocol-freeze marker exists.
- The 12:15 CST heartbeat found M301-H1 at epoch 4, batch 1,700/5,692 after
  epoch-3 Dev Macro-F1 0.4264, with best 0.4485 at epoch 2. M301-H2 is at
  epoch 3, batch 1,600/5,692 after epoch-2 Dev Macro-F1 0.4383, with best
  0.4430 at epoch 1. Their next Dev passes are expected in roughly 20-30
  minutes. Queue state remains 5/7 complete with both head variants active.
  Both children and keepers are alive, checkpoints and registry rows are
  current, stderr logs are empty, GPU memory is about 4.55/4.58 GiB at 78/76
  C, H: has 421.5 GiB free, and protected markers remain absent.
- The 12:35 CST heartbeat found M301-H1 through all 5,692 batches of epoch 4
  and entering fixed-Dev evaluation, with best Macro-F1 0.4485 at epoch 2.
  M301-H2 reached epoch 3, batch 5,200/5,692 with best Macro-F1 0.4430 at
  epoch 1. Both next Dev/early-stopping decisions are expected within roughly
  5-15 minutes. Queue state remains 5/7 complete with both variants active.
  Both children and keepers are alive, stderr logs are empty, checkpoint and
  registry identities are current, GPU memory is about 4.55/4.58 GiB at 57/73
  C, H: has 421.5 GiB free, and protected markers remain absent.
- The 12:55 CST heartbeat found M301-H1 at epoch 5, batch 2,400/5,692 after
  epoch-4 Dev Macro-F1 0.4330, with best 0.4485 at epoch 2. M301-H2 is at
  epoch 4, batch 2,200/5,692 after epoch-3 Dev Macro-F1 0.4208, with best
  0.4430 at epoch 1. Their next frozen Dev/early-stopping decisions are
  expected in roughly 20-30 minutes. Queue state remains 5/7 complete with
  both variants running. Both children and keepers are alive, last/best
  checkpoints and registry rows are current, stderr logs are empty, GPU memory
  is about 4.55/4.58 GiB at 77/75 C, H: has 421.5 GiB free, and protected
  markers remain absent.
- The 13:15 CST heartbeat found both M301 variants through their current full
  epochs and entering fixed-Dev evaluation: H1 completed all 5,692 batches of
  epoch 5 with best Macro-F1 0.4485 at epoch 2, while H2 completed epoch 4
  with best 0.4430 at epoch 1. Their next frozen Dev/early-stopping decisions
  are expected within roughly 5-15 minutes. Queue state remains 5/7 complete.
  Both children and keepers are alive, stderr logs are empty, checkpoint and
  registry identities are current, GPU memory is about 4.55/4.58 GiB at 73/73
  C, H: has 421.5 GiB free, and protected markers remain absent.
- The 13:35 CST heartbeat found M301-H1 at epoch 6, batch 3,700/5,692 after
  epoch-5 Dev Macro-F1 0.4349, with best 0.4485 at epoch 2. M301-H2 is at
  epoch 5, batch 3,000/5,692 after epoch-4 Dev Macro-F1 0.4301, with best
  0.4430 at epoch 1. Their next frozen Dev/early-stopping decisions are
  expected in roughly 15-25 minutes. Queue state remains 5/7 complete with
  both variants active. Both children and keepers are alive, last/best
  checkpoints and registry rows are current, stderr logs are empty, GPU memory
  is about 4.55/4.58 GiB at 79/76 C, H: has 421.5 GiB free, and protected
  markers remain absent.
- The 13:55 CST heartbeat found both M301 variants through their current full
  epochs and finalizing fixed-Dev decisions. H1 completed epoch 6 with Dev
  Macro-F1 0.4243 and best 0.4485 at epoch 2; H2 completed epoch 5 with Dev
  Macro-F1 0.4319 and best 0.4430 at epoch 1. Both processes remain active
  while writing/reconciling the decision, with the queue transition expected
  in roughly 5-10 minutes. Queue state remains 5/7 complete. Children and
  keepers are alive, stderr logs are empty, checkpoints and registry identities
  remain valid, GPU memory is about 4.55/4.58 GiB, H: has 421.5 GiB free, and
  protected markers remain absent.
- M301-H1 and M301-H2 formally closed at 13:56:41 and 13:59:38 CST with
  `PASS_TRAINING_FINISHED`, frozen early stopping after 7 and 6 epochs, and
  best Dev Macro-F1 0.4485 and 0.4430. Receipt hashes begin
  `a1a0b255932f7061` and `37fdb9c7d1550299`; both confirm protected outcomes
  remained sealed. The frozen head-selection rule retained D205 because no
  candidate exceeded its 0.4430 baseline by the required 0.015, despite H1's
  higher raw 0.4485. The formal keeper then prepared and launched loss variants
  M302-BS/M302-CBF on GPUs 0/1 as PIDs 39620/26108. At the 14:15 CST heartbeat
  they were at epoch 0 batches 2,700 and 2,500 of 5,692, with first Dev passes
  expected in roughly 20-30 minutes. Program status is `RUNNING_LOSS_STAGE`;
  both children and the keeper are alive, stderr logs are empty, registry and
  selection receipts are current, H: has 421.5 GiB free, and protected markers
  remain absent.
- The 14:35 CST heartbeat found both M302 loss variants through all 5,692
  batches of epoch 0 and entering their first fixed-Dev evaluations. BS and
  CBF remain active as PIDs 39620/26108 on GPUs 0/1, with first Dev results
  expected within roughly 5-15 minutes. The loss queue is 0/2 complete and the
  program remains `RUNNING_LOSS_STAGE`. Both children and the keeper are alive,
  active stderr logs are empty, queue/registry identities are current, GPU
  memory is about 4.48 GiB per device, H: has 421.5 GiB free, and protected
  outcome/protocol-freeze markers remain absent.
- The 14:55 CST heartbeat found M302-BS at epoch 1, batch 3,700/5,692 after a
  first fixed-Dev Macro-F1 of 0.4121, and M302-CBF at epoch 1, batch
  3,400/5,692 after a first Dev Macro-F1 of 0.4082. Their next Dev passes are
  expected in roughly 15-25 minutes. The loss queue remains 0/2 complete and
  the program remains `RUNNING_LOSS_STAGE`. Both children and the keeper are
  alive, atomic best/last checkpoints exist, active stderr logs are empty,
  registry identities are current, GPU memory is about 4.48 GiB per device at
  80/79 C, H: has 420.4 GiB free, and protected markers remain absent.
- The 15:20 CST heartbeat found both M302 variants safely past their second
  fixed-Dev evaluations and training epoch 2: M302-BS is at batch 1,300/5,692
  with best Dev Macro-F1 0.4324 (epoch 1), while M302-CBF is at batch
  1,200/5,692 with best Dev Macro-F1 0.4185 (epoch 1). Their next Dev passes
  are expected in roughly 25-35 minutes. The loss queue remains 0/2 complete
  and the program remains `RUNNING_LOSS_STAGE`; both children and the keeper
  are alive, atomic best/last checkpoints are current, all active stderr logs
  are empty, registry identities remain unchanged, GPU memory is about 4.48
  GiB per device at 77/77 C, H: has 420.4 GiB free, and protected outcome and
  protocol-freeze markers remain absent.
- The 15:38 CST heartbeat found M302-BS at epoch 2, batch 4,800/5,692 with
  best fixed-Dev Macro-F1 0.4324, and M302-CBF at epoch 2, batch 4,300/5,692
  with best fixed-Dev Macro-F1 0.4185. Their next Dev evaluations are expected
  in roughly 5-15 minutes. The loss queue remains 0/2 complete and the program
  remains `RUNNING_LOSS_STAGE`; both children and the keeper are alive, atomic
  best/last checkpoints remain present, all active stderr logs are empty,
  registry identities are current, GPU memory is about 4.48 GiB per device at
  78/75 C, H: has 420.4 GiB free, and no protected-outcome or protocol-freeze
  marker exists.
- The 15:58 CST heartbeat found both loss variants safely past their epoch-2
  fixed-Dev evaluations and training epoch 3. M302-BS is at batch 1,500/5,692
  with best Dev Macro-F1 0.4324 (epoch 1); M302-CBF is at batch 900/5,692 and
  improved its best Dev Macro-F1 to 0.4208 (epoch 2). Their next Dev passes are
  expected in roughly 20-30 minutes. The queue remains 0/2 complete and the
  program remains `RUNNING_LOSS_STAGE`; both children and the keeper are
  alive, atomic best/last checkpoints are current, all active logs remain
  empty, registry identities are unchanged, GPU memory is about 4.48 GiB per
  device at 75/68 C, H: has 420.2 GiB free, and protected outcome and
  protocol-freeze markers remain absent.
- The 16:18 CST heartbeat found M302-BS at epoch 3, batch 5,000/5,692 with
  best fixed-Dev Macro-F1 0.4324, and M302-CBF at epoch 3, batch 4,200/5,692
  with best fixed-Dev Macro-F1 0.4208. Their next fixed-Dev evaluations are
  expected in roughly 5-15 minutes. The loss queue remains 0/2 complete and
  the program remains `RUNNING_LOSS_STAGE`; both children and the keeper are
  alive, atomic best/last checkpoints remain present, all active logs are
  empty, registry identities remain current, GPU memory is about 4.48 GiB per
  device at 77/76 C, H: has 418.8 GiB free, and no protected-outcome or
  protocol-freeze marker exists.
- The 16:38 CST heartbeat found both variants safely past their epoch-3
  fixed-Dev evaluations and training epoch 4. M302-BS is at batch 2,200/5,692
  and improved its best Dev Macro-F1 to 0.4349; M302-CBF is at batch
  1,100/5,692 and improved sharply to 0.4536. No selection is made while the
  frozen runs remain active; their next Dev passes are expected in roughly
  20-30 minutes. The queue remains 0/2 complete and the program remains
  `RUNNING_LOSS_STAGE`; both children and the keeper are alive, atomic
  checkpoints are current, all active logs are empty, registry identities are
  unchanged, GPU memory is about 4.48 GiB per device, H: has 417.0 GiB free,
  and protected-outcome and protocol-freeze markers remain absent.
- The 16:58 CST heartbeat found M302-BS through all 5,692 batches of epoch 4
  and entering its fixed-Dev evaluation, while M302-CBF is at epoch 4, batch
  4,500/5,692. Their current best Dev Macro-F1 values remain 0.4349 and 0.4536;
  the next evaluation results are expected in roughly 5-15 minutes. The loss
  queue remains 0/2 complete and the program remains `RUNNING_LOSS_STAGE`;
  both children and the keeper are alive, atomic checkpoints remain present,
  all active logs are empty, registry identities are current, GPU memory is
  about 4.48 GiB per device at 78/75 C, H: has 416.2 GiB free, and no
  protected-outcome or protocol-freeze marker exists.
- The 17:18 CST heartbeat found both variants safely past their epoch-4
  fixed-Dev evaluations and training epoch 5. M302-BS is at batch 3,100/5,692
  and M302-CBF at batch 1,600/5,692; their best Dev Macro-F1 values remain
  0.4349 and 0.4536, respectively. Their next fixed-Dev evaluations are
  expected in roughly 15-25 minutes. The loss queue remains 0/2 complete and
  the program remains `RUNNING_LOSS_STAGE`; both children and the keeper are
  alive, atomic checkpoints are current, all active logs are empty, registry
  identities are unchanged, GPU memory is about 4.48 GiB per device at 78/76
  C, H: has 416.1 GiB free, and protected-outcome and protocol-freeze markers
  remain absent.
- The 17:38 CST heartbeat found M302-BS safely past its epoch-5 fixed-Dev
  evaluation and at epoch 6, batch 600/5,692, while M302-CBF is at epoch 5,
  batch 5,200/5,692 and approaching its evaluation. Their best Dev Macro-F1
  values remain 0.4349 and 0.4536; the next CBF result is expected in roughly
  5-10 minutes. The loss queue remains 0/2 complete and the program remains
  `RUNNING_LOSS_STAGE`; both children and the keeper are alive, atomic
  checkpoints remain present, all active logs are empty, registry identities
  are current, GPU memory is about 4.48 GiB per device at 78/75 C, H: has
  416.1 GiB free, and no protected-outcome or protocol-freeze marker exists.
- The 17:58 CST heartbeat found both loss variants training epoch 6: M302-BS
  is at batch 4,500/5,692 and M302-CBF at batch 2,400/5,692. Their best
  fixed-Dev Macro-F1 values remain 0.4349 and 0.4536, respectively; the next
  evaluations are expected in roughly 10-20 minutes. The queue remains 0/2
  complete and the program remains `RUNNING_LOSS_STAGE`; both children and
  the keeper are alive, atomic checkpoints are current, all active logs are
  empty, registry identities remain unchanged, GPU memory is about 4.48 GiB
  per device at 78/76 C, H: has 416.1 GiB free, and protected-outcome and
  protocol-freeze markers remain absent.
- The 18:18 CST heartbeat found M302-BS safely past its epoch-6 fixed-Dev
  evaluation and at epoch 7, batch 2,000/5,692, while M302-CBF has completed
  all 5,692 epoch-6 batches and is entering fixed-Dev evaluation. Their best
  Dev Macro-F1 values remain 0.4349 and 0.4536; the next CBF result is expected
  in roughly 5-10 minutes. The queue remains 0/2 complete and the program
  remains `RUNNING_LOSS_STAGE`; both children and the keeper are alive,
  atomic checkpoints remain present, all active logs are empty, registry
  identities are current, GPU memory is about 4.48 GiB per device, H: has
  416.1 GiB free, and protected-outcome and protocol-freeze markers remain
  absent.
- The 18:38 CST heartbeat found M302-BS through all 5,692 epoch-7 batches and
  entering fixed-Dev evaluation, while M302-CBF is at epoch 7, batch
  3,000/5,692. Their best Dev Macro-F1 values remain 0.4349 and 0.4536; the
  next BS result is expected in roughly 5-10 minutes. The loss queue remains
  0/2 complete and the program remains `RUNNING_LOSS_STAGE`; both children
  and the keeper are alive, atomic checkpoints remain present, all active
  logs are empty, registry identities are current, GPU memory is about 4.48
  GiB per device at 77/75 C, H: has 416.1 GiB free, and no protected-outcome
  or protocol-freeze marker exists.
- The 18:58 CST heartbeat recorded M302-BS as
  `PASS_TRAINING_FINISHED` after frozen early stopping at eight completed
  epochs, with best fixed-Dev Macro-F1 0.4349 at epoch 3 and a complete
  Train/Dev-only receipt (`protected_outcomes_opened=false`). Its best-model
  SHA-256 is `7041302d...403309d`. M302-CBF has completed all 5,692 epoch-7
  batches and is in fixed-Dev evaluation with current best 0.4536; its terminal
  result is expected in roughly 5-10 minutes. The loss queue is 1/2 complete,
  GPU 0 is released, GPU 1 and the keeper remain healthy, all stderr logs are
  empty, the registry now contains the BS terminal record, H: has 416.1 GiB
  free, and protected-outcome and protocol-freeze markers remain absent.
- The 19:18 CST heartbeat confirmed the loss stage terminally complete at 2/2.
  M302-CBF passed frozen early stopping with best fixed-Dev Macro-F1 0.4536 at
  epoch 3, best-model SHA-256 `b33b88df...c49605a`, complete receipt SHA-256
  `b857c80a...88ae353`, and no protected outcomes opened. The frozen selector
  qualified and chose M302-CBF over D205 without worsening the prior-control
  gap, then prepared and launched the single adapter run `M303-last2` on GPU 0.
  At audit time it was healthy at epoch 0, batch 4,000/5,692, with its first
  fixed-Dev result expected in roughly 10-20 minutes. Program status is now
  `RUNNING_ADAPTER_STAGE`; the keeper and adapter child are alive, stderr is
  empty, H: has 416.1 GiB free, and protected-outcome/protocol-freeze markers
  remain absent.
- The 19:38 CST heartbeat found `M303-last2` safely past its first fixed-Dev
  evaluation and training epoch 1 at batch 1,400/5,692. Its initial Dev
  Macro-F1 is 0.4005; the frozen run continues without tuning, with the next
  evaluation expected in roughly 25-35 minutes. Program status remains
  `RUNNING_ADAPTER_STAGE`; the adapter child and keeper are alive, atomic
  best/last checkpoints exist, stderr logs are empty, registry identity and
  config hashes are unchanged, GPU 0 uses about 2.94 GiB at 72 C, GPU 1 is
  idle, H: has 415.0 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 19:58 CST heartbeat found `M303-last2` through all 5,692 epoch-1 batches
  and entering its second fixed-Dev evaluation. Its current best Dev Macro-F1
  remains 0.4005; the next result is expected in roughly 5-10 minutes. Program
  status remains `RUNNING_ADAPTER_STAGE`; the adapter child and keeper are
  alive, atomic best/last checkpoints remain present, stderr logs are empty,
  registry and config identities are unchanged, GPU 0 uses about 2.94 GiB at
  71 C, GPU 1 is idle, H: has 415.0 GiB free, and no protected-outcome or
  protocol-freeze marker exists.
- The 20:18 CST heartbeat found `M303-last2` at epoch 2, batch 4,600/5,692
  after improving its best fixed-Dev Macro-F1 to 0.4069 at epoch 1. The next
  evaluation is expected in roughly 5-10 minutes. Program status remains
  `RUNNING_ADAPTER_STAGE`; the adapter child and keeper are alive, atomic
  checkpoints are current, stderr logs are empty, registry and config
  identities remain unchanged, GPU 0 uses about 2.94 GiB at 69 C, GPU 1 is
  idle, H: has 414.9 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 20:38 CST heartbeat found `M303-last2` safely past its epoch-2 fixed-Dev
  evaluation and at epoch 3, batch 2,900/5,692. Its best Dev Macro-F1 improved
  to 0.4306 at epoch 2; the next evaluation is expected in roughly 15-25
  minutes. Program status remains `RUNNING_ADAPTER_STAGE`; the adapter child
  and keeper are alive, atomic checkpoints are current, all logs are empty,
  registry and config identities are unchanged, GPU 0 uses about 2.94 GiB at
  72 C, GPU 1 is idle, H: has 414.9 GiB free, and protected-outcome and
  protocol-freeze markers remain absent.
- The 20:58 CST heartbeat found `M303-last2` safely past its epoch-3 fixed-Dev
  evaluation and at epoch 4, batch 1,400/5,692. Its best Dev Macro-F1 improved
  to 0.4531 at epoch 3; the frozen run continues without selection until its
  terminal receipt, with the next evaluation expected in roughly 25-35
  minutes. Program status remains `RUNNING_ADAPTER_STAGE`; the adapter child
  and keeper are alive, atomic checkpoints are current, all logs are empty,
  registry and config identities remain unchanged, GPU 0 uses about 2.94 GiB
  at 72 C, GPU 1 is idle, H: has 414.9 GiB free, and protected-outcome and
  protocol-freeze markers remain absent.
- The 21:18 CST heartbeat found `M303-last2` through all 5,692 epoch-4 batches
  and entering fixed-Dev evaluation. Its best Dev Macro-F1 remains 0.4531 at
  epoch 3; the next result is expected in roughly 5-10 minutes. Program status
  remains `RUNNING_ADAPTER_STAGE`; the adapter child and keeper are alive,
  atomic checkpoints remain present, all logs are empty, registry and config
  identities are unchanged, GPU 0 uses about 2.94 GiB at 71 C, GPU 1 is idle,
  H: has 414.9 GiB free, and no protected-outcome or protocol-freeze marker
  exists.
- The 21:38 CST heartbeat found `M303-last2` safely past its epoch-4 fixed-Dev
  evaluation and at epoch 5, batch 5,100/5,692. Its best Dev Macro-F1 remains
  0.4531 at epoch 3; the next evaluation is expected in roughly 5-10 minutes.
  Program status remains `RUNNING_ADAPTER_STAGE`; the adapter child and keeper
  are alive, atomic checkpoints are current, all logs are empty, registry and
  config identities remain unchanged, GPU 0 uses about 2.94 GiB at 73 C, GPU
  1 is idle, H: has 414.9 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 21:58 CST heartbeat found `M303-last2` safely past its epoch-5 fixed-Dev
  evaluation and at epoch 6, batch 3,400/5,692. Its best Dev Macro-F1 remains
  0.4531 at epoch 3; the next evaluation is expected in roughly 15-25 minutes.
  Program status remains `RUNNING_ADAPTER_STAGE`; the adapter child and keeper
  are alive, atomic checkpoints are current, all logs are empty, registry and
  config identities remain unchanged, GPU 0 uses about 2.94 GiB at 73 C, GPU
  1 is idle, H: has 414.9 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 22:18 CST heartbeat found `M303-last2` safely past its epoch-6 fixed-Dev
  evaluation and at epoch 7, batch 1,700/5,692. Its best Dev Macro-F1 remains
  0.4531 at epoch 3; the next evaluation is expected in roughly 20-30 minutes.
  Program status remains `RUNNING_ADAPTER_STAGE`; the adapter child and keeper
  are alive, atomic checkpoints are current, all logs are empty, registry and
  config identities remain unchanged, GPU 0 uses about 2.94 GiB at 73 C, GPU
  1 is idle, H: has 414.9 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 22:38 CST heartbeat found `M303-last2` through all 5,692 epoch-7 batches
  and entering fixed-Dev evaluation, with best Dev Macro-F1 still 0.4531 at
  epoch 3. The terminal early-stopping decision and receipt are expected in
  roughly 5-10 minutes. Program status remains `RUNNING_ADAPTER_STAGE`; the
  adapter child and keeper are alive, atomic checkpoints remain present, all
  logs are empty, registry and config identities are unchanged, GPU 0 uses
  about 2.94 GiB at 73 C, GPU 1 is idle, H: has 414.9 GiB free, and no
  protected-outcome or protocol-freeze marker exists.
- The 22:59 CST heartbeat confirmed `M303-last2` terminally complete after
  frozen early stopping at eight epochs, best Dev Macro-F1 0.4531 at epoch 3,
  best-model SHA-256 `93de3940...5e6e12`, and receipt SHA-256
  `81560d6a...20d085`; protected outcomes remained sealed. It did not exceed
  parent M302-CBF's 0.4536, so the frozen selector retained M302-CBF and
  launched confirmation seeds `M304-S29` and `M304-S43` on GPUs 0/1. At audit
  time they were healthy at epoch 0 batches 2,500/5,692 and 2,300/5,692, with
  first fixed-Dev results expected in roughly 15-25 minutes. Program status is
  `RUNNING_CONFIRM_STAGE`; both children and keeper are alive, stderr logs are
  empty, H: has 414.9 GiB free, and protected-outcome/protocol-freeze markers
  remain absent.
- The 23:19 CST heartbeat found both confirmation seeds through all 5,692
  epoch-0 batches and entering their first fixed-Dev evaluations. No metric or
  checkpoint has been emitted before those evaluations complete; first results
  are expected in roughly 5-10 minutes. Program status remains
  `RUNNING_CONFIRM_STAGE`; both children and the keeper are alive, stderr logs
  are empty, queue and registry identities are current, GPU memory is about
  4.48 GiB per device at 75/69 C, H: has 414.8 GiB free, and protected-outcome
  and protocol-freeze markers remain absent.
- The 23:39 CST heartbeat found both confirmation seeds safely past their
  epoch-0 fixed-Dev evaluations and training epoch 1. `M304-S29` is at batch
  3,600/5,692 with Dev Macro-F1 0.4105, while `M304-S43` is at batch
  2,800/5,692 with Dev Macro-F1 0.4194. Their next evaluations are expected in
  roughly 10-20 minutes. Program status remains `RUNNING_CONFIRM_STAGE`; both
  children and keeper are alive, atomic checkpoints are current, all logs are
  empty, queue and registry identities remain unchanged, GPU memory is about
  4.48 GiB per device at 79/82 C, H: has 413.7 GiB free, and protected-outcome
  and protocol-freeze markers remain absent.
- The 23:59 CST heartbeat found `M304-S29` safely past its epoch-1 fixed-Dev
  evaluation and at epoch 2, batch 600/5,692, with best Dev Macro-F1 improved
  to 0.4476. `M304-S43` has completed all 5,692 epoch-1 batches and is entering
  evaluation, with best Dev Macro-F1 0.4221. Its next result is expected in
  roughly 5-10 minutes. Program status remains `RUNNING_CONFIRM_STAGE`; both
  children and keeper are alive, atomic checkpoints are current, all logs are
  empty, queue and registry identities remain unchanged, GPU memory is about
  4.48 GiB per device, H: has 413.7 GiB free, and protected-outcome and
  protocol-freeze markers remain absent.
- The 00:19 CST heartbeat found both confirmation seeds training epoch 2:
  `M304-S29` is at batch 4,700/5,692 with best Dev Macro-F1 0.4476 and
  `M304-S43` at batch 3,700/5,692 with best 0.4221. Their next evaluations are
  expected in roughly 5-15 minutes. Program status remains
  `RUNNING_CONFIRM_STAGE`; both children and keeper are alive, atomic
  checkpoints are current, all logs are empty, queue and registry identities
  remain unchanged, GPU memory is about 4.48 GiB per device at 82/83 C, H:
  has 413.7 GiB free, and protected-outcome and protocol-freeze markers remain
  absent.
- The 00:39 CST heartbeat found both confirmation seeds safely past epoch-2
  fixed-Dev evaluation and training epoch 3. `M304-S29` is at batch
  2,400/5,692 with best Dev Macro-F1 0.4476, while `M304-S43` is at batch
  1,000/5,692 and improved to 0.4443. Their next evaluations are expected in
  roughly 15-30 minutes. Program status remains `RUNNING_CONFIRM_STAGE`; both
  children and keeper are alive, atomic checkpoints are current, all logs are
  empty, queue and registry identities remain unchanged, GPU memory is about
  4.48 GiB per device at 81/84 C, H: has 413.7 GiB free, and protected-outcome
  and protocol-freeze markers remain absent.
- The 00:59 CST heartbeat found `M304-S29` safely past its epoch-3 fixed-Dev
  evaluation and starting epoch 4 at batch 200/5,692, with best Dev Macro-F1
  0.4476. `M304-S43` is at epoch 3, batch 4,600/5,692 with best 0.4443 and its
  next evaluation expected in roughly 5-10 minutes. Program status remains
  `RUNNING_CONFIRM_STAGE`; both children and keeper are alive, atomic
  checkpoints are current, all logs are empty, queue and registry identities
  remain unchanged, GPU memory is about 4.48 GiB per device at 81/85 C, H:
  has 413.7 GiB free, and protected-outcome and protocol-freeze markers remain
  absent.
- The 01:19 CST heartbeat found both confirmation seeds training epoch 4:
  `M304-S29` is at batch 4,300/5,692 with best Dev Macro-F1 0.4476 and its next
  evaluation expected in roughly 5-10 minutes; `M304-S43` is at batch
  1,900/5,692 with best 0.4443. Program status remains
  `RUNNING_CONFIRM_STAGE`; both children and keeper are alive, atomic
  checkpoints are current, all logs are empty, queue and registry identities
  remain unchanged, GPU memory is about 4.48 GiB per device at 82/84 C, H:
  has 413.7 GiB free, and protected-outcome and protocol-freeze markers remain
  absent.
- The 01:39 CST heartbeat found `M304-S29` safely past its epoch-4 fixed-Dev
  evaluation and at epoch 5, batch 2,000/5,692, with best Dev Macro-F1 improved
  to 0.4630. `M304-S43` is at epoch 4, batch 5,600/5,692 with best 0.4443 and
  is entering its next evaluation. No cross-seed conclusion is drawn before
  both frozen runs finish. Program status remains `RUNNING_CONFIRM_STAGE`;
  both children and keeper are alive, atomic checkpoints are current, all logs
  are empty, queue and registry identities remain unchanged, GPU memory is
  about 4.48 GiB per device at 82/84 C, H: has 413.7 GiB free, and
  protected-outcome and protocol-freeze markers remain absent.
- The 01:59 CST heartbeat found `M304-S29` through all 5,692 epoch-5 batches
  and entering fixed-Dev evaluation, with best Dev Macro-F1 0.4630 at epoch 4.
  `M304-S43` is at epoch 5, batch 2,900/5,692 and improved its best Dev
  Macro-F1 to 0.4594 at epoch 4. Both frozen seeds continue to terminal
  receipts before any conclusion. Program status remains
  `RUNNING_CONFIRM_STAGE`; both children and keeper are alive, atomic
  checkpoints are current, all logs are empty, queue and registry identities
  remain unchanged, GPU memory is about 4.48 GiB per device at 82/84 C, H:
  has 413.7 GiB free, and protected-outcome and protocol-freeze markers remain
  absent.
