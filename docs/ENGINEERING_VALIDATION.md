# Engineering validation receipt

Date: 2026-08-02 (Asia/Shanghai)

Status: `PASS_ENGINEERING_SMOKE__HOLD_SCIENTIFIC_PARITY`

## Passing gates

- Editable install: `python -m pip install -e . --no-deps`.
- Import from the parent directory: package version `0.1.0`.
- Pytest: `14 passed`.
- Ruff: `All checks passed`.
- Compile: `python -m compileall -q src scripts tests`.
- Preflight: `PASS_PRTA_CXR_ENGINEERING_PREFLIGHT`.
- Default dry-run scripts: 01-06 and 08-11 all `PASS_DRY_RUN`.
- Synthetic smoke train: `PASS_SYNTHETIC_SMOKE`, Seed 17, 3 steps,
  loss `1.696425 -> 1.656803 -> 1.618791`, checkpoint size 58,594 bytes.
- Manual and experiment-plan copies match supplied originals by SHA-256.

## Safety receipts

- Formal experiment started: `false`.
- Real data opened: `false`.
- Protected outcomes opened: `false`.
- Luna/Codex external labeling call made: `false`.
- Cloud remote configured or pushed: `false`.
- Smoke checkpoint and receipt are ignored by Git.

## Remaining Phase 0 gate

Scientific old-checkpoint/small-cohort parity was deliberately not run. The
project remains `HOLD_PARITY_NOT_RUN`; passing engineering smoke does not
authorize Phase 1 or support a scientific result claim.
