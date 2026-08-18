# PRTA-CXR repository rules

- `docs/PRTA_CXR_最终论文实验与项目重构执行手册_CN.md` and
  `docs/PRTA_CXR_实验计划与空结果表_Markdown版_CN.md` are the active authority.
- Do not run formal training, labeling, caching, evaluation, baseline,
  ablation, trust, visualization, or VLM jobs without explicit user authority.
- Formal entry points must require both `--formal` and
  `PRTA_CXR_ALLOW_FORMAL=I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN`.
- Never read protected outcomes during data preparation or development.
- Never place real patient identifiers, reports, credentials, images, feature
  caches, checkpoints, or predictions in Git.
- Keep all paths repository-relative in configs and receipts.
- Run `pytest`, `ruff check`, `python -m compileall`, preflight, and the
  synthetic smoke train before calling an engineering handoff ready.
- A passing smoke suite is not scientific parity and is not Phase 0 GO.
- For SUES-HPC connection failures, follow
  `docs/operations/SUES_HPC_SSH连接恢复手册_CN.md` as the default recovery
  procedure. Do not parallel-retry the gateway, restart adapters/proxies, kill
  unverified processes, or create status-only `srun` steps.
