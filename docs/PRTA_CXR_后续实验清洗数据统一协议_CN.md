# PRTA-CXR 后续实验清洗数据统一协议

> 生效日期：2026-08-10
> 适用范围：后续基线、组件消融、效率测试、鲁棒性分析及任何重新训练任务。
> 核心要求：所有可训练实验只能使用医生清洗后冻结的 Train/Dev 数据面。

## 1. 唯一允许的训练与开发数据

后续实验统一使用：

| Split | 冻结行数 | 用途 |
|---|---:|---|
| Train | 80,402 | 参数更新 |
| Dev | 11,201 | 早停、最佳 checkpoint 选择和实验比较 |

权威 Train/Dev manifest：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\formal_cleaned_split_v1_1\manifests\train_dev_cleaned_v1.jsonl`

manifest SHA-256：

`45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89`

清洗冻结回执 SHA-256：

`aa761c13ae74f29f7c30bc0fecb23db20eab02d79a52778dbbeddec9563cd069`

任何实验只要行数、manifest 路径、manifest SHA、清洗冻结回执或排除集审计不一致，必须在训练前 fail closed。

## 2. Wave033 适配器层范围消融的数据身份

Wave033 的 Tail4、Tail6、Tail8 × Seeds17/28/43 九格条件消融已经在上述医生清洗后 Train 80,402 / Dev 11,201 数据面完成，不需要因为数据清洗问题重新运行。

九个格子保持相同的 Train/Dev 行、标签版本、H0、rank32、EMA0.999、DMW0.01、直接反方向代价0.05、state辅助0.025、恒定学习率、优化器、batch、epoch预算和早停规则。唯一的条件差异是适配器范围及其实现所要求的缓存入口：

- Tail4：Block-8 缓存；
- Tail6：Block-4 缓存；
- Tail8：Block-4 缓存。

Block-8 与 Block-4 是同一清洗后 Train/Dev 行集合的不同无标签特征入口，不代表使用了不同病例队列。Wave033 九格终态 SHA-256：

`606e10c0168bd662fee07999f40e8d9c32134d039c049a5b992fea626d6f221d`

因此，Wave033 的 tail4/tail6/tail8 直接复用，不再重复训练。为补齐更完整的
层范围曲线，后续矩阵扩展为 no-tail/tail2/tail4/tail6/tail8/tail10：

| Scope | Adapter定义 | 缓存入口 | 处理方式 |
|---|---|---:|---|
| no-tail | 无视觉bottleneck adapter，保留相同冻结视觉尾部和PRTA时序头 | Block-8 | 新运行 |
| tail2 | 最后2个Block插入adapter | Block-8 | 新运行 |
| tail4 | 最后4个Block插入adapter | Block-8 | 复用Wave033 |
| tail6 | 最后6个Block插入adapter | Block-4 | 复用Wave033 |
| tail8 | 最后8个Block插入adapter | Block-4 | 复用Wave033 |
| tail10 | 最后10个Block插入adapter | Block-2 | 新建缓存后新运行 |

no-tail/tail2/tail10 × Seeds17/28/43 共九个新增格子必须在结果揭示前整体
冻结。旧 `last2` 只提供实现语义参考；除非其数据、源代码、配置和预算完全
等同于当前矩阵，否则不复用其历史指标。

## 3. 后续组件消融的数据规则

后续 Tail8 组件消融必须：

1. 固定 Tail8、Block-4、rank32、EMA0.999、Seeds17/28/43；
2. 固定上述 Train 80,402 / Dev 11,201 manifest；
3. 每个格子只改变预先登记的目标组件；
4. 在任何终态结果揭示前冻结完整消融矩阵，不因中间结果删格、加格或改顺序；
5. 只使用 Dev 形成消融结论，Macro-F1 为主要指标，ODER 仅作描述；
6. 不打开、不推理、不重新计算 Internal-test 或 Gold；
7. 只有与本协议的 manifest、数据计数、标签版本、配置和预算完全一致的历史运行才允许复用，否则必须视为不同实验。

当前拟定组件矩阵：

| 配置 | 唯一变化 |
|---|---|
| Full Tail8 | 复用冻结的完整方法 |
| w/o DMW | DMW `0.01 -> 0` |
| w/o Direct Cost | 直接反方向代价 `0.05 -> 0` |
| w/o State Auxiliary | state辅助 `0.025 -> 0` |
| Classification-only | DMW、Direct Cost、State Auxiliary 全部关闭 |

正式启动前还需要对历史运行做只读身份审计，以确定哪些格子可以合法复用。

## 4. 禁止使用的数据面

以下数据不得进入任何后续训练、开发、基线或消融：

- 清洗前 Train/Dev manifest；
- 任意历史调试、小样本或旧标签 manifest；
- 医生确认排除或隔离区中的样本；
- Internal-test、Gold 及其标签、预测错误或病例清单；
- 内容看似相同但没有被清洗冻结回执和 SHA 注册的 manifest 副本。

正式 Internal-test 12,219 例和 Gold 175 例均已完成最终评估并封存。它们不能用于后续方法选择、消融、超参数调整或新增基线设计。

## 5. 每次实验必须记录的审计字段

每个新运行至少记录：

- Train/Dev manifest 绝对路径、SHA-256 和行数；
- cleaned-split freeze receipt 路径和 SHA-256；
- 医生排除 ID 交集必须为 0；
- Train/Dev 患者交集必须为 0；
- 源代码、配置、缓存、模型权重和 launcher SHA-256；
- Seed、训练预算、最佳 checkpoint、终态指标；
- Internal-test/Gold/protected outcome 读取计数必须为 0。

缺少任一强制身份字段时，不得把结果纳入论文正式基线或消融表。

## 6. Wave041 完整消融冻结（2026-08-10）

后续完整消融已冻结为固定队列，统一使用医生最终清洗后的 Train 80,402 / Dev 11,201，禁止读取 Internal-test 或 Gold。新增训练共 30 格，使用 Seeds 17/28/43：

- 范围新增：no-tail、tail2、tail10；已有 tail4、tail6、tail8 复用 Wave033 的九格终态证据。
- Tail8 单组件删除：w/o Finding Conditioning、w/o Cross-time Alignment、w/o Dual Branch、w/o Direction Margin、w/o Opposite-direction Cost、w/o State Preservation，以及 Classification-only。
- 最终 Full 配置中的 semantic-alignment loss、CMCP loss、temporal-inversion loss 本来就是 0；相应删除项属于恒等对照，标记 `N/A_FINAL_METHOD_ALREADY_DISABLED`，不得伪装成新的训练结果。

固定队列包含 15 个双卡阶段，不因任何中间或终态结果删格、改序、调参或追加探索。Wave041 冻结回执 SHA-256 为 `af802481cd5da93f8564f59942cfa1a35a412e2e1fb7a86373d41ea304567ce7`，控制器 SHA-256 为 `c230a772b70ea399995aeb2b40d383d16d2805b192ae0ffb3dae4eeea9b37be8`。
