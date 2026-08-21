# PRTA-CXR 论文材料工作区

本目录保存可迁移、可审计的论文写作材料。当前内容只使用冻结的 Train/Dev 聚合
证据与任务语义一致的 MIMIC-CXR/CheXpert Plus 跨来源评估，不包含患者级预测、
影像、报告、checkpoint、账号信息或任何受保护测试集结果。

原始安全约束继续有效：只有通过注册冻结、一次性正式评估和不可变凭据校验的
结果才能进入论文表格；尚未完成的可靠性、跨数据来源泛化或临床价值只能写成计划或
假设，不能提前写成已观察结论。

最终投稿主方法已于 2026-08-18 锁定为 `PRTA-CXR-Slim / Slim-S1`。现有 V2
材料保留为历史开发证据。full Train / official Dev 的 Phase20-A 已以 88/88
唯一 PASS 收口；其 21 组训练和 2 组 source-held 三 Seed汇总现可进入论文材料。
comparator 当前已有严格校验的 14/24 阶段性快照，其中 4/8 方法齐全三 Seed；
最终比较结论与 S1 专属可信性仍须等待各自 finalizer。

旧私有 checkpoint 清理后，V2/S0/B401/B402/TILA8 与三项纵向内部/论文复现比较器
需要按 Phase20 输入合同重建 8×3 单元，才能生成患者级 paired/safety 证据；相关
代码已完成且四条独立队列已按各自冻结门执行。阶段性结果只包含 terminal PASS，
最终汇总仍由严格 24/24 comparator finalizer 门控。

Phase20 证据链拆为 Phase B/B1（6 个 focused trustworthiness jobs）与 B2（27 个
比较器概率导出 + 1 个 patient-cluster/Holm/safety/disagreement 统计 job）。Phase C
只保存 11 个现有可选 job 的非 runnable 目录及 4 类后置扩展，不进入完成门。三层
finalizer 分别对账 Phase20-A、24-cell comparator 与 B1+B2。Phase20-A finalizer
已经 PASS；后两层仍等待当前 GPU 队列和后续证据任务。

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
8. [后续实验路线图](07_后续实验路线图_CN.md)：校准、效率、跨来源泛化等缺口。
9. [表格与配图规划](08_表格与配图规划_CN.md)：每张表/图的数据就绪状态。
10. [校准与选择性预测](09_校准与选择性预测_CN.md)：五折温度缩放、风险覆盖与转诊模拟。
11. [效率与部署](10_效率与部署_CN.md)：固定 A800 的参数量、FLOPs、延迟、吞吐和缓存。
12. [比较器可信性与亚组](11_比较器可信性效率与亚组_CN.md)：四个比较器的三 Seed 校准、同卡效率与描述性亚组。
13. [PRTA-CXR-Slim 最小矩阵最终结果](12_PRTA-CXR-Slim最小矩阵结果_CN.md)：
    Train-only 三 Seed 正式精简判定、冻结规则与收口凭据。
14. [Slim-S1 最终主线与重跑矩阵](13_PRTA-CXR-Slim-S1最终主线与重跑矩阵_CN.md)：
    最终配置、继承/重跑/重推理边界与 Phase20 进度。
15. [Phase20 中期结果](14_Phase20阶段结果中期汇总_CN.md)：
    已齐全三 Seed主结果、结构消融、数据规模曲线与跨来源评估门控。
16. [Phase20-A 正式收口与三 Seed 汇总](15_Phase20-A正式收口与三Seed汇总_CN.md)：
    88/88 核验、21 组训练汇总及 2 组双向 source-held 聚合。
17. [Phase20 comparator 阶段性结果](16_Phase20-comparator阶段性结果_CN.md)：
    14/24 terminal PASS 快照、完整三 Seed方法与明确待跑单元。
18. [论文实验数据总表与待跑清单](17_论文实验数据总表与待跑清单_CN.md)：
    当前可写结果、数据协议、B1/B2 空表状态与论文叙事统一入口。

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
- [Phase20-A 三 Seed 正式聚合 JSON](data/12_Phase20-A三Seed正式聚合.json)
- [Phase20 comparator 阶段性聚合 JSON](data/13_Phase20-comparator阶段性聚合.json)

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
- Phase20-A 已核验 88/88 唯一 PASS，并形成 21 组训练与 2 组双向
  MIMIC-CXR/CheXpert Plus source-held 三 Seed正式聚合。后者只能称为 cross-source
  domain generalization，不能称为独立外部临床验证。24-cell comparator 当前为
  14 PASS、4 RUNNING、6 PENDING；B1/B2 可信性链和各自 finalizer 尚未完成；
  医生人工/reader study 已明确取消。

## 迁移说明

整个 `paper/` 可以复制到另一台电脑。Markdown 内不依赖本机绝对路径；
[证据来源与哈希](data/04_证据来源与哈希.md) 仅登记产物角色与 SHA256，
不公开本机或服务器运行目录。
