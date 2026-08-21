# Phase16 PRIOR 安全路由模拟

状态：`PASS_PHASE16_PRIOR_SAFETY_ROUTING_NO_SELECTION`

## 协议

- 使用冻结 V2 与 Current-only（B401）三 Seed Dev predictions，不重新训练；
- synthetic intervention 身份作为已知无效历史标记，比较 Always-V2、
  Invalid→Current-only、Invalid→abstain；
- 无阈值拟合、无模型选择、未读取 Internal-test/Gold；
- 这是 **oracle-detectable invalid-history routing simulation**，用于估计正确识别无效
  PRIOR 后的路由上界，不代表已实现真实临床 PRIOR 异常检测器。

## 三 Seed 结果（ordinary patient-observation metrics）

| PRIOR 条件 | 策略 | Coverage | Macro-F1 mean ± SD | ODER mean ± SD |
| --- | --- | ---: | ---: | ---: |
| true | Always-V2 / 两种路由 | 1.00 | 0.551821 ± 0.006574 | 0.003720 ± 0.000743 |
| matched-hard wrong | Always-V2 | 1.00 | 0.342056 ± 0.005420 | 0.053061 ± 0.001343 |
| matched-hard wrong | Invalid→Current-only | 1.00 | 0.412872 ± 0.007166 | 0.035116 ± 0.004222 |
| matched-hard wrong | Invalid→abstain | 0.00 | — | — |
| null | Always-V2 | 1.00 | 0.249746 ± 0.084352 | 0.024760 ± 0.003664 |
| null | Invalid→Current-only | 1.00 | 0.412872 ± 0.007166 | 0.035116 ± 0.004222 |
| null | Invalid→abstain | 0.00 | — | — |
| reversed | Always-V2 | 1.00 | 0.191750 ± 0.001607 | 0.171324 ± 0.001119 |
| reversed | Invalid→Current-only | 1.00 | 0.412872 ± 0.007166 | 0.035116 ± 0.004222 |
| reversed | Invalid→abstain | 0.00 | — | — |

## 解释

若无效历史能被可靠识别，Current-only fallback 可显著恢复 matched-hard、null 和
reversed 条件下的 Macro-F1，并把 reversed PRIOR 的 ODER 从约 0.171 降至 0.035。
null 条件下 fallback 的 ODER 高于 Always-V2，但 Macro-F1 大幅提高，因此仍应作为
多目标权衡报告，不能只挑一个指标。全 abstain 在这些“整批均为无效历史”的合成
cohort 上 coverage 为 0，只说明安全拒绝边界，不提供分类性能估计。

下一步不是训练新主模型，而是把真实可观测的 patient/time/view/availability 检查实现
成独立审计层；任何 sensitivity threshold 必须预冻结或患者级 cross-fitting。

## 溯源

- 正式聚合角色：`prior_safety_routing.json`（私有运行目录不进入 Git）
- SHA-256：
  `cdf2c459bda30c5349c46139b7bcaf01545105601fd43c57d82be37621567a20`
- 输入 receipt hashes 已完整记录在正式 JSON 中。
