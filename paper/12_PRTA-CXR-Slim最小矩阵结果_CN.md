# PRTA-CXR-Slim 最小矩阵最终结果

## 证据状态

状态：`PASS_SLIM_MATRIX_SELECTED`

服务器正式 finalizer 已于 2026-08-18 收口。冻结矩阵的 4 Arms × 3 Seeds
共 12 个唯一训练单元全部通过配置、输入、回执与队列校验；Seeds 17/28 来自
A800，预注册的 Seed43 来自 RTX3090。服务器重复或中断的 Seed43 副本已隔离，
没有进入汇总、增加样本量或替换权威单元。

所有结果只来自原 Train 患者派生的 patient-disjoint 选择面；原 Dev、
Internal-test、Gold、外部测试及患者级输出均未打开。

## 冻结矩阵

| Arm | Prototype CE | State anchor | 可选模块数 |
|---|---:|---:|---:|
| Slim-S0 | 开 | 开 | 2 |
| Slim-S1 | 关 | 开 | 1 |
| Slim-S2 | 开 | 关 | 1 |
| Slim-S3 | 关 | 关 | 0 |

finding conditioning、cross-time attention、temporal relation residual、ODC 和
matched-hard CMCP 全部固定开启，DMW 固定关闭。除上述两个二元因素外，没有根据
结果改变结构、损失权重、Seed、数据或容差。

## 三 Seed 正式结果

| Arm | Macro-F1 ↑ | ODER ↓ | Min class recall ↑ | 冻结规则 |
|---|---:|---:|---:|---|
| Slim-S0 | 0.562879 ± 0.003051 | 0.006445 ± 0.000095 | 0.472719 ± 0.006455 | admissible |
| Slim-S1 | 0.560520 ± 0.001253 | 0.006880 ± 0.000578 | 0.475585 ± 0.003966 | admissible |
| Slim-S2 | 0.562299 ± 0.002738 | 0.006383 ± 0.000475 | 0.481087 ± 0.006852 | recall gate failed |
| Slim-S3 | 0.561058 ± 0.002174 | 0.006859 ± 0.000251 | 0.476043 ± 0.008647 | recall gate failed |

表中为 Seeds 17/28/43 的 mean ± sample SD。ODER 越低越好。未报告 best seed，
也未把重复运行加入样本量。完整逐 Seed 数值与机器可读状态见
[最终公共结果 JSON](data/09_PRTA-CXR-Slim最终结果.json)。

## 冻结选择结论

运行前冻结的 admissibility 条件为：

- Macro-F1 距四个 Arms 中最佳均值不超过 0.003；
- ODER 距最低均值不超过 0.0005；
- 每一类别 recall 距该类别最佳均值不超过 0.01；
- 多个 Arms 合格时，选择可选模块最少者，再按 Arm ID 决胜。

`Slim-S0` 与 `Slim-S1` 通过全部门；`Slim-S2` 和 `Slim-S3` 未通过逐类别
recall 门。因此正式冻结规则选择：

> `Slim-S1`：删除独立 Prototype CE，保留 State anchor。

相对 Slim-S0，Slim-S1 的 Macro-F1 均值下降 0.002359，仍在 0.003 容差内。
Slim-S1 的 ODER 相对全矩阵最低值高 0.000497，位于 0.0005 门内但接近边界。
论文应完整报告数值和容差，不写成笼统的“性能不变”。

机制上，删除 State anchor 的 S2/S3 均未通过逐类别召回门，而只删除
Prototype CE 的 S1 仍合格；当前证据支持在后续 Slim 候选中保留 State anchor，
移除独立 Prototype CE。历史 Full V2 与全部既有消融结果继续保留，本矩阵不覆盖
或删除旧证据。

## 正式收口与可审计性

- offload reconciliation：`PASS_SLIM_OFFLOAD_RECONCILED`；
- 原始服务器 lane completion：A800-3066 为 7/7 PASS，A800-9929 为 6/6 PASS；
- finalizer：`PASS_SLIM_MATRIX_SELECTED`；
- 正式 final JSON SHA-256：`2fc88e884c01cdc247a0815b90ea007f6c0dd5167e110e94cb1161be4539e47d`；
- reconciliation SHA-256：`33cb928ca4a35257b3a3e6fc6ac848e5c0bf6c2edb07601291111becb80c187d`；
- finalizer module SHA-256：`4af1f9226eeabbe6b6687cf235a3c7ff18fb4f9e75fe2fda1143b8fd048c911e`；
- Internal-test、Gold、external 与 protected outcome 读取次数均为 0。

上述哈希标识服务器原始凭据；GitHub 仅保存不含患者数据、checkpoint、私有路径
或账号信息的公共聚合副本。Slim-S1 是 Train-only 开发选择面上的最终精简候选，
不是外部验证或临床验证后的最终模型。
