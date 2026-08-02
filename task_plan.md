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

- On 2026-08-03 the user authorized implementation and formal execution of the
  complete experiment program defined by the two Chinese paper authority
  documents, including a 20-minute recurring monitor, until the registered
  program reaches its terminal GO/HOLD/STOP state.
- Authorization does not collapse the documents' sequencing gates: freeze the
  patient-disjoint split first; use Train/Dev for performance development;
  freeze method/config/checkpoint/temperature and the test protocol before the
  single formal Internal-test/Gold read; run the VLM appendix only after the
  ViT program is frozen.
- Never tune from Internal-test/Gold, reuse revealed legacy cohorts, weaken
  legal/privacy exclusions, or silently continue past a preregistered HOLD/STOP
  gate. Every formal run must receive a registry row, immutable config/receipt,
  completion marker, and patient-level leakage audit.

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

### Phase 10 - Rule candidates and Luna pilot
Status: complete - HOLD_FULL_EXPANSION

- Generate deterministic rule candidates from the frozen 238,511-pair pool.
- Audit candidate counts by source, finding, label, and time basis.
- Prepare a deterministic stratified 100-200-row Luna pilot and run the locked
  external reviewer only within the newly authorized labeling scope.
- Fail closed on ID/schema/evidence conflicts and decide whether full-scale
  Luna expansion is operationally and scientifically justified.

### Phase 11 - Full Luna expansion and label manifest
Status: pending - held by pilot gate

- Expand Luna review only after the pilot passes quality and runner gates.
- Merge outputs, audit Tier-A/Tier-B/Reject counts and hashes, and stop before
  split freeze, cache generation, or training.

### Phase 12 - Labeling verification and local handoff
Status: complete

- Run tests/static/preflight gates, update the durable labeling receipt,
  commit, push to the local-only remote, and verify equality.

### Phase 13 - Independent-intersection silver protocol
Status: complete

- Preserve the strict evidence-based 150-row pilot as engineering history.
- Add a separate rule-blind AI interface whose external payload contains only
  a short sample alias, target finding, prior/current reports, and temporal
  semantics; never expose the rule label or alias-to-original map.
- Accept a training silver row only when the local rule label exactly equals
  the independent AI label and the AI label is not `Unclear`.
- Record mismatches and `Unclear` rows as exclusions, with source-specific
  agreement statistics.

### Phase 14 - Simplified 150-row pilot
Status: complete

- Reuse the frozen deterministic 150-patient selection for a comparable pilot.
- Run one canary before the remaining batches and fail closed on schema or ID
  mismatch.
- Report MIMIC and CheXpert Plus agreement separately; do not launch the full
  148,798-row expansion from this pilot authorization.

### Phase 15 - Audit gate, documentation, and local handoff
Status: complete

- Encode a required 200-300-row source-by-five-label human audit before formal
  training or paper use of the full silver corpus.
- Update the active manuals/status documents, run repository verification,
  commit, and push only to the local bare remote.

### Phase 16 - Sol blind-review authority and three-way audit code
Status: complete

- Reuse the exact frozen 150-row candidate roster and the same report-only
  input fields; never expose the Luna label, rule label, patient ID, or private
  alias map to Sol.
- Add a separately gated `gpt-5.6-sol` pilot authority and a deterministic
  three-way comparison of rule, Luna, and Sol outputs.
- Report six-class and decisive five-class agreement, Cohen's kappa, complete
  confusion, source/label strata, `Worse`, the 30 rule-Luna mismatches, and the
  17 Luna-Unclear rows without calling any agreement an accuracy estimate.

### Phase 17 - Sol canary and 150-row blind review
Status: complete

- Run one 20-row canary, then resume the remaining seven batches only after
  schema and exact-ID checks pass.
- Preserve all raw outputs and timing receipts; do not retry or manually repair
  a structurally invalid output.

### Phase 18 - Sol comparison status, verification, and local handoff
Status: complete

- Write the bounded Sol-vs-Luna result and retain the 200-300-row human audit
  requirement.
- Keep full labeling, split, cache, training, test, gold, and external outcomes
  closed.
