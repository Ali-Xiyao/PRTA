# PRTA-CXR-Slim-S1 最终主线与重跑矩阵

## 最终决定

最终投稿方法锁定为 **PRTA-CXR**，`Slim-S1` 仅为冻结配置身份：保留 finding conditioning、cross-time alignment、
temporal relation residual、state anchor 0.025、ODC 0.05、matched-hard CMCP 0.01
和 Tail8/H0；删除 standalone Prototype CE 与 DMW。

这不是从 official Dev 二次选模型。S1 来自已经冻结并完成的 Train-only Slim
矩阵；本轮 full Train / official Dev 实验只做确认与论文证据补全。

## 重跑盘点

| 类型 | 内容 | 结论 |
|---|---|---|
| 历史继承 | IF-A10/S0、TILA8、Current-only、Siamese 的 Git-safe 聚合结论 | 只作历史证据；旧私有 checkpoint 已删除 |
| 新训练 | full S1、精确损失/结构消融、F01/F02-DMW0 | 已完成并由 Phase20-A finalizer 核验 |
| 新训练 | source-held、scaling、symmetric/plausible noise | 已完成并纳入 88/88 PASS |
| 新推理 | PRIOR 压力、校准/选择性预测、亚组、效率/剪枝、安全路由 | B1 6/6、B2 28/28 PASS |
| 对比重建 | V2、S0、B401、B402、TILA8、BioViL-T-style、CheXRelNet-inspired、`TILAPaper` | 8 系统 × 3 Seeds，24/24 finalizer PASS |
| 历史保留 | V2 及其既有表格/诊断 | 只作开发父方法证据 |
| 正文泛化 | 双向 MIMIC-CXR/CheXpert Plus source-held | 三 Seed跨来源评估；不称为独立外部验证 |
| 退役 | ReXGradient / 其他外部验证 | 不再运行，不进入论文结果或模型选择 |
| 封存 | Internal-test、Gold、医生人工 | 本阶段不做 |

新训练固定 63 单元：S1 3、loss ablation 9、structural ablation 9、F01/F02-
DMW0 6、source-held 6、scaling 12、label noise 18。Seeds 固定为 17/28/43。
执行资源为服务器双 A800 + 本地 RTX3090 GPU0；本地 GPU1 明确预留为空闲卡，
全部任务按三卡预计时长重新平衡。

## 历史执行记录与最终状态

截至 2026-08-22，Phase20-A 88/88、comparator 24/24、B1 6/6、B2 28/28
及 evidence finalizer 均为 PASS。以下段落只记录 2026-08-18 起跑和接力设计，
不再表示存在运行中或待跑任务。

Phase20 已冻结为 88 个自动依赖 job，其中 63 个为新训练单元。服务器 A800 两条
lane 分别从 `P20-FINAL-S1-S17` 与 `P20-FINAL-S1-S28` 开始，本地 RTX3090 GPU0
从 `P20-FINAL-S1-S43` 开始；RTX3090 GPU1 保持空闲。三条 lane 均已进入正式
训练，外部数据、Internal-test、Gold 与医生人工均未打开。

为避免旧 checkpoint 清理后丢失患者级 paired/safety 分析能力，24-cell 对比重建
程序与 Slim-S1 专属可信性推理程序已经构建并通过全仓测试。它们不会停止或抢占
当前任务：Phase20-A 三条 lane 正常运行；对比重建只接受跨 server/local host shard
合并后的 88-job 全局 finalizer，不能按单条 lane completion 提前接力。可信性程序
必须等三 Seed final S1 checkpoint 全部 PASS 后才能冻结。两者都不分配 GPU1。
旧逐 lane watcher 已退出；修复后的 `6100318` 不可变源码、comparator program 和
三个 v2 hash-gated CPU watcher 已部署。它们不会停止当前训练，且全局 finalizer
非 PASS 时不会绕过失败继续训练；host-shard 合并由独立 CPU coordinator 自动完成。

历史源码/聚合结论保存在 GitHub 分支
`codex/archive-v2-history-before-phase20`（冻结提交 `6f471d93421b743fed446b650d7e2fd5f71ef24d`）。
旧私有运行目录、checkpoint、患者级预测副本和传输包不进入 Git，已在当前输入
allowlist 复验后从本地与服务器删除；清理不触碰 Phase20 及其必要输入。

若需查看旧方法的源码、配置和公开聚合叙事，只使用上述只读归档分支；该分支不含
任何 checkpoint、私有患者数据或账号凭据，不能作为恢复旧运行数据的渠道。

## 论文写法

当前可写：“Train-only 模块选择按冻结容差确定了更精简的 PRTA-CXR 配置；随后在
full Train / official Dev 上完成独立确认与可信性重评估。”正式主表使用 Phase20
finalizer 的三 Seed结果，不使用 Slim Train-only 的 0.560520。

完整机器协议见
[Slim-S1 最终主线锁定与确认实验协议](../docs/PRTA_CXR_Slim-S1最终主线锁定与确认实验协议_CN.md)。
