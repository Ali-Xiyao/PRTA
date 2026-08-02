# Engineering validation receipt

Date: 2026-08-02 (Asia/Shanghai)

Status: `PASS_ENGINEERING_SMOKE__HOLD_SCIENTIFIC_PARITY`

## Passing gates

- Editable install: `python -m pip install -e . --no-deps`.
- Import from the parent directory: package version `0.1.0`.
- Pytest: `28 passed`.
- Ruff: `All checks passed`.
- Compile: `python -m compileall -q src scripts tests`.
- Preflight: `PASS_PRTA_CXR_ENGINEERING_PREFLIGHT`.
- Scripts 01, 02, 04, and 05 pass their synthetic data/label/split paths;
  script 03 passes the no-call Luna preflight; scripts 06-08 pass preflight.
- Scripts 09-11 retain safe `PASS_DRY_RUN` placeholders because trust,
  figures, and VLM work are downstream of formal training evidence.
- Synthetic smoke train: `PASS_SYNTHETIC_SMOKE`, Seed 17, 3 steps,
  loss `1.696425 -> 1.656803 -> 1.618791`.
- Synthetic Block-8 cache: six images, three FP16 shards, successful indexed
  round trip; no reports, labels, or patient identifiers stored.
- Synthetic evaluation: five-class metric path passed without opening the
  internal-test split.
- Read-only local BiomedCLIP asset check: strict 12-block visual load, four
  tail blocks, `[1,197,768]` finite Block-8 output, `[1,512]` finite text
  output, and `[1,5]` finite full-size PRTA logits. Model SHA-256:
  `52cc993c5c5ff962bd0c60931874bc001e7e9b41666a385530f4a036294576be`.
- Formal cache/train/evaluate entry points are tested to reject before input
  opening when the exact authorization environment value is absent.
- Manual and experiment-plan copies match supplied originals by SHA-256.

## Safety receipts

- Formal experiment started: `false`.
- Real data opened: `false`.
- Protected outcomes opened: `false`.
- Luna/Codex external labeling call made: `false`.
- Cloud remote configured or pushed: `false`.
- Smoke checkpoint and receipt are ignored by Git.

## Remaining Phase 0 gate

Scientific old-checkpoint/small-cohort parity and the new full-data build were
deliberately not run. The project remains `HOLD_PARITY_NOT_RUN`; passing these
engineering gates does not authorize formal data processing, training, or a
scientific result claim.
