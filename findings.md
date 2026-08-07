# Findings - full-data training pipeline

## 2026-08-04 Sol all-risk rerun initial boundary

- The historical development result remains `STOP_DEVELOPMENT_GATE`; the new
  user authorization creates a separate label-version rerun and does not
  authorize retrospective tuning or protected outcome access.
- The private runtime still contains the previous formal program, cache,
  development outputs, keeper state, and unified registry, so the safest path
  is to prove subset compatibility and reuse immutable features while creating
  new run identities rather than rebuilding or overwriting historical assets.
- Both RTX 3090 GPUs are currently completely idle (0 MiB, 0% utilization),
  with no Python training process. The only command-line match was the current
  read-only PowerShell probe itself. Free space is approximately 410 GiB on H:
  and 244 GiB on E:, sufficient for versioned rerun outputs.
- The previous formal root is intact at
  `H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\formal_program_v1`.
  Its reusable cache is `cache/full_repartition_v1`; historical development
  outputs remain under `development/runs`, and terminal gate/state receipts
  remain under `program_keeper_v1`. The split surfaces include outcome-free
  `cache_input_v1.jsonl`, labeled `train_dev_v1.jsonl`, and separately sealed
  `internal_test_labeled_v1.jsonl`; the rerun must use only the new active
  Train/Dev manifest and must not parse the sealed file.
- The exact historical gate inputs were PRTA `M302-CBF` (seed 17),
  `M304-S29`, `M304-S43`, plus diagnostic baselines B401-B403 at seed 17.
  The strongest temporal comparator was `M305-B403-S17` (Macro-F1 0.447629,
  ODER 0.037021). The frozen gate failed on mean F1 0.458680, every seed below
  0.48, seed-17 gain only +0.005959, and mean ODER 0.042202 above baseline.
- The reusable store contains a 44.2-GB contiguous Block-8 feature file plus
  cache manifest, text cache, image inventory, and training-store receipt.
  No protected outcome needs to be read to determine cache subset coverage.
- Frozen configs use PRTA/CB-Focal/tail4/H0 with rank 32, batch 16, LR 1e-4,
  20-epoch maximum, 6-epoch minimum, patience 4, and seeds 17/29/43. The TILA
  comparator uses the same optimization budget and seed 17. Although stored
  class counts reflect the old labels, the formal CLI deterministically
  rematerializes counts from the supplied Train rows before model creation.
- The existing queue runner already launches versioned output directories on
  two explicit CUDA devices, writes registry RUNNING/terminal rows, and keeps
  Internal-test/Gold closed. A separate rerun queue/root can reuse this logic.
- The local BiomedCLIP root is `H:\xiyao\model\biomedclip`; the rerun must bind
  its weight hash to the cache encoder hash
  `52cc993c5c5ff962bd0c60931874bc001e7e9b41666a385530f4a036294576be`.
  The completed 250-row human Silver quality audit remains the formal training
  gate; it is not a label source and can be reused unchanged. Its 0.984 value
  is explicitly Luna-visible senior-panel confirmation and must not be called
  accuracy of the later Sol replacements. The user separately authorized this
  rerun after manual inspection, so the receipt is only the pre-existing
  clinical-QC gate and its limitation stays explicit in the rerun receipt.
- To reproduce the earlier development decision rather than only the PRTA
  mean, the rerun needs PRTA seeds 17/29/43 plus both temporal seed-17 baselines
  B402 (Siamese Diff) and B403 (TILA). The same frozen function chooses the
  stronger of those two. Current-only B401 is not part of that temporal maximum
  and is unnecessary for the requested threshold comparison.
- Image Block-8 features are label-free and safely reusable by subset. Static
  dataset inspection initially raised a possible text-cache label-version risk
  because per-sample transition embeddings would take precedence over label
  prototypes. Direct inspection of both the writer and live cache resolved the
  concern: the cache has no `transition_embeddings` key and contains exactly
  12 finding embeddings plus 60 `finding|label` prototypes. Each rerun row
  therefore selects the prototype from its current Sol label, so the existing
  text cache is label-version safe and can be reused unchanged.

## 2026-08-04 Tier-B/C Sol-authoritative replacement exact-set audit

- The replacement target is the exact union of 5,968 newly reviewed Train Tier-B/C rows and 13 pilot-only Train Tier-B/C rows already reviewed by Sol but never made authoritative. The sets are disjoint and all 5,981 IDs are present in the current 90,771-row active Train manifest.
- New review actions are 4,604 decisive / 1,364 `Unclear`, including 1,091 changed labels and 3,513 same-value authority rebindings. Pilot-only actions are 12 decisive / 1 `Unclear`; 2 historical pilot Luna labels differ from the current active Train value, so applying Sol to the actual active baseline gives 2 changed and 10 same-value pilot actions. Combined active-baseline actions are therefore 4,616 decisive / 1,365 `Unclear`, 1,093 changed, and 3,523 same-value rebindings.
- Applying the frozen `Unclear -> exclude` policy must yield exactly 89,406 Train rows. With the unchanged 13,420-row Sol-authoritative Dev surface, the new active Train+Dev manifest must contain exactly 102,826 rows.
- Existing implementation patterns already enforce private output paths, immutable input hashes, byte-preserving copies for non-target rows, and versioned active pointers. The new materializer should reuse those contracts while leaving the current Dev, Internal-test, and physician-consensus Gold hashes unchanged.
- The 2 pilot baseline mismatches are not silently normalized: provenance records both the historical review label and the current active label. Sol remains the user-authorized authority, so both rows take their Sol labels; this changes the active label value in both cases.

## User-authorized policy direction

- Old debugging-only subsets and small-cohort partitions are not authorities for
  the new training roster.
- All previously used datasets should be reconsidered through one new source
  catalog so eligible data can contribute to a larger training pool.
- New splits must be generated from scratch at patient level.

## Boundaries that remain active

- Dataset presence is not sufficient for activation: provenance,
  license/DUA/privacy, lineage, joins, and overlap checks must pass.
- Historical revealed tests cannot become train/dev data.
- Protected gold and external confirmation cohorts stay outside model selection.
- Formal work continues to require explicit authorization plus the repository's
  double acknowledgement lock.

## Independent-silver protocol decision - 2026-08-02

> Historical pilot policy, superseded for the full run by the Luna-primary
> policy below. The pilot artifacts and measurements remain immutable.

- The strict v6 pilot established that evidence-heavy per-row review is costly
  and failure-prone; it remains useful as engineering validation but is not the
  full-scale labeling authority.
- Future large-scale labeling should use two independent automated judgments:
  deterministic rules locally and a rule-blind AI label from the report pair.
- The AI must not receive the rule label. Exact non-`Unclear` agreement alone
  enters the silver manifest; all mismatches and `Unclear` responses are
  excluded rather than repaired or adjudicated automatically.
- Overall agreement is insufficient: MIMIC and CheXpert Plus require separate
  rates, and the final corpus requires a source-by-five-label human audit of
  roughly 200-300 rows before training or paper claims.
- The simplified two-field output eliminated the engineering failures observed
  in the strict evidence pilot: all 8 batches and all 150 IDs passed without a
  retry, at 344.991 seconds total external time.
- Pilot exact-agreement retention was 103/150 (68.67%). Source retention was
  similar (MIMIC 69.33%, CheXpert Plus 68.00%), but that is retention rather
  than clinical accuracy and still requires separate source-level human audit.
- Rule-label retention varied materially: Resolved 74.07%, Stable 73.33%, New
  70.00%, Improved 69.70%, and Worse 56.67%. The low Worse intersection is a
  priority stratum for the later human accuracy sample, not a reason to expose
  the rule answer or tune against this pilot.

## Sol blind-review analysis contract - 2026-08-02

- Luna-Sol agreement measures inter-model consistency, not Luna correctness;
  shared training signals and report ambiguity can create correlated errors.
- Primary reporting must include all six outputs including `Unclear`; a
  separate decisive five-class agreement must state its reduced denominator.
- The frozen 150-row roster is rule-stratified and therefore evaluates the
  existing rule-extractable candidate pool, not every possible report pair.
- The 30 rule-Luna mismatches require four-way accounting: Sol supports Luna,
  supports rule, selects a third label, or returns `Unclear`. The 17 Luna-
  `Unclear` rows require a separate Sol-label distribution.
- The blind comparison passed all engineering gates. Six-class Luna-Sol
  agreement was 80.67% because 26 rows had at least one `Unclear`; among 124
  mutually decisive rows, five-class agreement was 92.74% with kappa 0.908.
- Both sources cleared 90% decisive agreement: CheXpert Plus 90.48% and MIMIC
  95.08%. Their all-six-class rates were 80.00% and 81.33%, respectively.
- `Worse` was not the weakest decisive Luna stratum: Sol agreed on 19/20
  decisive Luna-Worse rows (95%), with three further Sol `Unclear` and one
  New-versus-Worse disagreement. New was the lowest decisive label stratum at
  30/35 (85.71%).
- In the 30 rule-Luna mismatches, Sol favored Luna 21 versus rule 4 (plus one
  third label and four `Unclear`). This is pilot evidence for Luna as the main
  five-class generator inside the current rule-extractable candidate pool, not
  proof of correctness and not evidence for label-agnostic candidate coverage.
- Of 103 prior rule-Luna exact rows, Sol confirmed 94, differed on 4, and was
  `Unclear` on 5. Across all 9 mutually decisive Luna-Sol disagreements, zero
  were direct Improved/Worse or New/Resolved opposite-direction pairs.

## Luna-primary policy - 2026-08-02

- The five-class label authority is now Luna alone within the frozen
  rule-extractable candidate pool. The old rule label remains provenance and
  diagnostic metadata only and must not overwrite or veto a Luna class.
- Every valid Luna output in the five-label vocabulary is retained as Silver;
  Luna `Unclear`, missing IDs, duplicate IDs, extra fields, or unknown labels
  are fail-closed exclusions.
- A sampled clinician audit estimates Silver accuracy. A Gold test artifact is
  a different object: every row in that subset must be human-reviewed, and its
  patients must be fully excluded from training to prevent leakage.
- The roster quarantine is not consumed automatically by split freezing.
  Roster generation must therefore materialize a training-eligible Silver
  manifest that removes every Silver row from every selected patient; focused
  tests require zero patient overlap with the quarantined manifest.

## Returned human review - 2026-08-02

- The original blind workbook was modified in place and passed read-only import
  validation: 250 rows, 250 unique `review_id` values, exact headers and case
  sequence, no missing or invalid human labels, reviewer IDs, or review dates.
- Human dispositions before deblinding are Improved 50, Worse 46, New 14,
  Resolved 35, Stable 61, Unclear 40, and Unusable 4. Every Unusable row has a
  reason. These are response-completeness facts, not Luna accuracy results.
- Human `Unclear` and `Unusable` cannot enter Gold. The remaining 206 decisive
  five-class rows may be frozen with the human label only after exact roster
  binding and deblinded source/label audits pass. All 250 roster patients must
  remain quarantined regardless of whether their selected row enters Gold.

## Initial code state

- The clean repository has validated PRTA/CMCP/cache/evaluation core and
  synthetic smoke coverage.
- Scripts 01-06 and 08-11 currently return dry-run receipts only.
- Formal training deliberately raises `NotImplementedError`.
- The next implementation must preserve the current 14-test baseline while
  converting data/train/evaluate surfaces into functional code.

## Legacy reference audit

- The old data builder contains useful algorithms for one-frontal-per-study,
  adjacent longitudinal pairing, exclusion registries, overlap audits, and
  cache sizing, but it hard-codes R37 schemas, cohort floors, absolute H-drive
  paths, and old quarantine counts. Only the generic algorithms are reusable.
- The old report-transition extractor contains useful deterministic evidence,
  negation, uncertainty, comparison-object, and direction rules. These should
  move into the clean labeling namespace without its R37 schema/version.
- The old Block-8 cacher contains the validated BiomedCLIP preprocessing and
  intermediate-token extraction, but model/data/runtime paths must become
  explicit config/CLI values and formal writes must remain locked.
