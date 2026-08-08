# Progress - full-data training pipeline

## 2026-08-04 Sol all-risk Train/Dev rerun authorization

- User explicitly authorized retraining and comparison on the newly activated
  Sol all-risk label version. This is a new Train/Dev-only rerun, not a rewrite
  of the historical `STOP_DEVELOPMENT_GATE` result.
- Frozen comparison targets carried forward: per-seed Dev Macro-F1 >= 0.48,
  three-seed mean >= 0.52, and PRTA gain >= 0.03 over the strongest equal-budget
  temporal baseline. Internal-test and physician Gold remain sealed unless a
  later protocol gate and separate outcome-opening authority are satisfied.
- No rerun process has been launched yet. The next gate is cache/manifest/code/
  GPU compatibility and immutable run-registry freeze.
- The first parallel runtime inventory returned aggregate exit code 1 because
  one read-only `rg`/optional-directory branch had no match. No process or file
  changed. The partial evidence confirmed preserved `formal_program_v1`,
  `cache`, `development`, `program_keeper_v1`, and unified `run_registry.jsonl`
  surfaces. Subsequent probes are split and treat no-match as non-fatal.
- Live resource gate: both 24-GiB RTX 3090 GPUs are idle with no GPU process;
  H: and E: have approximately 410 GiB and 244 GiB free. A first optional
  listing of subpaths under `formal_program_v1` returned no rows without an
  error, so the next probe resolves exact filesystem objects before assuming
  directory layout.
- Config/runner inspection recovered the exact PRTA and TILA budgets and the
  formal CLI's runtime class-count rematerialization. One read guessed a
  nonexistent `src/prta_cxr/data/cached_dataset.py`; the implemented dataset is
  imported as `data/training_dataset.py`. The missing-file read changed no
  state and the exact module is used next.
- A potential old-label leak through per-sample transition text embeddings was
  checked before launch. The writer and live `text_cache.pt` prove that only
  finding embeddings and 60 label prototypes exist; no sample-keyed transition
  map is present. Existing text features are therefore safe for the new labels.
- A findings append initially used imprecise surrounding text and failed
  closed; it was reapplied after locating the exact paragraph. No runtime file
  or experiment state changed.

## 2026-08-04 Tier-B/C Sol-authoritative replacement exact counts

- Exact-ID audit completed before materialization: current active Train 90,771 unique rows; replacement union 5,981 unique rows; overlap between the 5,968 new-review rows and 13 pilot-only rows is zero; all targets exist in active Train.
- Frozen target counts: 4,616 decisive Sol five-class labels and 1,365 Sol `Unclear` exclusions. A later active-baseline verification found 2 pilot rows whose historical pilot Luna label differs from the current active Train label; therefore the correct active-baseline actions are 1,093 label-value changes and 3,523 same-value Sol authority rebindings. Expected new counts remain Train 89,406 and Train+Dev 102,826.
- No label file has yet been materialized in this phase; no training or metric computation has started.
- A first planning-file append assumed the generic heading `# Findings`; the repository uses `# Findings - full-data training pipeline`, so the patch failed closed and was reapplied against the exact heading without touching data artifacts.
- A documentation read guessed a longer Tier-B/C summary filename that does not exist; the actual Git-safe file is `docs/PRTA_CXR_TierBC_Sol复核摘要_CN.md`. No artifact changed. The first focused implementation lint then found two 90-92 character lines; focused tests and compilation passed, and the two lines were wrapped before materialization.
- The first formal materialization attempt stopped immediately after writing only `preopen_receipt.json`: the 5,968-row review result intentionally omits `split` because its preparation receipt freezes the roster as Train-only, while the new loader initially required an inline `split=train`. No label/provenance/active file was written. The loader now accepts an omitted split but rejects any explicit non-Train value, and resume is permitted only when the existing root contains exactly the matching preopen receipt.
- The second materialization attempt stopped during the temporary Train stream because 2 of the 13 historical pilot-only rows have a pilot-era Luna label different from the current active Train Luna label (`Worse -> Stable` and `New -> Stable`). No final/private label file was published and the temporary file was removed. The implementation now permits this only for the explicitly identified pilot namespace, records both baselines, and computes change/same counts against the actual active Train surface; full-review rows remain strict.
- Materialization completed from the unchanged inputs: 5,981 exact targets, 4,616 decisive Sol labels, 1,365 `Unclear` exclusions, 1,093 active-baseline label changes, 3,523 same-value authority rebindings, and 84,790 non-target Train rows copied byte-exact. The new active counts are Train 89,406 and Train+Dev 102,826.
- Independent audit passed after rebuilding the target set from source artifacts. Dev and Internal-test are byte-identical to the previous active Sol version, physician Gold is unchanged, training remains false, and no replacement-version metric was computed.
- The first full verification passed Ruff, all 139 pytest cases, compileall, and `git diff --check`; its final privacy grep returned nonzero only because the long-standing training manual documents the input schema names `patient_id, study_id, image_path`. This is a schema description, not row-level data. The privacy scan was narrowed to the newly added config/status surfaces and added diff content instead of weakening any artifact boundary.
- Refined privacy scan passed with zero row-level fields in the new Git-safe config/status surfaces; current PRTA training process count is 0. Final runtime receipt and independent audit both PASS with Train 89,406, Dev 13,420, Train+Dev 102,826, Internal-test 13,588, and physician Gold 250.
- Implementation, config, tests, and Git-safe documentation were committed as `f1ded683a05608a8552dbef90981a10a9036715c` and pushed only to local bare `main`; local worktree HEAD and local bare `main` matched exactly after the push. GitHub origin was not accessed or pushed.

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
- The 02:19 CST heartbeat found both confirmation seeds training epoch 6:
  `M304-S29` is at batch 4,400/5,692 with best Dev Macro-F1 0.4630 at epoch 4
  and its next evaluation expected in roughly 5-10 minutes; `M304-S43` is at
  batch 700/5,692 with best 0.4594 at epoch 4 and its next evaluation expected
  in roughly 25-35 minutes. The scheduler remains 0/2 complete and both frozen
  seeds continue to terminal receipts before any conclusion. Program status
  remains `RUNNING_CONFIRM_STAGE`; both children and keeper are alive, atomic
  best/last checkpoints are present and hashed, all five monitored logs remain
  empty, queue and 12-row registry identities remain unchanged, GPU memory is
  about 4.48 GiB per device at 82/83 C, H: has 413.7 GiB free, and
  protected-outcome and protocol-freeze markers remain absent.
- The 02:39 CST heartbeat found `M304-S29` safely through its epoch-6 fixed-Dev
  evaluation and training epoch 7 at batch 1,600/5,692. Its epoch-6 Dev
  Macro-F1 was 0.4607, so the frozen best remains 0.4630 at epoch 4.
  `M304-S43` is training epoch 6 at batch 3,800/5,692 with frozen best 0.4594
  at epoch 4 and its next evaluation expected in roughly 10-15 minutes. The
  scheduler remains 0/2 complete and both seeds continue to terminal receipts
  before any cross-seed conclusion. Program status remains
  `RUNNING_CONFIRM_STAGE`; both children and keeper are alive, atomic best/last
  checkpoints are present and hashed, all five monitored logs remain empty,
  queue and 12-row registry identities remain unchanged, GPU memory is about
  4.48 GiB per device at 81/85 C, H: has 413.7 GiB free, and protected-outcome
  and protocol-freeze markers remain absent.
- The 02:59 CST heartbeat found `M304-S29` through all 5,692 epoch-7 batches
  and entering fixed-Dev evaluation, with frozen best Dev Macro-F1 0.4630 at
  epoch 4. `M304-S43` safely completed its epoch-6 evaluation (Dev Macro-F1
  0.4337, not a new best) and is training epoch 7 at batch 1,000/5,692 with
  frozen best 0.4594 at epoch 4; its next evaluation is expected in roughly
  20-30 minutes. The scheduler remains 0/2 complete and both seeds continue to
  terminal receipts before any cross-seed conclusion. Program status remains
  `RUNNING_CONFIRM_STAGE`; both children and keeper are alive, atomic best/last
  checkpoints are present and hashed, all five monitored logs remain empty,
  queue and 12-row registry identities remain unchanged, GPU memory is about
  4.48 GiB per device at 80/83 C, H: has 413.7 GiB free, and protected-outcome
  and protocol-freeze markers remain absent.
- The 03:19 CST heartbeat found `M304-S29` safely through its epoch-7 fixed-Dev
  evaluation (Dev Macro-F1 0.4374, not a new best) and training epoch 8 at
  batch 3,400/5,692 with frozen best 0.4630 at epoch 4; its next evaluation is
  expected in roughly 10-15 minutes. `M304-S43` is at epoch 7, batch
  4,700/5,692 with frozen best 0.4594 at epoch 4 and is expected to enter its
  next evaluation in roughly 5-10 minutes. The scheduler remains 0/2 complete
  and both seeds continue to terminal receipts before any cross-seed
  conclusion. Program status remains `RUNNING_CONFIRM_STAGE`; both children
  and keeper are alive, atomic best/last checkpoints are present and hashed,
  all five monitored logs remain empty, queue and 12-row registry identities
  remain unchanged, GPU memory is about 4.48 GiB per device at 80/81 C, H:
  has 413.7 GiB free, and protected-outcome and protocol-freeze markers remain
  absent.
- The 03:39 CST heartbeat verified `M304-S29` reached
  `PASS_TRAINING_FINISHED` after epoch 8 with frozen best Dev Macro-F1 0.4630
  at epoch 4. Its child exited normally, GPU0 was released, the 42,620-byte
  training receipt hashes to `cf4a44f8...c1966`, the best checkpoint hashes
  to `d158401a...c840`, and the unified registry row now contains the terminal
  checkpoint, receipt, and end time. `M304-S43` safely completed its epoch-7
  evaluation (Dev Macro-F1 0.4331, not a new best) and is training epoch 8 at
  batch 2,000/5,692 with frozen best 0.4594 at epoch 4; its expected remaining
  time is roughly 15-25 minutes. The scheduler is 1/2 complete and the keeper
  remains healthy. GPU1 is active at 84 C with about 4.48 GiB allocated, all
  stderr logs remain empty, H: has 413.7 GiB free, and protected-outcome and
  protocol-freeze markers remain absent.
- The 03:59 CST heartbeat found `M304-S43` at epoch 8, batch 5,600/5,692 and
  entering its terminal fixed-Dev evaluation, with frozen best Dev Macro-F1
  0.4594 at epoch 4 and an estimated 5-10 minutes remaining for the receipt
  and scheduler closeout. `M304-S29` remains independently verified
  `PASS_TRAINING_FINISHED`; GPU0 is idle and its receipt/checkpoint hashes are
  unchanged. The scheduler remains 1/2 complete, the remaining child and
  keeper are alive, GPU1 retains about 4.48 GiB while evaluation is in
  progress, every stderr log is empty, the 12-row registry remains consistent,
  H: has 413.7 GiB free, and protected-outcome and protocol-freeze markers
  remain absent.
- The 04:19 CST heartbeat verified the confirmation queue closed 2/2 as
  `PASS_TRAINING_QUEUE_FINISHED` without opening Internal-test or Gold.
  `M304-S43` finished after epoch 8 with frozen best Dev Macro-F1 0.4594 at
  epoch 4; its 42,578-byte receipt hashes to `198ca435...905e`, its best
  checkpoint to `1213cfaa...124f`, and the queue receipt to
  `353da34b...13ab`. The keeper then advanced within Phase 33 to the frozen
  Dev-baseline gate: `M305-B401-S17` and `M305-B402-S17` are alive on GPUs
  0/1 and have completed all 5,692 epoch-0 training batches before their first
  fixed-Dev evaluations, while `M305-B403-S17` remains planned. The registry
  is current at 14 rows, all new stdout/stderr logs are empty, both GPUs are
  healthy, H: has 413.7 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 04:39 CST heartbeat found the Dev-baseline gate healthy and still 0/3
  complete. `M305-B401-S17` has completed all 5,692 epoch-3 training batches
  and is entering fixed-Dev evaluation, with best Dev Macro-F1 0.3608 at epoch
  2. `M305-B402-S17` is at epoch 2, batch 4,700/5,692 with best 0.4298 at
  epoch 0 and is expected to enter its next evaluation in roughly 5-10
  minutes; `M305-B403-S17` remains planned until a GPU is released. Both live
  children and the keeper are alive, atomic best/last checkpoints are present
  and hashed, all five monitored logs remain empty, the 14-row registry is
  current, H: has 413.1 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 04:59 CST heartbeat found the Dev-baseline gate healthy and still 0/3
  complete. `M305-B401-S17` is at epoch 6, batch 5,000/5,692 and improved its
  best Dev Macro-F1 to 0.3666 at epoch 5, with its next evaluation expected in
  roughly 5 minutes. `M305-B402-S17` is at epoch 4, batch 3,800/5,692 and
  improved its best to 0.4410 at epoch 2, with its next evaluation expected in
  roughly 5-10 minutes; `M305-B403-S17` remains planned until a GPU is
  released. Both live children and the keeper are alive, atomic best/last
  checkpoints are present and hashed, all five monitored logs remain empty,
  the 14-row registry is current, H: has 413.1 GiB free, and protected-outcome
  and protocol-freeze markers remain absent.
- The 05:19 CST heartbeat found the Dev-baseline gate healthy and still 0/3
  complete. `M305-B401-S17` is at epoch 9, batch 3,400/5,692 with frozen best
  Dev Macro-F1 0.3666 at epoch 5 and its next evaluation expected in roughly
  10-15 minutes. `M305-B402-S17` is at epoch 6, batch 2,700/5,692 with frozen
  best 0.4410 at epoch 2 and its next evaluation expected in roughly 10-15
  minutes; `M305-B403-S17` remains planned until a GPU is released. Both live
  children and the keeper are alive, atomic best/last checkpoints are present
  and hashed, all five monitored logs remain empty, the 14-row registry is
  current, H: has 413.1 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 05:39 CST heartbeat verified the Dev-baseline gate is 2/3 complete.
  `M305-B401-S17` finished cleanly with best Dev Macro-F1 0.3666 at epoch 5;
  its receipt hashes to `48853dc9...e2a1`. `M305-B402-S17` finished cleanly
  with best 0.4410 at epoch 2; its receipt hashes to `e5606fcf...a931`.
  Their child processes exited normally and the keeper launched the final
  frozen baseline `M305-B403-S17` on GPU0; it is at epoch 1, batch
  3,700/5,692 with initial best Dev Macro-F1 0.4003 and an estimated 30-50
  minutes remaining. GPU1 is idle, the live child and keeper are healthy,
  every stderr log is empty, all checkpoints are present and hashed, the
  registry is current at 15 rows, H: has 412.8 GiB free, and protected-outcome
  and protocol-freeze markers remain absent.
- The 05:59 CST heartbeat found the Dev-baseline gate healthy at 2/3 complete.
  The final frozen baseline `M305-B403-S17` is at epoch 3, batch
  5,100/5,692, improved its best Dev Macro-F1 to 0.4375 at epoch 2, and is
  expected to enter its next fixed-Dev evaluation in roughly 5 minutes, with
  an estimated 20-40 minutes remaining to its terminal receipt. GPU1 remains
  idle; the live child and keeper are healthy, its atomic best/last checkpoints
  are present and hashed, all monitored logs remain empty, the 15-row registry
  is current, H: has 412.8 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 06:19 CST heartbeat found the Dev-baseline gate healthy at 2/3 complete.
  The final frozen baseline `M305-B403-S17` completed all 5,692 epoch-5
  training batches and is in fixed-Dev evaluation, with best Dev Macro-F1
  improved to 0.4476 at epoch 3 and an estimated 10-25 minutes remaining to
  its terminal receipt. Both GPUs are currently compute-idle during evaluation;
  the child and keeper remain alive, the current best/last checkpoints are
  present and hashed, all monitored logs remain empty, the 15-row registry is
  current, H: has 412.8 GiB free, and protected-outcome and protocol-freeze
  markers remain absent.
- The 06:39 CST heartbeat verified the final Dev baseline and formal keeper
  both exited cleanly. `M305-B403-S17` finished after epoch 7 with best Dev
  Macro-F1 0.447629 at epoch 3; its receipt hashes to `6ec1524f...802d` and
  best checkpoint to `d8a0d17a...9a46`. The 3/3 Dev-baseline queue receipt
  hashes to `b47ccfff...f448`, all three terminal rows are current in the
  15-row registry, both GPUs are idle, and the final keeper/B403 stderr logs
  are empty. Two earlier failed resume attempts remain preserved in their
  historical stderr logs (missing formal flag; transient atomic-replace
  permission error), and both were later resolved without altering run
  identity. H: has 412.8 GiB free. The frozen development gate issued
  `STOP_DEVELOPMENT_GATE`: PRTA mean
  three-seed Dev Macro-F1 was 0.458680 (<0.52), no seed reached 0.48, seed-17
  gain over the strongest temporal baseline was 0.005959 (<0.03), and mean
  ODER 0.042202 exceeded the baseline's 0.037021. Mean minimum-class recall,
  seed range, and all positive prior gaps passed but did not override the STOP
  gate. Program state is terminal
  `STOP_FORMAL_PROGRAM_AT_DEVELOPMENT_GATE`; no protocol freeze was created
  and Internal-test/Gold were never opened.
- On 2026-08-04 the user authorized implementation of a separate full
  Train/Dev approximate-TracIn data-quality audit. Phase 41 starts with the
  protected-outcome firewall and read-only contracts; no training, deletion,
  relabeling, repartitioning, Internal-test access, or Gold access is allowed.
- Phase 41 completed with a dedicated `audit` package and entry point. The
  path firewall rejects `sealed`, `internal_test`/`internal-test`, and `Gold`
  spellings before a file open; the real preflight conserved exactly 91,065
  Train plus 16,666 Dev rows, bound all six immutable checkpoint hashes, and
  reported zero protected-outcome reads. Eleven focused tests now cover exact
  split conservation, 300-probe source-by-label balance, Tier logic, a
  synthetic mislabeled opponent, direct-gradient equality for Captum's fast
  last-layer dot product, adapter-confirmation equality, and the absence of
  training-loop calls. A real Seed-17 one-Train/one-Dev GPU smoke passed for
  both Captum and the four-adapter confirmation without writing an audit
  result or modifying an input.
- The private full audit keeper waited rather than competing with two unrelated
  22 GiB GPU jobs, then launched Seed 17 on GPU0 and Seed 29 on GPU1 when both
  cards fell below the 4,000 MiB safety threshold. Both 91,065-row Train
  prediction passes completed and were saved independently. Seed 17 completed
  and checkpointed its full `best.pt` Captum/adapter contribution and entered
  `last.pt`; Seed 29 reached 7,800/11,384 batches of the final adapter-minus
  pass for `best.pt`. All stderr logs remain empty, private progress receipts
  report `training_started=false`, and protected-outcome reads remain zero.
- At 16:09 CST both initial GPU lanes remained healthy. Seed 17 and Seed 29
  each completed all 91,065 rows for prediction and `best.pt`; their `last.pt`
  lanes reached Adapter-plus 1,900/11,384 and exact last-layer 7,300/11,384,
  respectively. Both GPUs were actively computing, all four audit stderr logs
  remained empty, the keeper and both children were alive, and every live
  receipt continued to report zero protected reads and no training.
- At 16:47 CST Seed 17 and Seed 29 both completed their independent
  `best.pt`/`last.pt` trajectories. Each final NPZ contains exactly 91,065 rows
  for all ten arrays with no NaN/Inf; positive influence is nonnegative,
  negative influence is nonpositive, Self-influence is nonnegative, and the
  maximum `signed - (positive + negative)` error is 7.63e-6 (Seed 17) and
  7.15e-6 (Seed 29). The keeper then launched only Seed 43 on GPU0; zero
  protected reads and no-training receipts remain intact.
- At 17:59 CST Seed 43 and the full private assembly completed. The final
  receipt reports 91,065 Train, 16,666 Dev, 300 probes, and 17,200 complete
  candidates (Tier A 3,866; Tier B 2,921; Tier C 10,413). Independent streaming
  validation confirmed unique IDs, zero missing/duplicate/wrong-split rows,
  finite numeric fields, 17,200 matching candidate/JSONL/Markdown records,
  matching output hashes, immutable input hashes, zero protected reads, and no
  training or optimizer step. Phases 42-44 are terminal complete; only the
  final repository verification and local-bare handoff commit remain.
- On 2026-08-04 the user authorized a full blind Sol review of exactly the
  3,866 Tier-A candidates, preferring `gpt-5.6-sol` with medium reasoning. New
  Phases 45-48 begin with a private report-only projection and exact-ID canary;
  Luna labels and all TracIn/model-risk fields must remain absent from the Sol
  payload. No relabeling, retraining, Internal-test access, or Gold access is
  authorized by this comparison.
# 2026-08-04 Tier-A GPT-5.6 Sol 全量盲审

- 已确认本轮审计全集为 Train Tier A `3,866` 条；Internal-test/Gold 保持零读取边界。
- 已确定旧 150 条 Sol pilot 配置不可作为本轮权限依据；正在建立新的全量盲审配置、私有匿名名册、严格输出 schema、断点续跑和 Luna 对比流程。
- 模型策略固定为 `gpt-5.6-sol`、`medium`；先做小批 canary 验证模型身份、字段最小化、输出枚举和 alias 数量守恒，通过后再启动全量并发。
- 私有 Tier-A 名册已生成并通过数量守恒：`3,866/3,866`，candidate manifest SHA-256 为 `62664433924c7770dc192505c0f802b5187dd767333ec24644150890e009371f`；两来源×五标签分层数量与 TracIn 回执完全一致。
- 首次批次生成被仓库既有正式运行环境门禁拦截（未发生外部调用）；用户本轮已经明确授权，下一步将在单条命令进程内设置专用授权环境变量后重试，保持配置与数据不变。
- 已生成 `194` 个匿名批次（batch size 20，末批 6 条）；批次回执确认外发项仅含 `sample_id` 短 alias、finding、prior_report、current_report，Luna 标签、患者标识和 alias map 均未外发。
- `batch_00000` canary 已一次成功：20/20 行、34.792 秒、`gpt-5.6-sol`、`medium`，schema/alias/枚举校验全部通过，无失败尝试、无模型回退。现在可以按不重叠批次分片启动全量并发。
- 已启动 15 个互不重叠的正式分片覆盖全部 194 批；首轮运行监控显示 15/15 分片存活、58/194 批（1,160 条）完成、错误日志 0，未发生模型或推理强度降级。
- 全量中段监控：134/194 批、2,680/3,866 条完成；15/15 分片仍存活，stderr 非空文件为 0。Luna 标签尚未用于比较，确保剩余 Sol 调用继续保持盲态。
- 全量完成：194/194 批、3,866/3,866 条；15 个分片回执齐全，stderr 0，失败尝试 0。统一复核回执确认所有批次均为 `gpt-5.6-sol`、`medium`，且全部既有输出哈希/ID/schema 通过。
- 已在全部 Sol 输出封存后完成 Luna 比较：全体一致 77.65%，Sol Unclear 7.60%，decisive 五类一致 84.04%，κ=0.7720；570 条明确分歧、39 条方向相反。私有全量 CSV/JSONL、聚合 JSON、内部 Markdown 与哈希回执已生成。
- 已完成代码收口：完成态配置锁死再次执行，Git 仅记录聚合计数和私有文件哈希；`ruff`、`compileall` 与全仓 `pytest` 均通过（125 passed）。输入路径门禁显式拒绝 Internal-test/Gold。

# 2026-08-04 人工授权 Sol 标签替换

- 用户在人工查看后明确决定：Tier A 全部以 Sol 判断为准，替换对应 Luna 结果。
- 执行解释固定为：3,572 条 Sol 明确五分类覆盖 Luna；294 条 Sol `Unclear` 按既有策略从新训练标签版本排除，不强制映射为五分类。
- 本轮只创建新的 Train-only 版本与审计回执；旧 Luna/TracIn/Sol 产物保持不变，不读取 Dev、Internal-test、Gold，也不启动重训。
- Train manifest 定位的第一次 `rg --files` 正则搜索未命中（退出码 1，无文件读取）；已改用受限目录枚举，确认权威正式数据表面在 `formal_program_v1` 下，下一步从公开回执/配置定位精确 Train-only 输入。
- 已实现 Sol-authoritative 流式物化器：以 TracIn Train 91,065-ID allowlist 在组合 manifest 中先按 ID 分流，只解析 Train 行；Dev 原始 JSONL 行逐字节复制并单独哈希验证。单元测试覆盖“一致标签重绑定、分歧标签替换、Unclear 排除、Dev 不进入 Train 输出”。
- 正式物化已完成并发出 PASS 回执：新 Train 90,771 行，新 Train+Dev 107,437 行；3,572 条 Sol 权威、570 个实际标签值变化、3,002 个同值 provenance 重绑定、294 个 Unclear 排除，Dev 16,666 行原始字节哈希保持一致。未启动训练。
- 独立磁盘重读审计 PASS：新 Train ID 集精确等于旧 Train 减 294 个排除 ID；87,199 个非 Tier-A Train 行逐字段不变，570/3,002 的变更/重绑定动作与 provenance 一致；Train-only 与组合文件的 Train 字节流相同，16,666 个 Dev 原始行字节流哈希相同。
- 收口检查全部通过：Ruff、compileall、全仓 pytest（126 passed）、Git diff whitespace 和 Git-safe 文档隐私扫描均 PASS；未发现训练/队列进程。新版本状态保持 `PASS_FROZEN_NOT_TRAINED`。

# 2026-08-04 Dev / Internal-test / Gold Sol 标签质量复核