- Run repository gates, commit, push only to the local bare remote, and verify
  local/remote equality.

### Phase 19 - Luna-primary policy and full-run authority
Status: complete

- Replace rule-Luna agreement admission with Luna-primary five-class labels
  inside the already frozen 148,798-row candidate pool.
- Retain deterministic code only for pair/finding construction, uncertainty
  and structural filtering, ID/source/patient audits, batching, and receipts.
- Keep every valid Luna five-class output; discard `Unclear` and any invalid or
  missing output. Never repair a label manually or from the old rule label.
- Define a future clinician-reviewed Gold subset: Luna may prelabel it, but
  every Gold row must receive human confirmation and its patients must remain
  quarantined from training.

### Phase 20 - Full batch preparation and concurrency qualification
Status: complete

- Prepare the exact 148,798 candidates with the frozen two-field prompt/schema
  and verify candidate, prompt, schema, and external-field hashes.
- Run a bounded concurrent qualification before the long expansion; choose a
  safe shard count from observed failures/rate limits rather than assuming
  unlimited service concurrency.

### Phase 21 - Complete full Luna labeling and primary merge
Status: complete

- Resume until every frozen batch has one structurally valid, exact-ID output.
- Merge all non-`Unclear` Luna labels into the Silver manifest and write all
  discarded `Unclear`/invalid rows to an exclusion manifest and audit.
- Report source/finding/label counts, retention, failures, retries, hashes, and
  patient/source integrity; do not start training.

### Phase 22 - Human-audit and Gold-review rosters
Status: complete

- Generate a deterministic 200-300-row source-by-Luna-label Silver accuracy
  audit roster, with no overlap into training while review is pending.
- Generate a separate fully reviewed Gold-test candidate roster and make clear
  that it remains `GOLD_PENDING_HUMAN_REVIEW` until every row is confirmed.

### Phase 23 - Documentation, verification, and local handoff
Status: complete

- Update the paper manual/result tables to describe deterministic preprocessing
  plus Luna-primary Silver, with human accuracy and fully reviewed Gold gates.
- Run repository/runtime audits, commit, push only to the local bare remote,
  and verify equality.

### Phase 24 - Blind human-review handoff
Status: complete

- Write the Chinese review protocol for the seven allowed human dispositions.
- Export the frozen 250-row roster as a blind workbook with no Luna label,
  rule label, patient hash, or original sample ID.
- Add validated input fields, completion formulas, a codebook, and QC counts;
  keep deblinding and Gold freeze closed until the completed workbook returns.

### Phase 25 - First human-response import and audit
Status: withdrawn by user; result deleted

- The first returned workbook and its derived runtime audits were invalidated
  after reviewer reliability was questioned.
- The tracked workbook was restored to the verified original empty template;
  both `human_review_complete_v1` and `human_review_complete_v2` were deleted.
- No first-review human label or derived Gold row remains authoritative.

### Phase 26 - Result documentation, verification, and local handoff
Status: superseded by Phase 27

- Write the bounded human-review result without presenting one-reviewer Gold as
  clinical truth beyond the protocol.
- Run focused tests/static checks and runtime conservation/leakage audits.
- Commit and push only to the local bare remote; do not start split/cache/train.

### Phase 27 - Senior-doctor Luna-assisted review handoff
Status: complete

- Rebuild the same frozen 250-row roster in a newly shuffled workbook.
- Show the five-class Luna label while keeping all first-review answers absent.
- Collect an empty senior-doctor label, reviewer, date, optional correction
  note, and required unusable reason for every row.
- Treat the result as Luna-assisted confirmation/correction, not independent
  blind agreement; keep Gold freeze and training closed until the workbook
  returns and passes exact-ID/completeness audits.

### Phase 28 - Compact response import and senior-consensus Gold freeze
Status: complete

- Accept the doctor-returned compact A-H workbook without modifying its 250
  labels or pretending the deleted reviewer/date columns were filled.
- Bind a separate user-attested provenance receipt: two physicians, each with
  more than five years of clinical experience, producing one shared result
  column while seeing the Luna label.