- The old formal pipeline has useful atomic-write, lock, task-state, and receipt
  patterns. Old GPU lanes, candidate statuses, R-numbered tasks, and revealed
  roster assumptions are not reusable.

## Implementation direction

- A source catalog will distinguish `eligible`, `debug_only_legacy`,
  `revealed_test`, `protected_gold`, `external_confirmation`, and governance
  blocks. Debug-only legacy status will not exclude a record in the new build;
  the other boundaries will.
- New partitions should be source-aware and label-aware while assigning whole
  patients atomically and deterministically.
- Formal CLI commands should support a `--preflight`/synthetic path without the
  environment acknowledgement, and require the existing double lock before
  reading real inputs or writing formal artifacts.

## Implemented data interfaces

- `SourceSpec` activates both `eligible_candidate` and former
  `debug_only_legacy` sources only after license, de-identification, processing,
  and longitudinal-report gates pass. Revealed/gold/external/governance statuses
  remain blocked.
- Source manifests resolve from named environment variables rather than
  hard-coded disk paths.
- Raw patient identifiers are immediately namespaced and SHA-256 hashed; output
  study/pair manifests do not persist raw patient IDs.
- Full candidate assembly selects one deterministic frontal image per study,
  removes protected patients and duplicate image lineage, then pairs adjacent
  visits within source and patient.
- The split algorithm treats the patient as atomic and greedily balances
  source/finding/label strata plus row and patient totals for new
  Train/Dev/Internal-test partitions.

## Cache and training implementation

- Image cache identity is `SHA256(source|normalized_image_path)`, preventing
  equal source-local paths from colliding without persisting patient IDs.
- The new cache stores only `[197, 768]` Block-8 FP16 features. Reports, labels,
  and patient identifiers are explicitly absent from the cache receipt.
- Finding queries and transition supervision use the same locally loaded,
  frozen BiomedCLIP text tower as the vision checkpoint. Transition text is a
  fixed finding-by-class prototype, not a protected outcome lookup.
- The training loader reads only the requested split. The formal train CLI
  creates Train and Dev datasets and records `internal_test_opened=false`.
- Formal internal evaluation is a different CLI gate and requires both the
  global formal lock and `--open-internal-test`; checkpoint input hashes must
  exactly match split, text cache, visual weights, and cache manifest.
- The code path is runnable, but first formal training still depends on
  activated data sources, unified study manifests, a protected exclusion
  registry, labeling, a newly frozen split, local optional vision packages,
  and a local BiomedCLIP model root. GPU availability alone does not satisfy
  these prerequisites.

## Real asset inventory - 2026-08-02

- `H:` is mounted and the known local MIMIC-CXR and BiomedCLIP roots resolve.
  The public-dataset surface exposes junctions for `mimic-cxr`,
  `mimic-cxr_less`, and `mimic_cxr_other` into the canonical
  `H:\xiyao\dataset\MIMIC-CXR` root.
- The public dataset inventory also contains CheXpert-v1.0-small,
  CheXlocalize, Chest ImaGenome archive, MS-CXR, NIH Chest X-rays, and VinDr;
  presence alone does not establish longitudinal-report eligibility.
- The old R37 runtime remains available and includes structural cohort/cache
  artifacts plus later protected/revealed result folders. Only structural
  identifier projections and source receipts may be consulted in this phase;
  prediction, metric, gold, sealed-reveal, and outcome files remain closed.
- The canonical MIMIC root contains the official v2.0 metadata and split gzip
  tables plus the main image/report tree. The separately present v2.1 labeled
  test file is explicitly outside the allowed inventory surface and was not
  opened.
- `source_manifests` currently contains only a checksum list, so a new unified
  study manifest still needs to be built from the official metadata/split and
  report/image tree.
- `CheXpert-v1.0-small` contains train/valid images and classification CSVs but
  no report corpus at its top-level contract; it is not yet eligible as an
  independent longitudinal PRTA source. `CheXlocalize/redivis_v1_0` requires
  a deeper structural inventory before classification.
- The MIMIC image/report roots are confirmed at
  `mimic-cxr/mimic-cxr/mimic-cxr-images` and
  `mimic-cxr/mimic-cxr/mimic-cxr-reports`.
- CheXlocalize contains a validation localization bundle (annotation JSON and
  Grad-CAM/segmentation assets), not a longitudinal report source. It may be an
  auxiliary localization audit source later, but must not enlarge PRTA train.
- The legacy R37 structural builder confirms the correct MIMIC joins and path
  formulas and produced 108,732 eligible adjacent pairs only after excluding
  all R32 train/dev/sealed and gold patients. That old exclusion policy is too
  conservative for the user's new instruction: old debug/train roster
  membership alone is not an exclusion, while old dev/sealed/gold boundaries
  remain protected.
- The existing `r37_forbidden_patient_registry.json` is a valuable
  outcome-free structural source because it already separates R32 train, dev,
  sealed-test, and gold patient IDs. The new registry can reuse only the
  dev/sealed/gold categories and deliberately reactivate the old train IDs.
- The legacy R37 pair manifests are evidence and migration references, not the
  new source of truth: they contain a fixed 90/10 old partition and exclude
  1,574 old-train patients that the new full repartition should reconsider.
- A local `CheXpert-Plus` root exists at
  `H:\Xiyao_Wang\02101\data\dataset\CheXpert-Plus`; this is the only
  CheXpert-family candidate found so far that may carry report text and stable
  study/patient identifiers. It must be inventoried directly rather than
  inferred from the classification-only CheXpert-v1.0-small copy.
- The CheXpert Plus root contains one 114,520,998-byte parquet with 223,462
  rows. Its schema includes deidentified patient IDs, patient report order,
  report/section text, frontal/lateral and AP/PA fields, image/DICOM paths, and
  a split field, so it satisfies the structural shape for a longitudinal
  report source if the referenced images are present and processing rights are
  confirmed.
- Structural-only CheXpert Plus statistics: 64,725 patients; 223,228 train and
  234 valid rows; 191,071 frontal rows (161,622 AP and 29,432 PA); zero missing
  patient report-order values and zero duplicate image-path strings.
- The parquet image paths resolve against the local
  `CheXpert-v1.0-small` image root; three sampled train images exist. The image
  root exposes 64,540 train and 200 valid patient directories, consistent with
  the parquet patient-scale order of magnitude. A full existence audit is
  still required before activation.
- CheXpert Plus `patient_report_date_order` is an integer within-patient ordinal
  (range 1-92), not a recoverable calendar date. Its source adapter must mark
  the temporal basis as ordinal and must not claim real interval-day analyses.
- MIMIC official metadata and split tables join one-to-one at 377,110 rows:
  368,960 train, 2,991 validate, and 5,159 test images. Official train contains
  237,972 frontal images, 213,365 frontal studies, and 63,169 patients before
  the new protected registry is applied.
- The outcome-free legacy registry separates 1,574 R32 train, 300 R32 dev, 483
  sealed-test, and 693 gold-quarantine patients and records zero outcome-field
  access. The new policy will reactivate only the old-train category and retain
  dev/sealed/gold exclusions.
- Separate R29, R30, and R31 fresh-silver cohort directories exist under
  `F:\VisualVIT_runtime\050_routeC`, each with a large `cohort.json` plus a
  small structural audit/manifest. Their development and test patient IDs must
  also be projected into the new historical-reveal exclusion registry; the
  large cohort files must not be opened until the structural audit schemas are
  checked for an identifier-only projection route.
- The small R29/R30/R31 audits mix structural counts with aggregate label
  counts. Those aggregate counts were exposed once during inventory but are
  not used for source activation, exclusions, splitting, or model decisions;
  no row-level cohort, prediction, or patient-outcome mapping was opened. All
  subsequent exclusion work must use an ID/partition-only projection path.
- Structurally, the historical active partitions comprise R29 700/200/300,
  R30 1,500/400/600, and R31 1,200/300/500 train/dev/test patients. At minimum,
  every dev/test patient from these revealed waves must be excluded from the
  new train/dev/internal-test pool; old train membership alone remains
  eligible under the user's new policy.
- The R29/R30/R31 cohort builders establish a stable structural projection
  contract: every row has `patient_id` and `partition`, with partitions
  `train`, `dev`, `test`, or `sealed_reserve`. The new projector can consume
  only those two fields, hash the patient into the MIMIC namespace, and discard
  every other field without evaluating it.
- The earlier R24 MIMIC, R25, and R26 cohort/pair manifests used as R29
  exclusions are all still present at their frozen paths. Their union was 223
  patients in the existing structural audit. These are historical evaluated
  cohorts and should join the new `revealed_historical_test` exclusion category
  through the same ID-only projection rule.
- The first combined real source build exceeded the outer 30-minute wait.
  Atomic semantics worked: no formal `sources_v1` exists, and staging exposed
  a partial MIMIC temp JSONL with 176,745 readable lines at the first check.
  A follow-up process audit showed Python PID 29840 was still alive and writing;
  no duplicate task was launched. The builder still needs a per-source/resume
  boundary for future runs.
- PID 29840 was stopped only after live I/O confirmed poor throughput. Its
  preserved partial file contains 206,724 complete JSON rows with 206,724
  unique image IDs and no malformed tail. Compared with 213,365 selected MIMIC
  frontal studies, only a small tail remains for a resume-aware builder.
- The third atomic source-manifest attempt completed successfully at
  `H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\sources_v1`. Independent
  full JSONL parsing confirmed MIMIC 213,365 rows / 63,169 patients and
  CheXpert Plus 187,474 rows / 64,510 patients, with unique image lineage and
  patient-study keys, zero empty reports, and the expected calendar versus
  within-patient-ordinal time bases.
- The exclusion registry contains 3,750 unique hashed MIMIC-namespace
  patients. Before normalization it intersects 38,243 MIMIC study rows and no
  CheXpert Plus rows, as expected from the historical MIMIC routes. The source
  preparation receipt and an independent audit both confirm no training,
  Luna, internal-test opening, or protected-outcome opening occurred.
- The pair layer previously dropped source `time_basis`, which could have made
  CheXpert Plus ordinal gaps look like elapsed calendar days. It now preserves
  interval basis and an explicit `calendar_interval_available` flag; ordinal
  gaps remain usable for order/adjacency only and must never support real-day
  interval claims.
- The first full pair attempt failed before artifact writing because MIMIC has
  exactly four extra rows sharing a patient and timestamp with another study;
  CheXpert Plus has none. Timeline normalization now resolves this structural
  ambiguity deterministically (PA first, then stable study/image IDs) and
  records `duplicate_patient_time`, while still rejecting every zero-interval
  pair.
- 2026-08-02 reviewer reset: the first doctor's responses are no longer
  evidence. The user explicitly invalidated that review, the filled workbook
  was restored to the original empty template, and all derived first-review
  runtime directories were deleted.
- The replacement senior doctor will see Luna's five-class label. This is a
  practical confirmation/correction workflow but introduces anchoring, so its
  outcome must be described as `Luna-assisted senior review`, not independent
  blind accuracy or inter-reader agreement.
- The frozen 250-row roster and patient quarantine remain unchanged. The senior
  doctor supplies the final human label; `Unclear`/`Unusable` remain excluded
  and no training authority is created by completing the workbook.
- 2026-08-03 final senior-panel result: all 250 rows were decisive and became
  Gold. Luna was confirmed on 246/250 (98.4%); the two-physician consensus
  corrected four rows: Stable-to-Resolved pleural effusion, Improved-to-Stable
  atelectasis, Worse-to-Stable atelectasis, and Improved-to-Stable pleural
  effusion. Each source had 123/125 confirmation (98.4%).
- This is Luna-assisted panel consensus from two physicians with more than five
  years of clinical experience each, recorded in one shared column. It is not
  independent double annotation or inter-rater agreement. The human consensus
  label is the Gold label for all 250 rows, while the full patient quarantine
  remains intact with zero overlap into the 124,430-row training candidate set.
