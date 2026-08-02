# Phase 0 status

Decision: `HOLD_PARITY_NOT_RUN`

## Engineering scope completed in this handoff

- Independent package/repository skeleton.
- Whitelist core migration and legacy exclusion map.
- Central five-class/inversion and sample contracts.
- Luna JSON schema and fail-closed parser/merge gates.
- Patient-disjoint manifest audit and deterministic pairing/folds.
- Native H0/H1 heads and PRTA core unit coverage.
- Run receipt schema, authority hashing, no-absolute-path preflight.
- Synthetic CPU smoke training with checkpoint receipt.
- Functional data, label, cache, train, and internal-evaluation entry points
  with preflight/synthetic modes and a formal double-authorization lock.
- Frozen BiomedCLIP Block-8 and text-cache adapters, hashed cache inventory,
  PRTA multi-loss training, checkpoint/resume, and input-hash-bound evaluation.

## Deliberately not claimed

- Old-checkpoint/small-cohort prediction parity was not run.
- A real single-GPU train was not run; only generated tensors were used.
- The real source and pair manifests have passed exclusion/lineage audits, but
  no labeled formal split manifest exists yet.
- Luna pilot, clinician audit, expanded data, formal baselines, ablations,
  trust analysis, figures, and VLM deployment have not started.

Phase 1 cannot open until the user explicitly authorizes the specific parity
inputs/run and the parity table in the supplied plan is filled with evidence.

Code readiness does not remove the data gate. The exact remaining inputs and
formal command templates are recorded in
[TRAINING_READINESS_AND_COMMANDS_CN.md](TRAINING_READINESS_AND_COMMANDS_CN.md).

## 2026-08-02 data-policy addendum

The user directed the new project to retire debugging-only dataset isolation,
reconsider all previously used datasets, and rebuild larger patient-level
splits from scratch. The durable policy and unchanged protected boundaries are
recorded in [DATA_REPARTITION_POLICY.md](DATA_REPARTITION_POLICY.md). This is
The authorized source/pair preparation has now completed; training has not
started. Current counts, hashes, and the next gate are recorded in
[REAL_DATA_PREPARATION_STATUS_CN.md](REAL_DATA_PREPARATION_STATUS_CN.md).