- 用户明确授权启动独立只读标签质量任务，覆盖 Dev 全量 16,666、Internal-test 全量 16,699、Gold 全量 250；这是此前封存边界之后的新受控标签访问权限。
- 本轮固定 `gpt-5.6-sol` / `medium`，外发仅批内 alias、finding、PRIOR、CURRENT；现有 Luna/医生标签、患者/日期/路径、TracIn 风险和模型预测均不外发。
- 输出 schema 将包含六分类标签及受控质量标志，用于区分报告不足、配对异常、finding 不可判断等原因；不输出自由文本，不训练、不改标、不删样本、不重划分、不计算改标后指标。
- 只读路径/哈希预检已开始。第一次使用错误文件名 `internal_test_v1.jsonl` 返回不存在，未解析内容；已通过目录枚举定位实际 `internal_test_labeled_v1.jsonl`。Dev 与 Gold 输入已完成只读字节哈希，尚未构建或外发任何受保护 roster。
- 首次 Ruff 检查只发现一个未使用导入、编码参数简化和超长行等纯代码质量问题；当时未运行复核程序、未解析任何受保护标签、未调用 Sol。修正后再进入本地测试。
- Ruff 修正后已通过。随后按旧命名查找 `tests/test_sol_tier_a_review.py` 时发现文件不存在；这是只读测试定位错误，改从实际 `test_independent_silver.py` 与 `test_sol_review.py` 提取约定。
- 测试夹具继续查找时确认仓库没有 `tests/conftest.py`；测试数据由各测试模块自身构造。检查同时发现 Gold 的 `label_tier=Gold` 不符合通用 Silver 样本验证器，因此本任务采用局部 Gold 兼容验证与自有批构建器，不放宽全局训练数据契约。
- 首轮聚焦测试 20/21 通过；唯一失败来自错误断言“外发 JSON 不得出现标签单词 Stable”，而合成 CURRENT 报告正文合法地含有该词。实际外发字段集合已正确限定，测试改为检查不存在 `progression_label`、`label_tier`、`patient_id_hash` 等键。
- 修正后的 Ruff、compileall 与 21 项聚焦测试全部通过。开封前回执已在解析前写入，随后精确构建 Dev 16,666、Internal-test 16,699、Gold 250，共 33,615 条、1,682 批；三份输入哈希与预检完全一致，外发字段仍只有 alias/finding/PRIOR/CURRENT。
- v1 三队列 canary 均在服务端响应 Schema 校验前失败：`quality_flags.uniqueItems` 不被响应格式支持，未产生任何有效 Sol 标签。失败 v1 私有目录原样保留；新增 v2 Schema 只移除该不兼容关键字，重复 flag 仍由本地严格验证器拒绝，并将重建全新 v2 回执与批次。
- v2 三队列 canary 全部一次通过：Dev、Internal-test、Gold 各 20/20 条，固定 `gpt-5.6-sol`/`medium`，失败尝试均为 0，Schema、枚举、alias 和输出 ID 守恒全部通过。准备启动全量不重叠分片。
- 全量复核已启动 30 个互不重叠、可断点续跑的后台分片：Dev 14、Internal-test 14、Gold 2。每个分片均有独立 PID、批次范围、stdout/stderr 和完成回执；已成功的 canary 首批只复用、不重复调用，未启动训练或标签修改。
- 首次全量状态查询在逐 PID 调用 `Get-Process` 时达到 10 秒工具超时；命令已先成功读取 Dev 风险表头，未改变任何进程或文件。后续改为一次性进程快照再做 PID 集合比较。
- 全量首轮健康检查：30/30 分片存活，Dev 57/834 批、Internal-test 55/835 批、Gold 7/13 批已落盘；所有 stderr 均为空，尚无失败或降级。按批上限估算已覆盖约 1,140 / 1,100 / 140 条。
- 全仓测试全部通过（132 collected/passed），`git diff --check` 通过。组合隐私扫描最终退出码 1 是 `rg` 零匹配的正常结果；新增外发入口未发现患者哈希、图像路径、Luna 标签或医生标签字段。随后状态为 30/30 存活、Dev 80 批、Internal-test 78 批、Gold 10 批、stderr 0。
- Gold 已完成 13/13 批并生成 2/2 正式分片回执；Dev/Internal-test 的其余 28 个分片继续运行且 stderr 为 0。新增本地只读收口守护器：只在三队列批次数精确达到冻结值后运行比较，超时则写 `HOLD_INCOMPLETE_REVIEW_TIMEOUT`，不自动重训、改标或删除数据。
- 本地收口守护器 PID 37296 已启动并写出首个状态：Dev 116/834、Internal-test 112/835、Gold 13/13，状态 `WAITING_FOR_FULL_BLIND_REVIEW`；守护器 stderr 为空，最长等待 3 小时，完成后自动生成只读比较与哈希回执。
- 19:51 CST 实时状态：Dev 568/834、Internal-test 579/835、Gold 13/13；28 个 Dev/Internal-test 分片仍存活，30 个分片及守护器 stderr 均为 0。启动后 35.9 分钟完成 1,166/1,682 批，实际吞吐约 32.44 批/分钟，按当前速度预计约 16 分钟后进入自动比较与最终哈希审计。
- 20:13 CST 全量终态 PASS：Dev 834/834 批（16,666 条）、Internal-test 835/835 批（16,699 条）、Gold 13/13 批（250 条），总计 33,615 条。30 个正式分片回执均为 `gpt-5.6-sol`/`medium`、失败尝试 0，worker/keeper stderr 均为空。
- 只读比较完成：Dev 明确一致 12,073/13,420=89.96%，Internal-test 12,155/13,588=89.45%，Gold 医生共识 175/201=87.06%；对应 κ 为 0.8504/0.8434/0.8378。Sol Unclear 分别为 3,246/3,111/49。
- 全部需关注记录去重并集 9,984 条；Dev 高风险但 Sol 明确同意当前标签的困难样本 4,772 条。Gold 明确样本中 Sol–医生一致 175/201，Sol–Luna 一致 178/201；Luna–医生全量一致 246/250。
- 最终哈希回执确认三份受保护输入复核前后 SHA-256 完全一致，标签修改 0、删除 0、划分修改 0、训练/模型指标计算均未启动。逐样本结果继续仅位于 Git 外私有目录。
- 最终仓库门禁通过：Ruff、全仓 pytest（132 passed）、`git diff --check` 和 Git-safe 摘要隐私扫描均 PASS。本地 bare 远端为 `E:\Xiyaowang\050_VisualVIT\PRTA-CXR-local.git`；GitHub origin 仅保留配置，不执行云端推送。
- 只读标签质量任务的实现、Git-safe 摘要和私有哈希已提交为 `aecf2ab263e7441e041d2e3eb1f261ffdba342cf`，并成功推送到本地 bare `main`；本地工作树与 bare main 完全一致。缓存的 GitHub `origin/main` 仍为 `77f0c76272c3b39feb271ad24ba87a3c0c8691e6`，未执行云端访问或推送。

# 2026-08-04 Sol-authoritative Dev/Internal-test 标签替换

- 用户明确授权用已完成的 Sol 全量复核替换此前 Luna 数据。执行语义固定为：Dev/Internal-test 的 Sol 五分类直接成为新版本标签；Sol `Unclear` 按既有策略从新版本排除，不强制映射。
- Gold 当前 `progression_label` 是两位资深医生共识而非 Luna，因此保持医生 Gold 不变；Sol 结果继续作为独立复核侧表。旧 manifest 不原地覆盖，后续入口切换到带哈希/回执的新版本，以保留回退和审计能力。
- 本轮只做标签版本物化与入口切换；不训练、不重新计算模型指标。
- 已恢复完整 planning-with-files 上下文并定位既有 Sol-authoritative Train 实现与配置。原 Train 新版本为 90,771 行，组合 Train+Dev 仍含原始 16,666 行 Dev；本轮将复用其流式、版本化、哈希守恒和 `Unclear` 排除模式。
- 当前正式程序没有单一可变“active label”配置，训练/评估入口通过显式 `--split-manifest` 与 `--sealed-internal-test` 路径绑定。因此真正的切换应创建新版本化 split surface 与显式 active receipt/config，而不是破坏性覆盖 `formal_program_v1`。
- 已精确定位既有私有 Train 版本：`train_sol_authoritative_v1.jsonl` 90,771 行，SHA-256 `7306898c6b31af50956fa4ee32c5b6b8ba468751e6fc4e26f6a9353355fff219`。新的组合 Train+Dev 将逐字节复用该 Train，再附加 Sol-authoritative Dev。
- 源 Dev 16,666 行和 Internal-test 16,699 行的 `label_source` 均为 `luna_primary_report_label`、`label_tier=Silver`，确认它们全部属于用户要求替换的 Luna 数据，而非混合人工标签。
- 已新增独立物化与审计入口：按 exact-ID 连接 Sol 结果，明确标签改为 Sol 权威来源，Unclear 写入排除表；新组合 manifest 逐字节复用既有 90,771 行 Sol Train。实现同时冻结医生 Gold 不变、禁止训练/指标计算，并为替换/同值重绑定/排除分别保留私有 provenance。
- 聚焦 Ruff、compileall 与 10 项替换/旧 Train/受保护复核测试全部通过。正式物化 PASS：新 Dev 13,420、Internal-test 13,588、Train+Dev 104,191；值变化 1,347/1,433，同值 Sol 权威重绑定 12,073/12,155，Unclear 排除 3,246/3,111。
- 新输出哈希：Dev `89ea77c1...60e0c`、Internal-test `fe76a30e...44305`、Train+Dev `478e7cce...4cd21`；医生 Gold 修改数 0，训练和指标计算均未启动。
- 独立磁盘审计 PASS：新 Dev/Internal ID 集精确等于源 ID 减 Sol Unclear；所有保留行的非标签字段不变，标签与 Sol 完全一致，`label_source` 全部切为 Sol。组合 manifest 的前 90,771 行与既有 Sol Train 逐字节一致，医生 Gold 哈希不变。
- 私有活动指针 SHA-256=`ddd707c791a3e62610516bc677fd0579340afd902b3fa6c76a170f82d5efdf66`，正式物化回执=`63b9fc6e...98ae9`，独立审计=`89104893...07c64`。
- 已冻结 Git-safe 活动标签配置与中文替换状态文档，并将未来训练命令模板显式切换到新 Sol-authoritative Train+Dev/Internal-test 路径；新增配置回归测试锁定行数、核心哈希、Unclear 排除和医生 Gold 不变约束。正式训练仍保持关闭。
- 首轮并行门禁使用了不存在的旧测试名 `test_apply_tier_a_sol_labels.py` 和 `test_protected_label_quality_review.py`，pytest 在收集前失败，未执行数据、训练或写入动作。已用 `rg --files` 定位实际测试为 `test_tier_a_sol_review.py` 与 `test_protected_quality_review.py`，随后按真实文件名重跑。
- 最终哈希复核首次把 provenance 文件误写成不存在的 `label_replacement_provenance.jsonl`；其余活动文件、回执状态、Gold 不变和未训练状态已经验证，错误路径未产生任何写入。只读目录清单确认实际文件名为 `sol_authority_provenance.jsonl`，随后使用冻结回执中的真实名称重跑完整哈希核对。
- 源输入哈希复核的首条 PowerShell 命令再次触发“直接把 `foreach` 块接到管道”的空管道解析错误，命令在读取文件前即失败。按项目已记录的兼容写法改为先收集显式数组再输出；不影响任何数据或运行状态。
- 最终仓库门禁 PASS：全仓 Ruff、compileall、`git diff --check` 和 134 项 pytest 全部通过。Git-safe 新配置/替换文档不含逐病例 patient/report/image/study 字段值；扫描唯一命中来自既有训练手册对输入 schema 字段名的说明，不是本轮新增病例数据。
- 最终磁盘复核 PASS：Dev/Internal-test/Train+Dev/provenance/exclusions 的 SHA-256 分别为 `89ea77c1...60e0c`、`fe76a30e...44305`、`478e7cce...4cd21`、`77137a5e...c9ec`、`cf5ade98...fcfa`；源 Train+Dev、源 Internal-test、既有 Sol Train 和医生 Gold 的冻结哈希均未漂移。当前 PRTA 训练进程数为 0。
- Sol-authoritative 替换实现与 Git-safe 活动配置已提交为 `7c2fe96`，并成功推送到本地 bare `main`。Phase 59 至此完成；GitHub origin 未访问、未推送，训练与指标计算仍未授权。

# 2026-08-04 Tier-B/C GPT-5.6 Sol 覆盖补审

- 用户授权检查 Tier B/C 中尚未由 Sol 复核的样本，并用 Sol 完成缺口复核。新增 Phase 60-63：先按 exact sample ID 对齐全部既有 Sol 命名空间，只为真正缺失行建立盲态 roster，再固定 `gpt-5.6-sol`/`medium` 执行；本任务不改标签、不训练、不删除、不调整划分、不计算新指标。
- 已恢复 planning-with-files 上下文并定位既有 Tier-A 与受保护队列 Sol 批处理实现。当前设计选择复用质量标志版输出契约，以便 Tier B/C 不仅获得五分类/Unclear，还能记录报告、配对和时间方向问题；尚未发起任何 Sol 调用。
- 首次私有产物盘点递归列出了数千个历史 batch 文件并导致工具输出截断；这只是只读文件名枚举，没有打开逐病例内容或改变文件。后续改为只列三个已知根目录的顶层/analysis 文件，并直接使用最终合并 JSONL 做 exact-ID 覆盖审计。
- Exact-ID 覆盖审计完成：Tier B/C 13,334 条中已有 Sol 去重覆盖 7,366 条，尚缺 5,968 条，全部来自 Train（Tier B 2,912、Tier C 3,056）。旧 pilot 额外消除了 13 个原本会重复调用的 Train 样本；新批处理只会处理这 5,968 条。
- 已新增独立 Tier-B/C 缺口准备、分片启动和只读比较入口，并把现有质量复核运行器泛化为由冻结 config 验证 cohort，而不是硬编码三个旧队列。新实现固定 5,968-row exact-ID 缺口、质量标志 schema、私有路径和零训练/零改标约束；下一步先过 Ruff/测试，再创建正式私有 roster。
- 首轮聚焦门禁在执行任何数据准备或 Sol 调用前由 Ruff 停止：发现一个未使用的 `math` 导入和一处 93 字符行。已用最小格式修正移除导入并换行，行为与任务契约不变。
- 修正后 Ruff、compileall 和 11 项聚焦测试全部通过。正式私有 roster 已冻结为 5,968 条/299 批；候选 SHA-256=`5a36c264...a8af`，metadata=`74117096...02d2`，config=`a6a4f90e...fdff`。回执确认外发字段仅为 alias/finding/PRIOR/CURRENT，Luna/TracIn/患者字段均未外发，训练或改标为 false。Phase 60 完成，进入 canary。
- 20-row canary 一次通过：104.124 秒，失败尝试 0，模型 `gpt-5.6-sol`、推理强度 `medium`，匿名 alias 与恢复后的20个ID完全守恒。随后启动30个互不重叠、resume-safe 分片覆盖299批；batch 0 由首分片复用已验证 canary，不重复调用。训练/改标状态仍为 false。
- 首轮运行监控：30/30 分片存活，48/299 批已落盘，完成分片回执尚为0，stderr 非空文件为0。所有分片仍处于盲态生成阶段，未进行 Luna 比较或标签修改。
- 中段运行监控：157/299 批已落盘，30/30 分片仍存活，stderr 非空文件为0；尚无分片提前退出或完成，模型比较与任何标签动作仍未开始。
- 全量生成终态：299/299 批、5,968/5,968 行、30/30 分片回执，`gpt-5.6-sol`/`medium` 唯一，失败尝试0、stderr 0、唯一复用为已验证 canary batch 0。Phase 61 完成。
- 只读比较 PASS：总体明确五类4,604条，一致3,513（76.30%，κ=0.67583），Unclear 1,364，明确分歧1,091，需关注去重并集2,548；Tier B 明确一致64.87%且显著弱于 Tier C 的86.34%。标签修改、样本删除、划分修改、训练和改标后指标计算均为0/false。
- 已新增独立磁盘审计入口，将再次核对 candidate/metadata/299个Sol output/5,968个comparison result 的 exact-ID 集、全部标准样本字段、风险等级、Sol标签与质量标志、30份分片回执、模型身份、失败尝试及所有最终文件哈希。
- 首次 Git-safe 收口补丁因 TracIn 摘要标题与预期文本不完全一致而整体 fail-closed，未写入任何文件；读取实际标题后用精确上下文重新应用。
- 独立磁盘审计 PASS：candidate/output/result/unique-ID 均为5,968，299批、30份分片回执，模型与推理强度固定，失败尝试0；标准样本字段、risk tier、Sol标签和质量标志逐条一致，输入/输出哈希全部匹配。独立审计 SHA-256=`98c3b3e1...45b0`。
- 已生成 Git-safe 完成配置和中文聚合摘要，只记录分层计数、质量标志、私有文件哈希与“Sol不是医学Gold”的边界；逐病例报告、ID、路径和分数继续只留在 Git 外。
- 新增 Git-safe 配置回归测试，锁定13,334总量、7,366既有覆盖、5,968本轮补审、Tier B/C分层、299批/30回执以及零修改/零训练约束。
- 最终仓库门禁 PASS：全仓 Ruff、compileall、137项 pytest 和 `git diff --check` 全部通过。新 Git-safe 配置/摘要的逐病例字段扫描为0命中，当前 PRTA 训练进程数为0；本地 bare 仍与本轮开始提交 `993da6d` 对齐，缓存的 GitHub origin/main 仍为 `77f0c762...` 且未访问云端。
- 首次暂存后 `git diff --cached --check` 发现中文摘要日期行有两个尾随空格；这是纯 Markdown 格式问题。已移除尾随空格并重新暂存，私有结果和执行状态不受影响。
- Tier-B/C 补审代码、聚合摘要和私有哈希已提交为 `2436893` 并成功推送本地 bare `main`；Phase 63 完成。GitHub origin 未访问、未推送，逐病例私有结果未进入 Git，标签替换与重训仍未授权。

# 2026-08-04 Tier-B/C Sol-authoritative 标签替换

- 用户明确授权用 Tier-B/C Sol 数据直接替换此前 Luna 数据。执行语义沿用已冻结策略：Sol 五分类成为权威标签，Sol `Unclear` 从新活动版本排除；旧版本只作为审计历史保留，不再作为未来活动入口。医生 Gold 不变，不启动训练或指标计算。
- 为确保 Tier-B/C Train 不残留可用的 Luna 权威标签，本轮除5,968条新补审结果外，还会纳入此前 pilot 已复核但未权威化的13条 Train；所有集合先按 exact sample ID 去重并检查 Sol 结果冲突。
# 2026-08-04 Sol-authoritative 全风险标签重跑

- 用户已明确授权用最终替换后的 Sol-authoritative Train/Dev 数据重新训练，
  并按原冻结门槛判断是否超过旧结果。执行边界固定为新运行身份和新私有输出根；
  历史 `STOP_DEVELOPMENT_GATE` 不覆盖、不改写，Internal-test/Gold 不读取。
- 两张 RTX 3090 当前均空闲，H: 约 410 GiB、E: 约 244 GiB 可用，未发现存活的
  PRTA 训练进程。活动输入已重新确认是 Train 89,406 + Dev 13,420，SHA-256
  `a39e03e64ac43faed9348d3f8aabe79eede8bf2e398bff7cb2b795673ca1aa41`。
- 新增专用准备/收口模块与脚本，冻结三条 PRTA 种子和两条 seed-17 时序基线，
  并复用既有 GO/HOLD/STOP 判定函数。路径防火墙会在打开文件前拒绝
  Internal-test、Gold 和 sealed 路径；测试覆盖新身份、等预算、门槛差值和
  protected-path 拒绝。
- 聚焦 Ruff、compileall 与 9 项相关 pytest 全部通过。下一步在 Git 提交后运行
  全量缓存映射预检并冻结私有五运行队列；尚未启动训练。
- 首次前台预检的外层 shell 在 124 秒达到工具超时，但 Python PID 29440 继续
  健康执行；未重复启动。它最终独立完成并正常退出，错误仅是观察窗口过短，
  不是预检或数据失败。
- 正式预检 PASS：Train 89,406、Dev 13,420、总计 102,826；唯一 patient
  28,613，跨 split 重叠 0，缺失缓存键 0，两个来源和五类标签完整。训练存储
  `050a4837...40e540`、活动 manifest `a39e03e...1aa41`、权重
  `52cc993c...576be` 的前后哈希均一致，protected read count=0。
- 冻结队列 SHA-256=`c6b56beba9374ac283c679306783ec5d39aa3d6bc3355ef04b5ca3c7df2b2817`，
  运行身份为 `SOLR1-PRTA-S17/S29/S43`、`SOLR1-B402-S17`、
  `SOLR1-B403-S17`。准备回执绑定 Git commit `cdcf692`。
- 22:04 CST 五运行队列正式启动；scheduler PID 28944，首批
  `SOLR1-PRTA-S17`/`S29` 分别在 GPU0/GPU1。22:07 CST 两条均到 epoch 0
  batch 400/5,588，显存各 4,479 MiB、GPU 利用率 94%/78%、stderr 均为空。
  当前吞吐约每卡 2.5--3 batch/s，首个 Dev 指标预计约 35--45 分钟出现。
- 私有只读收口守护器 PID 35788 已启动；它只等待 scheduler 的完成回执，
  完成后调用冻结的 gate finalizer 写 `development_gate.json`，队列 HOLD 时
  fail-closed。它不会打开 Internal-test/Gold，也不会启动额外训练。
- 23:38 CST 现场复核：队列仍为 0/5 terminal，首批 seed 17/29 均在 epoch 2
  末段，分别为 5,500/5,588 与 4,700/5,588；当前最佳 Dev Macro-F1 已达到
  0.496082 与 0.483786，均超过冻结的单 seed 0.48 下限。两卡显存各
  4,479 MiB、利用率 83%/76%，所有训练 stderr 仍为 0 字节，H: 尚余
  409.3 GiB。三 seed 均值 0.52 和相对最强时序基线 +0.03 尚不能判定。
- 用户要求的 30 分钟心跳自动化已创建并启用：
  `prta-cxr-sol-rerun-monitor`，绑定当前任务。它会持续检查队列、GPU、日志、
  checkpoint、哈希与最终 gate，只在五运行、收口回执、文档和本地 handoff
  全部终态完成或出现真实权限阻塞时停止；Internal-test/Gold 保持禁止读取。
- 2026-08-05 00:11 CST 心跳：队列仍为 0/5 terminal；seed 17 已完成
  epoch 3 的 5,588/5,588 batches，正在固定 Dev 评估，暂存最佳 Macro-F1
  0.496082；seed 29 位于 epoch 3 的 4,300/5,588，暂存最佳 0.483786。
  两个训练 PID、scheduler PID 28944 和 finalizer PID 35788 均存活；四个
  best/last checkpoint 均为约 310.3 MB，所有 stdout/stderr 仍为 0 字节。
  GPU0 因 seed-17 Dev 评估暂时 compute-idle，GPU1 利用率 92%；H:/E: 分别
  尚余 409.3/244.5 GiB。活动 manifest、cache manifest、text cache、权重及
  五份 config 哈希全部与准备回执一致；protected marker=0，最终 gate/queue
  receipt 尚未生成。按当前速度估计完整五运行和收口尚需约 9--13 小时。
- 2026-08-05 00:43 CST 心跳：队列仍为 0/5 terminal，当前并行的 seed 17
  和 seed 29 均已进入 epoch 4，分别完成 4,700/5,588 与 4,200/5,588
  batches。seed 17 暂存最佳 Macro-F1 仍为 0.496082；seed 29 在 epoch 3
  将暂存最佳提高到 0.486053。两个训练 PID 42892/2992、scheduler PID
  28944 与 finalizer PID 35788 均存活；GPU0/GPU1 利用率 96%/84%，显存
  各 4,479 MiB，所有训练 stdout/stderr 仍为 0 字节。五份 config 哈希全部
  与 queue 冻结值一致，运行目录 protected-name 扫描为 0，最终 gate 与
  scheduler receipt 尚未生成。H:/E: 分别尚余约 409.3/244.5 GiB；按当前
  速度估计完整五运行与收口仍需约 8.5--12.5 小时。
- 2026-08-05 01:12 CST 心跳：队列仍为 0/5 terminal；seed 17 与 seed 29
  均进入 epoch 5，分别完成 4,300/5,588 与 3,300/5,588 batches，暂存最佳
  Macro-F1 仍为 0.496082（epoch 1）与 0.486053（epoch 3）。两个训练 PID、
  scheduler PID 28944 和 finalizer PID 35788 均存活，GPU0/GPU1 利用率
  95%/92%，显存各 4,479 MiB；stdout/stderr 仍全部为 0 字节，四个 best/last
  checkpoint 均存在且 last checkpoint 持续更新。五份冻结 config 哈希全部
  匹配，protected-name 扫描为 0，H:/E: 仍余 409.3/244.5 GiB；最终 gate 与
  scheduler receipt 尚未生成。预计完整五运行与收口仍需约 8--12 小时。
- 2026-08-05 01:42 CST 心跳：队列首次达到 1/5 terminal。`SOLR1-PRTA-S17`
  已按冻结 early-stopping 在 6 epochs 后生成 `PASS_TRAINING_FINISHED` 回执，
  最佳 Dev Macro-F1 为 0.496082（epoch 1），best/last checkpoint 与完整 history
  均已封存；回执明确记录 `internal_test_opened=false`、
  `protected_outcomes_opened=false`，输入哈希与冻结值一致。seed 29 已进入
  epoch 6 的 2,700/5,588，且 epoch 5 将最佳值提高到 0.494122；scheduler
  自动在释放的 GPU0 上启动 seed 43，当前为 epoch 0 的 3,700/5,588。
  scheduler、finalizer 和两个活动训练 PID 均存活，GPU0/GPU1 利用率
  87%/86%，stderr 全部为 0，五份 config 哈希全匹配，protected-name=0，
  H:/E: 仍余 409.3/244.5 GiB。最终 gate/queue receipt 尚未生成；按当前并行
  接力速度估计剩余四运行与收口约需 5--8 小时。
- 2026-08-05 02:12 CST 心跳：队列保持 1/5 terminal。seed 29 已进入
  epoch 7 的 2,200/5,588，最佳 Macro-F1 保持 0.494122（epoch 5），最近
  epoch-6 值为 0.484468；seed 43 已完成首轮 Dev，epoch-0 Macro-F1 为
  0.466218，并在 epoch 1 完成 3,700/5,588。scheduler、finalizer 与两个
  活动训练 PID 均存活，GPU0/GPU1 利用率 88%/80%，stderr 全为 0；五份
  config 哈希继续匹配，protected-name=0，H:/E: 尚余 408.8/244.5 GiB。
  最终 gate 与 scheduler receipt 尚未生成，预计剩余四运行和收口约 5--8 小时。
- 2026-08-05 02:42 CST 心跳：队列仍为 1/5 terminal。seed 29 位于
  epoch 8 的 900/5,588，最佳 Macro-F1 保持 0.494122（epoch 5）；seed 43
  位于 epoch 2 的 3,700/5,588，epoch 1 将最佳值由 0.466218 小幅提高到
  0.468736。scheduler、finalizer 和两个训练 PID 均存活，GPU0/GPU1 利用率
  86%/87%，显存各 4,479 MiB；活动 stderr 仍为 0，五份 config 哈希全匹配，
  protected-name=0，H:/E: 尚余 408.8/244.5 GiB。最终 gate 与 scheduler
  receipt 尚未生成，预计剩余运行和收口约需 4.5--7.5 小时。
- 2026-08-05 04:45 CST 补偿心跳（覆盖 03:12--04:44 间隔）：队列已推进到
  3/5 terminal。`SOLR1-PRTA-S29` 在 10 epochs 后 early-stop PASS，最佳
  Macro-F1 0.494122（epoch 5）；`SOLR1-B402-S17` 在 6 epochs 后 PASS，
  最佳 0.499292（epoch 1）。两份新回执均记录 Internal-test/protected outcomes
  零读取且全部输入哈希匹配。seed 43 当前 epoch 6 的 3,900/5,588，最佳值
  已提高到 0.488005（epoch 3）；scheduler 已在 GPU1 启动最后一条 B403，
  当前 epoch 0 的 400/5,588。scheduler、finalizer 与两个活动 PID 均存活；
  GPU0/GPU1 利用率 87%/13%（B403 启动阶段），所有 stderr 为 0，五份 config
  哈希匹配，protected-name=0，H:/E: 尚余 408.5/244.5 GiB。最终 gate 与
  scheduler receipt 尚未生成；预计余下两运行和收口约 2.5--4 小时。