- The paper authorities prescribe a strict lifecycle even under full execution
  authority: patient split and data freeze; Train/Dev-only performance
  development; method/protocol freeze; formal baseline and ablation training;
  then one-time frozen Internal-test/Gold inference; trust/calibration/subgroup
  analysis; figures; and only then the VLM appendix.
- Required formal matrices include B401-B404 and A500-A506 over seeds 17, 29,
  and 43. B405 and A507 are conditional/optional rather than automatically
  mandatory. The development exit gate explicitly forbids proceeding as if
  successful when enlarged-data Dev macro-F1 remains below 0.48.
- The bounded development search is exactly H0/H1/H2, three imbalance losses,
  and at most two adapter scopes. Screening is Seed 17, one axis per round;
  final confirmation is seeds 17/29/43, and architecture changes stop after two
  consecutive improvements below 0.5 percentage points.
- The desired performance-development GO is Dev macro-F1 at least 0.52, at
  least +3 percentage points over the strongest simple temporal baseline,
  min-class recall at least 0.20, non-worse ODER, a positive True-versus-wrong
  PRIOR gap, and no single-seed collapse. Values 0.48-0.52 trigger HOLD and
  diagnosis; below 0.48 with saturated scaling is STOP/redesign.
- Every run must record experiment/config/split/label hashes, seed, GPU, times,
  checkpoint/prediction/metrics/log paths, and failed runs must be preserved.
  Patient-clustered paired bootstrap uses 10,000 replicates; temperature,
  threshold, and checkpoint are Dev-only choices.
- Phase-30 live audit: both local RTX 3090 GPUs are idle with 24,576 MiB each;
  no PRTA cache/train/evaluate process is active. H: has about 546.6 GB free,
  E: about 262.5 GB free, and the existing formal runtime is on H:.
- The generic split/cache/train/evaluate CLIs exist, but every formal experiment
  config directory (`performance_development`, `formal_baselines`, `ablations`,
  `trust_audits`, `visualizations`, `vlm_additional`) contains only `.gitkeep`.
  Therefore the paper matrix is not yet runnable end-to-end: a formal registry,
  variant configs/orchestrator, native baselines/ablations, freeze receipt, and
  downstream audit/figure/VLM implementations must be added before claiming
  readiness beyond split/cache/basic PRTA training.
- The split implementation is deterministic, exact-capacity patient assignment
  with source/finding/label stratification cost, canonical manifest/assignment
  hashes, atomic output writes, and a built-in all-pairs patient-overlap audit.
  It is suitable for the Phase-31 formal freeze once the authoritative runtime
  training-eligible manifest path is pinned.
- The current generic model/config surface supports H0/H1 but not the authority
  document's H2 screening head; the one training config is fixed to seed 17,
  H0, Weighted-CE-like default loss, 20 epochs, and one adapter scope. It cannot
  represent the required development/formal matrix without code/config work.
- Formal split `full_repartition_v1` completed from commit `0eb29b6` over the
  exact 124,430-row training-eligible manifest. Patient capacities are exactly
  26,045 Train, 3,256 Dev, and 3,256 Internal-test (80/10/10 by patient), with
  91,065 / 16,666 / 16,699 rows respectively.
- Independent re-read proved full sample-ID conservation, 124,430 unique IDs,
  zero duplicates, zero Train/Dev/Internal-test patient overlap, and zero
  overlap between every split and all 250 Gold patients. Every split contains
  both sources and all five labels. Canonical split hash is
  `9eb2fadf8d5c568b701f6cfebd75fc06d3bd2bf3fb20f889f20f5f47cf93283b`;
  output file SHA-256 is `3901895d927ee8de614545086ddb70e817a38d6c1c80c47a4dc51b2bf8583ea7`.
- The exact local BiomedCLIP root is
  `H:\.cache\modelscope\hub\models\microsoft\BiomedCLIP-PubMedBERT_256-vit_base_patch16_224`.
  Config SHA-256 is `9a41f334a8c444678772c0ebb9ab854c97ab350bced3a17b803e258d39c23dc0`;
  visual weights SHA-256 is
  `52cc993c5c5ff962bd0c60931874bc001e7e9b41666a385530f4a036294576be`.
- The current formal cacher is not full-scale safe: it materializes every
  unique image's `[197,768]` float32 feature tensor in GPU/host memory before
  writing any shard. At only 100k images this is about 60.5 GB float32, and a
  crash loses all work. Phase 32 therefore requires streaming, atomic shards,
  resumable completion, and an independent manifest audit before launch.
- The frozen split references 146,110 unique images across 124,430 rows and 12
  findings. All image paths exist. A full FP16 Block-8 cache is estimated at
  41.175 GiB across 571 shards of 256 images, safely below current H: capacity.
- Training/evaluation audit found additional formal blockers: only PRTA H0/H1
  exists; H2, Current-only, Siamese Diff, and TILA are absent; imbalance-loss
  selection and component switches are absent; Dev metrics omit balanced
  accuracy/min recall/ODER/NLL/Brier; scripts 09-11 are dry-run gates only.
- The formal evaluator currently compares checkpoint input hashes including the
  training-only label-quality audit against an evaluation hash map that omits
  that field, so every real checkpoint would fail equality. It also supports
  Internal-test only, not Gold, interventions, temperature scaling, bootstrap,
  subgroup analysis, or immutable one-time-open receipts. These must be fixed
  before protocol freeze, not worked around after test access.
- The authority documents still contain legacy D0/D1/D3 Rule-label experiments,
  while the later user-frozen policy says Rule labels are diagnostic-only and
  never training labels. Formal implementation must resolve this in favor of
  Luna-primary scaling and mark Rule-only D3/A507 N/A unless the user explicitly
  reverses the later policy; automation remains structural only.
- Reusable patient-balanced confusion metrics and hierarchical patient
  bootstrap code already exist, but the trainer reimplements a weaker metric
  subset instead of calling them. The dataset also drops source/finding/view/
  interval metadata from each batch, preventing registered subgroup outputs.
- A strict run-receipt field contract exists but is not wired into training,
  evaluation, interventions, or figures. Formal orchestration should reuse that
  contract rather than inventing a parallel registry schema.
- The single labeled split manifest is not an acceptable development input:
  both cache and training CLIs parse the entire file before filtering, exposing
  Internal-test labels in process memory. The cache does not use those labels
  and no model/prediction exists, but strict protocol requires separate labeled
  Train/Dev, sealed labeled Internal-test, and outcome-free cache manifests.
- Formal sealing now provides 107,731 labeled Train/Dev rows, 16,699 labeled
  Internal-test rows in the sealed directory, and 124,430 outcome-free cache
  rows containing only sample/source/finding/image paths/split. Independent
  audit found no patient or label fields, exact ID conservation, and the same
  146,110-image inventory hash as the 52 completed cache shards.
- Canonical hashes are Train/Dev
  `925ec2cbbba7b2093a410cc24da39f0941e927f4c083d039702fba0c7473d538`,
  sealed Internal-test
  `762def7cc4340d2bb6492b903ff9e89381ef48d90cd384f442d7e70738474bf6`,
  and outcome-free cache input
  `31b1c3095faf53c37ef60db519a02b6d13ad6df8e428095c34d087b067412d08`.
- The senior-panel comparison can satisfy the registered 200-300-row Silver
  quality gate only under its real interpretation: Luna-visible assisted
  confirmation/correction, not blind medical accuracy. It contains exactly 25
  rows per source-by-label stratum; overall/source confirmation is 0.984 and
  the weakest label stratum is Improved at 0.96, so the configured 0.95 gate
  passes without claiming independent ground truth.
- The frozen Train population supports nested Luna-primary scaling cleanly:
  2,604/6,511/13,022/19,534/26,045 patients yield
  9,282/23,043/45,885/68,676/91,065 rows at 10/25/50/75/100%, respectively.
  Each point preserves both sources and every progression class, including
  245 Resolved rows at the smallest fraction, while the full 16,666-row Dev
  set is unchanged and patient-disjoint.
- Formal training needs mutable state but immutable scientific artifacts. The
  implementation therefore uses replace-in-place atomic files only for
  `training_progress.json` and the unified registry; configs, checkpoints,
  final receipts, predictions, and metrics retain refuse-overwrite behavior.
- Random training directly from 571 torch shards would repeatedly deserialize
  entire ~72 MiB tensors for two-image lookups. A single 41.175 GiB contiguous
  FP16 store enables page-level random reads via `numpy.memmap`; it is derived
  only after every source shard hash/shape/finite-value check passes, and its
  own byte count and SHA-256 are recorded in the cache manifest.
- Because two GPUs may finish/start runs concurrently, the unified registry
  needs a cross-process lock around read-modify-replace. The Windows lock-file
  implementation prevents one run closeout from erasing the other run's row.
- The head-selection rule cannot be implemented from ordinary Dev Macro-F1
  alone because the authority also requires that matched-wrong PRIOR behavior
  not worsen. The new derangement is outcome-independent and frozen before
  training: same source/finding/view/interval bin when possible, progressively
  relaxed only for support, always a different patient, with deterministic
  sample-hash selection.
- Batch size 16 has ample memory headroom on a 24 GiB RTX 3090 for the current
  PRTA implementation: a full synthetic forward/backward through four frozen
  tail blocks plus trainable adapters peaked below 4 GiB reserved. Formal OOM
  risk is therefore more likely to come from loader/process behavior than the
  core model tensor graph.
- The pending human-review roster uses `clinician_label=None`, not an empty
  string; guards must distinguish this sentinel from an actual value. Its 250
  sample IDs join exactly to the pre-existing Luna Silver image lineage, so a
  label-free Gold-candidate cache can be prepared without reading senior-panel
  outcomes or changing the main training/test cache identity.
- Deterministic retraining of the same PRTA config/seed after Dev selection
  would reproduce the same checkpoint while doubling compute. The formal
  matrix therefore records B404/A500 aliases to the three already-confirmed
  PRTA runs, while every distinct baseline and one-component ablation receives
  its own run. This preserves equal frozen budgets without duplicate science.
- Protocol freezing can safely bind protected cohorts by file SHA-256 without
  parsing their JSONL contents. The actual one-time outcome session remains a
  separate later transition after formal training, while temperature values
  are fitted from Dev under the already-frozen algorithm.
- The run registry cannot itself be content-frozen before formal training
  because B/A rows are added as those runs finish. The protocol instead freezes
  every config hash and the registry path; the outcome-session marker then
  binds the completed registry SHA-256 immediately before opening outcomes.
- Formal significance reporting is now fully paired at the patient level.
  B401-B404 and all seven PRTA input conditions must have identical patient,
  observation, target, and patient-weight layouts for every seed or the audit
  fails closed. The frozen protocol supplies 10,000 hierarchical replicates;
  empirical two-sided contrast p-values are corrected together with
  Benjamini-Hochberg.
- The paper figure surface can be outcome-independent in implementation while
  remaining outcome-locked in execution. V701-V708 now require the completed
  formal outcome receipt and matching trust receipt, emit PNG/SVG plus hashes,
  and use the frozen five-bucket hash selection for both successes and failures.
- The bounded additional VLM path can reuse the final PRTA representation
  without a second model-selection loop: exact 64 physical positions use the
  registered 4/12/16/16/12/4 layout, only one projector is trained on 2,500
  deterministic Train Silver rows, Qwen remains fully frozen, and the only
  evaluation cohort is the 250-row senior Gold after the common outcome open.
  Model paths stay portable because protocol freeze hashes the local model
  config/index, referenced weight shards, and tokenizer assets.
- Final paper tables should distinguish reproducible N/A values from missing
  work. The generator recomputes final split/source counts and every outcome
  metric from frozen artifacts, but leaves early candidate/pair fields as
  `N/A—not frozen` because those aggregate receipts are not part of the formal
  runtime. It never fills such cells from chat history or legacy debug counts.
- Queue execution mutates scheduler state in place, so a scientifically frozen
  queue identity must exclude PID/device/log/timestamps and normalize the
  mutable status back to `PLANNED`. The protocol now hashes this immutable plan
  projection while retaining runtime state for operations and auditing.
