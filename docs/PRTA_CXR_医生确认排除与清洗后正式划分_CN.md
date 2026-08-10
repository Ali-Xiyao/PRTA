# PRTA-CXR 医生确认排除与清洗后正式划分

> **当前执行补充（2026-08-10）**：本文件第3节的 13,219 例 Internal-test 是第一阶段医生清洗冻结时的历史数量。用户随后确认进一步医生复核后的 12,219 例为论文正式 Internal-test；13,219 例只保留为复核前数据质量基线。后续新增实验不得再使用任一 Internal-test 或 Gold 做选择或调参。所有可训练基线和消融统一使用清洗后 Train 80,402 / Dev 11,201，权威 Train/Dev manifest SHA-256 为 `45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89`。

## 1. 最终数据决策

医生已经复核全量 `11,667` 条全局 Top-10% 风险候选，并确认这些样本不应继续用于本项目。它们不再是“待复核”状态，统一冻结为：

- `review_status = PHYSICIAN_CONFIRMED_EXCLUDE`
- `physician_decision = DO_NOT_USE`
- `cleaned_split_action = EXCLUDED_FROM_ALL_FUTURE_TRAIN_DEV_TEST_GOLD`

Luna、Sol、历史多种子误判、高 NLL、方向相反错误和近似 TracIn 只负责发现候选；医生对全部候选的复核决定是最终排除依据。

## 2. 隔离方式

不移动、不删除原始影像，也不原地修改历史 manifest。全部排除病例的完整内部记录放在私有隔离目录：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\formal_cleaned_split_v1_1\quarantine`

其中：

- `physician_confirmed_exclusions_v1.jsonl`：全量 11,667 条内部审计记录；
- `physician_confirmed_exclusions_v1.csv`：便于内部检查的索引表；
- `README_CN.md`：明确禁止训练、验证、Internal-test、Gold 及其他模型实验使用。

隔离区只用于私有追溯和审计，不得提交公开 Git。

## 3. 清洗后冻结划分

Top 3%、Top 5% 与 Top 10% 是严格嵌套集合，因此最终排除的是 Top-10% 并集 11,667 条，而不是三个集合相加。

| Split | 清洗前 active | 医生确认排除 | 清洗后冻结 |
|---|---:|---:|---:|
| Train | 89,406 | 9,004 | 80,402 |
| Dev | 13,420 | 2,219 | 11,201 |
| Internal-test | 13,588 | 369 | 13,219 |
| Gold | 250 | 75 | 175 |
| 合计 | 116,664 | 11,667 | 104,997 |

在本次医生排除之前，上游自动标签流水线已经按“明确五分类才保留”的约定完成不确定样本筛除：Luna-primary 候选 148,798 条中 22,071 条 `Unclear` 未进入 silver；后续 Sol 权威版本又从 Train 排除 1,365 条 `Unclear`、从 Dev 排除 3,246 条、从 Internal-test 排除 3,111 条。上述数字属于版本演化链路，不能与本次 11,667 条医生排除简单相加或解释为同一批病例。Gold 的医生共识标签没有被 Sol 自动覆盖。

清洗后正式 manifest 位于：

- `manifests/train_dev_cleaned_v1.jsonl`
- `manifests/internal_test_cleaned_v1.jsonl`
- `manifests/gold_cleaned_v1.jsonl`

活动指针：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\active_cleaned_split.json`

冻结回执：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\formal_cleaned_split_v1_1\cleaned_split_freeze_receipt.json`

冻结回执 SHA-256：

`aa761c13ae74f29f7c30bc0fecb23db20eab02d79a52778dbbeddec9563cd069`

活动指针 SHA-256：

`770e119c6d415af2cf5c9e4b8ab67b4d4efcd0a1caecc99312d93cf5d4787da3`

## 4. 强制使用约束

后续正式训练、开发队列、协议冻结和 Internal-test 评价必须显式传入 `--cleaned-split-freeze`，且 manifest 的绝对路径与 SHA-256 必须和冻结回执一致。以下行为一律 fail closed：

- 使用清洗前 Train/Dev manifest；
- 使用清洗前 Internal-test 或 Gold；
- 使用内容相同但未登记的 manifest 副本；
- 修改任一清洗后 manifest；
- 让任何医生确认排除 ID 重新进入四个划分。

独立审计确认：104,997 条 active 样本与 11,667 条医生排除样本的 ID 交集为 0；四个划分之间患者交集全部为 0；每个划分均保留五类标签支持；保留行与来源逐字节一致。

## 5. 论文与统计边界

这次排除属于医生确认的数据清洗，但候选发现使用过 Sol 冲突/Unclear、历史模型错误、NLL 和近似 TracIn。因此清洗后的 Internal-test 与 Gold 是 outcome-adaptive curated evaluation sets，不能被描述为原始临床分布上的无偏泛化估计。

后续论文可报告“医生确认排除后的冻结清洗队列”结果，但必须同时披露筛选来源与选择偏倚。旧正式开发门 `STOP_DEVELOPMENT_GATE` 仍是历史事实，不能由本次清洗追溯性改写。