- 2026-08-05 05:15 CST 心跳：队列仍为 3/5 terminal。seed 43 位于
  epoch 7 的 3,800/5,588，最佳 Macro-F1 保持 0.488005（epoch 3）；B403
  已完成 epoch 2 的 5,588/5,588，正在固定 Dev 评估，且把最佳值提高到
  0.491505（epoch 2）。scheduler、finalizer 和两个活动 PID 均存活；GPU0
  利用率 63%，GPU1 在 B403 Dev 评估阶段为 53%，活动 stderr 全为 0。五份
  config 哈希继续匹配，protected-name=0，H:/E: 尚余 408.1/244.5 GiB；
  最终 gate 与 scheduler receipt 尚未生成，预计剩余运行和收口约 1.5--3 小时。
- 2026-08-05 05:45 CST 心跳：队列达到 4/5 terminal。seed 43 在 8 epochs
  后 early-stop PASS，最佳 Macro-F1 0.488005（epoch 3），回执确认全部输入哈希
  匹配且 Internal-test/protected outcomes 零读取。三个 PRTA seed 的冻结均值为
  0.492736，seed range 为 0.008077。最后一条 B403 当前位于 epoch 6 的
  800/5,588，最佳值保持 0.491505（epoch 2）；其 PID、scheduler 和 finalizer
  均存活，GPU1 利用率 76%，stderr 为 0。GPU0 已正常释放至 0 MiB；五份 config
  哈希全匹配，protected-name=0，H:/E: 尚余 408.1/244.5 GiB。最终 gate 与
  scheduler receipt 等待 B403 完成，预计剩余运行与收口约 0.5--1.5 小时。
- 2026-08-05 06:15 CST 终态心跳：五个冻结运行全部生成
  `PASS_TRAINING_FINISHED` 回执，队列回执为 `PASS_TRAINING_QUEUE_FINISHED`；
  B403 最佳 Macro-F1 为 0.491505（epoch 2）。统一 `development_gate.json`
  已生成 `HOLD_DEVELOPMENT_GATE`：三种子均值 0.492736（历史 0.458680，提升
  +0.034056）但未达到 0.52；seed-17 相对最强 B402 baseline 增益 -0.003210
  （历史 +0.005959，变化 -0.009169）且未达到 +0.03。其余五项检查通过：
  三个 seed 均不低于 0.48、mean min-recall 0.375768、mean ODER 0.034302
  不高于最强 baseline、三个 prior gap 均为正、seed range 0.008077。
  队列和 gate 均确认 Internal-test/Gold 零读取；所有 stderr 为 0，五份 config
  哈希匹配，GPU 已完全释放，scheduler/finalizer 正常退出。Phase 69--70 终态
  complete，科学结论为 HOLD，不启动封存结果推理或任何新训练。
- 终态独立验收 PASS：五份训练回执、queue count/status、config SHA-256、空
  stderr、registry SHA-256、preparation-receipt SHA-256、scheduler receipt、
  `HOLD` 决策与零 protected-outcome reads 全部一致；`ruff check`、全量
  `pytest`（144 passed）及 `git diff --check` 均通过。仅 Git-safe 的聚合结论与
  计划账本进入本地版本库，逐样本私有数据、路径和封存结果均未进入 Git。
- 2026-08-05 用户新授权：将全局 Top 3%、3--5%、5--10% 三个严格嵌套风险带
  全部标记为 `SUSPICIOUS_PENDING_REVIEW` 并在一次新诊断版本中停用；保留原
  Train/Dev/Internal-test/Gold 归属，仅使用剩余 104,997 条，先在 GPU0 训练
  PRTA seed 17，再评估保留的 Dev/Internal-test/Gold。该过滤依据含历史模型
  错误、NLL 和 TracIn，故结果固定标注为后验/选择偏倚诊断，不覆盖原正式结果。
- Top-10% 风险排除模块、准备/评估 CLI 和三项聚焦测试已实现；真实物化 PASS：
  11,667 条均写入私有 `SUSPICIOUS_PENDING_REVIEW` roster，三风险带为 3,500 /
  2,334 / 5,833 条，过滤后 Train/Dev/Internal-test/Gold 精确为 80,402 /
  11,201 / 13,219 / 175。原 manifest、标签和划分未修改，保留行逐字节复制，
  Train/Dev 患者重叠为 0，全部 104,997 条 ID 与缓存覆盖守恒。
- 全仓 Ruff、147 项 pytest、真实缓存/五类标签/患者泄漏预检和 diff 检查均通过。
  为使代码提交与回执绑定，首次 pre-commit v1 物化保留但不训练；正式 v2 回执
  绑定 commit `ce30eb9b1acacdfd3e52c931327a4b3d23da9b14`。
- GPU0 首次启动在 argparse 阶段因带空格的 owner 被拆词而退出，未创建训练目录、
  未加载模型/数据；失败 stdout/stderr 已保留为 `failed_launch_01.*`。使用无空格
  owner 以相同 ID、数据、seed、方法和预算重新启动成功：训练 PID 42532，
  epoch 0 已完成 200/5,026 batches，GPU0 利用率 55%、显存 4,479 MiB、stderr 0。
  只读收口守护 PID 23588 将等待 PASS 训练回执后才评估保留三队列。
- 2026-08-05 16:41 CST 训练终态 PASS：`RISKF10-PRTA-S17` 完成 9 epochs 后
  early-stop，最佳 retained-Dev Macro-F1 为 0.535971（epoch 4），训练 stderr
  为空，冻结 config 与全部输入哈希匹配。相对前一 Sol-authoritative seed-17
  的原 Dev 0.496082，表面增加 0.039888；但当前 Dev 已按同一后验风险规则排除
  2,219 条，因此该差值不是无偏、同分布的模型增益。
- 16:51 CST 守护器完成且未重复启动评估：Dev 11,201、Internal-test 13,219、
  Gold 175 条预测均一次性落盘，回执为
  `PASS_POSTHOC_TOP10_EXCLUSION_DIAGNOSTIC`。Accuracy / Macro-F1 分别为
  Dev 0.616552 / 0.535971、Internal-test 0.580150 / 0.494916、Gold
  0.531429 / 0.539749；三队列 ODER 分别为 0.005357 / 0.036917 / 0.062857。
- 终态验收通过：三份预测行数精确守恒，checkpoint、preparation receipt、
  training receipt 与三份 prediction SHA-256 全部匹配，失败 argparse 日志仍原样
  保留；Ruff、全量 pytest（147 passed）和 `git diff --check` 均通过。GPU0/GPU1
  已释放，Phase 71--74 complete；该诊断不覆盖既有正式 HOLD 结论。

# 2026-08-05 清洗后正式数据版本授权

- 用户确认医生认为全局 Top-10% 的 11,667 条候选均可疑，授权将其统一标记为
  `SUSPICIOUS_PENDING_REVIEW` 并从后续活动数据中排除；Luna/Sol 存疑、无助或
  冲突及历史模型风险继续作为排除 provenance。旧数据、旧标签和旧划分不得覆盖。
- 新版本将冻结现有 retained membership，而不是重新随机划分：Train 80,402、
  Dev 11,201、Internal-test 13,219、Gold 175。由于候选生成使用过历史模型错误、
  NLL 和 TracIn，Internal-test/Gold 必须标注为清洗后选择偏倚评估集，不能反称为
  原始临床分布的无偏测试集。
- 首次聚合命令使用了当前 PowerShell 不支持的 `??` 空值合并语法，在解析阶段
  退出；未读取完整数据、未写入或修改任何产物。后续改用显式键存在性判断。
# 2026-08-05 医生确认排除与清洗后正式划分完成

- 用户明确确认：医生已经逐条复核全部 11,667 条全局 Top-10% 风险候选，结论是这些样本都不应使用；正式状态不再是待复核，而是 `PHYSICIAN_CONFIRMED_EXCLUDE / DO_NOT_USE`。
- 已在 Git 外生成活动包 `H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\formal_cleaned_split_v1_1`。清洗后固定数量为 Train 80,402、Dev 11,201、Internal-test 13,219、Gold 175，共 104,997 条。
- 全量排除记录位于 `quarantine/physician_confirmed_exclusions_v1.jsonl` 与 CSV；`quarantine/README_CN.md` 明确禁止用于训练、Dev、Internal-test、Gold 或其他模型实验。原始影像未移动、未删除，历史 manifest 未改写。
- 冻结回执状态为 `PASS_CLEANED_SPLIT_FROZEN`，SHA-256 为 `aa761c13ae74f29f7c30bc0fecb23db20eab02d79a52778dbbeddec9563cd069`；活动指针 SHA-256 为 `770e119c6d415af2cf5c9e4b8ab67b4d4efcd0a1caecc99312d93cf5d4787da3`。
- 独立审计重新读取三份 active manifest 和隔离清单：active 104,997、排除 11,667、排除 ID 在 active 中命中 0、四划分患者两两交集全为 0、每个划分均保留五类标签。
- 正式训练、开发队列、program keeper、protocol freeze 与正式 Internal-test 入口新增 `--cleaned-split-freeze`；路径或哈希不等于活动回执时 fail closed，防止后续误用旧数据。
- 首个 `formal_cleaned_split_v1` 草稿在隔离 README 纳入哈希前已经成功物化；删除命令被安全策略拒绝，因此原样保留为 audit-only。活动指针已原子更新到完整的 `formal_cleaned_split_v1_1`，后续只允许使用 v1.1。
- 本轮未训练模型、未改变标签、未重新划分患者、未打开新的受保护结果。清洗后的 Internal-test/Gold 因候选发现使用过历史模型风险信号，继续标记为 outcome-adaptive curated evaluation sets。
- 全仓库 Ruff、151 tests 与 `git diff --check` 通过；实现提交 `0748adb1257dc4c33568e92e994ffc57baaa93d7` 已推送并验证等于本地 bare `main`。未向 `origin` 或其他云端远程推送。
# 2026-08-05 医生清洗版正式五运行授权

- 用户明确要求把三 PRTA 种子改为 17/28/43，并启动正式实验及同预算时序基线；Seed 28 是新运行身份，不复用旧 Seed 29 checkpoint。
- 运行范围固定为医生清洗后的 Train 80,402 / Dev 11,201；Internal-test 13,219 与 Gold 175 在开发门终态前不打开。
- 计划运行五条：PRTA seeds 17/28/43、Siamese-Diff B402 seed 17、TILA B403 seed 17。门槛保持不变，不因为前一条 seed-17 诊断 0.535971 而调参。
- 启动前资源检查：GPU0/GPU1 均为 RTX 3090、显存使用 0 MiB、空闲 24,326 MiB、利用率 0%；未发现冲突训练进程；H: 约 401.2 GiB、E: 约 244.5 GiB 可用。

# 2026-08-05 医生清洗版五运行正式启动

- 准备回执 `PASS_PHYSICIAN_CLEANED_RERUN_PREPARED`：Train 80,402、Dev 11,201、缓存缺失 0、患者交叉 0、受保护结果读取 0；清洗冻结回执 SHA-256=`aa761c13ae74f29f7c30bc0fecb23db20eab02d79a52778dbbeddec9563cd069`。
- 冻结队列共五条：`CLN1-PRTA-S17/S28/S43`、`CLN1-B402-S17`、`CLN1-B403-S17`；队列 SHA-256=`7efeae134f72ed4a3b016232a74b2386ff97676c69263c54ad88dea3f900a712`。
- 18:43 CST 双 GPU 调度器 PID 19536 启动；PRTA seed 17（PID 10500）位于 GPU0、seed 28（PID 5448）位于 GPU1。两条均生成 RUNNING 训练进度回执，每 epoch 5,026 steps，stderr 为空；seed 43 与两条基线保持 PLANNED。
- 私有收口守护器 PID 23488 已启动，只在调度器五条全部 PASS 后计算冻结 development gate；不会打开 Internal-test/Gold，也不会启动额外训练或调参。
- 第一次“已有调度器”检查把自身 PowerShell 命令文本误判为调度器并在启动前安全退出；随后将匹配限定为 Python 进程，成功启动唯一调度器，队列/配置未发生变化。
- 18:44 CST 首批运行证据：seed 17/28 均到 epoch 0 的 100/5,026 steps，显存各 4,479 MiB，GPU0/GPU1 利用率分别约 75%/82%，两份 stderr 仍为 0 字节。
- 19:38 CST 首次自动巡检：队列为 0/5 terminal、2 RUNNING、3 PLANNED；seed 17/28 分别位于 epoch 1 的 4,100/3,800 steps，首轮暂存 Dev Macro-F1 为 0.515731/0.514442。两条 best/last checkpoint 均已生成且各 310,275,736 bytes，stderr 仍为 0 字节；GPU 显存各 4,479 MiB，调度器与 finalizer 守护器均存活。
- 活动 manifest 与清洗 freeze 哈希仍精确匹配准备回执，受保护读取计数仍为 0；`run_queue.json` 因调度器写入 RUNNING/PID/device 等运行状态而产生预期哈希变化，五份冻结 config 身份未改变。按当前吞吐预计整个五运行队列尚需约 7--10 小时。
- 20:08 CST 自动巡检：seed 17/28 分别位于 epoch 2 的 3,800/3,500 steps，best Dev Macro-F1 仍为 0.515731/0.514442（epoch 0）；seed 17 最新完成的 epoch-1 Macro-F1 为 0.486352，属于正常逐 epoch 波动，不据此调参或提前停止。双卡显存各 4,479 MiB、利用率约 90%/83%，所有训练 stderr 为 0 字节，调度器/finalizer 存活，五份 config 哈希均匹配，H: 尚余约 400 GiB。
- 20:38 CST 自动巡检：seed 17/28 分别位于 epoch 3 的 4,000/3,300 steps；best 仍为 0.515731/0.514442，最新完成的 epoch-2 Macro-F1 为 0.514652/0.498231。队列仍为 0/5 terminal、2 RUNNING、3 PLANNED；双卡显存各 4,479 MiB、利用率约 70%/71%，stderr 为空，last checkpoint 正常更新，manifest/freeze/config 哈希匹配且 protected read count=0。
- 21:10 CST 自动巡检：seed 17/28 分别位于 epoch 4 的 4,500/3,300 steps；seed 28 在 epoch 3 将 best Dev Macro-F1 提高到 0.519320，seed 17 best 仍为 0.515731（其最新 epoch-3 为 0.494841）。队列仍为 0/5 terminal、2 RUNNING、3 PLANNED；GPU 利用率约 82%/75%，显存各 4,479 MiB，stderr 为空，调度器/finalizer、manifest/freeze/config 哈希与 protected read count=0 均正常。
- 21:40 CST 自动巡检：seed 17/28 分别位于 epoch 5 的 5,000/3,200 steps，二者均在 epoch 4 刷新 best Dev Macro-F1 至 0.528364/0.526764。它们尚未形成正式终态，三 seed 均值和相对最强基线增益也尚不可计算；队列仍为 0/5 terminal、2 RUNNING、3 PLANNED。双卡显存各 4,479 MiB、stderr 为空，GPU、调度器/finalizer、manifest/freeze/config 哈希与 protected read count=0 均正常。
- 22:17 CST 自动巡检：seed 17/28 分别位于 epoch 7 的 1,100 steps与 epoch 6 的 4,400 steps，best 维持 0.528364/0.526764；最新完成轮为 seed 17 epoch 6=0.516267、seed 28 epoch 5=0.521430。冻结 patience 尚未满足，故继续训练而非提前停止；队列为 0/5 terminal、2 RUNNING、3 PLANNED，双卡/日志/checkpoint/哈希/守护器均健康，protected read count=0。
- 22:48 CST 自动巡检：seed 17/28 分别位于 epoch 8 的 1,700 steps 与 epoch 7 的 4,400 steps；seed 28 在 epoch 6 将 best 刷新至 0.530123，seed 17 best 仍为 0.528364（epoch 4）。冻结 early-stopping 继续正常执行，队列为 0/5 terminal、2 RUNNING、3 PLANNED；双卡显存各 4,479 MiB、stderr 为空，调度器/finalizer、manifest/freeze/config 哈希及 protected read count=0 均正常。
- 23:17 CST 自动巡检：`CLN1-PRTA-S17` 已在 epoch 8 完整结束并以 `PASS_TRAINING_FINISHED` 闭合，best Dev Macro-F1=0.528364（epoch 4），训练回执 42,533 bytes、registry checkpoint/metrics/end_time 均已写入。GPU0 随即按冻结顺序启动 `CLN1-PRTA-S43`（PID 31708），当前 epoch 0 的 700/5,026 steps；seed 28 位于 epoch 8 的 3,700 steps，best=0.530123。队列为 1/5 terminal、2 RUNNING、2 PLANNED；双卡显存各 4,479 MiB、全部 stderr 为空，哈希/守护器/protected read count=0 正常。
- 23:47 CST 自动巡检：seed 28 位于 epoch 9 的 3,500 steps，best 维持 0.530123；seed 43 已完成首轮 Dev，epoch-0 Macro-F1=0.493712，并进入 epoch 1 的 1,100 steps。队列为 1/5 terminal、2 RUNNING、2 PLANNED；双卡显存各 4,479 MiB、stderr 为空，调度器/finalizer、manifest/freeze/config 哈希与 protected read count=0 正常，H: 尚余约 399.4 GiB。检测到两份论文文档有并行工作区修改，本次仅暂存/提交 `progress.md`，未触碰或覆盖它们。
- 2026-08-06 00:17 CST 自动巡检：seed 28 位于 epoch 10 的 3,600 steps，best 维持 0.530123；seed 43 在 epoch 1 将 best 提高到 0.519625，并进入 epoch 2 的 1,500 steps。队列仍为 1/5 terminal、2 RUNNING、2 PLANNED；双卡显存各 4,479 MiB、stderr 为空，调度器/finalizer、manifest/freeze/config 哈希与 protected read count=0 均正常，并行论文文档修改继续原样保留未暂存。
- 00:47 CST 自动巡检：`CLN1-PRTA-S28` 已在 epoch 10 以 `PASS_TRAINING_FINISHED` 闭合，best Dev Macro-F1=0.530123（epoch 6）；GPU1 已按序启动 `CLN1-B402-S17`（PID 33032），其首轮 best=0.524022，当前 epoch 1 的 4,800/5,026 steps。seed 43 在 epoch 2 将 best 提高到 0.527886，并进入 epoch 3 的 1,900 steps。队列为 2/5 terminal、2 RUNNING、1 PLANNED；stderr 全空，调度器/finalizer、manifest/freeze/config 哈希与 protected read count=0 正常。
- 01:17 CST 自动巡检：seed 43 位于 epoch 4 的 2,300 steps，best=0.527886；B402 位于 epoch 5 的 1,600 steps，best=0.524022、最新 epoch-4=0.521892。队列仍为 2/5 terminal、2 RUNNING、1 PLANNED；Seed 43/B402 best/last checkpoint 分别约 310.3/156.2 MB 且持续更新，双卡、stderr、调度器/finalizer、manifest/freeze/config 哈希与 protected read count=0 均健康。
- 01:47 CST 自动巡检：`CLN1-B402-S17` 已在 epoch 5 以 `PASS_TRAINING_FINISHED` 闭合，best Dev Macro-F1=0.524022（epoch 0）；GPU1 已按序启动最后一条 `CLN1-B403-S17`，当前 epoch 2 的 3,200 steps，best=0.521602。seed 43 位于 epoch 5 的 2,800 steps，best=0.527886。队列为 3/5 terminal、2 RUNNING、0 PLANNED；stderr 全空，双卡/回执/checkpoint/哈希/守护器/protected read count=0 均正常，预计尚需约 2--4 小时。
- 02:17 CST 自动巡检：seed 43 位于 epoch 6 的 3,400 steps，best=0.527886；B403 已完成 epoch 5 并把 best 提高到 0.526094（epoch 2），随后正常进入 epoch 6。队列仍为 3/5 terminal、2 RUNNING；双卡/checkpoint/stderr/调度器/finalizer、manifest/freeze/config 哈希与 protected read count=0 均健康。B403 暂成最强 baseline，使 Seed-17 PRTA 的当前方法增益进一步缩小到约 +0.002270。
- 02:30 CST 五运行全部完成：PRTA seeds 17/28/43 的 best Dev Macro-F1 为 0.528364/0.530123/0.527886，B402/B403 为 0.524022/0.526094；五份 queue/receipt/config 全部 PASS 且哈希一致，stderr 全空，两张 GPU 已释放，Internal-test/Gold opened=false。
- finalizer 守护器因只接受 `PASS`、而 scheduler 合法终态为 `PASS_TRAINING_QUEUE_FINISHED` 而 fail-closed 退出；未损坏训练。随后使用同一冻结 registry、preparation receipt 与 comparison gate 单次执行既有 finalizer，生成 `development_gate.json`，SHA-256=`b952a88e8ae3ed3f2ab016222bf9c7344785abeecc8902911e1e56d1ef224230`。
- 正式结论为 `HOLD_DEVELOPMENT_GATE`：三-seed均值 0.528791、单 seed 下限、少数类召回、prior-gap 与 seed-range 通过；Seed-17 相对最强 B403 增益仅 +0.002270（要求 +0.03），mean ODER 0.006130 高于 B403 的 0.005535。protected read count=0，故不打开 Internal-test/Gold、不继续调参。
# 2026-08-06 Minimum contribution-diagnostic wave

- User authorized the bounded next wave: paired cleaned-Dev PRTA-S17 versus
  B403-S17 analysis, followed by exactly A508-S17, A509-S17, B403-S28, and
  B403-S43.
- Scope remains Train/Dev only. Internal-test/Gold, further Dev cleaning,
  post-hoc threshold changes, and loss-weight tuning remain prohibited.
- A508/A509 definitions were recovered from the current authority documents:
  A508 disables only transition-text semantic alignment; A509 keeps the full
  PRTA architecture and disables alignment, CMCP, inversion, and state losses.
- Existing five-run artifacts retain best/last checkpoints and aggregate
  receipts but no row-level Dev predictions. Phase 84 will therefore perform
  deterministic, no-training Dev-only inference from the frozen best
  checkpoints before the four-run launch.
- Dual-GPU no-training Dev inference completed all four conditions for both
  frozen checkpoints, exactly 11,201 rows per condition and zero protected
  reads. Patient-bootstrap Macro-F1 delta was +0.002270 with 95% CI
  [-0.008452, +0.013238], so the apparent +0.227 percentage-point gain is not
  statistically distinguishable from zero.
- The four-run queue was frozen and launched. Scheduler PID 25632 is healthy;
  A508-S17 is active on cuda:0 and A509-S17 on cuda:1, while B403-S28/S43 are
  queued. No Internal-test/Gold path was opened.
# 2026-08-06 11:47 CST minimum-wave monitor

- Scheduler PID 25632 and both children remain healthy with empty stderr.
  A508-S17 is training epoch 1 at 4,400/5,026 (best Dev Macro-F1 0.502288,
  epoch 0); A509-S17 is training epoch 3 at 1,700/5,026 (best 0.515225,
  epoch 2). B403-S28/S43 remain immutable PLANNED entries.
- GPU0/GPU1 utilization is 65%/54% with 4,479/2,053 MiB used. Preparation,
  paired-analysis, and audit-receipt hashes still match; protected read count
  remains zero and Internal-test/Gold remain unopened. Current throughput gives
  an estimated 3--4 hours to finish the queue plus final aggregation.
# 2026-08-06 12:17 CST minimum-wave monitor

- Scheduler and both training children remain healthy with zero-byte stderr.
  A508-S17 is at epoch 2, 4,800/5,026 with best Dev Macro-F1 0.502288
  (epoch 0). A509-S17 is at epoch 5, 4,200/5,026 and improved its best to
  0.526869 (epoch 4). B403-S28/S43 remain unchanged PLANNED entries.
- GPU0/GPU1 utilization is 95%/56% with 4,479/2,053 MiB used; H: retains
  426.9 GB free. Preparation and paired-analysis hashes match, protected reads
  remain zero, and Internal-test/Gold remain unopened. Estimated queue plus
  aggregation time is now about 2.5--4 hours.
# 2026-08-06 12:47 CST minimum-wave monitor

- Scheduler and both children remain healthy with empty stderr. A508-S17 has
  completed epoch 3 and improved its best Dev Macro-F1 to 0.523156 (epoch 2).
  A509-S17 is at epoch 8, 800/5,026 with best 0.526869 (epoch 4).
  B403-S28/S43 remain frozen PLANNED and will start as lanes release.
- GPU0/GPU1 utilization is 73%/67%, checkpoints are present, H: has 426.9 GB
  free, preparation/analysis hashes remain stable, and protected reads remain
  zero. Estimated remaining queue and aggregation time is 2.5--3.5 hours.
# 2026-08-06 13:17 CST minimum-wave monitor

- A509-S17 completed with `PASS_TRAINING_FINISHED` after 9 epochs. Its frozen
  best Dev Macro-F1 is 0.526869 at epoch 4, with accuracy 0.613160, ODER
  0.006160, minimum recall 0.443159, NLL 0.955344, and true-minus-wrong-prior
  gap 0.161945. Receipt SHA-256 is `805b13cc34bb37c32ccb1b099dcc4447c58b63b9e54a9cc167683d5dd229b453`;
  best-checkpoint SHA-256 is `6254ce54bca357e817e7e438efeb7c648a27f609610397d0dcb18b09df2e437a`.
- The scheduler automatically started B403-S28 on the released GPU1 lane; it
  is at epoch 1, step 4,600/5,026 with best Dev Macro-F1 0.514865. A508-S17 is
  at epoch 5, step 100/5,026 with best 0.524551 (epoch 4), and B403-S43 remains
  immutable PLANNED. Both active stderr logs are empty.
- Scheduler PID 25632 remains healthy; GPU0/GPU1 utilization is 84%/60%, H:
  has 426.5 GB free, all frozen hashes remain stable, protected reads remain
  zero, and Internal-test/Gold remain unopened. Estimated remaining queue plus
  fail-closed aggregation time is approximately 1.5--3 hours.
# 2026-08-06 13:47 CST minimum-wave monitor

- A508-S17 remains healthy at epoch 6, step 500/5,026; its frozen running best
  remains Dev Macro-F1 0.524551 at epoch 4. B403-S28 completed epoch 4 and
  improved its running best to 0.526998 at epoch 3. A509-S17 remains terminal
  PASS and B403-S43 remains immutable PLANNED until a GPU lane releases.
- Scheduler PID 25632 and both active children are alive, all three stderr
  logs remain empty, GPU0/GPU1 utilization is 95%/47% with 4,479/1,601 MiB
  allocated, and H: has 426.5 GB free. All four config SHA-256 values still
  match the frozen queue; preparation and paired-analysis receipts remain PASS
  with protected read count zero and Internal-test/Gold unopened.
- No aggregate finalizer has started because only 1/4 runs is terminal. The
  estimated remaining training plus fail-closed aggregation time remains
  approximately 1.5--3 hours.
# 2026-08-06 14:17 CST minimum-wave monitor

- A508-S17 is healthy at epoch 7, step 800/5,026 with running best Dev
  Macro-F1 0.524551 (epoch 4). B403-S28 completed the epoch-7 Dev pass with
  running best 0.526998 (epoch 3) and is finishing its frozen early-stop/prior
  audit path; A509-S17 remains PASS and B403-S43 remains PLANNED.