- One controller can safely automate the long program only if it preserves the
  gates. The keeper waits for the existing initial runner, executes each Dev
  selection queue in order, stops before outcomes on non-GO, requires a clean
  worktree for protocol freeze, and resumes the one-time outcome session only
  under an immutable pre-open identity.
- Windows cannot use `os.kill(pid, 0)` as the queue's authoritative liveness
  test: for a terminated child it can surface `SystemError`/WinError 87 or keep
  a stale process identity from being reconciled. The runner now queries the
  native process exit code through `OpenProcess`/`GetExitCodeProcess` and treats
  only `STILL_ACTIVE` as alive, with a regression test that keeps the child
  handle open after termination. This preserves queue identities while safely
  releasing a GPU for the next planned run.
- Windows can also transiently deny `os.replace` on a mutable JSON state file
  even when the writer owns the temporary file. The initial queue keeper hit
  WinError 5 while replacing `scheduler_state.json`; the queue and both active
  training children remained intact. Mutable-state replacement now retries a
  bounded 3.15-second exponential schedule while preserving the same atomic
  replace operation and still raises after exhaustion. A regression test
  forces two sharing violations before success.
- In the frozen loss comparison, M302-CBF reached Dev Macro-F1 0.453588 versus
  D205's 0.442987 and preserved the prior-control audit gap (0.112643 versus
  0.105443). It was therefore the sole qualified loss variant under the
  predeclared selector and became the immutable parent for adapter experiment
  `M303-last2`; Internal-test and Gold remained sealed throughout selection.
- The last-two-block adapter reached Dev Macro-F1 0.453134, slightly below its
  immutable M302-CBF parent at 0.453588, and therefore did not qualify under
  the frozen positive-gain selector. The method remained M302-CBF and moved to
  independent confirmation seeds 29 and 43 without opening protected outcomes.
- The two independent M302-CBF confirmation seeds finished cleanly with best
  Dev Macro-F1 0.463033 (seed 29) and 0.459419 (seed 43), both at epoch 4,
  while Internal-test and Gold remained sealed. These runs provide stable
  Train/Dev confirmation but do not by themselves settle the preregistered
  development decision; the frozen B401-B403 seed-17 Dev-baseline gate must
  complete before the keeper can issue the Phase-33 GO/HOLD/STOP receipt.
- The complete frozen development gate issued `STOP`, not GO or HOLD. PRTA's
  three-seed Dev Macro-F1 was 0.453588/0.463033/0.459419 (mean 0.458680), so
  the mean >=0.52 and every-seed >=0.48 checks failed. The strongest temporal
  baseline was M305-B403-S17 at 0.447629; seed-17 PRTA gained only 0.005959,
  below the preregistered +0.03, and mean PRTA ODER 0.042202 exceeded the
  baseline's 0.037021. Mean minimum-class recall (0.318904), seed range, and
  all three positive prior gaps passed, but those bounded positives cannot
  override the failed gate. The keeper correctly stopped before protocol
  freeze, formal matrices, Internal-test, Gold, figures, or the VLM appendix.
- The user separately authorized a post-STOP, read-only approximate-TracIn
  audit over all 91,065 open Train rows and 16,666 open Dev rows. The protected
  Internal-test and Gold surfaces are entirely out of scope: no parsing,
  inference, structural inspection, or outcome access. Existing evidence is
  limited to best/last checkpoint pairs for M302-CBF, M304-S29, and M304-S43,
  so each seed must be scored as its own sparse two-checkpoint trajectory and
  the final artifact must not be called full-trajectory TracIn or causal proof.
- Captum 0.8's `TracInCPFast` primitive is usable for the exact last linear
  layer when streamed checkpoint-first: each best/last checkpoint is loaded
  once, 300 probe Jacobian/input embeddings are cached, and Train-by-probe
  blocks are reduced into separate positive, negative, signed, and
  self-influence columns. This avoids the public API's repeated 296 MiB
  checkpoint reload for every Train batch while preserving the same dot
  product, verified against a direct synthetic gradient calculation.
- The frozen ViT's CUDA efficient-attention kernel does not implement
  forward-mode AD, so an all-Train head-plus-four-adapter JVP is unavailable
  in torch 2.5. The confirmation therefore uses a bounded symmetric central
  finite difference along the summed probe-gradient direction. It requires
  two inference passes per checkpoint, restores every in-memory parameter
  exactly afterward, and matched the direct selected-parameter gradient dot
  product on a synthetic fixture. Captum remains the primary exact
  last-layer result; the adapter lane is explicitly a stability confirmation.
- The full read-only approximate-TracIn audit completed with exact coverage of
  91,065 Train and 16,666 Dev rows. It listed all 17,200 non-Context candidates
  without truncation: Tier A 3,866, Tier B 2,921, and Tier C 10,413; 9,847 are
  Train and 7,353 are Dev.
- Median last-layer versus head-plus-four-adapter Top-5 overlap was 0.639458,
  0.712349, and 0.751785 for seeds 17, 29, and 43. All exceed the preregistered
  0.60 global instability threshold, but the results remain high-risk
  candidates rather than proven mislabeled or harmful data.
- Independent final validation found no duplicate, missing, wrong-split, NaN,
  or Inf row; the candidate CSV, 17,200-line case JSONL, and 17,200-record
  Markdown agree exactly. All private-output hashes match the receipt, input
  hashes are unchanged, and Internal-test/Gold read counts remain zero.
# 2026-08-04 Tier-A GPT-5.6 Sol 全量盲审启动发现

- 近似 TracIn 私有审计共识别 `3,866` 条 Tier A，且全部来自 Train；本轮不触碰 Dev、Internal-test 或 Gold。
- Tier A 分层数量为：CheXpert Plus 2,243（Improved 278 / Worse 443 / New 378 / Resolved 34 / Stable 1,110），MIMIC-CXR-JPG 1,623（Improved 278 / Worse 338 / New 309 / Resolved 61 / Stable 637）。
- 旧 `configs/labeling/sol_blind_review_v1.json` 是 150 条 pilot 的封闭配置，且 `full_execution_enabled=false`；它不能被静默扩展为本轮 3,866 条正式盲审权限，必须建立新的专用配置与回执。
- 本机 `codex exec` 支持显式 `--model` 和 `-c key=value` 覆盖；本轮将固定请求 `gpt-5.6-sol` 与 `model_reasoning_effort=medium`，任何不可用情况都 fail-closed，不回退模型或推理强度。
- 私有来源 `case_details.jsonl` 含 Luna 标签和完整内部字段；对 Sol 的批次载荷必须重新投影，仅保留批内匿名 alias、finding、PRIOR 报告、CURRENT 报告。Luna 标签只在所有 Sol 输出落盘后用于本地比较。
- 全量 Sol 盲审完成 `3,866/3,866`，194/194 批均固定为 `gpt-5.6-sol`、`medium`；失败尝试 0，输出 ID、枚举、schema 与输入批次全部守恒。
- Sol–Luna 全体精确一致 `3,002/3,866 = 77.65%`；Sol 输出 `Unclear` 294 条（7.60%）。排除 `Unclear` 后五类一致为 `3,002/3,572 = 84.04%`，Cohen's κ=`0.7720`；明确分歧 570 条，其中方向相反 39 条。
- 来源间五类一致率几乎相同：CheXpert Plus `83.99%`（κ=`0.7615`），MIMIC-CXR-JPG `84.11%`（κ=`0.7831`），不支持“问题仅来自某一数据源”的解释。
- 按 Luna 标签，五类一致率为 Stable `90.16%`、Improved `87.22%`、Worse `80.32%`、New `71.02%`、Resolved `67.78%`。这说明 Tier A 中时间边界类（尤其 New/Resolved）和 Worse 值得优先人工审查。
- 旧 150 条 pilot 的 decisive 五类一致率为 `92.74%`、κ=`0.9084`，本轮 Tier A 分别低约 8.70 个百分点和 0.1364；但两批样本选择机制不同，因此只能说明 Tier A 富集了不一致/困难样本，不能单凭 Sol 认定 Luna 错标。

# 2026-08-04 Sol-authoritative Train 标签版本

- 用户已把人工决策从“只读审计”提升为“以 Sol 为准替换 Tier A Luna 标签”。五分类 Sol 输出有 3,572 条；`Unclear` 有 294 条，按先前已冻结的不确定样本废弃策略从新训练版本排除。
- 当前运行根包含 `formal_program_v1`、`poststop_audits` 等版本化目录；旧 TracIn/Luna/Sol 产物无需也不应原地修改。
- 初次用 `rg --files` 搜索 Train manifest 没有命中并返回退出码 1，未读取任何数据文件。后续目录只读枚举确认正式 split/cache 位于 `formal_program_v1`，需要从安全回执或 Train-only 路径进一步解析权威输入，避免打开 protected outcome 文件。
- 正式 split 表面只有组合开放文件 `formal_program_v1/splits/train_dev_v1.jsonl`，未发现独立的 91,065-row Train JSONL。TracIn 的 `train_all_scores.csv` 确实覆盖 91,065 条 Train，但只含审计/标签/ID字段，不含训练清单所需的完整图像、报告和时间字段，不能直接替代训练 manifest。
- 因此安全实现应对开放的 `train_dev_v1.jsonl` 做单次流式过滤：仅把 `split=train` 行物化到新版本，Dev 行不改、不输出、不参与标签 join；Internal-test 和 Gold 文件仍完全不打开。源组合文件及输出都必须哈希绑定。
- Sol-authoritative 正式物化 PASS：源 Train 91,065 行中 3,572 行采用 Sol 五分类权威，实际标签值变化 570 行，Sol/Luna 同值但 provenance 改为 Sol 的有 3,002 行，294 条 Sol `Unclear` 被排除；新 Train 为 90,771 行。
- 可直接供后续训练的组合 manifest 为 107,437 行（Train 90,771 + Dev 16,666）。Dev 行没有 JSON 解析或重写，而是原始字节复制；独立原始行流哈希为 `28c9f7dea729ebb24ba34cc20ddd5078ba735f2ebdc2fc6a164225404f25373d`，记录的 Dev 修改数为 0。
- 新 Train SHA-256=`7306898c6b31af50956fa4ee32c5b6b8ba468751e6fc4e26f6a9353355fff219`；新 Train+Dev SHA-256=`d798feb5adc65955add617371a38e337d9ffe721a18756e958851a50d51c897b`。旧输入前后哈希一致，Internal-test/Gold 未打开，训练未启动。
- 私有新 Train 文件为 246,876,831 bytes，组合 Train+Dev 为 292,407,707 bytes；provenance 为 1,298,615 bytes，Unclear exclusion 表为 78,913 bytes。独立审计 SHA-256=`f898233c0370e9746bdc80d64f480f3c2394fe319baef6d2049b41335a1a27c5`。

# 2026-08-04 Dev/Internal-test/Gold Sol 只读标签质量复核