- Verify exact `review_id`, report, source, finding, and displayed Luna-label
  binding; freeze all decisive senior-consensus rows as Gold and retain every
  roster patient in quarantine.
- Report confirmation/correction statistics without calling this independent
  blind accuracy or inter-rater agreement; stop before split/cache/training.

### Phase 29 - Gold result documentation, verification, and local handoff
Status: complete

- Synchronize the active status/manual/result surfaces with the frozen audit,
  hashes, source/label counts, and four corrected cases.
- Run repository and runtime conservation/leakage gates, commit, push only to
  the local bare remote, and verify local/remote equality.

### Phase 30 - Full-program authority, readiness audit, and 20-minute monitor
Status: in progress

- Re-read both paper authority documents, inventory implemented versus missing
  experiment surfaces, inspect GPU/model/data/disk/process state, and bind the
  new full-program authorization without changing frozen Gold or Silver.
- Create one thread heartbeat every 20 minutes that re-reads planning files,
  monitors the active formal stage, resumes only identity-preserving work, and
  never opens Internal-test/Gold before the protocol-freeze gate.

### Phase 31 - Patient-disjoint split freeze and leakage receipt
Status: complete

- Formally freeze the 80/10/10 patient split from exactly 124,430 eligible
  Silver rows while keeping all 250 Gold patients and 2,297 associated Silver
  rows quarantined.
- Independently verify counts, label/source support, manifest hashes, and zero
  overlap across Train/Dev/Internal-test/Gold before caching.

### Phase 32 - Full Block-8/text cache and input audit
Status: pending

- Bind the local BiomedCLIP checkpoint, build resume-safe caches for the frozen
  split, and verify exact sample/image/text lineage, shapes, finite values,
  storage conservation, and completion markers.

### Phase 33 - Train/Dev performance development
Status: pending

- Implement any still-missing D2xx/M3xx data-scaling, head, adapter, and loss
  variants required by the authority documents; use only Train/Dev.
- Run the bounded development matrix and apply the documented macro-F1 exit
  gate. Diagnose label/source/class failure if the gate is not met; do not read
  Internal-test or Gold.

### Phase 34 - Formal protocol and method freeze
Status: pending

- Freeze the selected PRTA method, baseline/ablation list, three seeds, metrics,
  bootstrap, calibration, intervention, subgroup, visualization, checkpoint,
  and one-time test-read protocol with hashes and a freeze receipt.

### Phase 35 - Formal baselines and PRTA main runs
Status: pending

- Execute B401-B404 for seeds 17/29/43 under equal frozen budgets; include B405
  only if its stable native implementation is available before freeze.
- Validate checkpoints and Dev outputs without choosing anything from test.

### Phase 36 - Formal ablations
Status: pending

- Execute A500-A506 across seeds 17/29/43 with the same split, head, and budget;
  run optional A507 only if its frozen Rule-only label manifest is valid.

### Phase 37 - One-time evaluation, trust, calibration, and subgroups
Status: pending

- After the protocol freeze and all formal training complete, open Internal-test
  and the 250-row Gold once for frozen inference only.
- Run T601-T614, patient-clustered confidence intervals, calibration fitted on
  Dev only, and preregistered source/finding/progression/view/interval analyses.

### Phase 38 - Figures and failure analysis
Status: pending

- Produce V701-V708 from frozen results and select qualitative cases only by
  the preregistered, outcome-independent bucket rules.

### Phase 39 - PRTA-to-VLM appendix
Status: pending

- Freeze the final PRTA checkpoint, implement X801-X806 as a single appendix
  path, and ensure VLM outcomes cannot alter the ViT method or claims.

### Phase 40 - Paper tables, final audit, and local handoff
Status: pending

- Populate the unified Run Registry and Tables 1-8, reconcile every planned
  task with an artifact or explicit N/A/HOLD/STOP rationale, run final audits,
  commit, and push only to the local bare remote.

## Next Step

Pin and strictly load the local BiomedCLIP model root, estimate/cache storage,
then implement resume-safe full-cache orchestration and begin the frozen
Block-8/text cache without opening Internal-test or Gold outcomes.

## Completion record - 2026-08-03