- Scheduler PID 25632 and both children remain alive with empty stderr. GPU0
  and GPU1 are active at 85%/37% utilization with 4,479/1,601 MiB allocated;
  H: has 426.5 GB free. Preparation and paired-analysis receipts remain PASS,
  their protected-read counts remain zero, and the paired-analysis output hash
  still matches. Internal-test/Gold remain unopened.
- Only 1/4 runs is terminal, so the aggregate finalizer correctly remains
  closed. Estimated remaining queue plus aggregation time remains about
  1.5--3 hours.
# 2026-08-06 14:47 CST minimum-wave monitor

- B403-S28 completed with `PASS_TRAINING_FINISHED` after 8 epochs. Its frozen
  best Dev Macro-F1 is 0.526998 at epoch 3, with accuracy 0.620034, balanced
  accuracy 0.551245, ODER 0.008214, minimum recall 0.448098, NLL 0.972258, and
  true-minus-wrong-prior gap 0.169621. Receipt SHA-256 is
  `27730c39350bc35d9275e9f0c31a6db2be160cf16021d12e7a8d2263c94edee1`;
  best-checkpoint SHA-256 is
  `19ba005d633f1e721cfdb670fe6ba1b759c9234c9421fa06f4dd47993bdd134d`.
- The scheduler started B403-S43 on the released GPU1 lane; it has completed
  epoch 2 with running best Dev Macro-F1 0.512814 (epoch 1). A508-S17 is at
  epoch 8, step 1,000/5,026 with running best 0.524551, while A509-S17 remains
  terminal PASS. The queue is now 2/4 terminal.
- Scheduler PID 25632 and both active children are healthy; all stderr logs
  remain empty. GPU0/GPU1 memory is 4,479/1,601 MiB, H: has 426.1 GB free,
  all four config hashes match, preparation and paired-analysis receipts remain
  PASS with protected-read count zero, and Internal-test/Gold remain unopened.
  Estimated remaining training plus aggregation time is about 1--2 hours.
# 2026-08-06 15:17 CST minimum-wave monitor

- A508-S17 completed with `PASS_TRAINING_FINISHED` after 9 epochs. Its frozen
  best Dev Macro-F1 is 0.524551 at epoch 4, with accuracy 0.613427, balanced
  accuracy 0.533139, ODER 0.006071, minimum recall 0.452689, NLL 0.972698, and
  true-minus-wrong-prior gap 0.182209. Receipt SHA-256 is
  `65e048b9fc597413fcb281e074e2fbe36a84b1bf9fbc9add39d02c82ec0597f2`;
  best-checkpoint SHA-256 is
  `de9e9e26cef5b2ba7227d1caff776ed2839b18dd083d725dc44fb4b4027bfe0c`.
- The queue is now 3/4 terminal. B403-S43 is the sole remaining child at
  epoch 5, step 4,700/5,026 with running best Dev Macro-F1 0.520605 (epoch 2).
  Scheduler PID 25632 and child PID 38804 are healthy; all stderr logs remain
  empty. GPU0 is released and GPU1 is active with 1,601 MiB allocated; H: has
  426.2 GB free.
- Preparation and paired-analysis receipts remain PASS, their protected-read
  counts remain zero, the paired-analysis output hash matches, and
  Internal-test/Gold remain unopened. The aggregate finalizer remains closed
  until B403-S43 passes; estimated remaining training plus aggregation time is
  approximately 30--75 minutes.
# 2026-08-06 15:46 CST minimum-wave training and aggregation closure

- B403-S43 completed with `PASS_TRAINING_FINISHED` after 7 epochs and frozen
  best Dev Macro-F1 0.520605 at epoch 2. The scheduler closed 4/4 jobs as
  `PASS_TRAINING_QUEUE_FINISHED`; both GPUs are released and all four stderr
  logs are empty.
- Added and tested a fail-closed minimum-wave finalizer. It requires exact
  four-run and parent registries, the immutable previous HOLD hash, scheduler
  receipt, paired Dev analysis/receipt, all PASS training receipts, and zero
  protected reads before writing any decision. Focused Ruff and 5 minimum-wave
  tests passed.
- Final aggregate: PRTA three-seed Macro-F1 0.528791 +/- 0.001178; B403
  0.524565 +/- 0.003460; mean delta +0.004226. The Seed-17 paired Macro-F1
  95% CI [-0.008452, +0.013238] includes zero, while the PRTA-minus-B403 ODER
  CI [0.000263, 0.003751] is adverse and every tested PRIOR intervention loses
  more Macro-F1 for PRTA. The result is `STOP_CURRENT_PRTA_ROUTE`, not a PRTA
  advantage or a mechanism/trust advantage. The prior HOLD is unchanged.
- Private decision and finalization receipt were written outside Git as
  `minimum_wave_decision.json` and `finalization_receipt.json`; both report
  Internal-test/Gold unopened and protected-outcome read count zero. Full
  repository validation and local-only Git handoff remain.

# 2026-08-06 16:02 CST minimum-wave terminal validation

- Full repository validation passed: Ruff reported no findings, all 158 tests
  passed, and `git diff --check` was clean.
- The private finalization receipt conserves the cleaned Dev cohort at 11,201
  rows / 2,427 patients, binds four PASS run receipts, and records zero reads
  of Internal-test/Gold. The decision artifact hash matches its receipt.
- Phase 87 is terminally complete. Only the Git-safe finalizer, tests, and
  planning records are included in the local-only handoff; the two pre-existing
  user-modified paper documents remain unstaged and unchanged by this closure.

# 2026-08-06 exploratory method-revision start

- User explicitly authorized a new case-study-driven method modification and
  exploratory attempt to exceed existing methods. This is a new Train/Dev-only
  namespace; it does not rewrite the prior HOLD or route-stop decision.
- Recovered the completed paired Dev artifacts (11,201 rows / 2,427 patients)
  and confirmed the active cleaned manifest contains only Train/Dev. No
  Internal-test or Gold artifact was opened.
- Initial aggregate failure signal: PRTA gains on Improved/Worse but loses on
  Stable/New/Resolved, has more harmful directional errors, and degrades more
  under matched-wrong/null/reversed PRIOR. Code inspection shows frozen H0 uses
  only pooled transition tokens, motivating a state-anchored gated residual.
- First focused case-study lint stopped before execution on the new script
  bootstrap import and three long lines. Reused the repository's `_bootstrap`
  dispatch pattern and wrapped the expressions; no data or model was opened by
  the failed lint pass.
- The first synthetic case-study test exposed that the intervention audit was
  incorrectly requiring a `true` row to declare the changed intervention.
  Split cross-system condition validation from within-system observation
  identity validation; this preserves fail-closed alignment without conflating
  two deliberately different conditions.
- The corrected case-study builder passed focused Ruff/tests and completed the
  real cleaned-Dev analysis at 11,201 rows / 2,427 patients. It selected 48
  representative cases and wrote summary/cases/Markdown/receipt under the
  private `exploratory_state_anchored_v1/case_study` runtime directory. All
  hashes were recorded; protected reads remained zero.
- User requested trying hyperparameter repair before structural real-data
  training. Frozen a four-arm loss-only screen on the A509 classification-only
  structure, with an explicit conditional two-point learning-rate follow-up and
  no other adaptive search. The state-anchor implementation remains synthetic-
  only until this screen closes.
- Implemented and qualified the optional bounded state-anchor H3 head and
  opposite-direction margin loss. Identical PRIOR/CURRENT features force the
  temporal mixture gate to exactly zero; random changed pairs remain in [0,1]
  and backpropagate through the gate.
- Full repository qualification passed: Ruff clean, 165/165 tests, compileall,
  engineering preflight, and a three-step synthetic smoke. Prepared the four
  immutable Seed-17 loss-screen configs and queue with hashes; no real training
  had started at preparation time and protected reads remained zero.
- Loss screen launched under scheduler PID 5020. `TUNE-FG1-S17` PID 42876 is
  bound to cuda:0 and `TUNE-WCE-S17` PID 41444 to cuda:1; balanced-softmax and
  ordinary-CE remain immutable PLANNED for the two released lanes. Initial
  scheduler and child stderr logs are empty.
- Created the 30-minute heartbeat monitor
  `prta-cxr-exploratory-method-monitor` for the bounded loss/LR/state-anchor
  decision tree. The first two creation calls failed validation on lowercase
  status and missing thread destination; corrected to `ACTIVE` with
  `destination=thread`. The final automation was created successfully and no
  experiment process was affected by the validation failures.

# 2026-08-06 16:46 CST exploratory loss-screen monitor

- Scheduler PID 5020 and both children remain healthy with empty stderr logs.
  `TUNE-FG1-S17` and `TUNE-WCE-S17` each completed epoch 0 and are training
  epoch 1/20; the other two frozen arms remain PLANNED until a lane releases.
- All four config hashes still match the preparation receipt. GPU0/GPU1 hold
  2,053 MiB each, H: has 424.8 GB free, and no protected cohort was opened.
  Intermediate Dev values were recorded only as runtime health evidence and
  were not used to change the queue or select parameters.

# 2026-08-06 17:16 CST exploratory loss-screen monitor

- Both active arms completed epoch 2 and remain healthy under scheduler PID
  5020. `TUNE-FG1-S17` running best Macro-F1 is 0.513309 and
  `TUNE-WCE-S17` is 0.507527; these non-terminal values did not alter the
  frozen queue or selection rule.
- Both stderr logs remain empty, config hashes match, GPU0/GPU1 are active with
  about 2,055/2,053 MiB allocated, and H: has 415.1 GB free. The two remaining
  arms remain PLANNED and protected cohorts remain sealed.
# 2026-08-06 17:46 CST exploratory loss-screen monitor

- Both active arms remain healthy in epoch 4/20: `TUNE-FG1-S17` is at
  step 1,600/5,026 with running best Macro-F1 0.513309, while
  `TUNE-WCE-S17` is at step 1,500/5,026 with running best 0.507527.
  Intermediate values did not alter the frozen queue or selection rule.
- Scheduler/children are alive, stderr logs remain empty, all config hashes
  match, both GPUs are active, and H: has 406.8 GB free. The balanced-softmax
  and ordinary-CE arms remain PLANNED; protected cohorts remain sealed.
# 2026-08-06 18:16 CST exploratory loss-screen monitor

- The two active loss arms remain healthy in epoch 5/20 at step 3,400/5,026.
  `TUNE-FG1-S17` has a running best Dev Macro-F1 of 0.535933 at epoch 4
  (ODER 0.005892), while `TUNE-WCE-S17` retains 0.507527 at epoch 2; these
  intermediate values did not change the frozen queue or predeclared rule.
- Scheduler PID 5020 and both children remain alive, all stdout/stderr logs are
  empty, current best/last checkpoints are present, and every immutable config
  file hash matches the preparation receipt. GPU0/GPU1 are active and H: has
  406.0 GB free. `TUNE-BS-S17` and `TUNE-CE-S17` remain PLANNED, and protected
  Internal-test/Gold cohorts remain sealed.
# 2026-08-06 18:46 CST exploratory loss-screen monitor

- Both active arms remain healthy near the end of epoch 6/20 at step
  4,500/5,026. `TUNE-FG1-S17` retains its running best Macro-F1 0.535933
  (epoch-4 ODER 0.005892), while `TUNE-WCE-S17` retains 0.507527; no
  intermediate value changed the immutable queue or selection rule.
- Scheduler PID 5020 and both children are alive, stderr/stdout remain empty,
  best/last checkpoints are present, and all four config hashes still match
  the preparation receipt. Both GPUs remain allocated, H: has 405.0 GB free,
  the remaining two arms are PLANNED, and protected cohorts remain sealed.
# 2026-08-06 19:16 CST exploratory loss-screen monitor

- `TUNE-WCE-S17` is the first terminal arm: PASS after seven completed epochs,
  best Dev Macro-F1 0.507527 at epoch 2 and corresponding ODER 0.017766. It is
  below B403-S17 and violates the frozen ODER constraint, so it is not eligible
  for the conditional learning-rate branch.
- The scheduler immediately started immutable `TUNE-BS-S17` on cuda:1; it is
  healthy in epoch 0 at step 4,200/5,026. `TUNE-FG1-S17` remains healthy near
  the end of epoch 7 at step 4,800/5,026 with its running best unchanged at
  0.535933. `TUNE-CE-S17` remains PLANNED.
- Scheduler and children are alive; active stderr logs are empty, receipts and
  checkpoints are present, all four config hashes match the preparation
  receipt, both GPUs are active, and H: has 404.9 GB free. Protected cohorts
  remain sealed and no adaptive queue change was made.
# 2026-08-06 19:46 CST exploratory loss-screen monitor

- `TUNE-FG1-S17` remains healthy at the completed step boundary of epoch 8,
  with running best Macro-F1 0.535933 from epoch 4. `TUNE-BS-S17` has reached
  the completed step boundary of epoch 1 with a provisional best 0.465618.
  Both are in their normal Dev-evaluation/checkpoint interval; no receipt or
  branch decision is yet available.
- Scheduler PID 5020 and both children remain alive, active stderr logs are
  empty, checkpoints are present, and all config hashes match the preparation
  receipt. Both GPUs remain allocated and H: has 404.1 GB free. WCE remains
  terminal PASS, CE remains PLANNED, and protected cohorts remain sealed.

## 2026-08-06 — SUES HPC deployment

- Confirmed the requested remote placement is the sibling project root
  `~/projects/xiyaowang/050_VisualVIT`, not a child of `036_IndexMemory`.
- Authenticated using the existing `sues-hpc` SSH profile. The target
  `050_VisualVIT/PRTA-CXR` is absent; no remote file was created or modified.
- Recorded the deployment contract in
  `docs/operations/2026-08-06_SUES_HPC_DEPLOYMENT.md`. The current local
  scheduler/children are live, so package consistency must be reconciled before
  transfer. No scheduler, Slurm job, training process, or protected artifact
  was changed.
- Created the dedicated remote `prta-cxr311` environment and installed the
  project plus dev/vision/data/audit dependencies. Its first foreground
  installation exceeded the session timeout after the CUDA wheels completed;
  checked the partial state, then finished the remaining install through a
  logged `nohup` script. The environment import gate and engineering preflight
  both passed.
- Uploaded/extracted the source archive and verified the same SHA-256 on both
  hosts. It contains the current clean project, documents, results, outputs,
  and HPC environment/probe files, excluding VCS and disposable caches.
- Verified the resumable SFTP directory contract with the 329 MB cleaned split.
  The first recursive attempts failed before copying files because remote
  directories were absent and then because `reput` cannot create initial
  remote files. Pre-created the exact directory tree and used `put -R`; the
  final smoke transfer passed. Started local SFTP PID 39148 at 200 Mbit/s for
  non-active runtime artifacts only. The live local scheduler/PIDs and Slurm
  allocations were not changed.
# 2026-08-06 local-stop/server-migration authority

- User explicitly narrowed the active local work to the two currently running
  arms only: `TUNE-FG1-S17` and `TUNE-BS-S17`. `TUNE-CE-S17`, conditional LR
  follow-ups, and the structural screen must not start locally.
- The correct identity-preserving control is to stop only the queue scheduler
  and leave both training children alive, rather than editing the immutable
  queue or killing/restarting either run. The remaining local monitor will
  close after both in-flight receipts are terminal.
- Server readiness must be proved separately by login, allocation/GPU, remote
  paths/permissions, environment, data/cache authorization, transfer hashes,
  and a minimal validation. No remote experiment is authorized by readiness
  inspection alone.
- FG1 completed while the stop boundary was being recorded, and the old
  scheduler auto-started CE before it could be stopped. Identity checks then
  stopped scheduler PID 5020 and CE PID 39316; partial CE best/last checkpoints,
  progress, and empty stderr were preserved. BS PID 33140 remained alive and is
  now the only authorized local child.
- The heartbeat automation was narrowed to monitor BS only and explicitly
  forbids restarting the scheduler, CE, LR follow-ups, or structural runs.

# 2026-08-06 SUES HPC live readiness start

- Forced-TTY SSH through `sues-hpc` passed on login node `mu01` as `dqxy11`.
  Remote root `.../050_VisualVIT/PRTA-CXR` exists and is 2.9 GB; Conda env
  `prta-cxr311` exists with Python 3.11.15 and torch/torchvision 2.6.0/0.21.0
  CUDA 12.6 builds. Login-node engineering preflight passed without real-data
  or protected-outcome access.
- Slurm allocations 4161 and 3066 are RUNNING on gpu01, one A800 each. The
  expected shared BiomedCLIP weight is missing, remote data is only partially
  inventoried, and GPU-job CUDA validation is still pending. The environment
  also lacks sklearn, accelerate, and openpyxl, so the server is not yet ready
  for formal PRTA training.
- The first read-only `srun --jobid=4161 --overlap` GPU probe reached the
  allocation but failed before Python execution because nested SSH/Bash quoting
  corrupted the inline `python -c` expression. No project artifact, Slurm
  allocation, environment, data, or process was changed. The retry method is a
  versioned file-backed probe script on the shared project filesystem.
- The file-backed retry passed inside retained allocation 4161 on `gpu01`:
  NVIDIA A800 80GB PCIe, driver 590.48.01, torch 2.6.0+cu126, CUDA available,
  `pip check` clean, and `PASS_PRTA_CXR_ENGINEERING_PREFLIGHT`. No new Slurm
  job or formal experiment was submitted.
- A previously started broad SFTP batch was found to include audit/label
  directories beyond the minimum Train/Dev runtime surface. PID 39148 was
  identity-checked and stopped; existing remote partial files were preserved
  and nothing was deleted. Future transfer is restricted to the frozen
  Train/Dev manifest/receipts, BiomedCLIP weight, and minimal consolidated
  feature/text cache only.
- Remote Train/Dev manifest and all three cleaned-split receipts already match
  local SHA-256 exactly, including manifest
  `45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89`.
- A fresh full SHA-256 pass over the 44.2 GB local consolidated feature store
  exceeded the 300-second interactive limit after validating its metadata and
  small cache files. The immutable training-store receipt already records hash
  `050a4837dbff14f39cab75e9438c3bf7b86776583a06d12b68b1308fca44e540`;
  final server acceptance will compute and compare the remote file hash after
  transfer. No transfer of this active-read cache will begin before BS exits.
- BiomedCLIP weight upload completed and the remote 783,705,670-byte file
  matches local SHA-256
  `52cc993c5c5ff962bd0c60931874bc001e7e9b41666a385530f4a036294576be`.
- Added and remotely byte-verified a fail-closed Train/Dev asset probe plus a
  Linux path template. Local and remote Ruff/compile checks pass. The probe
  refuses protected path markers, validates the exact frozen hashes/counts,
  exercises the consolidated feature store, and starts no formal experiment.
- Prepared a resumable SFTP batch containing only the consolidated feature
  store, cache manifest/inventory, text cache, and two receipts. The 30-minute
  automation now waits for BS to become terminal, then transfers and validates
  only this minimal cache before closing server engineering readiness.

# 2026-08-06 20:43 CST narrowed local/server monitor

- `TUNE-BS-S17` remains healthy as the only authorized local child at epoch 5,
  step 1,700/5,026. Its best Dev Macro-F1 remains 0.488853 at epoch 3; this is
  monitoring evidence only and does not change the frozen run or stop rule.
- PID 33140 is alive on GPU1 (60% utilization, 2.1 GB memory); scheduler PID
  5020 and partial CE PID 39316 remain absent. No active error log was created,
  H: has 375.3 GB free, and all recorded immutable input hashes are unchanged.
- The minimal cache upload remains intentionally unopened while BS reads the
  same feature store. At the recent epoch rate, terminal early-stop evaluation
  is expected in roughly 1--2 hours; the post-terminal resumable transfer and
  server asset probe remain next.

# 2026-08-06 21:13 CST narrowed local/server monitor

- `TUNE-BS-S17` remains healthy near the end of epoch 7 at step 4,400/5,026.
  Its best Dev Macro-F1 is still 0.488853 from epoch 3; epoch-6 Macro-F1 was
  0.487350 with ODER 0.020087. These values remain monitoring-only.
- PID 33140 is alive on GPU1 (62% utilization, 2.1 GB memory); scheduler PID
  5020 and CE PID 39316 remain absent, no error log exists, and H: still has
  375.3 GB free. No minimal-cache SFTP process has started.
- With four completed non-improving Dev evaluations after the best epoch, the
  frozen early-stop decision is expected shortly. The next action remains to
  wait for the terminal receipt, then start exactly one minimal-cache upload.

# 2026-08-06 21:43 CST narrowed local/server monitor

- `TUNE-BS-S17` improved under its frozen training path and therefore remains
  active at epoch 10, step 200/5,026. The progress file records best Macro-F1
  0.508886 at epoch 7; the latest epoch-9 report is Macro-F1 0.509438 with ODER
  0.012677. No selection or tuning decision is made from these intermediate
  values.
- PID 33140 is healthy on GPU1 (52% utilization, 2.1 GB memory). Scheduler PID
  5020 and CE PID 39316 remain absent, best/last checkpoints and the progress
  file are fresh, H: has 375.3 GB free, and the cache transfer is still closed.
- Because the frozen early-stop patience reset at the epoch-7 improvement, BS
  is likely to require several more epochs. The bounded local-only authority
  remains unchanged; server upload waits for the terminal receipt.

# 2026-08-06 22:20 CST user status check

- `TUNE-BS-S17` remains the sole active local process after completing epoch
  10. Best Macro-F1 remains 0.508886 at epoch 7; epoch-10 Macro-F1/ODER are
  0.491185/0.021337. These values remain below the B403 reference and do not
  trigger any new run or tuning branch.
- PID 33140 is healthy on GPU1 (63% utilization, 2.1 GB memory). Scheduler PID
  5020 and CE PID 39316 remain absent. H: has 370.8 GB free.
- Server allocations 4161/3066 remain RUNNING. Weight, GPU environment, and
  frozen Train/Dev hashes are ready; the consolidated cache is still 0 bytes
  remotely by design and its SFTP process has not started while BS reads it.
- Expected remaining local time is roughly 30--60 minutes if the frozen
  early-stop patience is reached without another improvement; cache transfer
  and final server probe then require approximately 35--60 additional minutes.

# 2026-08-06 22:14 CST BS terminal and server transfer start

- `TUNE-BS-S17` reached `PASS_TRAINING_FINISHED` after 12 epochs with frozen
  early stopping. Best epoch 7 Macro-F1/ODER were 0.508886/0.012945. FG1 had
  already passed at 0.535933/0.005892 (epoch 4). Both receipts report
  Internal-test/protected outcomes unopened.
- All local exploratory processes are now absent: BS PID 33140, scheduler PID
  5020, and partial CE PID 39316. No CE/LR/structural arm was launched after
  the user narrowing; partial CE artifacts remain preserved.
- The protected-marker guard passed on the minimal-cache SFTP batch. Exactly
  one hidden resumable SFTP process started as PID 39508 with the 200 Mbit/s
  cap. Initial remote consolidated-store progress was 390,860,800 of
  44,211,717,120 bytes (0.88%); stdout/stderr logs are timestamped under
  `E:\Xiyaowang\050_VisualVIT\.tmp` and currently empty.
- The next heartbeat will monitor byte progress only. After transfer, remote
  hash validation and the retained-allocation Train/Dev asset probe remain;
  no server training job is authorized or started.

# 2026-08-06 22:43 CST server cache-transfer monitor

- Minimal-cache SFTP PID 39508 remains healthy with empty stdout/stderr logs.
  The remote consolidated store reached approximately 31.234/44.212 GB
  (70.6%); the small metadata/text-cache files follow after the store.
- All local training/scheduler/CE PIDs remain absent. Retained allocation 4161
  is RUNNING on gpu01 and no new Slurm job was submitted.
- At the observed transfer rate, the large store should finish in roughly
  10--15 minutes. Full remote SHA-256 and the aggregate-only Train/Dev asset
  probe must still pass before server readiness can close.

# 2026-08-06 23:14 CST SUES engineering readiness terminal PASS

- Minimal-cache SFTP completed cleanly: PID 39508 exited, stderr stayed empty,
  and all six intended files are present. The consolidated store is exactly
  44,211,717,120 bytes; no audit/label/Internal-test/Gold directory was in the
  replacement batch.
- Reused retained allocation 4161 on gpu01 for the aggregate-only asset probe;
  no new Slurm job was submitted and `PRTA_CXR_ALLOW_FORMAL` remained unset.
- `PASS_SUES_TRAIN_DEV_ASSET_PROBE`: Train 80,402, Dev 11,201, cache 146,110,
  feature probe `[8,197,768]`, protected paths opened 0, formal experiment
  started false. All six frozen input hashes match exactly.
- Phase 91 is terminal `PASS_SUES_HPC_ENGINEERING_READINESS`. Server training
  has not started and remains locked until a new Linux Train/Dev queue is
  frozen and explicitly authorized.

# 2026-08-06 23:27 CST continuous server Dev-search authority

- The user explicitly authorized continued lightweight hyperparameter search
  on retained allocations 4161 and 3066 until told to stop, with both A800s
  available and a 20-minute monitor requested after launch.
- The scope is a new Train/Dev-only exploratory namespace. Internal-test and
  Gold remain sealed; labels, patient sets, splits, cache, model family, native
  H0 head, adapters, optimizer, batch size, epoch budget, and early stopping
  remain fixed. Historical `HOLD_DEVELOPMENT_GATE` and
  `STOP_CURRENT_PRTA_ROUTE` remain immutable.
- The fixed target is the existing joint gate: Dev Macro-F1 >=
  0.5290939600646948 and ODER <= 0.00553522006963664. The completed FG1 arm is
  close at 0.535933/0.005892, so the first server wave will change only a small
  opposite-direction margin weight and will be frozen before training.
- Two read-only command errors were preserved: `squeue -s` rejected job-format
  `%T`, and source inspection guessed missing `cli_training.py` before locating
  the real `src/prta_cxr/cli.py`. Neither command changed code, data, jobs, or
  runtime state.
- Wave 001 is frozen to `SVR-FG1-DMW020-S17` on allocation 4161 and
  `SVR-FG1-DMW050-S17` on allocation 3066. Config SHA-256 values are
  `522a4d87769065b3bc4b538f0fb00ea5aba6e0b9e32cf2b2c91b27b40268678a`
  and `e5865476b57ef00176639525fe9f36d4b2169e96916109ee7992e3de528fc239`.
  The remote launcher rejects protected path markers, allocation/config/source
  identity drift, missing Train/Silver audit input, and existing output paths.
- Local WSL lacks `/bin/bash`, so its attempted `bash -n` check is invalid even
  though the subsequent focused Python checks passed. Exact launcher syntax
  validation is therefore moved to the Linux server before either arm starts.

# 2026-08-06 23:38 CST wave-001 fail-closed launch diagnosis

- Both retained-allocation launchers exited before creating any run output,
  checkpoint, registry row, or Dev result. The preserved logs show the same
  infrastructure error: the immutable cleaned-freeze receipt carries Windows
  absolute output paths, which cannot resolve on Linux.
- Allocations 4161/3066 returned to batch-only state. Configs, seeds, methods,
  data, and budgets remain unchanged, so an identity-preserving retry is
  available after a path-only platform projection is validated.
