# Findings - full-data training pipeline

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
