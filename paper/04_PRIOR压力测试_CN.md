# PRIOR 行为审计

## 最终可报告范围

Phase20 的 S1 probability export 已完成，但当前 Git-safe B1 聚合不包含
true/matched-hard/null/reversed 四条件的完整 S1 数值表。因此最终论文不得把历史
V2 四条件表改名为 PRTA-CXR，也不得声称该表由
`data/15_Phase20-B1正式聚合.json` 提供。

当前最终仓库只保留 probability export 的完成凭据，不保留可独立核验的 S1
四条件聚合数值。因此该实验不进入论文定量主表；若未来要恢复，必须从受保护的
patient-level export 重新运行 Git-safe finalizer，而不是从历史 V2 表或中期文档抄数。

## 写作口径

- 可写：受控 PRIOR 审计已经按冻结协议执行，但当前公开包不发布其 S1 定量表。
- 可写：relation residual 的结构消融显著降低主任务表现，与模型使用时间关系的
  设计目标一致。
- 不可写：最终 S1 已有公开可追溯的四条件或 true-versus-wrong 数值表。
- 不可写：模型对真实错误/缺失历史具有临床鲁棒性。
- 不可写：controlled intervention 证明了临床因果机制。

历史 V2 的四条件结果仍可在 VisualVIT 历史归档中审计，但不进入 PRTA-CXR
最终论文主表。扩展 finding/current corruption 属未运行的可选未来工作，不是论文
完成门。