- The correction is fail-closed and role-scoped: retain the original receipt
  byte-for-byte, map only its requested Train/Dev output path to the remote
  cleaned root, verify that one manifest against the original SHA, and do not
  open or hash Internal-test, Gold, or lineage files during training admission.

# 2026-08-06 23:45 CST wave-001 attempt-2 running

- The role-scoped portable admission fix passed the full repository gate:
  Ruff clean, 171/171 tests, compile, and `git diff --check`. Git-safe commit
  `e8deec111d5da3b8b81f013007017190d0612b76` was pushed only to the local bare
  remote; the two user-modified paper documents remain unstaged.
- The exact source archive, launcher, configs, Train/Silver quality receipt,
  and frozen inputs passed remote hashes. Linux `bash -n`, focused Ruff/tests,
  and `PASS_ROLE_SCOPED_PORTABLE_TRAIN_DEV_ADMISSION` all passed without
  opening protected files.
- Identity-preserving attempt 2 is running as Slurm steps `4161.27473` and
  `3066.39932`. After SSH disconnect, both srun launchers remained alive and
  both runs reached epoch 0 step 400/5,026. Each A800 held a training process;
  the 4161 probe observed 2,246 MiB and both launcher logs contained no error.
- Created active 20-minute heartbeat automation
  `prta-cxr-server-dev-search-monitor`. It monitors both runs, advances only
  from terminal receipts, freezes each next pair before launch, confirms a
  passing Seed-17 setting at seeds 28/43, and continues lightweight search
  until the user explicitly says stop.

# 2026-08-07 00:05 CST server Dev-search monitor

- Wave 001 remains healthy after 23 minutes. Slurm steps `4161.27473` and
  `3066.39932` are both RUNNING near the end of epoch 2 at step 4,600/5,026;
  neither training receipt exists yet, so no terminal selection is allowed.
- Both launcher PIDs remain registered, both run-registry rows are RUNNING at
  source commit `e8deec111d5da3b8b81f013007017190d0612b76`, and each A800 has one
  2,246 MiB training process. Attempt-2 logs contain only the scheduler GPU
  frequency notice and no error.
- Best/last checkpoints exist for both arms and have fresh epoch-boundary
  timestamps. All frozen config and six input hashes match the preparation and
  readiness pins; protected outcome reads remain zero. `/ipfs` has about 1.2 PB
  available, so storage is not a blocker.
- Intermediate best values are monitoring-only and were not used to alter the
  queue. At the observed approximately 7--8 minutes per epoch, the earliest
  valid early-stop window is roughly 25--35 minutes away; a later improvement
  may extend either run toward the 20-epoch maximum.

# 2026-08-07 00:25 CST server Dev-search monitor

- Both wave-001 arms remain healthy after 43 minutes. Steps `4161.27473` and
  `3066.39932` are RUNNING in epoch 5 at 1,500/5,026 and 1,600/5,026;
  neither terminal receipt exists, so the frozen queue remains unchanged.
- Each A800 still contains exactly one 2,246 MiB training process. Both
  run-registry rows remain RUNNING at source commit `e8deec1`; launcher logs
  contain no error, and fresh best/last checkpoints were written at the end of
  epoch 4.
- Config file hashes remain exactly
  `522a4d87769065b3bc4b538f0fb00ea5aba6e0b9e32cf2b2c91b27b40268678a`
  and `e5865476b57ef00176639525fe9f36d4b2169e96916109ee7992e3de528fc239`.
  Protected outcomes remain unopened and `/ipfs` storage remains non-blocking.
- The recorded intermediate best values are monitoring-only; they did not
  influence configuration or stopping. Both arms improved at epoch 4, so their
  frozen patience windows reset and terminal completion is now estimated in
  roughly 30--45 minutes if no later improvement occurs.

# 2026-08-07 00:45 CST server Dev-search monitor

- Both frozen wave-001 arms remain healthy after 63 minutes. Slurm steps
  `4161.27473` and `3066.39932` are RUNNING in epoch 7 at 4,400/5,026; neither
  terminal receipt exists, so no arm has been selected and no next wave has
  been opened.
- Both run-registry rows remain RUNNING at source commit `e8deec1`. Best/last
  checkpoints exist and the last checkpoints were refreshed at the end of
  epoch 6. Attempt-2 launcher logs still contain only
  `GpuFreq=control_disabled` and no training error.
- The allocation-4161 probe observed 90% GPU utilization and one 2,246 MiB
  training process. Allocation 3066 rejected an additional overlapping probe
  because its Slurm step limit was reached; its existing training step remains
  RUNNING and its progress/checkpoint evidence is fresh, so this is a probe
  limitation rather than a run failure.
- Frozen config file hashes still match
  `522a4d87769065b3bc4b538f0fb00ea5aba6e0b9e32cf2b2c91b27b40268678a`
  and `e5865476b57ef00176639525fe9f36d4b2169e96916109ee7992e3de528fc239`.
  `/ipfs` remains 2% used with about 1.2 PB available. Intermediate Dev values
  remain monitoring-only and did not alter the queue; if neither arm improves
  again, valid terminal receipts are expected in roughly 10--20 minutes.

# 2026-08-07 01:05 CST wave-001 terminal and confirmation launch

- Both wave-001 attempt-2 arms completed after nine epochs with valid
  `PASS_TRAINING_FINISHED` receipts. DMW=0.02 reached terminal Dev Macro-F1
  0.535648 and ODER 0.004553, clearing both immutable targets; DMW=0.05 reached
  0.525488 / 0.005000 and therefore missed the fixed F1 target.
- Frozen exact-setting confirmation `confirmation_dmw020_v1` contains only
  Seed 28 and Seed 43 copies of the qualified DMW=0.02 configuration. A
  byte-level parent comparison proved that only `experiment_id` and `seed`
  changed. Preparation and launch receipts report zero protected reads and no
  new Slurm job submission.
- Initial confirmation launch logs were preserved. Allocation 3066 rejected
  Seed 43 before output creation because the long-lived job reached its Slurm
  step limit. The first Seed-28 step on 4161 was cancelled when its SSH PTY
  closed, also before output creation.
- Identity-preserving Seed-28 attempt 2 now runs in detached Slurm step
  `4161.27567` with the original config, data, seed, method, and budget. It is
  healthy at epoch 0 step 1,200/5,026 with one 2,246 MiB training process and
  exact frozen input hashes. Seed 43 remains unstarted and will be retried
  sequentially on 4161 only after Seed 28 reaches a terminal receipt.
- Updated the existing 20-minute automation in place to monitor this sequential
  confirmation path and the subsequent frozen lightweight waves. The first
  update call omitted the required target thread ID; reading the existing
  automation record and retrying with that ID succeeded without duplication.

# 2026-08-07 01:25 CST Seed-28 confirmation monitor

- Identity-preserving Seed-28 attempt 2 remains healthy in Slurm step
  `4161.27567` after 16 minutes. It is at the epoch-1 completion/evaluation
  boundary (5,026/5,026 steps), has fresh best/last checkpoints, a RUNNING
  registry row, and no terminal receipt yet.
- Allocation 4161 contains exactly one 2,246 MiB training process. The detached
  launcher log contains only `GpuFreq=control_disabled`; the preserved failed
  attempt-1 logs are unchanged. Allocation 3066 remains batch-only and
  step-exhausted, and Seed 43 remains absent/unstarted as required.
- Both confirmation config hashes, the preparation receipt, queue, launcher,
  and all six Train/Dev input hashes match their frozen values. `/ipfs` remains
  2% used. The current Dev value is monitoring-only and did not change any
  decision; a valid terminal Seed-28 receipt is estimated in roughly 25--40
  minutes, depending on later epoch improvements.

# 2026-08-07 01:45 CST Seed-28 confirmation monitor

- Seed-28 attempt 2 remains healthy after 36 minutes in Slurm step
  `4161.27567`, now at epoch 4 step 2,300/5,026. The registry remains RUNNING,
  best/last checkpoints were refreshed after epoch 3, and no terminal receipt
  exists yet.
- Allocation 4161 still has exactly one 2,246 MiB training process. The active
  log contains only the scheduler GPU-frequency notice; all preserved failure
  logs remain unchanged. Seed 43 remains absent/unstarted and allocation 3066
  remains batch-only and step-exhausted.
- Frozen config, preparation, queue, launcher, and all six Train/Dev input
  hashes continue to match. `/ipfs` remains 2% used. The observed intermediate
  Dev value is monitoring-only and did not alter the method or queue. Because
  the best epoch advanced to epoch 3, terminal Seed-28 completion is now
  estimated in roughly 25--40 minutes if no later improvement resets patience.

# 2026-08-07 02:05 CST Seed-28 confirmation monitor

- Seed-28 attempt 2 remains healthy after 56 minutes in Slurm step
  `4161.27567`, at epoch 6 step 4,900/5,026. Its RUNNING registry row, active
  process, checkpoint timestamps, and input hashes are consistent; no terminal
  receipt exists yet.
- Allocation 4161 still hosts exactly one 2,246 MiB training process, with no
  active-log error. Seed 43 remains absent and allocation 3066 remains
  batch-only/step-exhausted. Failed launch logs remain preserved and unchanged.
- Config, preparation, queue, launcher, and all Train/Dev hashes still match;
  `/ipfs` remains 2% used. Intermediate Dev evidence was not used for a choice.
  With the patience window currently anchored at epoch 3, Seed 28 should reach
  a valid terminal receipt in roughly 8--20 minutes unless a later epoch
  improvement extends training.

# 2026-08-07 02:25 CST Seed-28 terminal and Seed-43 launch

- Seed 28 completed eight epochs with a valid `PASS_TRAINING_FINISHED` receipt.
  Terminal Dev Macro-F1 is 0.534867 and ODER is 0.005446, so the exact DMW=0.02
  setting passes both immutable targets at a second seed. Protected reads are
  zero and all six input hashes match.
- With Seed-28 step `4161.27567` gone, froze an allocation-only retry receipt
  for the unchanged Seed-43 config. Its first allocation-3066 failure log and
  absent-output evidence remain preserved; config, seed, data, method, and
  budget did not change.
- Seed 43 is now healthy in detached Slurm step `4161.27649` on allocation
  4161. It reached epoch 0 step 200/5,026 with one 2,246 MiB training process,
  a clean active log, exact frozen hashes, and no protected outcome access.
- Updated the existing 20-minute automation in place to monitor Seed 43, then
  perform the symmetric three-seed aggregate comparison before opening the
  next frozen one-axis wave. No job was submitted or cancelled.

# 2026-08-07 02:45 CST Seed-43 confirmation monitor

- Seed-43 identity-preserving attempt 2 remains healthy after 19 minutes in
  Slurm step `4161.27649`, at epoch 2 step 1,600/5,026. Its registry row is
  RUNNING, best/last checkpoints are fresh, and no terminal receipt exists.
- Allocation 4161 contains exactly one 2,246 MiB training process. The active
  Seed-43 log contains only `GpuFreq=control_disabled`; all prior failure logs
  and terminal Seed-28 artifacts remain preserved and unchanged.
- Seed-43 config and retry-receipt hashes, launcher hash, and all six Train/Dev
  input hashes match their frozen values. Allocation 3066 remains batch-only
  and step-exhausted; `/ipfs` remains 2% used. Intermediate Dev evidence was
  not used for selection. At the current pace, terminal completion is expected
  in roughly 25--45 minutes unless later improvement extends patience.

# 2026-08-07 03:05 CST Seed-43 confirmation monitor

- Seed-43 attempt 2 remains healthy after 39 minutes in Slurm step
  `4161.27649`, at epoch 4 step 4,100/5,026. Its registry remains RUNNING,
  checkpoints are fresh, and no terminal receipt exists.
- Allocation 4161 still contains exactly one 2,246 MiB training process; the
  active log has no error. Seed-28 terminal artifacts and all failed launch
  logs remain immutable, while allocation 3066 remains batch-only and
  step-exhausted.
- Config, retry receipt, launcher, and all Train/Dev input hashes continue to
  match, with `/ipfs` at 2% use. Intermediate Dev evidence was monitoring-only.
  The current patience anchor is epoch 2, so terminal completion is expected
  in roughly 15--30 minutes if no later improvement extends the run.

# 2026-08-07 03:35 CST three-seed confirmation and LR wave launch

- Seed 43 completed seven epochs with terminal Dev Macro-F1 `0.533353` and
  ODER `0.004196`. Together with Seeds 17/28, the exact DMW=0.02 setting is now
  3/3 above the fixed Macro-F1 target and 3/3 below the fixed ODER ceiling;
  every receipt reports zero protected reads.
- DMW=0.02 three-seed mean +/- sample SD is `0.534623 +/- 0.001167` Macro-F1
  and `0.004732 +/- 0.000644` ODER. Seed-matched B403 is
  `0.524565 +/- 0.003460` and `0.006279 +/- 0.001690`, giving mean differences
  of `+0.010057` Macro-F1 and `-0.001547` ODER. DMW=0.02 is better on both axes
  for each of the three paired seeds. This is aggregate-only Train/Dev evidence.
- Wrote immutable confirmation aggregate receipt SHA-256
  `070df3ceb1e94b13675b8ca1d0522597280ad5da64078e6f6a2469ff17a0e2ee`.
  Historical `HOLD_DEVELOPMENT_GATE` and `STOP_CURRENT_PRTA_ROUTE` remain
  unchanged; Internal-test and Gold were not opened.
- Froze `wave002_lr_v1` as the next one-axis wave: DMW=0.02 with learning rates
  `5e-5` and `2e-4`, Seed 17, unchanged optimizer family/data/method/budget.
  Because allocation 3066 is step-exhausted, both arms are assigned strictly
  sequentially to allocation 4161. Frozen config hashes are
  `e0fcb7acca0525a536f6ab9b82a40eba7b66636df46b812eb5c15fd407521ed5`
  and `9d0ca38ae858d103742498fda544d5d1122fb066da5f65cc8e03276c3be8da76`.
- Launched only `SVR-FG1-DMW020-LR050-S17` in detached Slurm step
  `4161.27720`. It is healthy at epoch 0 step 400/5,026 with one active child,
  exact six input hashes, a clean launcher log, and `/ipfs` at 2% use.
  `SVR-FG1-DMW020-LR200-S17` remains frozen and unstarted.
- The remote login node uses Python 3.9, so the first preparation script failed
  before any artifact write on `datetime.UTC`, then again before any write on
  `zip(strict=True)`. Replaced these with Python-3.9-compatible forms and the
  unchanged preparation completed. The first launch guard also matched the
  allocation's `.batch` step; narrowed it to non-batch child steps before the
  one authorized training launch.

# 2026-08-07 03:45 CST LR050 monitor

- `SVR-FG1-DMW020-LR050-S17` remains healthy in Slurm step `4161.27720`
  after 12 minutes, at epoch 1 step 2,700/5,026. Its registry row is RUNNING,
  `best.pt` and `last.pt` were written at the epoch-0 boundary, and no terminal
  receipt exists yet.
- The launcher log contains only `GpuFreq=control_disabled`; frozen preparation,
  aggregate, and both config hashes match exactly. All six Train/Dev input
  hashes remain unchanged, `/ipfs` is 2% used, and LR200 is still absent and
  unstarted as required.
- The observed epoch-0 Dev metrics are monitoring-only and did not change the
  queue or method. At the current roughly 7--8 minutes per epoch, the earliest
  valid early-stop window is approximately 30--40 minutes away unless later
  terminal improvements extend patience.

# 2026-08-07 04:05 CST LR050 monitor

- LR050 remains healthy after 32 minutes in Slurm step `4161.27720`, at the
  epoch-3 completion boundary (5,026/5,026). Its registry/process state is
  consistent, best/last checkpoints were refreshed at epoch 2, and no terminal
  receipt exists.
- Frozen preparation and config hashes, all six Train/Dev input hashes, and the
  clean launcher log remain unchanged. LR200 is still absent/unstarted and
  `/ipfs` remains 2% used; no duplicate child or protected-cohort access was
  introduced.
- Epoch-2 Dev values are monitoring-only and did not alter the frozen queue.
  With patience currently anchored at epoch 2 and the minimum-epoch rule still
  active, a valid terminal receipt is estimated in roughly 20--35 minutes if
  no later improvement extends the run.

# 2026-08-07 04:25 CST LR050 monitor

- LR050 remains healthy after 52 minutes in Slurm step `4161.27720`, now at
  epoch 6 step 2,300/5,026. Best and last checkpoints are fresh, the active log
  is clean, and no terminal receipt exists.
- Its frozen config/input identity remains unchanged; LR200 is still absent and
  unstarted, `/ipfs` remains 2% used, and no protected cohort was touched.
  Intermediate Dev values were not used to alter the queue or stopping rule.
- The patience anchor advanced to epoch 4. If there is no later terminal
  improvement, early stopping is expected in approximately 15--30 minutes;
  any valid improvement may extend the frozen run toward its 20-epoch cap.

# 2026-08-07 04:49 CST LR050 terminal and LR200 launch

- LR050 completed nine epochs with `PASS_TRAINING_FINISHED`. Its terminal best
  Dev Macro-F1 is `0.520378` and ODER is `0.006160`; it therefore misses both
  immutable targets (`0.529094` / `0.005535`) and is preserved as a losing run.
  The receipt reports zero protected reads and SHA-256
  `561769f56bb230a3be64038b7f76f9616416206ae37f4491c622bc0b7b43fb8e`.
- After Slurm step `4161.27720` disappeared, verified LR050 terminal identity,
  exact LR200 config hash, absent LR200 output/log, and no active child. Then
  launched the unchanged frozen LR200 arm sequentially in detached step
  `4161.27796`; no parent job was submitted or cancelled.
- LR200 is healthy at epoch 0 step 300/5,026 with a RUNNING registry row, clean
  launcher log, unchanged six Train/Dev input hashes, and `/ipfs` at 2% use.
  Its launch receipt SHA-256 is
  `8799eda75117208f9a68116b68b3b76f4d575b5067714950f0dd14db46839303`.
- The launch wrapper's 12-second post-launch assertion ran before the first
  progress receipt appeared and exited after the child had already started.
  A read-only check 15 seconds later confirmed the same detached child was
  healthy; no duplicate launch or scientific change was made.

# 2026-08-07 05:05 CST LR200 monitor

- LR200 remains healthy after 17 minutes in Slurm step `4161.27796`, at epoch
  2 step 300/5,026. Its RUNNING registry row, active process, and fresh best/last
  checkpoints agree; no terminal receipt exists.
- Preparation, config, and launch-receipt hashes match their frozen values.
  All six Train/Dev input hashes remain unchanged, the launcher log is clean,
  `/ipfs` remains 2% used, and protected outcomes remain unopened.
- Intermediate epoch metrics are monitoring-only and did not alter the queue.
  At the observed roughly 7--8 minutes per epoch, the earliest valid early-stop
  window is about 30--40 minutes away unless later improvement extends patience.

# 2026-08-07 05:25 CST LR200 monitor

- LR200 remains healthy after 37 minutes in Slurm step `4161.27796`, at epoch
  4 step 2,800/5,026. Its RUNNING registry/process state and fresh best/last
  checkpoints agree, with no terminal receipt or launcher error.
- Frozen hashes and all six Train/Dev input hashes remain unchanged; `/ipfs`
  is 2% used and protected cohorts remain sealed. Intermediate Dev evidence was
  not used for selection or mutation.
- The patience anchor advanced to epoch 2. If no later terminal improvement
  occurs, a valid terminal receipt is estimated in roughly 20--35 minutes;
  later improvement may extend the unchanged run.

# 2026-08-07 05:45 CST LR200 monitor

- LR200 remains healthy after 57 minutes in Slurm step `4161.27796`, at the
  epoch-6 completion boundary. Its process/registry state, fresh checkpoints,
  clean log, and frozen hashes are consistent; no terminal receipt exists.
- All six Train/Dev input hashes remain exact, `/ipfs` remains 2% used, and no
  protected cohort was opened. Intermediate Dev metrics were monitoring-only
  and did not change the run or queue.
- Patience is anchored at epoch 4. If no later terminal improvement resets it,
  the run should finish in roughly 10--25 minutes; a later improvement may
  extend the unchanged budget.

# 2026-08-07 06:05 CST LR200 monitor

- LR200 remains healthy after 77 minutes in Slurm step `4161.27796`, at epoch
  9 step 2,700/5,026. Its best checkpoint advanced at epoch 7, the last
  checkpoint and progress file are fresh, and no terminal receipt exists.
- The active log remains clean, frozen identity is unchanged, `/ipfs` is 2%
  used, and protected outcomes remain unopened. Intermediate Dev values were
  not used to alter the queue or stopping rule.
- Patience is now anchored at epoch 7. If no later terminal improvement occurs,
  completion is estimated in roughly 15--30 minutes; a valid later improvement
  may extend the same frozen run.

# 2026-08-07 06:25 CST LR200 monitor

- LR200 remains healthy after 97 minutes in Slurm step `4161.27796`, at the
  epoch-11 completion boundary. The best checkpoint advanced at epoch 9;
  process, registry, checkpoint, log, and input-hash evidence remain consistent,
  with no terminal receipt yet.
- `/ipfs` remains 2% used and protected cohorts remain sealed. The observed
  improvement is explicitly monitoring-only: it did not trigger selection,
  confirmation, config changes, or an altered stopping rule.
- Patience is anchored at epoch 9. If no later terminal improvement occurs,
  completion is estimated in roughly 15--30 minutes; only the final receipt
  may determine whether LR200 qualifies.

# 2026-08-07 06:50 CST LR200 terminal and exact confirmation launch

- `SVR-FG1-DMW020-LR200-S17` completed 14 epochs with
  `PASS_TRAINING_FINISHED`. Its terminal best Dev Macro-F1 is `0.537901` and
  best-epoch ODER is `0.003303`, so it clears the unchanged joint target and
  improves over confirmed LR=1e-4 Seed 17 on both constrained axes. Its
  training receipt SHA-256 is
  `a06a4c3e41b10cd0b714c863b28c0a135df62bed44f7d841c07292cbac59c707`.
- Closed `wave002_lr_v1` from terminal evidence only. LR050 remains preserved
  as a losing arm; LR200 is the selected Seed-17 winner. The immutable
  aggregate receipt SHA-256 is
  `644994729ce34991bd5331aef5e3890f4575aa1f8b00a9c3734d85d34517035d`.
- Froze exact LR=2e-4 confirmation for seeds 28/43. Preparation SHA-256 is
  `e6f7ae16fcae923a32ed3509c3f83c2de535ed6c0e84d3103494af81c8fef137`;
  Seed-28/43 config hashes are respectively
  `8864bccab797d2532dfcc32bef9389005dbcff877059664f7599cea0353141cb`
  and `d3a02bca316186ee6f5ed4562fb3d2e5c4ba3ca86688b898bfbb0d1009888085`.
- The first Seed-28 control-script attempt failed before launch because remote
  Python 3.9 does not accept `Path.write_text(newline=...)`. The failure record
  was preserved, the unsupported control-only argument was removed, and the
  unchanged scientific config launched in step `4161.27919`. It is healthy at
  epoch 0 step 1,100/5,026; Seed 43 remains absent and unstarted.
- A subsequent GPU-status check briefly created a separate overlapping
  `nvidia-smi` Slurm probe while the training step was active. It completed
  immediately, read no dataset or outcome, and changed no config, process, or
  budget. Future monitoring will use the existing training state and avoid
  concurrent diagnostic steps. Protected outcomes remain sealed and all six
  Train/Dev hashes are exact.

# 2026-08-07 07:05 CST LR200 Seed-28 confirmation monitor

- Seed 28 remains healthy in the sole child step `4161.27919`, at epoch 1
  step 5,000/5,026 after about 16 minutes. Progress, registry, process, and the
  clean launcher log agree; no terminal receipt exists.
- Config, preparation, and launch-receipt hashes remain exact, Seed 43 is
  absent/unstarted, `/ipfs` remains 2% used, and protected cohorts remain
  sealed. Intermediate Dev evidence was not used to alter the frozen run.
- With roughly eight minutes per epoch, the earliest valid unchanged
  early-stop window is approximately 35--50 minutes away unless a later
  improvement extends patience.

# 2026-08-07 07:25 CST LR200 Seed-28 confirmation monitor

- Seed 28 remains healthy in the sole child step `4161.27919`, at epoch 4
  step 2,100/5,026 after about 36 minutes. Progress, process, registry, and the
  clean launcher log remain consistent; no terminal receipt exists.
- Frozen config/preparation/launch hashes remain exact, Seed 43 remains
  absent and unstarted, storage is healthy, and protected outcomes remain
  unopened. Intermediate Dev values did not change selection or stopping.
- Patience is currently anchored at epoch 3. If no later improvement extends
  it, a valid terminal receipt is expected in roughly 20--35 minutes.

# 2026-08-07 07:45 CST LR200 Seed-28 confirmation monitor

- Seed 28 remains healthy in the sole child step `4161.27919`, at epoch 6
  step 4,700/5,026 after about 56 minutes. Its progress/process state and
  clean launcher log agree; no terminal receipt exists.
- Frozen hashes remain exact, Seed 43 is still absent/unstarted, storage is
  healthy, and protected outcomes remain sealed. No intermediate metric was
  used to mutate the run or queue.
- Patience is anchored at epoch 4. If it is not reset by a later valid
  improvement, terminal completion is expected in roughly 10--25 minutes.

# 2026-08-07 08:05 CST LR200 Seed-28 confirmation monitor

- Seed 28 remains healthy in the sole child step `4161.27919`, at epoch 9
  step 1,900/5,026 after about 76 minutes. Process, progress, registry, and the
  clean launcher log agree; no terminal receipt exists.
- Frozen identity remains exact, Seed 43 is absent/unstarted, storage remains
  healthy, and protected outcomes remain unopened. Intermediate Dev values
  were not used for selection or mutation.
- Patience is anchored at epoch 6. If no later valid improvement resets it,
  the unchanged run should finish in roughly 10--20 minutes.

# 2026-08-07 08:25 CST LR200 Seed-28 terminal and Seed-43 launch

- Seed 28 completed 11 epochs with `PASS_TRAINING_FINISHED`. Terminal best Dev
  Macro-F1 is `0.528899` and best-epoch ODER is `0.006964`; it misses both
  immutable joint targets and is preserved unchanged as a non-qualifying
  confirmation seed. Receipt SHA-256 is
  `64f66ef2735baff4439b5aea160587b54871f66c62ae4c88201d1bd2aad79387`.
- After step `4161.27919` disappeared, verified the exact receipt/config/input
  identity and absence of any child step or Seed-43 output. Then launched the
  unchanged frozen Seed-43 config sequentially in step `4161.28017`; no parent
  job was submitted or cancelled.
- Seed 43 is healthy at epoch 0 step 300/5,026. Its launch receipt SHA-256 is
  `409c522e54ea170d11c4669e097c5a5ef732bcfab23b1035ef762a68204abeb8`;
  launcher log is clean, protected outcomes remain sealed, and all six
  Train/Dev hashes remain exact.

# 2026-08-07 08:45 CST LR200 Seed-43 confirmation monitor

- Seed 43 remains healthy in the sole child step `4161.28017`, at epoch 2
  step 1,900/5,026 after about 19 minutes. Progress, process, registry, and the
  clean launcher log agree; no terminal receipt exists.
