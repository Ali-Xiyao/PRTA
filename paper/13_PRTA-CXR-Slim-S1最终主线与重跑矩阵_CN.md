# PRTA-CXR-Slim-S1 最终主线与重跑矩阵

## 最终决定

最终投稿主线锁定为 `Slim-S1`：保留 finding conditioning、cross-time alignment、
temporal relation residual、state anchor 0.025、ODC 0.05、matched-hard CMCP 0.01
和 Tail8/H0；删除 standalone Prototype CE 与 DMW。

这不是从 official Dev 二次选模型。S1 来自已经冻结并完成的 Train-only Slim
矩阵；本轮 full Train / official Dev 实验只做确认与论文证据补全。

## 重跑盘点

| 类型 | 内容 | 结论 |
|---|---|---|
| 继承 | IF-A10 作为 S0、TILA8、Current-only、Siamese | 不重复训练 |
| 新训练 | full S1、精确损失/结构消融、F01/F02-DMW0 | 必须重跑 |
| 新训练 | source-held、scaling、symmetric/plausible noise | 必须按 S1 重跑 |
| 新推理 | 模态压力、校准/选择性预测、亚组、效率/剪枝、安全路由 | full S1 checkpoint 后执行 |
| 历史保留 | V2 及其既有表格/诊断 | 只作开发父方法证据 |
| 延后 | 外部验证 | 数据合同解决后最后执行 |
| 封存 | Internal-test、Gold、医生人工 | 本阶段不做 |

新训练固定 63 单元：S1 3、loss ablation 9、structural ablation 9、F01/F02-
DMW0 6、source-held 6、scaling 12、label noise 18。Seeds 固定为 17/28/43。
执行资源为服务器双 A800 + 本地 RTX3090 GPU0；本地 GPU1 明确预留为空闲卡，
全部任务按三卡预计时长重新平衡。

## 当前执行状态（2026-08-18）

Phase20 已冻结为 88 个自动依赖 job，其中 63 个为新训练单元。服务器 A800 两条
lane 分别从 `P20-FINAL-S1-S17` 与 `P20-FINAL-S1-S28` 开始，本地 RTX3090 GPU0
从 `P20-FINAL-S1-S43` 开始；RTX3090 GPU1 保持空闲。三条 lane 均已进入正式
训练，外部数据、Internal-test、Gold 与医生人工均未打开。

历史源码/聚合结论保存在 GitHub 分支
`codex/archive-v2-history-before-phase20`（冻结提交 `6f471d93421b743fed446b650d7e2fd5f71ef24d`）。
旧私有运行目录、checkpoint、患者级预测副本和传输包不进入 Git，已在当前输入
allowlist 复验后从本地与服务器删除；清理不触碰 Phase20 及其必要输入。

## 论文写法

当前可写：“Train-only 模块选择按冻结容差选择了更精简的 S1；随后在 full Train /
official Dev 上进行独立确认与可信性重评估。”在 Phase20 finalizer 完成前，不得写
“S1 在 official Dev 优于 S0/V2”，也不得把 Slim 的 0.560520 当成最终主表数字。

完整机器协议见
[Slim-S1 最终主线锁定与确认实验协议](../docs/PRTA_CXR_Slim-S1最终主线锁定与确认实验协议_CN.md)。
