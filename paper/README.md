# PRTA-CXR 论文材料工作区

本目录保存可迁移、可审计的论文写作材料。当前内容只使用冻结的
Train/Dev 聚合证据，不包含患者级预测、影像、报告、checkpoint、账号信息或
任何受保护测试集结果。

原始安全约束继续有效：只有通过注册冻结、一次性正式评估和不可变凭据校验的
结果才能进入论文表格；尚未完成的可靠性、外部泛化或临床价值只能写成计划或
假设，不能提前写成已观察结论。

最终投稿主方法已于 2026-08-18 锁定为 `PRTA-CXR-Slim / Slim-S1`。现有 V2
材料保留为历史开发证据；full Train / official Dev 的 63-cell Phase20 训练与
S1 专属可信性重推理完成前，不得把 Slim Train-only 数字写入最终主表。

旧私有 checkpoint 清理后，V2/S0/B401/B402/TILA8 与三项纵向内部/论文复现比较器
需要按 Phase20 输入合同重建 8×3 单元，才能生成患者级 paired/safety 证据；相关
代码已完成；队列只在 Phase20-A 的 63-cell/88-job 全局 finalizer PASS 后接力，
不能仅凭单 lane completion 启动，并继续保留本地 GPU1。

Phase20 证据链拆为 B1（20 个 S1-only jobs）与 B2（27 个比较器概率导出 + 1 个
patient-cluster/Holm/safety/disagreement 统计 job）。三层 finalizer 分别对账 Phase20-A、
24-cell comparator 与 B1+B2。当前均为代码就绪、结果未就绪状态。

Phase20 之前的 Git-safe 源码、配置与聚合结论固定在 GitHub 分支
`codex/archive-v2-history-before-phase20`（提交 `6f471d93421b743fed446b650d7e2fd5f71ef24d`）。
旧 checkpoint、患者级预测、缓存和运行副本已按用户授权清理，不属于可迁移论文
材料，也不得恢复到 Git。

## 从哪里开始

1. [证据状态总览](00_证据状态总览_CN.md)：哪些已完成、哪些仍缺失。
2. [论文叙事与摘要骨架](01_论文叙事与摘要骨架_CN.md)：主线、贡献和安全措辞。
3. [Information Fusion 方法](02_Information_Fusion方法_CN.md)：可直接改写进 Methods。
4. [主结果与消融表](03_主结果与消融_CN.md)：论文主表和核心结论。
5. [PRIOR 压力测试](04_PRIOR压力测试_CN.md)：模态干预与机制解释。
6. [统计与报告协议](05_统计与报告协议_CN.md)：Seed、bootstrap、CI 和多重比较。
7. [讨论与局限](06_讨论与局限_CN.md)：可直接改写进 Discussion。
8. [后续实验路线图](07_后续实验路线图_CN.md)：校准、效率、外部评估等缺口。
9. [表格与配图规划](08_表格与配图规划_CN.md)：每张表/图的数据就绪状态。
10. [校准与选择性预测](09_校准与选择性预测_CN.md)：五折温度缩放、风险覆盖与转诊模拟。
11. [效率与部署](10_效率与部署_CN.md)：固定 A800 的参数量、FLOPs、延迟、吞吐和缓存。
12. [比较器可信性与亚组](11_比较器可信性效率与亚组_CN.md)：四个比较器的三 Seed 校准、同卡效率与描述性亚组。
13. [PRTA-CXR-Slim 最小矩阵最终结果](12_PRTA-CXR-Slim最小矩阵结果_CN.md)：
    Train-only 三 Seed 正式精简判定、冻结规则与收口凭据。
14. [Slim-S1 最终主线与重跑矩阵](13_PRTA-CXR-Slim-S1最终主线与重跑矩阵_CN.md)：
    最终配置、继承/重跑/重推理边界与 Phase20 进度。

## 数据附录

- [逐 Seed 结果](data/01_逐Seed结果.md)
- [完整 paired-bootstrap 结果](data/02_Paired_Bootstrap完整结果.md)
- [完整 PRIOR 干预聚合](data/03_PRIOR干预完整结果.md)
- [不可变证据来源与 SHA256](data/04_证据来源与哈希.md)
- [校准与选择性预测完整结果](data/05_校准选择性预测完整结果.md)
- [效率完整结果](data/06_效率完整结果.md)
- [论文材料清单与 SHA256](data/07_论文材料清单与哈希.md)
- [Phase 15 比较器证据汇总](data/08_Phase15比较器证据汇总.md)
- [PRTA-CXR-Slim 最终公共结果 JSON](data/09_PRTA-CXR-Slim最终结果.json)

## 当前结论边界

- 33 个 Information Fusion 训练单元、33 个四条件诊断导出和 10,000 次患者级
  paired bootstrap 已完成。
- 冻结投稿主方法为 Slim-S1；V2 保留为历史开发父方法，不重新选择 best seed。
- 现有证据支持 finding-conditioned visual query 与 temporal relation residual
  是关键组件；其他模块的独立效应较小或不确定。
- V2 与 B401/TILA8/F01/F02 的三 Seed Dev 校准、选择性预测、描述性亚组和固定
  A800 效率均已完成；自动化结果不等于临床验证。
- PRTA-CXR-Slim 的 4 Arms × 3 Seeds 已由服务器正式 finalizer 收口并选择
  `Slim-S1`；该 Train-only 选择现用于锁定最终主线，但不等同于 full-Train、
  external 或临床验证结果。
- 外部/跨源评估、正式官方纵向基线、source-held-out、grounding、data scaling
  和 label-noise 尚未完成；医生人工/reader study 已明确取消。

## 迁移说明

整个 `paper/` 可以复制到另一台电脑。Markdown 内不依赖本机绝对路径；本机
运行时证据的原始路径与哈希只记录在
[证据来源与哈希](data/04_证据来源与哈希.md) 中，便于将来核验。