- Config, preparation, and launch hashes remain exact, storage is healthy,
  and protected outcomes remain unopened. Intermediate Dev evidence was not
  used to change the frozen run.
- At the observed roughly eight minutes per epoch, the earliest unchanged
  early-stop window is approximately 30--45 minutes away unless a later valid
  improvement extends patience.

# 2026-08-07 09:05 CST LR200 Seed-43 confirmation monitor

- Seed 43 remains healthy in the sole child step `4161.28017`, at epoch 4
  step 4,500/5,026 after about 39 minutes. Progress/process state and the clean
  launcher log remain consistent; no terminal receipt exists.
- Frozen hashes remain exact, storage is healthy, and protected outcomes stay
  sealed. Intermediate Dev evidence was not used to alter the run or queue.
- Patience is currently anchored at epoch 2. If no later valid improvement
  extends it, terminal completion is expected in roughly 20--35 minutes.

# 2026-08-07 09:25 CST LR200 Seed-43 confirmation monitor

- Seed 43 remains healthy in the sole child step `4161.28017`, at epoch 7
  step 1,700/5,026 after about 59 minutes. Process/progress state and the clean
  launcher log agree; no terminal receipt exists.
- Frozen hashes and storage remain healthy, and protected outcomes stay
  sealed. No intermediate evidence changed the config, queue, or stopping rule.
- Patience advanced to epoch 6. If no later valid improvement resets it,
  terminal completion is expected in roughly 20--35 minutes.

# 2026-08-07 09:45 CST LR200 Seed-43 confirmation monitor

- Seed 43 remains healthy in the sole child step `4161.28017`, at epoch 9
  step 4,300/5,026 after about 79 minutes. Process/progress state and the clean
  launcher log agree; no terminal receipt exists.
- Frozen hashes and storage remain healthy, and protected outcomes remain
  sealed. Intermediate Dev evidence did not alter the config or stopping rule.
- Patience advanced to epoch 8. If no later valid improvement resets it,
  terminal completion is expected in roughly 25--40 minutes.

# 2026-08-07 10:05 CST LR200 Seed-43 confirmation monitor

- Seed 43 remains healthy in the sole child step `4161.28017`, at epoch 12
  step 1,400/5,026 after about 99 minutes. Process/progress state and the clean
  launcher log agree; no terminal receipt exists.
- Frozen identity and storage remain healthy, and protected outcomes remain
  unopened. Intermediate Dev evidence did not alter the run or queue.
- Patience remains anchored at epoch 8. If no valid improvement appears in the
  current epoch, terminal completion is expected in roughly 5--15 minutes.

# 2026-08-07 10:25 CST LR200 confirmation closure and wave003 launch

- Seed 43 completed 13 epochs with `PASS_TRAINING_FINISHED`: terminal best
  Dev Macro-F1 `0.531940`, ODER `0.006785`, receipt SHA-256
  `5a54332112301641804cd14235fab51b2210d313dc1a49dedee8888886b1c176`.
  It passes the F1 floor but misses the ODER ceiling; protected reads remain
  zero and all frozen input/config hashes match.
- Closed LR=2e-4 confirmation from all three terminal seeds. Only Seed 17
  passes the fixed joint target; the three-seed mean Macro-F1/ODER are
  `0.532913` / `0.005684`, worse than confirmed LR=1e-4 DMW=0.02 by
  `-0.001710` / `+0.000952`. The fail-closed aggregate receipt SHA-256 is
  `bcc6624e6931059f30e316d3f3913c8e81e4b5eb57f0724017ef3cf3768855f3`.
- Retained confirmed LR=1e-4 DMW=0.02 and froze the next small one-axis wave:
  DMW=0.01 then 0.03, both Seed 17, unchanged elsewhere and sequential on
  allocation 4161. Preparation SHA-256 is
  `366058dd88e5cfd26a9d4e68651d927b3ae8af9f5b93eb90fcb9f9df2c2d56fc`.
- DMW010 launched in step `4161.28142` and is healthy at epoch 0 step
  300/5,026. Its launch receipt SHA-256 is
  `f5d9d2f4ec829114c30da035873507733ba1a921ee52ea46a8bd051ce82117c2`;
  DMW030 remains absent/unstarted, with protected cohorts still sealed.

# 2026-08-07 10:45 CST wave003 DMW010 monitor

- DMW010 remains healthy in the sole child step `4161.28142`, at the epoch-1
  completion boundary after about 16 minutes. Progress/process state and the
  clean launcher log agree; no terminal receipt exists.
- Config, preparation, and launch hashes remain exact, DMW030 remains
  absent/unstarted, storage is healthy, and protected outcomes remain sealed.
- Intermediate Dev evidence was not used to mutate the run. At roughly eight
  minutes per epoch, the earliest unchanged terminal window is approximately
  35--50 minutes away unless later valid improvement extends patience.

# 2026-08-07 expanded lightweight search objective

- The user requested more tuning because the confirmed DMW=0.02 gain over
  B403 is about `+1.006` percentage points, below the desired 2--3 points.
- Kept the historical gate unchanged and added a separate exploratory target:
  Seed-17 Macro-F1 at least `0.546094` with ODER at most `0.005535`, followed
  by exact seeds 28/43; reproducible three-seed success requires mean
  Macro-F1 at least `0.544565` and non-worse mean ODER versus B403.
- The active DMW010/030 wave is unchanged. Subsequent permitted lightweight
  axes are focal gamma, class-balance beta, weight decay, dropout, and margin
  magnitude, tested in frozen two-arm waves. No protected cohort, data change,
  large architecture change, or silent multi-axis mutation is authorized.

# 2026-08-07 exploratory best-seed extension

- The user authorized finding three favorable seeds. Added a predeclared
  12-seed Dev sweep, but only after one parameter setting is frozen; this
  prevents simultaneous parameter-and-seed cherry-picking.
- The fixed pool is `3/7/11/17/23/28/31/37/43/47/53/59`. Select the top three
  by terminal Macro-F1 only among seeds satisfying ODER <= `0.005535`, retain
  all outcomes, and label the result `EXPLORATORY_BEST3_OF_12`.
- Fixed seeds 17/28/43 remain the scientific comparison. The selected top
  three cannot be reported as an unbiased three-seed mean or erase failed
  seeds; no Internal-test/Gold access is authorized.

# 2026-08-07 11:05 CST wave003 DMW010 monitor

- DMW010 remains healthy in the sole child step `4161.28142`, at epoch 4
  step 2,200/5,026 after about 36 minutes. Progress/process state and the clean
  launcher log agree; no terminal receipt exists.
- Frozen hashes remain exact, DMW030 remains absent/unstarted, storage is
  healthy, and protected outcomes remain sealed. Intermediate evidence did
  not change the run or queue.
- Patience is anchored at epoch 2. If no later valid improvement extends it,
  terminal completion is expected in roughly 20--35 minutes.

# 2026-08-07 11:25 CST wave003 DMW010 monitor

- DMW010 remains healthy in the sole child step `4161.28142`, at epoch 6
  step 4,800/5,026 after about 56 minutes. Process/progress state and the clean
  launcher log agree; no terminal receipt exists.
- Frozen hashes remain exact, DMW030 remains absent/unstarted, storage is
  healthy, and protected outcomes remain sealed. Intermediate Dev values did
  not alter the run or queue.
- Patience is anchored at epoch 4. If no later valid improvement resets it,
  terminal completion is expected in roughly 15--30 minutes.

# 2026-08-07 11:45 CST DMW010 terminal and DMW030 launch

- `SVR-FG1-DMW010-S17` completed 9 epochs with
  `PASS_TRAINING_FINISHED`: terminal best Dev Macro-F1 `0.538661`, ODER
  `0.005178`, best epoch 4, and terminal receipt SHA-256
  `c4061a87039738a8a28a35f80d48cb185f6b930393832c41ed95c0d7625c072d`.
  All frozen input/config hashes match and protected-read count remains zero.
- DMW010 passes the immutable joint gate and improves Seed-17 Macro-F1 over
  confirmed DMW=0.02 by `+0.003013`, but ODER is `+0.000625` higher and it
  does not reach the aspirational `0.546094` Seed-17 target.
- After verifying the exact DMW010 receipt, wave preparation/config hashes,
  absence of another child, and absence of prior DMW030 output, launched the
  unchanged `SVR-FG1-DMW030-S17` sequentially in step `4161.28187`. Launch
  receipt SHA-256 is
  `41f8069621900a291c2bb9125c6a4eb9ceb2e0d12b482e04edbb9647c24be5f9`.
  It is healthy at epoch 0 step 800/5,026; no protected cohort was opened.

# 2026-08-07 12:05 CST wave003 DMW030 monitor

- DMW030 remains healthy in the sole child step `4161.28187`, at epoch 2
  step 1,100/5,026 after about 18 minutes. Progress/process state and the clean
  launcher log agree; no terminal receipt exists.
- Frozen input identity remains exact and protected outcomes remain sealed.
  Intermediate Dev evidence was observed only as part of the registered
  progress receipt and did not alter the run, queue, or stopping rule.
- Preparation/config/launch hashes remain exactly
  `366058dd...` / `3837e43f...` / `41f80696...`; registry status is `RUNNING`,
  the shared filesystem has about 1.2 PB available, and no terminal receipt
  exists. A supplemental resource probe used an unsupported `sstat State`
  field and direct compute-node SSH is not authenticated from the login node;
  both failures were read-only, so subsequent checks will use step-valid
  Slurm control fields without opening a concurrent diagnostic step.
- A corrected Slurm control probe confirms step `4161.28187` is `RUNNING` on
  `gpu01` with one GPU and four CPUs; `sstat` reports about 37.5 GB average
  RSS and 38.2 GB maximum RSS. No second child step was opened.
- A fixed remote status script confirms progress advanced to epoch 2 step
  2,200/5,026, both `best.pt` and `last.pt` exist at about 310 MB, progress and
  checkpoint timestamps continue advancing, and the launcher log contains no
  error/traceback/OOM signature. The run remains healthy and unchanged.

# 2026-08-07 12:22 CST dual-allocation throughput authority

- The user made both server GPUs available. Live Slurm state now differs from
  the earlier step-exhausted snapshot: allocation 3066 was freshly restarted
  at 12:18 CST with one GPU and only `3066.batch`; allocation 4161 still has
  the sole DMW030 child `4161.28187`.
- DMW030 remains the unchanged single-GPU arm; attaching a second GPU would
  alter its execution identity and is not allowed. The safe speedup is to
  qualify 3066 for the same shared Train/Dev environment now, then run the next
  already-planned two-arm wave concurrently, one frozen arm per allocation,
  after wave003 closes from terminal evidence.
- Launched the engineering-only allocation-3066 Train/Dev asset/GPU probe as
  step `3066.1`; launch receipt SHA-256 is
  `e1b9d6218143a5526e7cc2302aacf3ade9ede9a43d6d4f7a4c9075b68e0ca2bc`.
  It explicitly unsets formal-run authority, starts no experiment, and binds
  protected-read count zero. The probe is still running its hash checks.
- The probe is terminal `PASS_SUES_TRAIN_DEV_ASSET_PROBE`: one NVIDIA A800
  80GB is visible, Train/Dev counts are exactly 80,402/11,201, cache probe is
  8x197x768, all six expected hashes match, protected paths opened are zero,
  and no formal experiment started. Output SHA-256 is
  `39517d8ba68f05de1e3d6903ded636c13ecaa1ae2bdb64d93bb52a7752d05bb1`.
- DMW030 remains healthy and unchanged on allocation 4161 at epoch 4 step
  2,700/5,026 after about 37 minutes. Allocation 3066 is now idle and ready;
  no second scientific arm is launched before the wave003 terminal decision.

# 2026-08-07 12:27 CST wave003 dual-allocation monitor

- DMW030 remains healthy in the sole scientific child step `4161.28187`, at
  epoch 4 step 4,100/5,026 after about 39 minutes. Checkpoints and progress
  continue updating, and the launcher log has no error/traceback/OOM signature.
- Allocation 3066 has only its batch step and remains qualified/idle for the
  next terminally selected parallel arm. No intermediate metric changed the
  frozen run or opened another scientific child; protected cohorts stay sealed.

# 2026-08-07 12:32 CST allocation topology correction

- Fresh Slurm evidence shows allocations 3066 and 4161 are both on physical
  node `gpu01`; each independently owns one GPU and four CPUs. They are not two
  different compute nodes, although they still support two independent
  single-GPU training runs.
- Allocation 3066 currently has user-owned telemetry step `3066.2`
  (`hpc-gpu-telemetry`) requesting its one GPU. It was not started by this
  workflow and will not be cancelled or overlapped. DMW030 remains unchanged
  on 4161; the second training arm waits until `3066.2` exits.

# 2026-08-07 13:00 CST allocation migration authority

- The user replaced retired allocation 4161 with retained allocation 9929 and
  authorized 9929 plus 3066 as two independent single-GPU workers. Allocation
  4161 is absent; no future command may target it.
- DMW030 was externally cancelled with step 4161.28187 at 12:34:15 CST. Its
  partial output, checkpoints, and launcher log are preserved, and no terminal
  receipt exists. The checkpoint stores model/optimizer/config/input/history,
  but not data-loader/RNG state; therefore a mid-epoch continuation cannot be
  described as exact trajectory preservation.
- The safe migration is an unchanged fresh DMW030 attempt on 9929 in a new
  output namespace, plus the pre-frozen focal-gamma 0.5 arm on 3066. Both keep
  the same Train 80,402 / Dev 11,201 boundary and zero protected reads. The
  unrelated telemetry steps remain untouched.

# 2026-08-07 12:52 CST 9929/3066 independent launches

- Allocation 9929 passed the same fail-closed Train/Dev readiness probe as
  3066: A800 runtime, Train 80,402 / Dev 11,201, exact six inputs, protected
  reads zero, and no formal experiment. Probe output SHA-256 is
  `39517d8ba68f05de1e3d6903ded636c13ecaa1ae2bdb64d93bb52a7752d05bb1`;
  launch receipt SHA-256 is
  `1a5b8057cfb023c7965fcad08c13573eeba69f8d85d7fcbc9aa15ad6bce3787d`.
- Preserved the externally cancelled DMW030 partial checkpoint at SHA-256
  `712bc5b1f5ac550a7df3b3a2642161bd03776e9e540545cd860f26c71f3c3f7a`
  and launched an unchanged fresh attempt in a new directory on allocation
  9929. It is running in step `9929.2` at epoch 0 step 300/5,026.
- Froze `wave004_focal_gamma_v1` before either focal arm ran. Gamma 0.5 config
  SHA-256 is `9df910cb258cc2f73a99e9f2f760c5d9ab9b5a04a71292e0faedddc83380ad1d`;
  gamma 1.5 config SHA-256 is
  `f7f6b1ec8e7cf51751582884ce4ea9da20692bebe7a5e5b8a09c43d6c9e2437e`;
  preparation SHA-256 is
  `ac39e8878b7899b0b3300d7d08ab0315486b84fa0311cb9872d3ab985592de9b`.
  Gamma 0.5 is running independently in step `3066.3` at epoch 0 step
  300/5,026; gamma 1.5 remains frozen and unstarted.
- Dual independent launch receipt SHA-256 is
  `5a2f305eccf16c10abb878480bef6e1d3e8e8d6e8b870e78a1f52aa16090142b`.
  Both user telemetry steps remain present, no parent job was submitted or
  cancelled, and Internal-test/Gold remain unopened.

# 2026-08-07 12:54 CST first dual-allocation monitor

- Both independent scientific children remain RUNNING: DMW030 attempt 2 in
  `9929.2` and focal gamma 0.5 in `3066.3`. Each advanced to epoch 0 step
  2,100/5,026; neither has a terminal receipt or launcher error.
- Slurm still shows exactly one scientific child plus the preserved telemetry
  step on each allocation. Current RSS is about 3.6 GiB on 9929 and 18.7 GiB
  on 3066 while initialization/training proceeds. Frozen identities are
  unchanged and no protected cohort was opened.

# 2026-08-07 13:14 CST dual-allocation monitor

- DMW030 attempt 2 (`9929.2`) and focal gamma 0.5 (`3066.3`) remain healthy
  and synchronized near the end of epoch 2 at step 4,400/5,026. Both have a
  valid best epoch 0 checkpoint; neither has a terminal receipt.
- Slurm still shows exactly one scientific child and the untouched telemetry
  step per allocation. Logs contain no traceback/error/OOM/non-finite marker,
  frozen wave/config hashes remain exact, and shared storage has about 1.2 PB
  free. With minimum epoch 6 and unchanged early stopping, the earliest likely
  terminal window is roughly another 25--50 minutes.

# 2026-08-07 13:34 CST dual-allocation monitor

- Both independent runs remain healthy and aligned at epoch 5 step
  1,500/5,026. DMW030 attempt 2 stays in `9929.2`; focal gamma 0.5 stays in
  `3066.3`. Both have valid 310 MB best/last checkpoints with best epoch 4,
  RUNNING registry rows, and no terminal receipt.
- No launcher error/OOM/non-finite marker is present, telemetry steps remain
  untouched, and protected cohorts remain sealed. If best epoch 4 is not
  extended, unchanged patience makes the earliest terminal point epoch 8,
  approximately another 20--40 minutes.

# 2026-08-07 13:54 CST dual-allocation monitor

- Both independent children remain healthy at epoch 7 step 4,100/5,026 with
  best epoch 4, one scientific step per allocation, intact checkpoints, and no
  terminal receipt or launcher error. Telemetry and protected-data boundaries
  remain unchanged.
- If epoch 8 does not improve on best epoch 4, the frozen patience rule should
  stop both runs after the next epoch evaluation, likely within about
  8--20 minutes. No queue or parameter decision has been made from the
  intermediate metrics.

# 2026-08-07 14:14 CST wave003 closure and focal gamma 1.5 launch

- Both earlier children completed nine epochs with
  `PASS_TRAINING_FINISHED`, unchanged early stopping, exact input hashes, and
  zero protected reads. DMW030 attempt 2 ended at Macro-F1 `0.526203` and
  ODER `0.006607`, failing both original joint thresholds; receipt SHA-256 is
  `025192b10814af245b9602f8184d7ea51de6e5da62d1095c0957a0d57ae157bc`.
- Wave003 closed with aggregate SHA-256
  `ead625a62d5117cd9a9264795d6ead58da69bf900d11dd0378ca06481ce1b0dd`.
  DMW010 remains the highest-F1 qualified Seed-17 arm (`0.538661` /
  `0.005178`), but it did not reach the aspirational target, so seeds 28/43
  confirmation was not opened.
- Focal gamma 0.5 ended at Macro-F1 `0.537393` and ODER `0.004464`, passing
  the original joint gate but missing the aspirational target; receipt SHA-256
  is `01747bf3843c4999e1120e5fb6f54b18f78444d840cb41568082edab926b2c5a`.
- Launched the already-frozen gamma 1.5 arm unchanged on allocation 9929 as
  step `9929.3`; launch receipt SHA-256 is
  `8f49e712690c3f5e1138342c40a66f889af714ff3c845ee08750201b2dd56a71`.
  It is RUNNING at epoch 0 step 100/5,026. Allocation 3066 is intentionally
  idle until wave004 closes; its telemetry remains untouched.

# 2026-08-07 14:34 CST focal gamma 1.5 monitor

- Gamma 1.5 remains healthy in the sole scientific step `9929.3`, at epoch 2
  step 2,100/5,026 with a valid best epoch 0 and 310 MB best/last checkpoints.
  The registry is RUNNING, no terminal receipt or launcher error exists, and
  allocation 3066 remains intentionally idle except for telemetry.
- Frozen identity and protected-data boundaries remain exact; shared storage
  has about 1.2 PB free. Under the unchanged minimum-epoch/patience rules, the
  earliest likely terminal window is roughly another 20--40 minutes.

# 2026-08-07 14:54 CST focal gamma 1.5 monitor

- Gamma 1.5 remains healthy in `9929.3`, at epoch 4 step 3,900/5,026 with
  best epoch 2 and intact 310 MB best/last checkpoints. No terminal receipt,
  launcher error, extra scientific child, or protected-cohort access exists.
- Allocation 3066 remains intentionally idle except for telemetry. If no later
  epoch improves on epoch 2, unchanged patience permits termination after
  epoch 6 evaluation, likely in another 10--25 minutes.

# 2026-08-07 15:14 CST focal gamma 1.5 monitor

- Gamma 1.5 remains healthy in `9929.3`, at epoch 7 step 1,000/5,026. Its
  best epoch advanced from 2 to 4, so the frozen early-stopping window also
  extended; no terminal receipt, error marker, or identity drift exists.
- Allocation 3066 remains intentionally idle except for telemetry, and no
  protected cohort was opened. If epoch 4 remains best, terminal evaluation is
  expected after epoch 8, approximately another 10--25 minutes.

# 2026-08-07 15:34 CST wave004 closure and beta-axis launch

- Gamma 1.5 completed nine epochs with `PASS_TRAINING_FINISHED` but failed the
  joint gate: Macro-F1 `0.525474`, ODER `0.007321`; receipt SHA-256 is
  `ec7aaca5fc6644f6246525efaaa26abd4a5dab5d927c46d04f751e631effde9c`.
  Wave004 therefore selects qualified gamma 0.5 and closes with aggregate
  SHA-256 `5a681932586e2fdc3ce3b15d323f2cb2d85c6966e099ec8e61e2fc4bd20aac85`.
  Neither focal arm reaches the aspirational target.
- Froze `wave005_class_balance_beta_v1` around DMW010, the globally
  highest-F1 completed jointly qualified Seed-17 setting. Preparation SHA-256
  is `ee3bc66a8db5bc96e7245ea402bee93b7883d7e2d02b682b09a16c07fb749d91`.
- Beta 0.999 config SHA-256
  `e272f9556ab1dd3c3d448fa6dd6813a9e33b33c815e508b7bbb23264a117a7a2`
  is RUNNING in `9929.4`; launch receipt SHA-256 is
  `fbaca88828828ecffbe717390e765a5321356f0c9b53719dbca78b23c46b8d30`.
  Beta 0.99999 config SHA-256
  `62ba635ed56f8b2f3978f28b3b99981d600c8f8d1c33ca60039a36cd6cb4fcd3`
  is RUNNING in `3066.4`; launch receipt SHA-256 is
  `5956776f2ef248553db18a28c25891cd60b069c9b721397e81bae40686245f22`.
  Both are healthy at epoch 0 step 200/5,026 with zero protected reads.

# 2026-08-07 15:54 CST beta-axis monitor

- Both frozen beta arms remain healthy and aligned at epoch 2 step
  1,300/5,026. Beta 0.999 in `9929.4` has best epoch 1; beta 0.99999 in
  `3066.4` has best epoch 0. Each has intact 310 MB best/last checkpoints,
  one scientific child per allocation, and no terminal receipt.
- Logs contain no traceback/error/OOM/non-finite marker, telemetry remains
  untouched, and protected cohorts remain sealed. The earliest likely terminal
  window under unchanged patience is roughly another 20--40 minutes.

# 2026-08-07 16:14 CST beta-axis monitor

- Both frozen beta arms remain healthy near the end of epoch 4: beta 0.999 in
  `9929.4` is at step 4,500/5,026 with best epoch 1, and beta 0.99999 in
  `3066.4` is at step 4,600/5,026 with best epoch 2. Both retain intact 310 MB
  best/last checkpoints and have no terminal receipt.
- Parent jobs and the two scientific steps remain RUNNING, immutable
  preparation/config/launch hashes are exact, launch receipts still record
  zero protected reads with Internal-test/Gold closed, and logs contain no
  traceback/error/OOM/non-finite marker. Under unchanged early stopping, the
  likely terminal window is about another 10--25 minutes.

# 2026-08-07 16:34 CST beta 0.99999 terminal; beta 0.999 continues

- Beta 0.99999 completed seven epochs with `PASS_TRAINING_FINISHED`, exact
  frozen inputs, and protected outcomes closed. Its terminal best Dev
  Macro-F1 is `0.526265` and ODER is `0.011338`; receipt SHA-256 is
  `62ec30e608294a306515358ec4ae5ac1c2b5f54e313974b5ee2f46bcf79a9141`.
  It fails both original joint thresholds and is preserved unchanged.
- Beta 0.999 remains healthy in `9929.4` at epoch 7 step 1,000/5,026. Its best
  epoch advanced to 6, so unchanged patience extends its likely terminal
  window by roughly another 15--30 minutes. Allocation 3066 is now
  scientifically idle; no next axis is launched before wave005 closes.
- Frozen hashes, registry state, 310 MB checkpoints, logs, storage, telemetry,
  and the zero-protected-read boundary remain valid. No Internal-test or Gold
  outcome was opened.

# 2026-08-07 16:54 CST beta 0.999 monitor

- Beta 0.999 remains healthy as the sole scientific child in `9929.4`, now at
  epoch 9 step 3,400/5,026 with best epoch 6 and intact 310 MB best/last
  checkpoints. Beta 0.99999 remains terminal and preserved; allocation 3066
  remains scientifically idle except for user telemetry.
- No terminal receipt or error marker exists for beta 0.999. Immutable hashes,
  registry state, storage, and the zero-protected-read boundary remain valid.
  If epoch 10 does not improve on best epoch 6, unchanged patience should end
  the run in approximately another 5--15 minutes.

# 2026-08-07 17:14 CST wave005 closure and weight-decay launch

- Beta 0.999 completed 11 epochs with `PASS_TRAINING_FINISHED` at terminal best
  Dev Macro-F1 `0.533685` and ODER `0.003839`; receipt SHA-256 is
  `4645a22977c9d0f9366d9dd5e2588946950a88e57f28d6eaeb28aab7cca3ad0b`.
  It passes the original joint gate but trails global DMW010 on Macro-F1.
  Together with the failing beta 0.99999 arm, wave005 closed with aggregate
  SHA-256 `732dba264824485ebd8d9463def281c7f2a42c923996ad4f44c6a6b744393983`.
- Neither beta arm reached the aspirational Seed-17 target, so no multiseed
  confirmation was opened. The unchanged globally highest-F1 qualified DMW010
  setting remains the parent for the next predeclared one-axis comparison.
- Froze `wave006_weight_decay_v1` at weight decay 0.005/0.02 with preparation
  SHA-256 `e2625368d19ac4c413e727e898e0f7b663088bc161eadac373a350b1a087208b`.
  WD005 config/launch SHAs are
  `85c8f87e48ce09406e9329c0cb10fbd7dd3ead147e479c07193c50020357c61f` /
  `00e760996a3bc156ad8b7cf5eb50080f50edd3b311619ddb4ea38ab31d1530db`;
  WD020 config/launch SHAs are
  `ac75eee43a415d6cc449e34acc2122c66b90c005144d43e96cef0a18e4e8c45c` /
  `7c7646a8888a341e4c5e42b8e93757983c5b19804e54ca22417d75671443aaf0`.
- The two independent arms are healthy at epoch 0 step 300/5,026 in `9929.5`
  and `3066.5`. Each allocation has exactly one scientific child plus its
  untouched telemetry step; launch receipts record protected reads zero and
  Internal-test/Gold closed.

# 2026-08-07 17:34 CST weight-decay monitor

