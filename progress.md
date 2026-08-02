# Progress - full-data training pipeline

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