- 用户已显式授权完整打开 Dev、Internal-test 和 Gold 标签用于独立 Sol 标签质量复核。这是此前 seal 后的新受控访问，必须在后续科学记录中披露；它不授权模型推理、训练、调参、改标或重新计算模型指标。
- Dev 权威来源仍是 293,168,028-byte `train_dev_v1.jsonl`（SHA-256 `b798d8412dc8c1e02840d56f2221d11fca940a36ccf716ff2efb659cce36ca77`），正式构建时只选择 16,666 个 `split=dev` 行。
- Gold 最终医生共识文件为 738,507 bytes，SHA-256 `e027916db1fb0a31f66cd5b72a60893ee538ff465ac97b9cdcf1246fe519f91d`；原始 250-row review roster 为 506,594 bytes，SHA-256 `0469e6c954c1fe0c7b81e4c371bf69fe0f7731894328a1a4cec9feba9b487e96`。Gold 医生标签必须在 Sol payload 中剥离。
- 初次假设的 Internal-test 文件名 `internal_test_v1.jsonl` 不存在（仅路径检查，无内容解析）；受控目录枚举确认实际文件名为 `internal_test_labeled_v1.jsonl`，45,514,722 bytes。后续使用实际文件并在解析前冻结 SHA-256。
- 实际 Internal-test 输入 `internal_test_labeled_v1.jsonl` SHA-256 为 `8d7ff0986793661827133351c089ca66caa728e33fb2b25fba771fe79d4684d9`。该哈希已在任何标签解析前记录。
- Gold 最终文件由原 Silver 样本完整字段加医生共识 `progression_label` 和 `label_tier=Gold` 构成，同时还含 `luna_label`、`human_label` 等解盲字段。因此 roster 构建必须只提取 sample_id 映射所需的 finding/PRIOR/CURRENT，并把所有医生/Luna/Gold 状态字段完全留在本地；比较阶段以 `progression_label` 作为当前 Gold 标签。
- 新复核脚本的首次 Ruff 失败仅涉及格式和一个未使用导入，不是数据或执行错误；在这些问题修复并通过测试前，不创建受保护 roster，也不发起任何 Sol 调用。
- 旧测试文件名 `test_sol_tier_a_review.py` 并不存在；仓库实际的独立盲审约定位于 `test_independent_silver.py` 和 `test_sol_review.py`，本轮测试应复用这些真实接口而不是假设旧文件名。
- Gold 记录使用 `label_tier=Gold`，而全局 `validate_sample` 只接受训练管线的 Tier-A/Tier-B/Reject/Silver。为避免扩大训练契约，本任务仅在局部验证时用兼容副本检查其余字段，并保留原始 Gold 值；盲审批次由独立只读构建器产生。
- 报告原文可能自然包含 `Stable` 等标签词，因此隐私/盲态测试不能禁止这些词出现在报告内容中；正确门禁是精确限制 payload 字段，并禁止现有标签键、医生字段、患者标识和真实 sample ID 外发。
- 正式私有 roster 构建 PASS：Dev 834 批、Internal-test 835 批、Gold 13 批，总计 1,682 批/33,615 条；候选 manifest 哈希分别为 Dev `9e409e3e90b19ce576c9c65e32697c13345ccafcecc4d4cbf2a52e2521b51c88`、Internal-test `c680b692d19c86aa59634f20806d79952e4ee73ebb808f1fcd1785a7a118d198`、Gold `3d8d87ca7bca3190eb9fdb6cf7dbf789b3fa05a43266f115fab8d5f49f90822e`。
- Codex/OpenAI 响应格式的受支持 JSON Schema 子集不接受数组上的 `uniqueItems`。这不会降低本任务契约，因为 `validate_quality_output` 已独立检查并拒绝重复 flag；因此 v2 只移除服务端不兼容关键字，保留本地唯一性门禁和全部枚举约束。
- v2 canary 延迟分别为 Dev 52.197 秒、Internal-test 40.958 秒、Gold 48.593 秒；三者均无重试或降级，说明以约 30 个并发、每片约 60 批执行时，预计全量需要约 35–55 分钟，具体取决于服务端并发吞吐。
- 全量受保护标签复核完成 33,615/33,615，所有正式分片模型/推理强度一致且失败尝试为 0。决定性一致率为 Dev 89.96%、Internal-test 89.45%、Gold 医生共识 87.06%；κ 分别为 0.8504、0.8434、0.8378。
- `New` 是三个队列中最弱的当前标签（决定性一致率约 74%–77%），主要与 Worse/Stable 混淆并伴随高 Unclear；优先人工复核应聚焦这一时间边界类别，而不是把所有高模型风险样本视为错标。
- 质量标志以配对异常 3,772 和时间方向含糊 3,388 最常见，其后是 finding 无法判断 2,371、报告不足 1,964、否定/不确定性冲突 1,215。标志可重叠，不能直接相加为病例数。
- Gold 的 Sol–医生明确一致率 87.06%，Sol–Luna 为 88.56%，而 Luna–医生全量一致 98.40%。这支持把 26 条 Sol–医生明确分歧和 49 条 Unclear 作为复核候选，但不支持自动用 Sol 覆盖医生 Gold。
- 项目既有 Luna-primary 规则明确规定五分类标签保留、`Unclear` 废弃；此前 Train Tier-A Sol 替换也采用 3,572 个五分类覆盖、294 个 `Unclear` 排除的同一语义。因此本次 Dev/Internal-test 替换应沿用该规则，不能把 `Unclear` 写入五分类 manifest。
- Gold `progression_label` 已由两位资深医生共识冻结，`luna_label` 只是辅助/历史字段。用户要求替换“Luna 数据”不应被解释为自动推翻医生 Gold；如未来要把 Sol 设为 Gold 权威，需要单独明确授权和新 Gold 协议。
- 既有 `apply_tier_a_sol_labels_main` 已证明适合复用的安全模式：输入先哈希、源 manifest 流式处理、五分类行改 `progression_label`/`label_source`、Unclear 独立排除、非标签字段逐字段不变、旧产物不修改、输出/回执再次哈希。
- 正式消费者（训练、queue、protocol freeze、tables、figures）都接收显式 manifest 路径，没有仓库内统一活动指针。标签替换必须新增一个权威 active-label receipt/config，并让未来命令指向新 split surface；原 `formal_program_v1` 作为旧实验历史保持不可变。
- Dev 与 Internal-test 的每一行都是 `luna_primary_report_label|Silver`，所以对这两组执行全量 Sol 决定性覆盖不存在误改人工标签的混合来源问题。预期新行数为 Dev 13,420、Internal-test 13,588，Unclear 排除分别为 3,246 和 3,111。
- 新组合 Train+Dev 应为 90,771 + 13,420 = 104,191 行；Sol 明确权威行共 27,008，其中相对 Luna 值变化 2,780（Dev 1,347 + Internal-test 1,433），同值权威重绑定 24,228。
- 冻结输入哈希：源 Train+Dev `b798d841...ca77`、源 Internal-test `8d7ff098...84d9`、Sol Train `7306898c...f219`、医生 Gold `e027916d...f91d`。物化前后必须完全一致。
- 正式物化和独立审计都确认实际动作数与计划一致：Dev 1,347 值变化 + 12,073 同值重绑定 + 3,246 排除；Internal-test 1,433 + 12,155 + 3,111。新活动表面为 Train+Dev 104,191 和 Internal-test 13,588。
- 新标签分布为 Dev Improved 1,954 / New 1,665 / Resolved 364 / Stable 6,816 / Worse 2,621；Internal-test 2,020 / 1,714 / 373 / 6,832 / 2,649。后续如重训，类别权重和样本计数必须从新表重新物化，不能沿用旧 16,666/16,699 计数。
- Dev TracIn 全量表头包含 `sample_id`、`risk_tier`、`selection_reasons`、三种子预测/置信度/NLL/错误等字段，足以在 Sol 完成后识别“非 Context 高风险且 Sol 与当前标签一致”的困难样本；该表不需要也不得在盲审前 join 到外发批次。

# 2026-08-04 Tier-B/C Sol 覆盖补审发现

- TracIn 冻结审计包含 Tier B 2,921、Tier C 10,413，共 13,334 条；全部非 Context 中 Train 为 9,847、Dev 为 7,353，而 Tier A 3,866 条全部属于 Train。此前 Tier A 已全量 Sol 盲审，Dev 也已在 16,666 条全量复核中覆盖，因此预计 Tier B/C 的未复核缺口只会来自 Train，但必须用 exact sample ID 集合验证，不能仅凭这些聚合数推断。
- 既有 `tier_a_sol_review.py` 已实现适合复用的安全接口：只从私有 `case_details.jsonl` 投影标准样本字段，外发时进一步缩减为 batch-local alias、finding、PRIOR/CURRENT 报告；固定 `gpt-5.6-sol`/`medium`，并对模型、schema、alias 和 exact-ID 守恒 fail-closed。
- `protected_quality_review.py` 提供质量标志版 Sol 输出（五分类/Unclear + 报告不足、配对异常、finding 不可判断、时间方向含糊、否定/不确定冲突），比旧 Tier-A 只有类别的输出更适合本轮 Tier-B/C 质量复核；可复用其批次运行器，但 roster 必须由新的 exact-ID 缺口审计生成。
- Exact-ID 三命名空间交集已经确定：Tier B/C 共 13,334 条，其中此前受保护队列全量复核覆盖 7,353 条、旧 150-row Sol pilot 命中 22 条（其中 9 条也已在受保护 Dev 中）、Tier-A 命名空间命中 0 条；去重后已有 Sol 结果 7,366 条，真正缺口为 5,968 条。
- Tier/split 结构为 Tier B Train 2,921、Tier C Train 3,060、Tier C Dev 7,353；不存在 Tier B Dev。已覆盖为 Tier B Train 9、Tier C Train 4、Tier C Dev 7,353，因此待补审精确为 Tier B Train 2,912 + Tier C Train 3,056 = 5,968，全部属于 Train。
- 旧 150-row pilot 不能简单忽略：它为 13 个不在全量 Dev 复核中的 Tier-B/C Train 样本提供了既有 Sol 结果，避免了重复调用。新的 roster 必须冻结这三个既有 review 集合的输入哈希及 union coverage 回执。
- 5,968 条缺口已全部由 `gpt-5.6-sol`/`medium` 盲审完成：299/299 批、5,968/5,968 行、30/30 分片回执，失败尝试0、stderr 0；唯一 reused output 是已通过的 batch-0 canary，因此没有重复外部调用。
- 补审总体 Sol 明确五类为4,604条，Unclear 1,364条（22.86%）；明确样本中与当前 Luna 标签一致3,513条、一致率76.30%、κ=0.67583，明确分歧1,091条。Unclear/分歧/质量标志去重并集2,548条。这些是自动复核信号，不是医学正确率。
- Tier B 明显比 Tier C 更不稳定：Tier B 2,912条中 Unclear 760，明确一致率64.87%、κ=0.503383、明确分歧756；Tier C 3,056条中 Unclear 604，明确一致率86.34%、κ=0.817666、明确分歧335。
- Tier B 的主要弱项仍是时间/边界类别：New 明确一致41.75%，Resolved 38.78%，Improved 60.82%，Worse 58.17%，Stable 82.84%。Tier C 各类明显更稳，明确一致率从 New 72.53% 到 Worse 92.38%。
- 质量标志可重叠：PAIRING_ABNORMAL 864、TEMPORAL_DIRECTION_AMBIGUOUS 749、FINDING_NOT_JUDGEABLE 447、REPORT_INSUFFICIENT 398、NEGATION_OR_UNCERTAINTY_CONFLICT 222。
# 2026-08-04 Sol-authoritative 全风险标签重跑发现

- 旧开发门的精确比较对象为 PRTA seeds 17/29/43，以及 seed-17 的
  Siamese-Diff (`B402`) 和 TILA (`B403`) 两条时序基线。原门槛仍是单 seed
  Macro-F1 ≥0.48、三 seed 均值 ≥0.52、seed-17 相对最强时序基线增益 ≥0.03，
  同时满足 min-recall、ODER、prior-gap 和 seed-range 条件。
- 既有 Block-8 训练存储只绑定图像特征和 encoder hash，不绑定 Luna/Sol 标签；
  text cache 只有 finding embeddings 与 finding×五分类 transition prototypes，
  没有 sample-keyed transition embeddings。因此新标签可以安全复用缓存，
  但必须逐行验证活动图像 key 与新的 finding×label prototype 均存在。
- 正式训练 CLI 会从传入的活动 Train 行重新物化 class counts；新准备器仍会把
  同一组新计数写入冻结 config，使登记配置与实际运行一致。五个运行保持原
  epochs、early stopping、batch size、优化器预算、架构及 loss 设定不变。
- 既有 250-row 人工审计是 Luna-visible senior-panel confirmation，而不是后续
  Sol 替换的独立医学准确率证明。它只满足既有训练入口的临床 QC 结构门；
  本次 Sol 权威化来自用户在人工查看后的明确授权，论文中必须分别披露。
