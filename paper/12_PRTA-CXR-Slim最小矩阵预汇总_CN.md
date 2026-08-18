# PRTA-CXR-Slim 最小矩阵预汇总

## 证据状态

状态：`PRELIMINARY_COMPLETE_PENDING_SERVER_FINALIZER`

本文件汇总已完成的 4 Arms × 3 Seeds 唯一训练单元。它使用冻结执行分工：Seeds
17/28 来自 A800，Seed43 来自 RTX3090；服务器意外重复产生的 Seed43 运行不参与
选择。当前数值已足够执行预注册规则，但正式服务器 lane completion、导入回执和
`slim_matrix_final.json` 尚未收口，因此本文件不能替代最终不可变结果。

所有结果只来自原 Train 患者派生的 patient-disjoint 选择面；未打开原 Dev、
Internal-test、Gold、外部测试或患者级输出。

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

## 三 Seed 结果

| Arm | Macro-F1 ↑ | ODER ↓ | Min class recall ↑ | 冻结规则 |
|---|---:|---:|---:|---|
| Slim-S0 | 0.562879 ± 0.003051 | 0.006445 ± 0.000095 | 0.472719 ± 0.006455 | admissible |
| Slim-S1 | 0.560520 ± 0.001253 | 0.006880 ± 0.000578 | 0.475585 ± 0.003966 | admissible |
| Slim-S2 | 0.562299 ± 0.002738 | 0.006383 ± 0.000475 | 0.481087 ± 0.006852 | recall gate failed |
| Slim-S3 | 0.561058 ± 0.002174 | 0.006859 ± 0.000251 | 0.476043 ± 0.008647 | recall gate failed |

表中为三 Seed mean ± sample SD。ODER 越低越好。未报告 best seed，也未把重复运行
加入样本量。

## 冻结选择规则与预判定

运行前冻结的 admissibility 条件为：

- Macro-F1 距四个 Arms 中最佳均值不超过 0.003；
- ODER 距最低均值不超过 0.0005；
- 每一类别 recall 距该类别最佳均值不超过 0.01；
- 多个 Arms 合格时，选择可选模块最少者。

`Slim-S0` 与 `Slim-S1` 通过全部门；`Slim-S2` 和 `Slim-S3` 未通过类别 recall
门。因而预注册规则预选择：

> `Slim-S1`：删除独立 Prototype CE，保留 State anchor。

相对 Slim-S0，Slim-S1 的 Macro-F1 均值下降 0.002359，仍在 0.003 容差内。
Slim-S1 的 ODER 相对全矩阵最低值高 0.000497，刚好位于 0.0005 门内。因此该精简
判定有效但接近 ODER 边界，论文应同时报告完整数值，不能只写“性能不变”。

机制解释上，删除 State anchor 的 S2/S3 均未通过逐类别召回门，而只删除
Prototype CE 的 S1 仍合格；当前证据支持保留 State anchor，并把独立 Prototype
CE 从最终精简候选中移除。

## 重复运行与正式收口边界

- 冻结的权威 Seed43 来源是本地 RTX3090 block；服务器重复 Seed43 不参与汇总。
- 已完成的重复结果保留作审计，不用于增加 Seed 数、挑选更好结果或替换权威单元。
- 尚需把四个权威 Seed43 回执导入服务器，生成原始 queue-hash lane completion，
  运行正式 Slim finalizer，再用最终不可变 JSON/Markdown 替换本文件的“预汇总”状态。
- 正式收口前，不据此访问受保护测试集，也不把 Slim-S1 称为独立验证后的最终模型。