- WD005 and WD020 remain healthy and aligned at epoch 2 step 1,200/5,026 in
  `9929.5` and `3066.5`, with best epoch 0, intact 310 MB best/last
  checkpoints, RUNNING registry rows, and no terminal receipt or error marker.
- Both parent jobs and exactly one scientific child per allocation are
  RUNNING. Preparation/config/launch hashes remain exact, protected reads stay
  zero with Internal-test/Gold closed, and shared storage has about 1.2 PB
  free. The earliest likely terminal window is roughly another 20--40 minutes.

# 2026-08-07 17:54 CST weight-decay monitor

- WD005 and WD020 remain healthy and synchronized at epoch 4 step
  3,600/5,026, each with best epoch 2 and intact 310 MB best/last checkpoints.
  Parent jobs, scientific steps, and registry rows remain RUNNING with no
  terminal receipt or error marker.
- Immutable preparation/config/launch hashes, zero protected reads,
  Internal-test/Gold closure, telemetry, and storage remain unchanged. If best
  epoch 2 is not extended, frozen patience should stop both after epoch 6
  evaluation, likely in another 10--25 minutes.

# 2026-08-07 18:13 CST weight-decay monitor

- Wave006 remains healthy on both retained allocations: WD005 is at epoch 7
  step 1,100/5,026 on `9929.5`, and WD020 is at epoch 7 step 1,200/5,026 on
  `3066.5`.
- Both runs most recently improved at epoch 4, retain complete last/best
  checkpoints, report no error marker, and remain at zero protected reads with
  Internal-test/Gold unopened.
- Frozen preparation/config/launch hashes still match; both parent jobs and
  telemetry steps are healthy, and shared storage has approximately 1.2 PB
  available. No next-wave decision was made from intermediate epochs; both
  terminal receipts remain pending.

# 2026-08-07 18:33 CST weight-decay closure and dropout launch

- Wave006 is terminal after nine completed epochs. WD005 ends at Dev Macro-F1
  `0.525530` / ODER `0.006696` with receipt SHA-256
  `0bf5f5f48dfddf73d9d4e5135779b10183589919ddecd36132e3442cef92e723`;
  WD020 ends at `0.527095` / `0.007321` with receipt SHA-256
  `97901807dc0221c52820abda744776d110c2951088a4062729535acdfbe6cbdd`.
  Both fail the original joint gate and miss the aspirational target.
- Closed Wave006 without selecting either arm. Aggregate receipt SHA-256 is
  `10b610dfa821188efabe66b303e33a8ce0ba7a3e339ddc4917a323d871591165`;
  the prior global DMW010 parent is retained unchanged.
- Froze `wave007_dropout_v1` at dropout 0.05/0.15 with preparation SHA-256
  `bd8db091c37ff3458678ff2e1ce68d815722d8cbf68f85011c8157fe9e7efbd0`.
  DO050 config/launch SHAs are
  `38b32b71c0daf435b5ccaacc4be4720af38f808bd038c7ce4271990f6d892e60` /
  `e556a9e8a71c7484bb88bc4836b0b3615b9bb06e0713f9c74d96605c43b9ea1c`;
  DO150 config/launch SHAs are
  `41304d54095e1261aa3872f5154bc92fb133292adeb48d1cc72665b0701f3875` /
  `40ab3fea918c20eb31240cbc74106a611b598d7fbbabcdd7bc86eea97cb1ec69`.
- Both independent dropout arms entered RUNNING state in `9929.6` and
  `3066.6`; telemetry was preserved, no parent job was submitted/cancelled,
  and launch receipts record zero protected reads with Internal-test/Gold
  closed.

# 2026-08-07 18:53 CST dropout monitor

- DO050 and DO150 remain healthy and synchronized at epoch 2 step
  1,200/5,026 in `9929.6` and `3066.6`, with best epoch 0 and intact 310 MB
  best/last checkpoints. Neither run has a terminal receipt or log error.
- Both parent allocations, telemetry steps, and exactly one scientific child
  per allocation remain RUNNING. Preparation/config/launch hashes still match;
  protected reads remain zero and Internal-test/Gold stay closed.
- No selection or next-axis mutation was made from intermediate evidence.

# 2026-08-07 19:13 CST dropout monitor

- DO050 and DO150 remain healthy and synchronized at epoch 4 step
  3,500/5,026 in `9929.6` and `3066.6`; both most recently improved at epoch 2
  and retain intact 310 MB best/last checkpoints.
- Parent allocations, telemetry, and one scientific child per allocation are
  RUNNING. Frozen hashes remain exact, launcher logs show no error marker, and
  shared storage has approximately 1.2 PB available.
- Terminal receipts remain pending. Protected reads stay zero with
  Internal-test/Gold closed, and no decision was made from intermediate data.

# 2026-08-07 19:33 CST dropout monitor

- DO050 and DO150 remain healthy and synchronized at epoch 7 step 700/5,026
  in `9929.6` and `3066.6`; both most recently improved at epoch 4 and retain
  intact 310 MB best/last checkpoints.
- Parent allocations, telemetry, and exactly one scientific child per
  allocation are RUNNING. Frozen hashes remain exact, logs remain error-free,
  and shared storage still has approximately 1.2 PB available.
- Terminal receipts remain pending. Protected reads stay zero with
  Internal-test/Gold closed, and no next-wave choice was made from intermediate
  evidence.

# 2026-08-07 19:53 CST first dropout terminal

- DO050 is terminal `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1
  `0.530996` / ODER `0.006696`, receipt SHA-256
  `95fc03650760c946333c6902666b3cda69c091ffdf79e493b0b21d29df9df556`.
  It passes the F1 floor but fails the original joint gate on ODER and misses
  the aspirational Seed-17 target.
- DO150 remains healthy at epoch 9 step 3,300/5,026 in `3066.6`, with best
  epoch 7, intact checkpoints, no log error, and no terminal receipt. Allocation
  9929 is scientifically idle with its telemetry step preserved.
- Frozen hashes remain exact and protected outcomes remain unopened. No wave
  selection, confirmation, or next-axis launch will occur before DO150 reaches
  a terminal receipt.

# 2026-08-07 20:13 CST dropout closure and margin-magnitude launch

- DO150 is terminal `PASS_TRAINING_FINISHED` after 12 epochs at Dev Macro-F1
  `0.529138` / ODER `0.007321`, receipt SHA-256
  `4f1db264cc4eb4af2a53700db26ed587c94dc962d748b30279037e00d4ac670a`.
  Together with DO050 (`0.530996` / `0.006696`), both dropout arms fail the
  original joint gate on ODER and miss the aspirational target.
- Closed Wave007 without selecting either arm. Aggregate receipt SHA-256 is
  `d2762f1c9f876f254ff5716ad1dd6929898a62356047f5bd49e74e6be1408f7e`;
  the prior global DMW010 parent remains unchanged.
- Froze `wave008_direction_margin_magnitude_v1` at margin 0.1/0.3 with
  preparation SHA-256
  `31fdce7d9e342de1fcd5919bb2d8368cab0354bb14986d2215358f7884cae914`.
  MARGIN010 config/launch SHAs are
  `73eaa6a3e5e3e779f763e8b0df30124adfefb466447262e8caa7d44fab4573b7` /
  `8ad13045d4fdf9d0bab3c264be78ce662f92365351f11ca589dedfd5bbe4df19`;
  MARGIN030 config/launch SHAs are
  `c4cf39019c81e566305de4d6d119920a1eba17c5901f57e577b6fbc964e9f6cc` /
  `f0c2c5382a50a08dcbc25f54a081f42b5bc4230d1690aee3db40dfe844e15417`.
- Both independent arms entered RUNNING state at epoch 0 step 100/5,026 in
  `9929.7` and `3066.7`; telemetry and parent jobs were preserved, and launch
  receipts record zero protected reads with Internal-test/Gold closed.

# 2026-08-07 20:33 CST margin-magnitude monitor

- MARGIN010 and MARGIN030 remain healthy and synchronized at epoch 2 step
  1,000/5,026 in `9929.7` and `3066.7`, with best epoch 0 and intact 310 MB
  best/last checkpoints. Neither run has a terminal receipt or log error.
- Parent allocations, telemetry, and exactly one scientific child per
  allocation remain RUNNING. Preparation/config/launch hashes are exact and
  shared storage has approximately 1.2 PB available.
- Protected reads remain zero with Internal-test/Gold closed; no combination
  or final-setting choice was made from intermediate evidence.

# 2026-08-07 20:53 CST margin-magnitude monitor

- MARGIN010 and MARGIN030 remain healthy and synchronized at epoch 4 step
  3,600/5,026 in `9929.7` and `3066.7`; both most recently improved at epoch 2
  and retain intact 310 MB best/last checkpoints.
- Both parent allocations, telemetry steps, and exactly one scientific child
  per allocation remain RUNNING. Frozen hashes remain exact and launcher logs
  show no error marker.
- Terminal receipts remain pending, protected reads remain zero, and
  Internal-test/Gold stay closed. No combination was chosen from intermediate
  evidence.

# 2026-08-07 21:13 CST margin-magnitude monitor

- MARGIN010 and MARGIN030 remain healthy at epoch 7 steps 1,400/5,026 and
  1,500/5,026 in `9929.7` and `3066.7`; both currently retain epoch 4 as the
  best checkpoint, with intact 310 MB best/last checkpoints.
- Both parent allocations, telemetry steps, and exactly one independent
  scientific child per allocation remain RUNNING. Preparation, config, and
  launch hashes remain exact, and neither launcher log has an error marker.
- Terminal receipts remain pending, protected reads remain zero, and
  Internal-test/Gold stay closed. No combination or final-setting decision was
  made from intermediate evidence.

# 2026-08-07 21:33 CST first margin-magnitude terminal

- MARGIN030 is terminal `PASS_TRAINING_FINISHED` after nine epochs with Dev
  Macro-F1 `0.523014` / ODER `0.006785`; terminal receipt SHA-256 is
  `5b65e74754a5a8a03ceaa492fc0302498a19b8db88eb89a5caef115cec56d1f6`.
  It fails both parts of the original joint gate and the aspirational target;
  the receipt confirms Internal-test and protected outcomes were not opened.
- MARGIN010 remains healthy at epoch 9 step 3,500/5,026 in `9929.7`, with best
  epoch 7, intact 310 MB checkpoints, no launcher error, and no terminal
  receipt. Allocation 3066 is scientifically idle with telemetry preserved.
- Preparation/config/launch hashes remain exact, shared storage has about
  1.25 PB available, and protected cohorts remain closed. Wave008 will not
  close and no combination will launch before MARGIN010 is terminal.

# 2026-08-07 21:53 CST margin-magnitude terminal pair

- MARGIN010 is terminal `PASS_TRAINING_FINISHED` after 12 epochs at Dev
  Macro-F1 `0.530479` / ODER `0.007499`; receipt SHA-256 is
  `721c3d05f38d509ed42ead1cd19b4e607011c2945e1876275cc7a65a5bf9ec02`.
  It clears the F1 floor but fails the original joint gate on ODER and misses
  the aspirational target.
- MARGIN030 remains terminal at `0.523014` / `0.006785`. Both Wave008 arms
  therefore fail the joint gate, so neither can replace the globally preferred
  DMW010 parent (`0.538661` / `0.005178`).
- Both scientific child steps have ended; allocations 9929 and 3066 retain
  only their batch and telemetry steps. Frozen hashes remain exact, shared
  storage has about 1.25 PB available, and both terminal receipts confirm that
  Internal-test and protected outcomes were not opened.
- The next permitted operation is to close Wave008 with a fail-closed aggregate
  receipt, then freeze at most one Seed-17 combination of the two best completed
  individual axes: DMW weight 0.01 plus focal gamma 0.5.
- Wave008 closed atomically with aggregate receipt SHA-256
  `3ebc4bff4409e29f81a6dbdd0d9bb9bd8d6527de4fc9545efe596d5f5bb3cabe`.
  The subsequent Wave009 control attempt stopped before creating that namespace
  because its pinned gamma-0.5 config hash was missing the final `d`; no
  scientific child launched and both allocations remain free. The exact remote
  hash was independently verified and the control script was corrected for one
  identity-preserving engineering retry.
- The corrected control completed successfully. Wave009 preparation SHA-256 is
  `86de8abb051db5ca0aa59eb6b74f3c1c51a06e4b2885a1afdf52c47d7b773b46`;
  its sole frozen config `SVR-FG050-DMW010-S17` has SHA-256
  `3f08bf3c318e8034f1d4b1161f62b7816b4335abf62caeb90495b65eea57ec5b`
  and combines only DMW weight 0.01 with focal gamma 0.5.
- The run is healthy at epoch 0 step 100/5,026 in `9929.8`; launch receipt
  SHA-256 is
  `a3e67b8b8890f1aa84783de0c52f52f2f38a3cc3632fdf02733f78a0c500b72a`.
  It has no error marker and records zero protected reads with Internal-test
  and Gold closed. Allocation 3066 remains scientifically idle with telemetry
  preserved until the combination is terminal.

# 2026-08-07 22:13 CST best-axes combination monitor

- `SVR-FG050-DMW010-S17` remains healthy at the end of epoch 1 in `9929.8`,
  with best epoch 0, intact 310 MB best/last checkpoints, no launcher error,
  and no terminal receipt.
- Wave009 preparation/config/launch hashes remain exact. Allocation 3066 stays
  scientifically idle with its telemetry step preserved; allocation 9929 has
  exactly one independent scientific child.
- Shared storage has about 1.25 PB available, protected reads remain zero, and
  Internal-test/Gold stay closed. No seed confirmation or sweep decision was
  made from intermediate evidence.

# 2026-08-07 22:33 CST best-axes combination monitor

- `SVR-FG050-DMW010-S17` remains healthy at epoch 4 step 2,600/5,026 in
  `9929.8`, with best epoch 2, intact 310 MB best/last checkpoints, no launcher
  error, and no terminal receipt.
- Wave009 preparation/config/launch hashes remain exact. Allocation 3066 stays
  scientifically idle with telemetry preserved, while allocation 9929 retains
  exactly one independent scientific child.
- Shared storage remains about 1.25 PB free, protected reads remain zero, and
  Internal-test/Gold stay closed. No downstream decision was made from
  intermediate evidence.

# 2026-08-07 user-expanded continuation authority

- The user explicitly removed the former one-combination stopping rule and
  authorized continued lightweight parameter search until a good Train/Dev
  result is found or they explicitly stop it.
- Preserve the running Wave009 combination unchanged and do not use its
  intermediate epochs. To use both retained cards without adaptive leakage,
  the next two-arm LR refinement is frozen solely from completed DMW010 and
  prior LR evidence: LR 1.25e-4 and 1.5e-4, with DMW weight 0.01, gamma 1.0,
  seed 17, and every other field fixed.
- Allocation 3066 may launch the first frozen LR arm immediately; the paired
  arm must stay frozen and unstarted until an allocation has no scientific
  child. All historical HOLD/STOP and protected-cohort boundaries remain.
- Froze `wave010_lr_refine_dmw010_v1` with preparation SHA-256
  `78e449d98dfd27b116a89e2d2272969c273a873e7d2c065a3420c760be20e6b6`.
  LR1.25e-4 / LR1.5e-4 config SHAs are
  `e2fa229adfcd5bcd72e22c2c3ef055cfb8d88888da238a1b89f5462930146c20` /
  `e4db85aa7930704ace23c1aa3774ba2c3ee4388d3f37cde5b5a9caf6b619bff3`.
- Launched `SVR-FG1-DMW010-LR125-S17` independently in `3066.8`; launch
  receipt SHA-256 is
  `29201b8a8211782f51dec8e868631e9dcf6460aa83df35e8c0c8293d4c94a2d4`.
  It is healthy at epoch 0 step 200/5,026 with no error marker. The unchanged
  LR1.5e-4 arm remains frozen and unstarted.
- Both retained cards are now scientifically occupied: Wave009 combination in
  `9929.8` is healthy at epoch 6 step 3,700/5,026, while Wave010 LR1.25e-4 runs
  in `3066.8`. Each allocation has exactly one independent scientific child;
  protected reads remain zero and Internal-test/Gold stay closed.
- The user further authorized a first-terminal-winner policy for parallel
  exploration. A run counts as "good" only from its complete terminal receipt
  when Macro-F1 is at least `0.546094` and ODER is at most `0.005535`; no
  intermediate epoch can trigger stopping. If either active run reaches that
  target, stop only the other scientific child, preserve its partial artifacts,
  keep both allocations/telemetry, and immediately freeze seeds 28/43 for the
  winning exact setting.

# 2026-08-07 22:54 CST parallel terminal-race monitor

- Both frozen scientific children remain healthy and non-terminal. Wave009
  `SVR-FG050-DMW010-S17` is at epoch 7 step 1,100/5,026 in `9929.8`, with
  best epoch 4 and intact 310 MB best/last checkpoints. Wave010
  `SVR-FG1-DMW010-LR125-S17` is at epoch 0 step 3,100/5,026 in `3066.8`.
- Neither launcher log contains an error marker and neither run has emitted a
  terminal receipt, so the frozen LR1.5e-4 arm remains unstarted and no
  terminal-race stop or confirmation action is permitted yet.
- Both allocations have exactly one independent scientific child plus their
  preserved telemetry/batch steps. All Wave009/Wave010 preparation and config
  hashes remain exact, shared storage has about 1.25 PB available, and the
  protected-cohort boundary remains unchanged with Internal-test/Gold closed.

# 2026-08-07 23:14 CST Wave009 terminal and LR1.5e-4 launch

- `SVR-FG050-DMW010-S17` is terminal `PASS_TRAINING_FINISHED` after nine
  epochs at Dev Macro-F1 `0.5352369134664762` / ODER
  `0.006249442014105883`; training receipt SHA-256 is
  `4825a2bb0199ee56f3155c23d06e047053925c1da88d600156f8813ffbbe34f2`.
  It clears the F1 floor but violates the ODER ceiling and misses the
  aspirational target, so it does not trigger the terminal-race stop policy.
- Wave009 closed fail-closed with aggregate receipt SHA-256
  `51ec2854e70a6371a37924b7d678d6b7c8a78070528b542b6f3245d8bd1f38f8`;
  the prior DMW010 terminal parent remains globally preferred.
- Allocation 9929 became scientifically free, so the already-frozen unchanged
  `SVR-FG1-DMW010-LR150-S17` arm launched independently in `9929.9`. Its
  launch receipt SHA-256 is
  `ca8d47cf5cb0192771bb9db7fad22416fe85f5951b2e48621d1b22479f6bd97c`
  and launcher SHA-256 is
  `96a4a3020aa0f0fdde92f1032f4d1def178c2ccd0f1963fa556947f583037bb1`.
- The LR1.5e-4 arm is healthy at epoch 0 step 200/5,026, while the unchanged
  LR1.25e-4 arm continues at epoch 3 step 1,400/5,026 in `3066.8`. Each
  allocation again has exactly one independent scientific child plus preserved
  telemetry/batch steps, no launcher error is present, hashes remain exact,
  and Internal-test/Gold remain closed with zero protected reads.

# 2026-08-07 23:34 CST Wave010 parallel monitor

- Both frozen LR refinement arms remain healthy and non-terminal. LR1.25e-4 is
  at epoch 5 step 2,100/5,026 in `3066.8`, with best epoch 4 and intact 310 MB
  best/last checkpoints. LR1.5e-4 is at epoch 2 step 800/5,026 in `9929.9`,
  with best epoch 0 and intact 310 MB best/last checkpoints.
- Each retained allocation has exactly one independent scientific child plus
  its preserved telemetry/batch steps. Neither launcher contains an error
  marker, all preparation/config/launch hashes remain exact, and no terminal
  receipt exists, so no terminal-race stop or downstream selection is allowed.
- Shared storage has about 1.25 PB available; the protected-cohort boundary is
  unchanged and Internal-test/Gold remain closed.

# 2026-08-07 23:54 CST Wave010 parallel monitor

- Both frozen LR refinement arms remain healthy and non-terminal. LR1.25e-4 is
  at epoch 7 step 4,700/5,026 in `3066.8`, with best epoch 4 and intact 310 MB
  best/last checkpoints. LR1.5e-4 is at epoch 4 step 3,400/5,026 in `9929.9`,
  with best epoch 2 and intact 310 MB best/last checkpoints.
- Each allocation still has exactly one independent scientific child plus its
  telemetry/batch steps. No launcher error or terminal receipt is present;
  preparation/config hashes remain exact and no terminal-race action is
  permitted from the intermediate state.
- Shared storage remains about 1.25 PB available and Internal-test/Gold stay
  closed with the protected-cohort boundary unchanged.

# 2026-08-08 00:14 CST Wave010 parallel monitor

- Both frozen LR refinement arms remain healthy and non-terminal. LR1.25e-4 is
  at epoch 10 step 1,800/5,026 in `3066.8`, with best epoch 8 and intact 310 MB
  best/last checkpoints. LR1.5e-4 is at epoch 7 step 600/5,026 in `9929.9`,
  with best epoch 4 and intact 310 MB best/last checkpoints.
- Both allocations retain exactly one independent scientific child plus their
  telemetry/batch steps. Launcher logs remain error-free, no terminal receipt
  exists, and no selection, stop, or new-wave freeze is permitted from these
  intermediate states.
- Shared storage remains about 1.25 PB available; Internal-test/Gold remain
  closed and the protected-cohort boundary is unchanged.

# 2026-08-08 00:34 CST Wave010 parallel monitor

- Both frozen LR refinement arms remain healthy and non-terminal. LR1.25e-4 is
  at epoch 12 step 4,300/5,026 in `3066.8`, with best epoch 8 and intact 310 MB
  best/last checkpoints. LR1.5e-4 is at epoch 9 step 3,000/5,026 in `9929.9`,
  with best epoch 7 and intact 310 MB best/last checkpoints.
- Exactly one scientific child remains on each allocation alongside preserved
  telemetry/batch steps. No launcher error or terminal receipt is present, so
  terminal-race stopping, selection, and any subsequent freeze remain locked.
- Shared storage remains about 1.25 PB available; Internal-test/Gold remain
  closed and the protected-cohort boundary is unchanged.

# 2026-08-08 00:54 CST LR1.25e-4 terminal and Wave011 launch

- Wave010 `SVR-FG1-DMW010-LR125-S17` is terminal
  `PASS_TRAINING_FINISHED` after 13 epochs at Dev Macro-F1
  `0.5299799428313788` / ODER `0.004285331666815463`; terminal receipt
  SHA-256 is
  `b1baa560437ebf62e51cc8124b8149cac26801164596b39e051fe8300915d897`.
  It passes the original joint gate but misses the aspirational target and is
  below the terminal DMW010 parent on Macro-F1, so no terminal-race stop or
  confirmation is opened.
- Wave010 LR1.5e-4 continues unchanged at epoch 12 step 1,600/5,026 in
  `9929.9`, with best epoch 9, intact checkpoints, and no launcher error.
- Using only completed LR1e-4 and LR1.25e-4 terminal evidence, froze
  `wave011_lr_bracket_dmw010_v1` with preparation SHA-256
  `7b321c77fcf9338153438e8bf2938313dd85ac227d6811ac28eb7fc579c8cf45`.
  Its exact LR8.75e-5 / LR1.125e-4 config SHAs are
  `58901ed64dde4bf65837915bfbe8279e650d21af124beb2088899d78dafcd336` /
  `4bccc9b82275d280146918e53704f77fefebd6360372269fc581d8330d61c78e`.
- Launched the first frozen bracket arm `SVR-FG1-DMW010-LR0875-S17`
  independently in `3066.9`; launch receipt SHA-256 is
  `0989e15f3999b241a864b0d7596cd18f3aa9b6600fbfaf18da079b0c9241187f`
  and launcher SHA-256 is
  `3cfbd8a2a4f4b900e4986b9a69f36d67ca0d1650de2d2627e5d40cfac3fb7e43`.
  It is healthy at epoch 0 step 200/5,026. LR1.125e-4 remains frozen and
  unstarted until an allocation is scientifically free.
- Each allocation again has exactly one independent scientific child plus its
  telemetry/batch steps. All new hashes verify exactly, no output was
  overwritten, and Internal-test/Gold remain closed with zero protected reads.

# 2026-08-08 01:14 CST Wave010 closed and LR1.125e-4 launched

- Wave010 `SVR-FG1-DMW010-LR150-S17` is terminal
  `PASS_TRAINING_FINISHED` after 14 epochs at Dev Macro-F1
  `0.5341771317851062` / ODER `0.0036603874654048746`; terminal receipt
  SHA-256 is
  `31abeefcf4d1a9b170163ddf6ccd4130499ec81f665076a15089fc214efaeabd`.
  It passes the original joint gate but misses the aspirational target and
  remains below the global DMW010 parent on Macro-F1.
- Wave010 closed fail-closed with aggregate receipt SHA-256
  `49f2b483096c9a8a5280d407711260267503f4a3ac462943ab8391ab98c81e8d`.
  LR1.5e-4 is the higher-F1 qualified arm within the wave, but the prior DMW010
  LR1e-4 parent remains globally preferred.
- Allocation 9929 became scientifically free, so the already-frozen unchanged
  Wave011 arm `SVR-FG1-DMW010-LR1125-S17` launched in `9929.10`. Its launch
  receipt SHA-256 is
  `6349b9d5503ca7aac30629f84f171eaa190685c2655ba7b2dd3203b16d1f23eb`
  and launcher SHA-256 is
  `2d9a4d63ee53887263dbfd4d5693e29edfd77a6f84e3d796d35ce9202306fe96`.
- LR1.125e-4 is healthy at epoch 0 step 100/5,026, while LR8.75e-5 continues
  at epoch 2 step 2,300/5,026 in `3066.9`. Each allocation again has exactly
  one independent scientific child plus telemetry/batch steps; hashes are
  exact, no output was overwritten, and Internal-test/Gold remain closed with
  zero protected reads.

# 2026-08-08 01:34 CST Wave011 parallel monitor

- Both frozen Wave011 LR bracket arms remain healthy and non-terminal.
  LR8.75e-5 is at epoch 4 step 3,800/5,026 in `3066.9`, with best epoch 2 and
  intact 310 MB checkpoints. LR1.125e-4 is at epoch 2 step 1,700/5,026 in
  `9929.10`, with best epoch 0 and intact 310 MB checkpoints.
- Each retained allocation has exactly one independent scientific child plus
  its telemetry/batch steps. Launcher logs are error-free, no terminal receipt
  exists, and no terminal-race or downstream selection action is permitted.
- Shared storage remains about 1.25 PB available; Internal-test/Gold remain
  closed and the protected-cohort boundary is unchanged.

# 2026-08-08 01:54 CST Wave011 parallel monitor

- Both frozen Wave011 LR bracket arms remain healthy and non-terminal.
  LR8.75e-5 is at epoch 7 step 900/5,026 in `3066.9`, with best epoch 4 and
  intact 310 MB checkpoints. LR1.125e-4 is at epoch 4 step 4,100/5,026 in
  `9929.10`, with best epoch 0 and intact 310 MB checkpoints.
- Exactly one independent scientific child remains on each allocation beside
  preserved telemetry/batch steps. No launcher error or terminal receipt is
  present, so terminal-race and downstream selection actions remain locked.
- Shared storage remains about 1.25 PB available; Internal-test/Gold remain
  closed and the protected-cohort boundary is unchanged.

# 2026-08-08 02:14 CST LR8.75e-5 terminal and Wave012 launch

- Wave011 `SVR-FG1-DMW010-LR0875-S17` is terminal
  `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1
  `0.5304341896827144` / ODER `0.005713775555753951`; receipt SHA-256 is
  `b21281a446c39c98f010b84c47eb68f4efe924fc3ca07ba90a4788729deb6335`.
  It clears the F1 floor but exceeds the original ODER ceiling and misses the
  aspirational target, so it opens neither stopping nor confirmation.