- Full Luna-primary output: 7,440/7,440 batches and 148,798/148,798 unique
  candidate IDs; final runtime audit PASS.
- Silver: 126,727 valid Luna five-class rows; 22,071 Luna `Unclear` rows
  discarded. Rule–Luna agreement remains diagnostic-only and never affects
  admission or labels.
- Gold candidate roster: 250 rows, 250 unique patients, exact 25 rows per
  source-by-five-label stratum. All 2,297 Silver rows belonging to those
  patients are quarantined, leaving 124,430 training-eligible Silver rows with
  zero patient overlap.
- Senior Luna-assisted panel result: two user-attested physicians with more
  than five years of experience produced one consensus column while seeing the
  Luna label; 246/250 labels were confirmed, four corrected, zero excluded,
  and all 250 decisive rows are frozen as Gold. This is assisted panel
  confirmation/correction, not independent blind accuracy or inter-rater
  agreement.
- Gold manifest SHA256:
  `564d9b389b6c0f80354a5880ed30aabfdb66281535d14b2f3626f9fa14a8bcad`.
- Full repository verification passes with 67 tests, Ruff, compile, human-review
  preflight, and zero Gold/training-patient overlap. Split, cache, training, and
  internal-test execution remain closed behind separate gates.

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
| Treat the 2026-08-02 follow-up approval as labeling-phase authority | The immediately preceding handoff named rule candidates and Luna review as the next gate; split/cache/train remain separately unauthorized. |
| Supersede the strict evidence workflow only for future full silver construction | The completed v6 pilot remains immutable engineering evidence; the new protocol gets separate prompt/schema/config/artifacts. |
| Keep the rule label local | The AI judgment must be independent and cannot receive a candidate-answer hint. |
| Require exact non-Unclear agreement for silver admission | Agreement raises confidence but is not asserted as ground truth; all other rows are excluded. |
| Require a 200-300-row source-by-label human audit before training/paper use | The lightweight audit measures silver accuracy without blocking automated labeling itself. |
| Treat Sol review as agreement evidence, not Luna accuracy | Correlated AI errors remain possible; only human review can estimate clinical correctness. |
| Keep rule outputs for diagnostics but reconsider them as admission labels | Sol review tests whether Luna can become the primary classifier while automation remains responsible for candidate structure and audits. |
| Adopt Luna-primary five-class admission | The user accepted the Sol evidence and explicitly authorized full labeling; non-`Unclear` Luna outputs are retained regardless of rule disagreement. |
| Do not call Luna-only test labels Gold | Gold status requires human confirmation of every selected row; a sampled accuracy audit validates Silver quality but does not convert unreviewed labels into Gold. |
| Treat the 2026-08-03 approval as full-program formal authority | The user explicitly requested code completion plus formal execution under both paper documents until terminal completion, with a 20-minute recurring monitor; internal sequencing and GO/HOLD/STOP gates remain binding. |

## Errors Encountered

- 2026-08-03: an inventory `rg` pattern began with `--mode`, which `rg`
  interpreted as an option and rejected. Future searches use the `--` option
  terminator before such patterns; no files or experiments were changed.
- 2026-08-03: the first heartbeat creation attempt used `destination=local`
  without an explicit thread ID, so the automation API rejected it before
  creation. Retry with the current-thread destination so the app binds the
  heartbeat to this task automatically.
- 2026-08-03: the first split-source inspection guessed `cli_split.py` and
  `data/splits.py`; the repository inventory shows the actual module is
  `data/splitting.py` and the script itself carries the CLI entrypoint. Inspect
  those exact files next; no execution was attempted.
- 2026-08-03: the first focused streaming-cache test pass found one missing
  `pytest` import plus Ruff import-order/line-length issues. The functional
  resume round-trip passed; add the import and format the two code locations
  before rerunning the same focused gate.

- 2026-08-02: a code-inventory command guessed a nonexistent
  `src/prta_cxr/cli_utils.py`; the existing CLI modules and script bootstrap
  already contained the required patterns, so no replacement utility was
  needed. The first human-review lint pass then found three 89-95 character
  lines; wrapped those lines without changing behavior before formal execution.