- 真实预检确认新 Train 类别计数为 Improved 13,173 / New 15,486 /
  Resolved 2,279 / Stable 41,700 / Worse 16,768；Dev 为 1,954 / 1,665 /
  364 / 6,816 / 2,621。新的冻结配置已使用这些 Train counts，不再沿用旧
  Luna-era 91,065-row 计数。
- 新标签重跑的首批早期证据已经跨过单种子 0.48 下限：seed 17 暂存最佳
  0.496082，seed 29 暂存最佳 0.483786。但它们仍处于 epoch 2，且 seed 43、
  B402、B403 尚未运行；因此现在只能报告“早期改善”，不能宣称通过三种子
  均值、baseline gain 或完整 GO 门。
- 00:11 CST 时两个暂存最佳值在完成/接近 epoch 3 后尚未进一步改变；这不构成
  退化或停滞证据，因为冻结 early-stopping 的 minimum epochs 为 6，且 seed 17
  正在正常 Dev 评估。必须继续等待其余 epochs、第三 seed 和两条时序基线。
- 00:43 CST 时 seed 29 的 epoch-3 暂存最佳 Macro-F1 已由 0.483786 提高到
  0.486053，seed 17 仍为 0.496082；两条轨迹均已进入 epoch 4 且双卡持续
  计算，说明上一心跳的短时平台并非运行故障。该证据仍不足以判定三种子均值、
  baseline gain 或最终 GO/HOLD，必须等五个冻结运行全部完成。
- 01:12 CST 时 epoch-4 即时 Macro-F1 为 seed 17 的 0.492711 与 seed 29 的
  0.467551，均未超过各自暂存最佳；这只是正常的逐 epoch 波动，两条轨迹仍在
  epoch 5 健康计算，且冻结 minimum epochs=6 尚未达到，不能据此提前停止或
  调参。最终判断仍必须等待第三 seed、两条 baseline 与统一 gate。
- seed 17 已形成首个正式终态证据：6 epochs 后 early-stop PASS，最佳 Dev
  Macro-F1 0.496082，超过单种子 0.48 下限，真实先验相对 matched-wrong-prior
  的 Macro-F1 gap 为 +0.142636，且 protected outcomes 零读取。但这仍只是
  五运行中的第一条；三种子均值、seed-17 baseline gain 和完整 GO/HOLD 尚不能
  判定。与此同时 seed 29 的 epoch-5 最佳值已提高到 0.494122。
- seed 43 的首轮 Dev Macro-F1 为 0.466218，低于单种子 0.48 门槛，但它仅完成
  epoch 0 且仍在 epoch 1 训练；由于冻结 minimum epochs=6，这只是初始轨迹，
  不能提前据此判定 seed 43 失败或改变配置。seed 29 的最佳值仍为 0.494122。
- seed 43 在 epoch 1 将最佳 Macro-F1 小幅提高至 0.468736，当前仍低于 0.48，
  但正在 epoch 2 正常训练且尚未到达 minimum-epoch gate；继续保持冻结配置，
  不进行任何调参或提前判定。seed 29 的最佳值继续稳定在 0.494122。
- seed 29 已正式以最佳 Macro-F1 0.494122 PASS；seed 43 也已在 epoch 3 把
  暂存最佳提高到 0.488005，故当前三个 PRTA seed 均各自高于 0.48 单种子下限，
  但三种子均值仍须等待 seed 43 正式终态后计算。
- B402 baseline 已正式以 0.499292 PASS，而同 seed-17 PRTA 为 0.496082；当前
  PRTA 相对已完成 baseline 的增益为 -0.003210。由于最终“最强 baseline”分数
  不可能低于 B402，冻结的 `seed17_gain >= 0.03` 条件已经不可逆地无法满足。
  这预示最终 development gate 至少有一项失败，但不改变继续完成 B403、统一
  收口与审计的授权顺序，也不触发调参或封存结果读取。
- B403 在 epoch 2 将暂存最佳 Macro-F1 提高至 0.491505；它尚未达到冻结的
  minimum epochs，不能视为最终 baseline 结果。无论其后是否超过 B402，已确认
  的 baseline-gain 失败结论不变，因为当前最强 baseline 已至少为 0.499292。
- seed 43 已正式以最佳 Macro-F1 0.488005 PASS；三个 PRTA seed 的冻结均值为
  0.492736，低于 `three_seed_mean >= 0.52`，因此第二项核心开发门槛也已确定失败。
  seed range 仅 0.008077，说明跨种子稳定性较好，但稳定地低于均值目标不能替代
  性能门槛。最终统一 gate 仍需等待 B403 回执后由收口程序正式生成。
- 五运行最终分数为 PRTA seeds 17/29/43 = 0.496082 / 0.494122 / 0.488005，
  B402/B403 = 0.499292 / 0.491505。统一 gate 的正式结论为
  `HOLD_DEVELOPMENT_GATE`：新标签把历史三种子均值提高 +0.034056，但 0.492736
  仍低于 0.52；seed-17 PRTA 反而比最强 B402 低 0.003210，未达到 +0.03
  方法增益。其余稳定性、minority recall、ODER 与 prior-gap 检查通过，不足以
  抵消两个核心性能门槛失败。Internal-test 与 Gold 因此继续封存，不能进入推理。
- 新风险排除任务的 Top 3%/5%/10% 是同一个 116,664-row active universe 上的
  全局嵌套排序，因此“全部不用”的唯一无重复解释是排除 Top-10% 并集 11,667
  条，而不是把 3,500+5,834+11,667 重复相加。按原 split 保留后的确定计数为
  Train 80,402、Dev 11,201、Internal-test 13,219、Gold 175，总计 104,997。
- 因候选分数使用了 Sol 冲突/Unclear、历史误判、高 NLL、方向错误和近似 TracIn，
  在同一风险规则过滤后的 Internal-test/Gold 上得到的指标具有 outcome-adaptive
  selection bias，只能回答“排除已知高风险病例后模型表现如何”，不能回答原始
  临床分布上的无偏泛化性能。
- 过滤后的 Train 类别计数为 Stable 39,126 / Improved 11,010 / Worse 13,884 /
  New 14,534 / Resolved 1,848；Dev 为 6,029 / 1,551 / 1,875 / 1,469 / 277。
  五类在 Train、Dev、Internal-test 和 Gold 中均仍有支持，缓存缺失键为 0，故
  风险过滤没有造成类别消失或需要重新划分。
- Top-10% 排除诊断的 retained-Dev 最佳 Macro-F1 为 0.535971，较前一
  Sol-authoritative seed-17 原 Dev 的 0.496082 高 0.039888；Accuracy 从
  0.583830 表面升至 0.616552，balanced accuracy 从 0.488578 升至 0.547278，
  min recall 从 0.389189 升至 0.466304，ODER 从 0.035917 降至 0.005357。
  这些变化同时混合了 Train 删除 9,004 条和 Dev 删除 2,219 条的作用，不能归因
  为单纯标签清洗或模型能力提升，也不能与原 Dev 作正式显著性比较。
- retained Internal-test 的 Accuracy / Macro-F1 / min recall / ODER 为
  0.580150 / 0.494916 / 0.437426 / 0.036917；retained physician Gold 为
  0.531429 / 0.539749 / 0.451613 / 0.062857。Gold 仅剩 175 条且已按风险排序
  删除 75 条，方差和选择偏倚都很大；这些数值只适合作为敏感性分析，不是新的
  临床 Gold 主结果。
- 终态回执和独立复算确认 Dev/Internal-test/Gold 预测行数分别为
  11,201/13,219/175，checkpoint、准备回执、训练回执与三份预测文件的 SHA-256
  全部一致。一次性评估守护器和 evaluator 均正常退出，未发生重复受保护推理。
- 用户的新授权把“诊断性排除”提升为后续活动数据版本的清洗决策，但没有使模型
  风险信号自动变成医学 Gold。正式记录应区分：医生确认这些候选具有复核/排除
  合理性；Luna/Sol 冲突、Unclear、报告不足和历史影响分数只是筛选依据；所有
  排除行继续保留在私有 quarantine 中，可追溯、可复核、不可静默删除。
# 2026-08-05 医生确认清洗后数据权威

- 医生复核范围是完整的 11,667 条全局 Top-10% 候选，不是抽样或集合级确认；最终状态必须写成 `PHYSICIAN_CONFIRMED_EXCLUDE`，不能继续写成 `SUSPICIOUS_PENDING_REVIEW`。
- Top 3%、Top 5%、Top 10% 严格嵌套，因此无重复的最终排除总量就是 Top-10% 并集 11,667 条。分 split 为 Train 9,004、Dev 2,219、Internal-test 369、Gold 75。
- 清洗后活动数据为 Train 80,402、Dev 11,201、Internal-test 13,219、Gold 175；活动指针只指向 `formal_cleaned_split_v1_1`。排除清单与 active manifest 的 ID 交集经独立重算为 0。
- 将排除病例放入私有 `quarantine/` 比移动原始影像更安全：能保持原始数据集和既有哈希不变，同时通过唯一活动 manifest 与 CLI 哈希门禁保证这些病例不再被训练、验证或测试读取。
- Luna、Sol、历史模型误判、高 NLL、方向相反错误和近似 TracIn 是候选发现信号，不是医学证明；医生对全部候选的逐条决定才是本版本的数据排除权威。
- 候选发现使用过模型结果，因此清洗后 Internal-test/Gold 的指标存在 outcome-adaptive selection bias。它们适合报告医生确认清洗队列上的敏感性结果，不得冒充原始临床分布的无偏泛化性能，也不追溯性覆盖旧 `STOP_DEVELOPMENT_GATE`。
# 2026-08-05 医生清洗版五运行启动边界

- 用户选择的新三种子集合是 17/28/43；这是一项显式协议变更。Seed 28 必须从零训练并获得新 config/run/checkpoint/receipt，历史 Seed 29 只保留为旧版本证据。
- 两张 RTX 3090 当前均完全空闲，存储充足，适合使用现有双 lane 队列；不能通过改变 batch size、epoch、early stopping 或模型结构来换取速度。
- 清洗后 manifest 已由 freeze receipt 强制绑定；新的队列必须显式传入 `--cleaned-split-freeze`，否则训练 CLI fail closed。
- 前一条 Top-10% seed-17 诊断的 Dev Macro-F1 0.535971 是配置选择的先验参考而非调参依据；新五运行仍按原 CBF PRTA、B402、B403 等预算配置从零完成统一门判定。

# 2026-08-05 医生清洗版五运行启动证据

- 正式准备回执绑定活动 manifest SHA-256=`45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89`、清洗冻结回执 `aa761c13...d069`、训练存储 `050a4837...e540`、文本缓存 `1846e3d9...a3fd` 与权重 `52cc993c...76be`；受保护结果读取计数为 0。
- Seed 17 与 Seed 28 都是从零开始的新运行身份，首个进度回执尚无 Dev 结果（best=-1）；此时只能确认训练入口、哈希和设备绑定正确，不能推断是否过门槛。
- 队列使用双 lane 串行接续：前两条 PRTA 完成后自动安排 seed 43 和 B402/B403，不改变数据、种子、方法或预算。最终门结论必须等待五条终态及统一 finalizer。
- 首个正式终态为 Seed 17：best Dev Macro-F1 0.528364，高于单 seed 0.48 与三-seed均值目标 0.52 的单臂参照，但是否满足三-seed均值及相对最强 B402/B403 的 +0.03 增益仍未知，不能据单臂结果宣布 development GO。
- B402 的首轮 best 已达 0.524021847，而 Seed-17 PRTA 正式 best 为 0.528363751，当前增益仅 +0.004341904。由于 baseline 的最终 best 不会低于其首轮 best，冻结的 `seed17_gain >= 0.03` 条件已不可逆地无法满足；即使三-seed均值随后通过，统一 development gate 也不能为 GO。仍需按授权跑完 Seed 43、B402、B403 并由 finalizer 正式闭合，不能据此提前停队列或改变阈值。
- B403 在 epoch 2 将 best 提高到 0.526093960，超过已终态 B402 的 0.524021847，暂为最强 temporal baseline；相对 Seed-17 PRTA 0.528363751 的增益仅 +0.002269791。该变化强化而不改变已经不可逆的 baseline-gain 失败结论。
- 清洗版最终三-seed均值为 0.528791110，较上一 Sol-label 版本 0.492736436 提高 +0.036054674；这说明医生清洗版在 outcome-adaptive Dev 上有明显改善，但不能抵消冻结方法门失败。最终 `seed17_gain=+0.002269791` 且 `mean_oder=0.006130405 > strongest_baseline_oder=0.005535220`，因此 HOLD 是唯一符合预注册条件的结论。
- 清洗版 Dev 本身由历史错误、Sol/TracIn 风险和医生排除形成，属于 outcome-adaptive curated evaluation set；即使三-seed均值超过 0.52，也不能将其表述为原始临床分布上的无偏泛化证据。HOLD 后继续封存 Internal-test/Gold，避免从受保护结果反向调参。
# 2026-08-06 Minimum-wave scope finding

