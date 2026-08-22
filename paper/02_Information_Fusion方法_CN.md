# PRTA-CXR Information Fusion 方法

## 任务定义

输入为同一患者的 current CXR 表示、PRIOR CXR 表示和目标 finding 文本，输出五类
纵向进展状态。最终论文方法名统一为 **PRTA-CXR**；`Slim-S1` 只用于冻结配置和
checkpoint 追溯，`V2` 只表示历史开发父方法。

## 最终信息流

1. **Finding-conditioned query**：finding 文本经过投影后形成视觉查询条件。
2. **Cross-time alignment**：以 current 表示为查询，对齐 PRIOR 视觉 token。
3. **Temporal relation residual**：显式构造时相关系并直接注入 current 路径，最终
   行为是 `current + relation residual`。冻结配置没有启用 learned/fixed residual
   scale。
4. **Transition prediction**：H0 头只汇聚 transition tokens 并输出五分类 logits。

## State 分支的准确角色

最终配置中的 state 分支是**训练辅助分支**：它为权重 `0.025` 的 state-anchor
目标提供表示，但不进入 H0 推理头。公开配置以
`branch_mode=training_auxiliary_state` 明确该语义；历史 checkpoint-side config
中的 `legacy` 名称仅为兼容别名。

部署时可以裁剪 state token 计算。Phase20-B1 在 S43 的全部 11,201 行上验证：
prediction mismatch=0，max absolute logit difference=0。该结果证明当前 H0
预测路径与 state 分支解耦，不证明任意 head/任意后续改造都可安全裁剪。

## 最终训练目标

| 目标 | 权重 | 作用 |
| --- | ---: | --- |
| Class-balanced focal classification | 1.0 | 五类主任务 |
| State anchor | 0.025 | 训练期状态保持约束 |
| Opposite-direction cost | 0.05 | 约束严重方向错误 |
| Matched-hard CMCP | 0.01 | 强化患者历史特异性 |

Standalone Prototype CE、DMW 与所有历史零权重损失不属于最终方法。

## 最终消融合同

核心结构消融分别移除 finding query、relation residual 与 cross-time alignment；
辅助目标消融分别移除 state anchor、ODC 与 CMCP。所有主结果使用 Seeds
17/28/43 的 mean ± sample SD，不以消融结果重新选择主方法。

## 比较器身份

比较器是在相同五分类标签空间、相同 backbone/cache 和训练预算下完成的独立适配：

- CheXRelNet-inspired relation model；
- BioViL-T–style temporal-token adaptation；
- TILA-adapted / paper-based temporal fusion；
- current-only、Siamese-difference 与通用 fusion rebuild。

它们不是发布方 official code/checkpoint reproduction。JSON 中的内部 experiment ID
仅用于追溯，不改变论文中的 adapted/inspired 身份。
