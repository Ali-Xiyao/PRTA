# Phase20 最终证据与论文叙事

## 最终一句话结论

PRTA-CXR 是一个 finding-conditioned、prior-responsive 的纵向胸片五分类方法；在
冻结主线后完成的 full-Train/official-Dev、消融、跨来源、纵向 comparator、校准、
选择性预测、亚组、state-pruning、效率及患者聚类配对统计表明：精简后的主方法保持
了有竞争力的 Macro-F1，并维持较低方向错误率，但没有证据支持其对所有比较器的
普遍显著优势。

## 论文主叙事

1. 纵向胸片进展判断不仅依赖当前影像，还依赖 PRIOR 的身份、时间方向和病灶语义。
2. PRTA-CXR 用 finding-conditioned query、cross-time alignment 与 temporal relation
   residual 组织这种信息，并用 state anchor、opposite-direction cost 和 matched-hard
   CMCP 约束训练。
3. 最小精简矩阵证明 standalone Prototype CE 可以删除，因此最终代码不再包含五个
   权重恒为 0 的历史损失实现；`Slim-S1` 只保留为配置追溯名，论文方法名统一写作
   **PRTA-CXR**。
4. Phase20 不是再次选模，而是在冻结方法后补齐 full-Train/official-Dev 证据。
5. 双向 MIMIC-CXR/CheXpert Plus source-held 结果写作“跨数据来源泛化”，不能写作
   独立外部临床验证。
6. ReXGradient 外部验证已退出论文证据，不报告旧结果，也不据此修改主方法。

## 结果措辞模板

主结果可写为：

> Across three frozen seeds, PRTA-CXR achieved a Dev Macro-F1 of
> 0.5520 ± 0.0011. Its paired difference relative to the strongest
> outcome-ranked compatible comparator was -0.0053 (95% CI -0.0129 to
> 0.0024; exploratory p=0.179), indicating comparable rather than uniformly
> superior discrimination.

安全性可写为：

> PRTA-CXR reduced opposite-direction errors relative to the strongest
> outcome-ranked comparator by 0.0011 on average, while the state-pruned
> deployment path preserved exact prediction and logit parity in the audited
> S43 export.

校准可写为：

> Cross-fitted temperature calibration reduced mean ECE from 0.0339 to
> 0.0285, whereas NLL changed minimally; the result supports calibration
> reporting but not a clinical referral claim.

## 不允许的主张

- 不写“显著优于全部 baseline”；所有预声明 Macro-F1 Holm-adjusted p 均为 1.0。
- 不把内部架构启发式重实现写成 official implementation。
- 不把 source-held 结果写成 external clinical validation。
- 不把 cached-feature latency 写成 raw-image end-to-end latency。
- 不把 descriptive subgroup、risk-coverage 或 oracle routing 写成真实临床效用。
- 不提已退役 ReXGradient 数值，不打开 Internal-test、Gold 或医生人工数据。

## 完成凭据

| 层 | 状态 |
| --- | --- |
| Phase20-A | 88/88 PASS |
| Comparator | 24/24 PASS |
| B1 | 6/6 PASS |
| B2 | 28/28 PASS |
| Evidence finalizer | `PASS_PHASE20_EVIDENCE_FINAL_NO_SELECTION_AGGREGATE` |
| Protected reads | 0 |
| Model re-selection | false |

最终 evidence receipt SHA256：
`198e27311dad49d1abea4d36cec86773bdc422df8aa06dd8f2ee1c6ee1185ffd`。