- The exact Seed-17 PRTA minus B403 Dev Macro-F1 difference is approximately
  +0.002270 (+0.227 percentage points), but the existing aggregate receipts
  cannot establish significance because they contain no row-level predictions.
- A paired patient-bootstrap analysis therefore requires re-inference on the
  already-open cleaned Dev cohort only; this remains a no-training read-only
  diagnostic and does not authorize Internal-test/Gold access.
- A508 is a single-factor loss ablation (`alignment=0`). A509 is explicitly a
  multi-objective diagnostic control (`alignment=cmcp=inversion=state=0`) and
  must not be described as a single-component ablation.
- Paired analysis supports only performance comparability at Seed 17, not a
  PRTA classification advantage: the patient-bootstrap Macro-F1 interval spans
  zero. PRTA had 943 exclusive correct rows versus 1,050 for B403 and lower
  overall accuracy (0.617088 versus 0.626640).
- PRTA's ODER was 0.007499 versus B403's 0.005535; the patient-bootstrap PRTA
  minus B403 interval [0.000263, 0.003751] excludes zero in the harmful
  direction. Its matched-wrong/null/reversed Macro-F1 drops were also all
  larger than B403's, so current evidence does not support a mechanism/trust
  advantage either. A508/A509 are now the decisive auxiliary-loss diagnostic.
- A509-S17 (classification-only PRTA) finished at Dev Macro-F1 0.526869. This
  is only 0.001495 below full PRTA-S17 and 0.000775 above B403-S17, so the
  auxiliary objectives currently show little single-seed classification gain.
  This is provisional until A508-S17 and B403-S28/S43 finish and the frozen
  multiseed finalizer closes the minimum wave.
- B403-S28 has already reached a running best Dev Macro-F1 of 0.526998 by
  epoch 3, close to B403-S17 (0.526094) and full PRTA-S17 (0.528364). This is
  non-terminal evidence only, but it further motivates waiting for the exact
  three-seed B403 comparison rather than attributing the small Seed-17 gap to
  method superiority.
- B403-S28 is now terminal at 0.526998. The two completed B403 seeds 17/28
  average 0.526546, versus the already frozen three-seed PRTA mean 0.528791;
  this provisional difference is only +0.002245 for PRTA. B403-S43 is still
  required before the symmetric multiseed conclusion can be finalized.
- A508-S17 (alignment loss removed) is terminal at Macro-F1 0.524551 and ODER
  0.006071, respectively 0.003813 lower and 0.001428 better than full
  PRTA-S17. Together with classification-only A509-S17 (0.526869, ODER
  0.006160), the single-seed evidence does not show a compelling classification
  benefit from the full auxiliary-objective stack; the final route decision
  still waits for B403-S43 and the fail-closed aggregate comparison.
- Symmetric three-seed comparison is now terminal: PRTA Macro-F1 is
  0.528791 +/- 0.001178 versus B403 0.524565 +/- 0.003460, a small +0.004226
  mean difference. This does not establish superiority because the paired
  Seed-17 patient-bootstrap interval [-0.008452, +0.013238] includes zero.
- PRTA lacks a compensating trust/mechanism advantage: its paired ODER delta
  CI [0.000263, 0.003751] is significantly adverse, and its Macro-F1 drops are
  larger under matched-wrong, null, and reversed PRIOR. A509 remains within
  0.001495 Macro-F1 of full PRTA while improving ODER by 0.001339, reinforcing
  that the auxiliary stack is not justified by this minimum wave.
- The only supported route decision is `STOP_CURRENT_PRTA_ROUTE`. This does
  not erase the prior `HOLD_DEVELOPMENT_GATE`; it closes the proposed current
  PRTA contribution route without opening Internal-test/Gold or starting the
  nine-baseline matrix.

# 2026-08-06 Exploratory case-study hypothesis

- PRTA-S17 versus B403-S17 class accuracy deltas are strongly asymmetric:
  Improved +0.1167 and Worse +0.0549, but Stable -0.0541, New -0.0347, and
  Resolved -0.0505. The problem is therefore not simply insufficient temporal
  sensitivity; PRTA appears over-sensitive to change while weakening the
  current-state anchor.
- The architectural path supports this hypothesis. Native H0 classifies only
  the mean transition tokens. The separately learned state branch and finding
  query do not enter its logits directly, while an unrestricted relation MLP
  is added to current tokens before transition resampling.
- A suitable case-driven redesign should preserve a direct current-state logit
  path and add a bounded, query-conditioned temporal residual. A gate that is
  exactly zero for identical/null PRIOR features gives a structural safeguard
  against arbitrary prior corruption; the residual can then focus on true
  Improved/Worse/New/Resolved evidence without erasing Stable evidence.
- The full case-study confusion delta quantifies the over-sensitivity: PRTA
  produces 326 fewer correct Stable predictions and 234 more Stable->Improved
  errors than B403. It gains 181 Improved and 103 Worse correct predictions,
  but loses 51 New and 14 Resolved correct predictions.
- Under matched-wrong PRIOR, PRTA changes 50.47% of predictions versus B403
  42.86%; under null PRIOR the rates are 79.46% versus 66.02%; under reversal
  they are 51.58% versus 45.59%. These are architectural robustness failures,
  not merely aggregate classification noise.
- The exploratory screen is frozen to two candidates before training:
  `SA-PRTA-C0` uses bounded state-anchor mixture logits with classification
  loss only; `SA-PRTA-DM` adds one fixed opposite-direction margin term. This
  avoids a post-hoc hyperparameter sweep.
# 2026-08-06 Exploratory loss-screen evidence

- Weighted cross-entropy is terminally disqualified under the predeclared
  constraint: `TUNE-WCE-S17` reached best Dev Macro-F1 0.507527 with ODER
  0.017766, versus B403-S17 0.526094 / 0.005535. The remaining frozen arms must
  still finish before choosing the loss-screen branch.

# 2026-08-06 SUES HPC readiness findings

- The remote clean project and project-specific Python 3.11 environment have
  already been provisioned, and repository engineering preflight passes on the
  login node. This proves code/import readiness only, not GPU training readiness.
- Current blocking gaps are the missing shared BiomedCLIP weight, unverified
  Train/Dev data/cache completeness and hashes, missing optional/runtime packages
  (`scikit-learn`, `accelerate`, `openpyxl`), and no successful A800 Slurm probe
  for this environment yet.
- Two retained one-GPU allocations (4161 and 3066) exist on gpu01, but they must
  be checked for active steps before reuse; login-node `torch.cuda=False` is
  expected and is not evidence that the CUDA environment is broken.

# 2026-08-06 SUES HPC deployment evidence

- The server root is
  `/ipfs/inspurfileset/home/dqxy/dqxy11/projects/xiyaowang/050_VisualVIT`, a
  sibling of `036_IndexMemory`. It contains only legacy `incoming/` and
  `releases/` top-level directories, and does not yet contain `PRTA-CXR`.
- The server's shared `dl310` environment is Python 3.10, incompatible with
  this project's declared Python >=3.11 requirement. Deployment must therefore
  use a dedicated Python 3.11 environment.
- The remote queue has unrelated retained jobs `4161` and `3066`; deployment
  must not alter either allocation.
- A source archive containing 323 deployed files is byte-verified on the
  server: 3,770,233 bytes and SHA-256
  `2169fccb5a46e698ac5b3217dd35b6b72d44407a23b83f9fd0647a2cc0f334f4`.
  It was extracted to `050_VisualVIT/PRTA-CXR` without `.git`, test/lint
  caches, or Python bytecode.
- Environment verification passed on the login node: Python 3.11.15,
  PyTorch 2.6.0+cu126, torchvision 0.21.0+cu126, project/dependency imports,
  `pip check`, and `PASS_PRTA_CXR_ENGINEERING_PREFLIGHT`. CUDA is expected to
  be unavailable on the login node; the project contains a separate
  engineering-only GPU Slurm probe and no formal lock was set.
- OpenSSH SFTP recursive uploads require all remote child directories to exist
  and use `put -R` for an initial copy; `reput -R` is only suitable after a
  remote file exists. The 329,180,041-byte cleaned-split package then passed
  this transfer smoke check. A 200 Mbit/s-limited static transfer is running
  for the remaining non-active runtime artifacts and BiomedCLIP weight.

# 2026-08-06 SUES HPC readiness correction

- The later live audit supersedes the earlier provisional blocker list. A
  file-backed probe passed inside retained allocation 4161 on `gpu01` with an
  A800 80GB, torch 2.6.0+cu126, CUDA available, clean `pip check`, and project
  engineering preflight PASS. The environment/GPU combination is ready.
- `scikit-learn`, `accelerate`, and `openpyxl` are not imported by current
  source, scripts, or tests and are not prerequisites for the frozen PRTA
  training entry point; their absence is not a formal runtime blocker.
- The exact physician-cleaned Train/Dev manifest and its receipts are already
  present remotely and match local hashes. Protected manifests were not read.
- The broad static SFTP batch was stopped after its scope was found to include
  audit/label directories beyond the minimum runtime surface. Partial remote
  files were preserved. Future upload is restricted to the weight and minimal
  consolidated Train/Dev cache.
- Server launch remains blocked only until the BiomedCLIP weight, the 44.2 GB
  consolidated feature store, its index/text cache/receipts, and the final
  post-BS source snapshot pass remote SHA-256/path validation. Readiness does
  not authorize a formal run.

# 2026-08-06 Narrowed loss-screen terminal evidence

- Focal gamma 1 is the strongest completed narrowed arm at Macro-F1 0.535933,
  but its ODER 0.005892 is slightly worse than the predeclared B403-S17 ceiling
  0.005535. It therefore does not satisfy the frozen joint advancement rule.
- Balanced softmax is inferior on both constrained axes: Macro-F1 0.508886 and
  ODER 0.012945. It does not justify a learning-rate or structural follow-up.
- These terminal results close local tuning exactly as requested. They do not
  revise the immutable HOLD/STOP decisions and do not authorize a server
  experiment; server work is limited to engineering readiness until a new
  queue is explicitly frozen.

# 2026-08-06 SUES engineering readiness terminal finding

- The university server is now technically ready for the frozen cached
  Train/Dev workload: source/environment/GPU/weight/manifest/cache hashes and a
  real consolidated-feature read all pass on an A800 allocation.
- This is an engineering readiness result, not a scientific GO. No formal
  server training queue exists, no protected cohort was opened, and the prior
  HOLD/STOP findings remain unchanged. The next legitimate action is to define
  and freeze a new Linux Train/Dev queue before seeking launch authority.

# 2026-08-06 Continuous lightweight server-search hypothesis

- FG1 already clears the fixed Macro-F1 target by 0.006839 but misses the B403
  ODER ceiling by only 0.000357, approximately four Dev rows. Broad loss changes
  (weighted CE and balanced softmax) damaged both objectives, so the next most
  evidence-aligned change is a small directional constraint on the otherwise
  unchanged FG1/A509-H0 path.
