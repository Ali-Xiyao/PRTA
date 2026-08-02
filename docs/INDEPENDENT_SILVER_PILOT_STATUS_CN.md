# PRTA-CXR 独立交集 Silver Pilot 状态

日期：2026-08-02

状态：`PILOT_PASS__FULL_LABELING_HOLD__TRAINING_HOLD`

后续更新：同一150条已经完成 Sol 盲审。明确五类 Luna–Sol 一致率为
115/124（92.74%），30条规则–Luna分歧中Sol支持Luna 21条、支持规则4条。
这支持考虑 Luna-primary，但尚未得到切换政策或全量运行授权。详见
[Sol 盲审状态](SOL_BLIND_REVIEW_STATUS_CN.md)。

## 结论

新简化方案已经在与历史严格 pilot 完全相同的 150 条样本上跑通。AI 外发请求
不含规则候选标签，只含短批次别名、目标 finding、PRIOR 报告和 CURRENT 报告；
AI 每条只输出 `sample_id + ai_label`，没有理由、置信度或证据引用。

150 条全部通过 schema 和精确 ID 门，8 个批次无失败、无重试。规则与 AI
非 `Unclear` 完全一致的 103 条进入 pilot Silver（68.67%）；30 条 mismatch 和
17 条 `Unclear` 已进入独立 exclusion 清单，没有人工修补。

该结果证明新流程在当前 pilot 上工程可运行，但不证明 103 个标签必然正确，
也不构成全量标注、split、cache、训练或论文使用授权。

## 冻结协议

1. 规则程序在本地生成候选五类标签。
2. AI 看不到规则标签、患者 ID、原始 sample hash 和 alias 映射。
3. AI 只读 finding 与前后报告，输出：
   `Improved/Worse/New/Resolved/Stable/Unclear`。
4. 本地精确比较：非 `Unclear` 且与规则完全一致才进入 Silver。
5. mismatch 或 `Unclear` 直接排除，不进行第二次自动裁决。
6. 全量完成后按 `source × 五类 Silver` 抽取 200–300 条人工复核。
7. 人工准确率收据完成前，正式训练与论文使用均 fail-closed。

## Pilot 构成

| 项目 | 数值 |
|---|---:|
| 样本 / 唯一患者 | 150 / 150 |
| MIMIC-CXR-JPG | 75 |
| CheXpert Plus | 75 |
| Calendar / ordinal | 75 / 75 |
| Improved / New / Resolved / Stable / Worse | 33 / 30 / 27 / 30 / 30 |
| Pilot canonical SHA-256 | `c7a44d86c5f160e3f4d667557b3956a2016517ad64154421be29fc2b807858f9` |

该 hash 与历史严格 v6 的 150 条 pilot 相同，因此两种工作流的工程行为可在同一
抽样上比较；历史严格输出没有被覆盖或作为新 Silver 输入。

## 结果

### 总体

| 状态 | 数量 | 比例 |
|---|---:|---:|
| Silver exact agreement | 103 | 68.67% |
| Excluded mismatch | 30 | 20.00% |
| Excluded Unclear | 17 | 11.33% |
| 合计 | 150 | 100.00% |

### 分来源

| Source | Rows | Silver | Mismatch | Unclear | Silver rate |
|---|---:|---:|---:|---:|---:|
| MIMIC-CXR-JPG | 75 | 52 | 13 | 10 | 69.33% |
| CheXpert Plus | 75 | 51 | 17 | 7 | 68.00% |

不得用总体 68.67% 取代上述两项来源结果。当前两来源 pilot 保留率接近，但正式
全量仍必须分别统计，并由人工抽检分别估计准确率。

### 分规则候选标签

| Rule label | Rows | Silver | Mismatch | Unclear | Silver rate |
|---|---:|---:|---:|---:|---:|
| Improved | 33 | 23 | 5 | 5 | 69.70% |
| New | 30 | 21 | 7 | 2 | 70.00% |
| Resolved | 27 | 20 | 4 | 3 | 74.07% |
| Stable | 30 | 22 | 2 | 6 | 73.33% |
| Worse | 30 | 17 | 12 | 1 | 56.67% |

`Worse` 的 pilot 保留率最低，是全量后人工分层抽检与误差分析的重点；不能在
没有人工准确率证据的情况下通过 prompt 调参追求更高自动一致率。

## 工程表现

| 指标 | 结果 |
|---|---:|
| 结构合法 / ID 完整 | 150/150 |
| 批次成功 | 8/8 |
| 失败输出 | 0 |
| 重试 | 0 |
| 总外部调用时间 | 344.991 秒 |
| 平均批次时间 | 43.124 秒 |
| 顺序吞吐 | 0.435 rows/s |
| 148,798 条顺序线性外推 | 约 95.1 小时 / 4.0 天 |

线性外推只用于资源规划，不代表额度、并发稳定性或全量科学质量已经验证。

## 权威文件与产物

仓库内：

- `configs/labeling/independent_silver_v1.json`
- `prompts/independent_silver_label_v1.md`
- `schemas/independent_silver_label_batch.schema.json`
- `src/prta_cxr/independent_silver.py`
- `src/prta_cxr/cli_independent_silver.py`

本地运行根：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\independent_silver_v1`

关键产物：

- `pilot_prepare_receipt.json`
- `pilot_run_receipt.json`
- `pilot_merge_audit.json`
- `pilot_silver_accepted.jsonl`
- `pilot_silver_excluded.jsonl`

Pilot Silver manifest SHA-256：

`e4be33b5e2ee9d01f5ae227d01b4fe816972f65b09ec65ccce9d1f409ab655c2`

## 当前门禁

- 新协议 pilot：`PASS`
- 全量 148,798 条独立 AI 标注：`HOLD`，配置中
  `full_execution_enabled=false`
- 人工 200–300 条准确率抽检：`HOLD_NOT_STARTED`
- 新 patient-disjoint split：`HOLD`
- 图像/文本 cache：`HOLD`
- GPU 训练：`HOLD`
- Internal-test / Gold / external confirmation：`CLOSED`

下一次若授权全量标注，应先冻结并发、额度、失败重试和运行目录，再保持同一
prompt/schema 完成全量。全量完成后先生成固定分层人工审核 roster；只有有效的
人工准确率收据通过代码门，正式训练入口才可继续。
