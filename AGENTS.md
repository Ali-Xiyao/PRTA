# PRTA-CXR repository rules

- `docs/PRTA_CXR_Slim-S1最终主线锁定与确认实验协议_CN.md` is the active
  method/experiment authority. Historical execution code and manuals live in
  the VisualVIT archive and are not runtime authority for this repository.
- Do not run formal training, labeling, caching, evaluation, baseline,
  ablation, trust, visualization, or VLM jobs without explicit user authority.
- Formal entry points must require both `--formal` and
  `PRTA_CXR_ALLOW_FORMAL=I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN`.
- Never read protected outcomes during data preparation or development.
- Never place real patient identifiers, reports, credentials, images, feature
  caches, checkpoints, or predictions in Git.
- Pre-Phase20 Git-safe history is frozen on
  `codex/archive-v2-history-before-phase20` at
  `6f471d93421b743fed446b650d7e2fd5f71ef24d`. Do not use that branch as a
  runtime/checkpoint store or restore superseded Phase16 queues from it.
- The complete Git-safe snapshot immediately before final-repository cleanup is
  archived in VisualVIT branch `codex/prta-history-archive-20260822` under
  `_archive/PRTA-CXR-dual-branch-repair/process_code_snapshot_before_final_cleanup_20260822/`.
  The sanitized archive commit is
  `fa27c71049b5a45a89816672ab4abbc44b94e547`.
- Keep all paths repository-relative in configs and receipts.
- Run `pytest`, `ruff check`, `python -m compileall`, preflight, and the
  synthetic smoke train before calling an engineering handoff ready.
- A passing smoke suite is not scientific parity and is not Phase 0 GO.
- Do not restore server-operation, queue-orchestration, labeling, retired
  external-validation, or manual-review utilities to this final repository.