- Wave011 LR1.125e-4 continues unchanged in `9929.10` at epoch 7 step
  2,400/5,026, with best epoch 4, intact checkpoints, and no launcher error.
- Using completed DMW and LR8.75e-5 terminal evidence only, froze
  `wave012_dmw_local_bracket_v1` with preparation SHA-256
  `e2d94f2be8989c1ed8909e4ef69be14c92d7773825fad65f9357318c9b57129d`.
  Exact DMW005 / DMW015 config SHAs are
  `a0dbf6e17e4457b6f08d1f68d5c9c365e6884b7ca3a44f4c4c29a7340be92aba` /
  `13a2ba82c8dac3d9632be1bb566aa5438d88cedc466a7e84a990e3d939440ec9`.
- Launched `SVR-FG1-DMW005-S17` independently in `3066.10`; launch receipt
  SHA-256 is
  `175a723005b9a073b32bceeda32631716ed29e750a482732f0dd43dca7104722`
  and launcher SHA-256 is
  `cc738d76a08dc544ba4df468dfc0caeabe60b75e99b60a6e6d86465745303f95`.
  It is healthy at epoch 0 step 300/5,026. DMW015 remains frozen and unstarted.
- Both retained allocations again host exactly one independent scientific
  child plus telemetry/batch steps. Hashes verify, no output was overwritten,
  and Internal-test/Gold remain closed with zero protected reads.

# 2026-08-08 02:34 CST Wave011 closed and DMW015 launched

- Wave011 `SVR-FG1-DMW010-LR1125-S17` is terminal
  `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1
  `0.5279630195665763` / ODER `0.00651727524328185`; receipt SHA-256 is
  `49bf30af6790e78ba1c5df2051972793da5a2257fc6dc0a7cbaa0a1c0e83efec`.
  It fails both the original joint gate and aspirational target.
- Wave011 closed fail-closed with aggregate receipt SHA-256
  `e5998fd4023d5047d20766e439baa79d8bc6e5566a75050286694e5047bfd6ac`;
  neither LR bracket arm qualifies, so DMW010 LR1e-4 remains globally retained.
- Allocation 9929 became scientifically free, so the already-frozen unchanged
  Wave012 `SVR-FG1-DMW015-S17` arm launched in `9929.11`; launch receipt
  SHA-256 is
  `695e0472be389d3d85c83c2e93f5202ed0395df9eb4665a7eb0c99f054f65ad8`
  and launcher SHA-256 is
  `1f6ca751579063e1568565a92114c7ad9c6cba1f18e842e68c4fdd70e266d75d`.
- DMW015 is healthy at epoch 0 step 100/5,026 while DMW005 continues at epoch
  2 step 2,600/5,026 in `3066.10`. Each allocation again has exactly one
  independent scientific child plus telemetry/batch steps; hashes verify, no
  output was overwritten, and Internal-test/Gold remain closed.

# 2026-08-08 02:54 CST Wave012 parallel monitor

- Both frozen Wave012 DMW bracket arms remain healthy and non-terminal. DMW005
  is at epoch 4 step 4,200/5,026 in `3066.10`, with best epoch 2 and intact
  310 MB checkpoints. DMW015 is at epoch 2 step 1,800/5,026 in `9929.11`,
  with best epoch 0 and intact 310 MB checkpoints.
- Each allocation retains exactly one independent scientific child plus its
  telemetry/batch steps. Launcher logs remain error-free, no terminal receipt
  exists, and no terminal-race or downstream selection action is permitted.
- Shared storage remains about 1.25 PB available; Internal-test/Gold remain
  closed and the protected-cohort boundary is unchanged.
# 2026-08-08 03:14 CST Wave012 parallel monitor

- Both frozen Wave012 DMW bracket arms remain healthy and non-terminal. DMW005 is at epoch 7 step 1,300/5,026 in `3066.10`, with best epoch 4 and intact 310 MB checkpoints. DMW015 is at epoch 4 step 4,300/5,026 in `9929.11`, with best epoch 2 and intact 310 MB checkpoints.
- Each allocation retains exactly one independent scientific child plus telemetry/batch steps. Launcher logs are error-free; there is no terminal receipt, terminal-race winner, or downstream selection.
- Storage remains about 1.25 PB free. Internal-test and Gold remain closed, and the protected boundary is unchanged.

# 2026-08-08 03:34 CST DMW005 terminal and Wave013 launch

- Wave012 `SVR-FG1-DMW005-S17` is terminal `PASS_TRAINING_FINISHED` after nine
  epochs at Dev Macro-F1 `0.5303079271663512` / ODER
  `0.005267386840460673`; receipt SHA-256 is
  `3d6bc8ab5dc2f641c5ab8a743a7b5240e9350e84b5ee9bc0c89c2e6145c6fb10`.
  It passes the original joint gate but trails DMW010 on Macro-F1 and misses
  the aspirational target, so it triggers neither cancellation nor
  confirmation.
- Using only DMW005 and prior terminal evidence while DMW015 remained blinded,
  froze `wave013_dmw_lower_midpoint_v1` at DMW0075. Preparation/config/launcher
  SHA-256 values are
  `52bc249980429399c2299627e753ec079260be73b04b2f2ec6e3f8ec7a345e2f`,
  `c2feeb9d0d5d676f4a9dadef4e005b2712cfa70982adddf447a5611edd9e8357`,
  and `cd2bfcd813c6dd922d57ceada9f7ad22ba681fc8a0d25c092c551add3aec4005`.
- Launched unchanged `SVR-FG1-DMW0075-S17` independently in `3066.11`. The
  12-second launch-control postcheck timed out before progress initialization;
  its preserved failure SHA-256 is
  `4f584456de8df8b06173caa8d804f91dd54b10c9ac986e54aae441dfe58fbbb9`.
  The same child then produced healthy progress without retry; launch receipt
  SHA-256 is
  `9352241e7a27ec18444cd063c1de8d720d5365dfe617f04d0d0ce2f24a4b034d`.
- DMW015 continues unchanged in `9929.11` at epoch 8 step 500/5,026 with intact
  checkpoints; DMW0075 is healthy at epoch 0 step 1,400/5,026. Each allocation
  has exactly one scientific child plus telemetry/batch steps, launcher logs
  are error-free, storage remains about 1.25 PB free, and Internal-test/Gold
  remain closed.

# 2026-08-08 03:54 CST DMW015 terminal and Wave014 launch

- Wave012 `SVR-FG1-DMW015-S17` is terminal `PASS_TRAINING_FINISHED` after nine
  epochs at Dev Macro-F1 `0.526627739328098` / ODER
  `0.006070886527988572`; receipt SHA-256 is
  `d56cdee061aef2d5a0ea947edbeef0ba3f5282d51b9ceff047674933132a53b5`.
  It fails the original joint gate and aspirational target.
- Closed Wave012 fail-closed with aggregate receipt SHA-256
  `acba6a1b3a242a21431e20b133e40a028b3a5c00a268d333a37eb7a5cd7e1d3c`.
  DMW005 is the within-wave qualified arm, but DMW010 remains the higher-F1
  global parent.
- Using only DMW015 and prior terminal evidence while DMW0075 stayed blinded,
  froze `wave014_dmw_upper_midpoint_v1` at DMW0125. Preparation/config/launcher
  SHA-256 values are
  `29be95a724c15dd2ec92e74dfb869c1fa03ab7bcf5dd87dda510f45cde0b94f7`,
  `cf3b11ad40391623a93d91e5a0378eaa085f9b118075048269ccdc6d7777040e`,
  and `4b5b92877e942068c24f9145d508bc5d635f10bba563923b6bbc7b56bd7553b8`.
- Launched unchanged `SVR-FG1-DMW0125-S17` in `9929.12`; launch receipt
  SHA-256 is
  `cd391cabd23231ca2765cc4451d0d55f4f62275f37b167a2c6429af757af7ed3`.
  It is healthy at epoch 0 step 500/5,026. DMW0075 continues in `3066.11` at
  epoch 2 step 2,900/5,026 with intact checkpoints. Each allocation again has
  exactly one scientific child plus telemetry/batch steps, launcher logs have
  no fatal markers, storage remains about 1.25 PB free, and Internal-test/Gold
  remain closed.

# 2026-08-08 04:14 CST Wave013/014 parallel monitor

- Both frozen midpoint arms remain healthy and non-terminal. DMW0075 is at
  epoch 4 step 1,900/5,026 in `3066.11`, with best epoch 2 and intact 310 MB
  checkpoints. DMW0125 is at epoch 1 step 5,000/5,026 in `9929.12`, with best
  epoch 0 and intact 310 MB checkpoints.
- Preparation/config/launch-receipt hashes for both waves still match exactly.
  Each allocation retains exactly one independent scientific child plus its
  telemetry/batch steps; launcher logs contain no fatal markers and neither
  terminal receipt exists.
- Shared storage remains about 1.25 PB free. Internal-test and Gold remain
  closed, protected-outcome access remains zero, and no terminal-race or
  downstream selection action is permitted.

# 2026-08-08 04:34 CST Wave013/014 parallel monitor

- Both midpoint arms remain healthy and non-terminal. DMW0075 is at epoch 6
  step 4,500/5,026 in `3066.11`, with best epoch 4 and intact 310 MB
  checkpoints. DMW0125 is at epoch 4 step 2,100/5,026 in `9929.12`, with best
  epoch 2 and intact 310 MB checkpoints.
- All frozen preparation/config/launch-receipt hashes still match. Each
  retained allocation contains exactly one independent scientific child plus
  telemetry/batch steps, and both launcher logs remain free of fatal markers.
- Shared storage remains about 1.25 PB free. No terminal receipt exists,
  Internal-test/Gold remain sealed, and no selection or cancellation action is
  permitted from the running state.

# 2026-08-08 05:02 CST DMW0075 terminal and Wave015 gamma bracket launch

- Wave013 `SVR-FG1-DMW0075-S17` is terminal
  `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1 `0.529707` / ODER
  `0.005267`; terminal receipt SHA-256 is
  `c76fc8cd22c4a4c1b5a7e12c0a3aecb4f8267f26e4838c075bebaa3d3fde978b`.
  It passes the original joint gate but misses the aspirational target and
  trails retained DMW010 by `0.008955` Macro-F1.
- Closed Wave013 fail-closed with aggregate receipt SHA-256
  `9deaad53f76104e50d6e53656e9503e05eb7b77d3dacee83141329c1baf13aa9`;
  DMW010 remains the globally retained Seed-17 parent. DMW0125 continues
  unchanged in `9929.12` and remained blinded for this selection.
- Froze `wave015_focal_gamma_local_bracket_v1` from completed terminal evidence
  only, predeclaring gamma `0.875/0.75` at unchanged DMW010. Preparation
  SHA-256 is
  `a725840da0840790769348a183101a6f536da66e857167f18a16db00f1520184`;
  config SHA-256 values are
  `45ed1494d139111032fa4b721f6cf0cd1a653b7b9caa6c3f9d023cb175a75235`
  and `0a87fe2ac9ef7b8299518e5ac0b79cd9f552664d0c982fcd193b560ca69333c0`.
- Launched unchanged gamma0.875 in `3066.12`; launch receipt SHA-256 is
  `b2e69357ee9c5911da204e666ad8a390a7ba3f73f0849b0e5fb309f41ec9f6a5`.
  It entered `RUNNING` with no fatal launcher marker. Gamma0.75 remains frozen
  and unstarted until an allocation is scientifically free. Both allocations
  again have exactly one independent scientific child plus telemetry/batch;
  Internal-test/Gold remain sealed and protected-outcome access remains zero.

# 2026-08-08 05:18 CST DMW0125 terminal and gamma0.75 launch

- Wave014 `SVR-FG1-DMW0125-S17` is terminal
  `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1 `0.534913` / ODER
  `0.005982`; terminal receipt SHA-256 is
  `c4cce14988ee0da2c7e52a5135a9200a2923e4a9587dd967ab261e3b41af4566`.
  It misses the ODER ceiling and aspirational target, so no terminal-race stop
  or confirmation is opened.
- Closed Wave014 fail-closed with aggregate receipt SHA-256
  `487c61ca880ddbc8add6ffee4bd250ac100e46305d4e9165fc27df41be8dada4`;
  DMW010 remains globally retained.
- Launched the already-frozen Wave015 gamma0.75 arm unchanged in `9929.13`.
  Launcher SHA-256 is
  `ac7a67afcd4edb1f54bba48a541b5460c667dcdaa2b401091feae31593b7f099`;
  launch receipt SHA-256 is
  `bff17bc0c2ed128efdf364d2d9d7fb6e120e22b0ab1426209cf44984527b77c5`.
  It entered `RUNNING` with no fatal launcher marker while gamma0.875 continues
  independently in `3066.12`. Each retained allocation again contains exactly
  one scientific child plus telemetry/batch; all frozen hashes match and
  Internal-test/Gold remain sealed.

# 2026-08-08 05:35 CST Wave015 parallel monitor

- Both predeclared focal-gamma midpoint arms remain healthy and non-terminal.
  Gamma0.875 is at epoch 4 with best epoch 2 in `3066.12`; gamma0.75 is at
  epoch 2 with best epoch 0 in `9929.13`. Both retain intact 310 MB best/last
  checkpoints and have no terminal receipt.
- Wave015 preparation, both config hashes, and both launch-receipt hashes still
  match exactly. Each retained allocation contains exactly one independent
  scientific child plus telemetry/batch, both launcher logs remain free of
  fatal markers, and shared storage has about 1.2 PB available.
- Internal-test/Gold remain sealed and protected-outcome access remains zero.
  No selection, cancellation, or new-wave action is permitted from these
  intermediate states.

# 2026-08-08 05:55 CST Wave015 parallel monitor

- Both frozen gamma-midpoint arms remain healthy and non-terminal. Gamma0.875
  is at epoch 6 with best epoch 5 in `3066.12`; gamma0.75 is at epoch 4 with
  best epoch 2 in `9929.13`. Their best/last checkpoints remain intact at about
  310 MB, and neither terminal receipt exists.
- Preparation/config/launch-receipt hashes still match exactly, both launcher
  logs have no fatal marker, and each allocation has exactly one scientific
  child plus telemetry/batch. Shared storage remains about 1.2 PB free.
- Internal-test/Gold remain sealed and protected-outcome access remains zero;
  no intermediate result is used for selection or mutation.

# 2026-08-08 06:15 CST Wave015 parallel monitor

- Both gamma-midpoint arms remain healthy and non-terminal. Gamma0.875 is at
  epoch 9 with best epoch 7 in `3066.12`; gamma0.75 is at epoch 7 with best
  epoch 4 in `9929.13`. Best/last checkpoints remain intact at about 310 MB,
  and neither terminal receipt exists.
- All Wave015 preparation/config/launch-receipt hashes still match. Each
  allocation contains exactly one independent scientific child plus
  telemetry/batch, both launcher logs remain free of fatal markers, and shared
  storage remains about 1.2 PB free.
- Protected-outcome access remains zero and Internal-test/Gold stay sealed;
  no terminal-race or downstream selection action is authorized yet.

# 2026-08-08 06:38 CST gamma0.75 terminal and Wave016 launch

- Wave015 gamma0.75 is terminal `PASS_TRAINING_FINISHED` after nine epochs at
  Dev Macro-F1 `0.534812` / ODER `0.00553522006963664`; terminal receipt
  SHA-256 is
  `69160ae5c89f442bd10765a8314652c658e26cf13d90fca81cc9d2f816894de6`.
  It passes the original gate exactly at the ODER ceiling but misses the
  aspirational target and trails retained DMW010 by `0.003849` Macro-F1.
  Gamma0.875 continues unchanged in `3066.12`, so Wave015 remains open.
- Using completed gamma0.75 and prior terminal evidence only while gamma0.875
  stayed blinded, froze `wave016_focal_gamma_tight_bracket_v1` at gamma
  `0.9375/1.125`. Preparation SHA-256 is
  `11c00d8cafdd27a9b3aacfb63f93762e9be21eb84e9e23909693488edec1fad1`;
  config SHA-256 values are
  `82dc7242d55abbaf24ed2dd65e7afe0f8090276d13ddb8378d743d8d2d8ce0b4`
  and `69a7b403a864a79b59b0931cfc545482407620b494c78c6f2b6683f0acc1569e`.
- Launched unchanged gamma0.9375 in `9929.14`; launcher SHA-256 is
  `1c5614e323f57a016746d6b39df4552aac2a46a317781c8f64891cab8a0e9bba`
  and launch receipt SHA-256 is
  `d16cc721ddcebd1f40d6f9135075e28452156ac7910cb2edad5ea9640cb19b20`.
  It entered `RUNNING` with no fatal marker. Gamma1.125 remains frozen and
  unstarted; both retained allocations again host exactly one scientific child
  plus telemetry/batch, and Internal-test/Gold remain sealed.

# 2026-08-08 06:58 CST gamma0.875 terminal and gamma1.125 launch

- Wave015 gamma0.875 is terminal `PASS_TRAINING_FINISHED` after 12 epochs at
  Dev Macro-F1 `0.527707` / ODER `0.008660`; terminal receipt SHA-256 is
  `6effab09151500d1d089bcf07f76e85d730004d21e544ae24d80dd75f13da26d`.
  It fails both parts of the original gate and misses the aspirational target.
- Closed Wave015 fail-closed with aggregate receipt SHA-256
  `c4d14c881232070000e83bd9ccb647f02dc6033b419c3397b6cfeeb9c09b90a9`.
  Gamma0.75 is the only jointly qualified arm within the wave, but retained
  gamma1/DMW010 remains higher on Macro-F1.
- Launched the already-frozen Wave016 gamma1.125 arm unchanged in `3066.13`.
  Launcher SHA-256 is
  `dc755340404207c5c63325694f9a226973abd7ad112156814659cac7850b55fc`;
  launch receipt SHA-256 is
  `e3a256457df0e411e5cc894556654238d8faba8bbb89377ddf852a5c7ee86832`.
  It entered `RUNNING` without a fatal marker while gamma0.9375 continues in
  `9929.14`. Both allocations again carry one scientific child plus
  telemetry/batch; all protected cohorts remain sealed.

## 2026-08-08 07:15 CST Wave016 parallel monitor

- Both frozen tight gamma-bracket arms remain healthy and non-terminal. Gamma0.9375 is at epoch 4 with best epoch 2 in `9929.14`; gamma1.125 is at epoch 2 with best epoch 0 in `3066.13`. Best/last checkpoints remain intact at about 310 MB; neither terminal receipt exists.
- Wave016 preparation/config/launch hashes remain exact; each retained allocation has one scientific child plus its preserved telemetry/batch steps. Launcher logs contain no fatal markers, and the server filesystem has about 1.2 PB free.
- Internal-test and Gold remain sealed with zero protected reads. No selection, cancellation, or new-wave launch was performed.

## 2026-08-08 07:35 CST Wave016 parallel monitor

- Both tight gamma-bracket arms remain healthy and non-terminal. Gamma0.9375 is at epoch 7 with best epoch 4 in `9929.14`; gamma1.125 is at epoch 5 with best epoch 4 in `3066.13`. Their progress files are fresh, best/last checkpoints remain intact at about 310 MB, and neither terminal receipt exists.
- Wave016 preparation/config/launch-receipt hashes still match exactly. Each retained allocation has one independent scientific child plus preserved telemetry/batch, launcher logs contain no fatal markers, and shared storage remains about 1.2 PB free.
- Internal-test and Gold remain sealed with zero protected reads. No intermediate selection, cancellation, or new-wave launch was performed.

## 2026-08-08 07:58 CST gamma0.9375 terminal and Wave017 launch

- Wave016 gamma0.9375 is terminal `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1 `0.5217260514330533` / ODER `0.008749218819748238`; terminal receipt SHA-256 is `2d71484e5037ea82c18c0347cfb66c1b3c43890b1069bff97f5b2c35ef8ef086`. It fails both original-gate dimensions and the aspirational target. Gamma1.125 continues unchanged in `3066.13`, so Wave016 remains open.
- Using only completed terminal evidence while gamma1.125 remained blinded, froze `wave017_class_balance_beta_tight_bracket_v1` at beta `0.9995/0.99995`. Preparation SHA-256 is `93220b7a5b178504c8d6981dac7b8b233a5f839ef7424feae071749a6349dff9`; config SHA-256 values are `6aab9cb50e7ce3e263593c0099c88e34f6d6fd37001345751eae5c559a494b60` and `6c056dc301efe7ce69340530e40e7791e9b897d5bcd00b6866ac7e31cc6ac0d1`.
- Launched unchanged beta0.9995 in `9929.15`; launcher SHA-256 is `ea673afc73bfd0bdb7e7e7cd22722901467ae6f8d4fb32bca6140523792657c5`, and launch receipt SHA-256 is `95b95c80640c34f2b593b2f6487fa374867f365083a0dc56a578d869bc178929`. It is healthy at epoch 0 step 700/5,026; beta0.99995 remains frozen and unstarted. Both retained allocations again host exactly one scientific child plus telemetry/batch, shared storage has about 1.2 PB free, and all protected-outcome counters remain zero.

## 2026-08-08 08:18 CST Wave016 closure and second Wave017 launch

- Wave016 gamma1.125 is terminal `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1 `0.5282841644175841` / ODER `0.005803053298812606`; terminal receipt SHA-256 is `3405002b1c97e697d7839ed5c1e73d6b9ecd80450245f071af52980ee976bd7b`. It fails both original-gate dimensions and the aspirational target.
- Closed Wave016 fail-closed with aggregate receipt SHA-256 `bfc010de1299fdd3cb1360b95759fe15cc65fe1933dd1c59d184be63d253e929`; neither gamma arm qualifies, so the retained DMW010 parent remains unchanged.
- Launched the already-frozen Wave017 beta0.99995 arm unchanged in `3066.14`. Launcher SHA-256 is `978a84f7b3b6dfa8aa33674b594414aff24db39b78b3fb1dca05f9622c70d706`, and launch receipt SHA-256 is `e4285a782d42d206dd08371dc4a06c479b57227660e5da6f9d3ecc5796936991`. It is healthy at epoch 0 step 200/5,026 while beta0.9995 continues at epoch 2 step 1,300/5,026 in `9929.15`; each allocation has exactly one scientific child plus telemetry/batch, hashes remain exact, shared storage has about 1.2 PB free, and protected reads remain zero.

## 2026-08-08 08:35 CST Wave017 parallel monitor

- Both frozen beta arms remain healthy and non-terminal. Beta0.9995 is at epoch 4 step 2,800/5,026 with best epoch 2 in `9929.15`; beta0.99995 is at epoch 2 step 1,800/5,026 with best epoch 0 in `3066.14`. Best/last checkpoints are intact at about 310 MB, and neither terminal receipt exists.
- Wave017 preparation/config/launch-receipt hashes remain exact. Each retained allocation has exactly one scientific child plus telemetry/batch, launcher logs contain no fatal markers, shared storage has about 1.2 PB free, and protected reads remain zero with Internal-test/Gold sealed.

## 2026-08-08 08:55 CST Wave017 parallel monitor

- Both beta arms remain healthy and non-terminal. Beta0.9995 has completed epoch 6 with best epoch 4 in `9929.15`; beta0.99995 is at epoch 4 step 4,300/5,026 with best epoch 2 in `3066.14`. Their progress files are fresh, best/last checkpoints remain intact at about 310 MB, and neither terminal receipt exists.
- All Wave017 preparation/config/launch-receipt hashes remain exact. Each retained allocation has one scientific child plus telemetry/batch, launcher logs contain no fatal markers, shared storage has about 1.2 PB free, and protected reads remain zero with Internal-test/Gold sealed. No decision was made from intermediate epochs.

## 2026-08-08 09:18 CST beta0.9995 terminal and Wave018 launch

- Wave017 beta0.9995 is terminal `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1 `0.5268827231128156` / ODER `0.003303276493170253`; terminal receipt SHA-256 is `6fb4af4122f65c759ac97b35a0e13593acaa34cb9906421a2aa436c3af5d9b60`. It gains ODER headroom but fails the original F1 floor and aspirational target. Beta0.99995 continues unchanged in `3066.14`, so Wave017 remains open.
- Using only completed terminal evidence while beta0.99995 remained blinded, froze `wave018_gradient_clip_norm_v1` at gradient-clip norm `0.5/2.0` around parent `1.0`. Preparation SHA-256 is `1265e7c545c46a8f9c0d02fd1869de43cab071a67d9d81d7b4f015ad793d26e8`; config SHA-256 values are `b9ed3bec08638e5b5960a4c386dabcd62281a3e19d1c320e4e9d1a27793fc948` and `ea6247c963516a5a39e0bb3d84043de27e83dc0c8c4002ab9fc74d6c3537361e`.
- Launched unchanged gradient clip 0.5 in `9929.16`; launcher SHA-256 is `0a5acaf427583a94b14a4fffd563995673bd3250661cc8418fbf4a687aabcaa3`, and launch receipt SHA-256 is `41e3bb06b22d5f2571454984fcdf0f4e626fecea644a63c7826583df9ea58d44`. It is healthy at epoch 0 step 200/5,026 while beta0.99995 continues at epoch 7 step 2,400/5,026. Each allocation has one scientific child plus telemetry/batch, shared storage has about 1.2 PB free, and protected reads remain zero.

## 2026-08-08 09:38 CST Wave017 closure and second Wave018 launch

- Wave017 beta0.99995 is terminal `PASS_TRAINING_FINISHED` after nine epochs at Dev Macro-F1 `0.5244603295972732` / ODER `0.009909829479510758`; terminal receipt SHA-256 is `4db231168d1c9e3b7fe86d0149098f904ccded6b09ab1604d8bb7e30af50a056`. It fails both original-gate dimensions and the aspirational target.
- Closed Wave017 fail-closed with aggregate receipt SHA-256 `e6cf4a499145eb3496ca24d66e363bbf55fd42ce8d75f78582779e84076292b5`; neither beta arm qualifies, so DMW010 remains globally retained.
- Launched the already-frozen Wave018 gradient-clip 2.0 arm unchanged in `3066.15`. Launcher SHA-256 is `4f25cef4c88551a2e8a0281babf2bdc391b8af586ddb14a48e9c6e86af76fd8c`, and launch receipt SHA-256 is `9c4aae4022ad68d54242d8989db8ab5cb497889b15771010e04076754c204d5f`. It is healthy at epoch 0 step 200/5,026 while gradient clip 0.5 continues at epoch 2 step 2,500/5,026 in `9929.16`; each allocation has one scientific child plus telemetry/batch, hashes remain exact, shared storage has about 1.2 PB free, and protected reads remain zero.
