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