- The first two server arms should therefore vary only the weight of the
  already-implemented opposite-direction margin loss. This directly targets
  Improved/Worse swaps while leaving the focal classification loss and main
  architecture unchanged. Terminal receipts, not intermediate epochs, decide
  whether to refine the margin, test the two predeclared learning rates, or
  freeze a winner for seeds 28/43.
- The continuous-search authority widens the number of sequential lightweight
  waves, not the data surface or the scientific claim. It does not authorize
  protected outcomes, retrospective threshold weakening, data cleaning, or a
  large architectural rewrite.
- The first Linux launch exposed a portability bug in the admission validator:
  `require_cleaned_manifest(role="train_dev")` delegated to a full-freeze
  validator that hashed every split and lineage path before checking the role.
  A server-safe implementation must validate freeze metadata and the requested
  role only; otherwise even a Train/Dev run unnecessarily touches protected
  files. The role-scoped projection both fixes Linux path portability and makes
  the zero-protected-read contract explicit.
- After the role-scoped correction, both identical scientific arms survived
  SSH disconnect and entered training on separate A800 allocations. This
  confirms the initial failure was purely a path-admission defect; it produced
  no result and does not consume a new hyperparameter observation.

# 2026-08-07 Direction-margin terminal result and confirmation boundary

- A small opposite-direction margin weight of 0.02 resolves the Seed-17 joint
  constraint that blocked local FG1: terminal Dev Macro-F1 is 0.535648 and
  ODER is 0.004553, respectively +0.006554 above the fixed F1 target and
  0.000982 below the B403-S17 ODER ceiling.
- Increasing the same one-axis weight to 0.05 lowers ODER to 0.005000 but also
  lowers Macro-F1 to 0.525488, below the fixed 0.529094 target. The current
  evidence therefore supports 0.02, not a monotonic claim that stronger
  directional regularization is better.
- This is still an outcome-adaptive Seed-17 Dev result. It cannot replace the
  historical HOLD/STOP decisions or support a protected-cohort claim until the
  exact DMW=0.02 setting completes seeds 28/43 and is compared symmetrically.
- Retained allocation 3066 is no longer usable for new `srun` steps because it
  has reached its Slurm step limit. This is an execution-capacity limitation,
  not model evidence; remaining confirmation/search jobs must run sequentially
  on allocation 4161 unless the server state changes.
- Seed 28 independently passes the same fixed joint target at Macro-F1
  0.534867 and ODER 0.005446. Thus DMW=0.02 has passed at two of two completed
  seeds, but the full confirmation remains incomplete until the frozen Seed-43
  receipt is terminal; no three-seed or protected-cohort claim is yet valid.
- Seed 43 independently passes at Macro-F1 `0.533353` and ODER `0.004196`, so
  DMW=0.02 passes the immutable joint target at all three frozen seeds. Its
  three-seed mean Macro-F1 `0.534623` exceeds seed-matched B403 by `0.010057`,
  while mean ODER `0.004732` is lower by `0.001547`; the direction is favorable
  at each paired seed on both metrics.
- This closes the exact-setting reproducibility question for the exploratory
  Train/Dev namespace, but it is still outcome-adaptive Dev evidence. It does
  not reopen protected cohorts or erase `HOLD_DEVELOPMENT_GATE` and
  `STOP_CURRENT_PRTA_ROUTE`. The next legitimate lightweight question is the
  predeclared learning-rate axis around the now-confirmed DMW=0.02 setting.
- Lowering the learning rate from `1e-4` to `5e-5` at fixed DMW=0.02 materially
  degrades the Seed-17 terminal result: Macro-F1 falls from `0.535648` to
  `0.520378`, while ODER rises from `0.004553` to `0.006160`. LR050 misses both
  fixed targets and provides no evidence for the lower-rate direction; the
  independently frozen LR200 arm remains required before closing this axis.
- Raising the learning rate from `1e-4` to `2e-4` at fixed DMW=0.02 improves
  Seed-17 terminal Macro-F1 from `0.535648` to `0.537901` and lowers ODER from
  `0.004553` to `0.003303`. This is the strongest jointly qualified Seed-17
  result in the current lightweight search, so the exact LR=2e-4 setting is
  now frozen for seeds 28/43.
- The LR=2e-4 result remains outcome-adaptive single-seed Dev evidence until
  both frozen confirmation seeds finish. It does not revise the historical
  HOLD/STOP decisions and cannot authorize Internal-test or Gold access.
- LR=2e-4 does not reproduce the Seed-17 joint pass at Seed 28: terminal
  Macro-F1 `0.528899` is just below the fixed `0.529094` floor, while ODER
  `0.006964` exceeds the `0.005535` ceiling. This seed is preserved as a real
  non-qualifying result; Seed 43 must finish before any symmetric aggregate
  comparison or next-wave decision.
- Seed 43 reaches Macro-F1 `0.531940` but ODER `0.006785`, so LR=2e-4 passes
  the fixed joint target at only 1/3 seeds. Its mean Macro-F1 is `0.001710`
  lower and mean ODER `0.000952` higher than confirmed LR=1e-4 DMW=0.02;
  therefore the higher learning rate is rejected as a reproducible setting.
- The next bounded refinement keeps LR=1e-4 and every other method/training
  field fixed while testing DMW 0.01 and 0.03 around the confirmed 0.02 value.
  This remains outcome-adaptive Dev search, not a revision of historical
  HOLD/STOP or permission to open protected cohorts.
- The confirmed LR=1e-4 DMW=0.02 setting improves three-seed mean Macro-F1 over
  B403 by `0.010057` (about one percentage point). Reaching the user's desired
  +2-point level requires another `0.009943` absolute mean Macro-F1 gain; a
  Seed-17-only spike is insufficient because LR=2e-4 already demonstrated
  that such gains may fail to reproduce.
- The expanded search therefore prioritizes low-dimensional regularization and
  imbalance axes rather than a main-method rewrite. Any future +2/+3-point
  statement requires exact three-seed confirmation and remains exploratory
  until a new development protocol is separately frozen.
- Choosing the three best seeds after observing Dev scores estimates a
  best-of-N upper envelope, not ordinary seed robustness. It can be useful for
  selecting deployment checkpoints, but reporting only those three would
  upward-bias performance. The audit-safe compromise is a predeclared pool,
  full result disclosure, and separate fixed-seed versus best-three tables.
- DMW=0.01 at fixed LR=1e-4 improves Seed-17 Macro-F1 from the confirmed
  DMW=0.02 value `0.535648` to `0.538661` (`+0.003013`), while increasing ODER
  from `0.004553` to `0.005178` (`+0.000625`). It remains inside the immutable
  ODER ceiling and therefore jointly qualifies, but misses the aspirational
  `0.546094` Seed-17 target. DMW=0.03 must finish before this axis can be
  closed or a confirmation/search-parent decision can be made.
- The previously exhausted 3066 allocation was restarted by the server/user
  and now has a fresh batch step plus one A800. This removes the sequential
  capacity constraint for future independent arms, but not for the already
  running DMW030 arm: changing it to two GPUs would alter its frozen execution.
  The valid acceleration is parallel arm-level search after both configs and
  the selected parent are frozen from terminal wave003 evidence.
- Allocation 3066 independently passes the same shared runtime boundary as
  4161: A800 80GB, exact cleaned Train/Dev rows, exact cache/model/manifest
  hashes, zero protected reads, and no formal experiment. Future two-arm
  parameter waves or two-seed confirmations can therefore run concurrently
  without mixing configurations or changing per-run budgets.
- Live topology resolves the ambiguity: 3066 and 4161 are two separate
  one-GPU Slurm allocations on the same physical host `gpu01`, not two hosts.
  Independent runs are still valid because Slurm assigns one GPU to each, but
  the workflow must wait for the unrelated `3066.2` GPU telemetry step to
  release allocation 3066 rather than forcing overlap.
- Allocation 4161 subsequently ended and cancelled DMW030 mid-epoch. Although
  the training API accepts `--resume`, its checkpoint does not retain the
  data-loader generator or global RNG states, so replay from `last.pt` would
  change the post-checkpoint minibatch trajectory. For auditable evidence, the
  partial attempt must remain preserved and the identical frozen configuration
  must restart in a new attempt namespace on replacement allocation 9929.
- The active compute authority is now only 9929 plus 3066. They are used as two
  independent one-GPU workers, not as a distributed two-GPU model; the second
  lane is the next predeclared focal-gamma arm anchored to the confirmed
  DMW=0.02 parent, not to DMW030 intermediate evidence.
- Both replacement lanes passed their runtime boundary and are now active as
  separate one-GPU runs: unchanged DMW030 attempt 2 on 9929 and focal gamma
  0.5 on 3066. This is arm-level parallelism only; no gradient, batch, model,
  or checkpoint is shared between the two experiments.
- Focal gamma 0.5 and 1.5 were frozen together before launching gamma 0.5, so
  the second value cannot be chosen from gamma 0.5 intermediate evidence.
  Gamma 1.5 remains queued for the first allocation that becomes free.
- DMW=0.03 does not improve the confirmed region: its unchanged fresh attempt
  ends below the F1 gate (`0.526203`) and above the ODER ceiling (`0.006607`).
  Wave003 therefore selects DMW=0.01 as its qualified Seed-17 result, while
  withholding multiseed confirmation because `0.538661` remains below the
  predeclared aspirational target.
- Focal gamma 0.5 is jointly qualified at Macro-F1 `0.537393` and ODER
  `0.004464`, but it is slightly below the DMW010 Seed-17 F1 and also misses
  the aspirational target. Gamma 1.5 remains necessary to close the focal axis;
  the idle second allocation is not used for a new axis before that comparison.
- Focal gamma 1.5 materially degrades both objectives to Macro-F1 `0.525474`
  and ODER `0.007321`, so wave004 selects gamma 0.5 but still does not reach
  the aspirational Seed-17 target. No focal setting is promoted to multiseed
  confirmation.
- For the next one-axis beta comparison, the parent is DMW010 rather than the
  lower-F1 focal winner: DMW010 remains the globally highest-F1 completed
  jointly qualified Seed-17 setting. Both beta values were frozen before
  launch and now run independently on 9929/3066.
- Class-balance beta does not improve the global Seed-17 reference. Beta 0.999
  is jointly qualified at Macro-F1 `0.533685` and ODER `0.003839`, trading
  lower ODER for `0.004976` less Macro-F1 than DMW010. Beta 0.99999 degrades
  both objectives to `0.526265` / `0.011338`. The global parent therefore
  remains DMW010; neither beta arm merits multiseed confirmation.
- The next frozen weight-decay axis keeps DMW010, LR=1e-4, focal gamma 1,
  beta 0.9999, seed 17, architecture, data, and budget unchanged while testing
  only weight decay 0.005/0.02. Both arms launched independently with zero
  protected reads; terminal evidence alone will select or reject this axis.
- Neither weight-decay alternative is viable: WD=0.005 reaches Macro-F1
  `0.525530` / ODER `0.006696`, and WD=0.02 reaches `0.527095` / `0.007321`.
  Both fail the original joint gate, so Wave006 retains DMW010 rather than
  promoting an inferior weight-decay setting.
- The next predeclared one-axis dropout comparison therefore varies only
  `model.dropout` between 0.05 and 0.15 around the unchanged DMW010 parent.
  Both configs were frozen before launch and run as separate single-GPU jobs;
  terminal evidence alone will determine whether either value advances.
- Dropout 0.05 (`0.530996` / `0.006696`) and dropout 0.15 (`0.529138` /
  `0.007321`) both retain just enough Macro-F1 to clear the floor but violate
  the ODER ceiling. Neither is an admissible improvement, so the original
  DMW010 parent remains globally preferred.
- The final predeclared individual axis varies only the direction-margin
  magnitude from its parent value 0.2 to 0.1/0.3 while keeping the direction
  loss weight at 0.01 and all other fields fixed. Both configs were frozen
  before launch; no combination will be chosen until both are terminal.