- 2026-08-02: static qualification found `--preparation-receipt` attached to the
  batch-preparation parser while the formal runner consumed it. Moved the option
  to the runner before any Luna full-run call; no external labeling was started
  with the faulty entrypoint.
- 2026-08-02: a preflight command referenced the nonexistent legacy name
  `scripts/03a_run_independent_ai.py`; corrected to the repository entrypoint
  `scripts/03b_run_independent_labeling.py`. No external call was made.
- 2026-08-02: the first 4-worker qualification exposed a real Luna omission:
  batch 1 returned 19/20 IDs. The runner correctly failed closed. Stopped the
  remaining qualification workers after preserving 8 valid outputs, then added
  bounded per-batch retry with every malformed attempt retained for audit.
- 2026-08-02: the first attempted 64-worker expansion used malformed PowerShell
  (`-Filter` and `-ne` lacked token-separating spaces), so completed outputs were
  misread as empty and only two resume-safe half-range workers started. No data
  was overwritten because their ranges were disjoint and `--resume` was active.
  Stopped those exact two PIDs and rebuilt the missing-range calculation with
  explicit file-count and 32-to-64 range assertions before retrying expansion.
- 2026-08-02: the corrected scan found 33, not 32, missing runs because outputs
  completed during earlier stop/restart boundaries fragmented one original
  shard. The assertion stopped execution before any new worker launch. Revised
  the splitter to preserve all 33 real gaps and bisect the 31 largest, yielding
  exactly 64 non-overlapping ranges with exact remaining-count coverage.

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
| First Luna pilot launch failed before sending input with Windows `WinError 5` because `codex` resolved to a PowerShell wrapper | 1 | Resolve `codex.cmd` explicitly on Windows, keep the empty output directory, and retry through the new resume-safe runner. |
| The fourth pilot batch returned `accept` together with a conflict flag; Windows stderr capture also attempted GBK decoding | 1 | Invalidate the v1 pilot outputs, strengthen the prompt, attempt schema-level Tier-A enforcement, capture UTF-8 with replacement, and preserve future rejected outputs; the next row records the schema compatibility result. |
| The v2 first batch was rejected before generation because Codex Structured Outputs does not permit `allOf` in this schema position | 1 | Retain the strengthened prompt and runtime contract, remove the unsupported conditional schema keyword, regenerate v3 batches with the new schema hash, and canary the first batch again. |
| The v3 pilot passed JSON/ID/decision gates but only 48/74 Tier-A rows had all three evidence fields as contiguous report spans | 1 | Hold full expansion, require verbatim contiguous extractive citations in the prompt and merge contract, invalidate v3 for downstream labeling, and rerun the same frozen 150-row pilot as v4. |
| The first v4 canary omitted or altered at least one sample ID and failed closed; the mismatch check sat just outside the failed-output preservation block | 1 | Move ID validation inside the preservation block, keep the output directory free of accepted files, and retry the unchanged v4 authority without manual repair. |
| The unchanged v4 canary again omitted IDs; the preserved output had 23 unique expected rows, 2 missing, 0 extra, and 0 duplicates | 1 | Keep the exact-ID gate, explicitly require one ordered output per input including rejects, reduce the regular batch size from 25 to 20, and regenerate the unchanged 150-row pilot as v5. |
| The v5 20-row canary returned 20 unique rows but altered one 64-character sample hash, yielding one missing and one extra ID | 1 | Introduce short batch-local aliases, withhold the alias-to-original map from the model payload, validate exact aliases, and restore original IDs locally before atomic output; regenerate as v6. |
| The v6 canary passed alias/ID gates, but one of 14 accepted rows used non-extractive current/comparison evidence | 1 | Preserve the Luna output, deterministically demote every non-extractive accept to Reject with an audit reason, and require Tier-A extractive evidence by construction rather than trusting prompt compliance. |
| v6 batch 6 twice returned an accept/flag contradiction under the unchanged prompt | 1 | Stop stochastic retrying; separate structural output validation from deterministic label admission, preserve raw Luna rows, and demote accept+conflict/mismatch/non-extractive records to audited Rejects. |
