# PRTA-CXR Dev / Internal-test / Gold 标签质量复核摘要

## 状态与边界

- 状态：`PASS_READ_ONLY_PROTECTED_LABEL_QUALITY_AUDIT`
- 复核模型：`gpt-5.6-sol`
- 推理强度：`medium`
- 全量覆盖：Dev 16,666、Internal-test 16,699、Gold 250，共 33,615 条。
- Sol 输入仅包含批内短 alias、finding、PRIOR 报告和 CURRENT 报告；现有 Luna 标签、Gold 医生标签、患者标识、日期、路径、模型预测和 TracIn 风险均未外发。
- 本任务未修改标签、删除样本、调整划分、训练模型或计算改标后指标。
- 本次受控复核终止了此前 Internal-test/Gold 标签从未打开的历史封存状态，后续论文和科学记录必须如实披露该访问。

## 总体结果

| 队列 | 总数 | Sol明确判断 | 明确一致 | 明确分歧 | 明确一致率 | Sol Unclear | 质量标志 | Cohen's κ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dev | 16,666 | 13,420 | 12,073 | 1,347 | 89.96% | 3,246 | 3,686 | 0.8504 |
| Internal-test | 16,699 | 13,588 | 12,155 | 1,433 | 89.45% | 3,111 | 3,480 | 0.8434 |
| Gold（医生共识） | 250 | 201 | 175 | 26 | 87.06% | 49 | 49 | 0.8378 |

- “Sol 分歧 / Sol Unclear / 任一质量标志”的去重并集为 9,984 条。
- Dev 中 TracIn 为 Tier A/B/C、但 Sol 仍明确同意当前标签的困难样本为 4,772 条；这些样本不应仅因模型风险高而视为错标。
- Gold 的 201 条 Sol 明确判断中，Sol 与医生共识一致 175 条（87.06%），与原 Luna 标签一致 178 条（88.56%）。原 Luna 与医生共识在 250 条中一致 246 条（98.40%）。这说明本轮少量分歧不能直接归因于某一方必然错标。

## 主要质量信号

| 质量标志 | 数量 |
|---|---:|
| 配对异常 `PAIRING_ABNORMAL` | 3,772 |
| 时间方向含糊 `TEMPORAL_DIRECTION_AMBIGUOUS` | 3,388 |
| finding 无法判断 `FINDING_NOT_JUDGEABLE` | 2,371 |
| 报告不足 `REPORT_INSUFFICIENT` | 1,964 |
| 否定/不确定性冲突 `NEGATION_OR_UNCERTAINTY_CONFLICT` | 1,215 |

同一病例可以触发多个质量标志，因此上述数量不能相加作为唯一病例数。

## 系统性混淆

- `New` 是三个队列中一致率最低的当前标签：Dev 76.98%、Internal-test 77.12%、Gold 74.29%。其主要混淆方向为 `New → Worse`、`New → Stable`，同时伴随较多 `Unclear`。
- Dev 来源间决定性一致率接近：CheXpert Plus 90.35%，MIMIC-CXR-JPG 89.53%。
- Internal-test 来源间同样接近：CheXpert Plus 89.75%，MIMIC-CXR-JPG 89.12%。
- Gold 中 CheXpert Plus 为 89.53%，MIMIC-CXR-JPG 为 85.22%；Gold 每来源仅 125 条，应避免对该差异作过强结论。
- finding 层面，`Pleural Other`、`Enlarged Cardiomediastinum` 等类别的 κ 较低或不稳定，需结合样本量和高 `Unclear` 比例解释。

## 私有逐样本交付物

所有逐样本 ID、报告、路径和分数均位于 Git 外：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\poststop_audits\protected_label_quality_v2\private\analysis`

- `all_review_results.jsonl`：全部 33,615 条。
- `all_flagged_for_review.csv`：全部 9,984 条需关注记录。
- `dev_high_risk_sol_agrees.csv`：4,772 条 Dev 困难但标签获 Sol 支持的记录。
- `aggregate_summary.json`：完整分层统计和混淆矩阵。
- `PRTA_CXR_受保护标签质量复核.md`：私有结果索引。

最终只读回执位于：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\poststop_audits\protected_label_quality_v2\final_audit_receipt.json`

输入在复核前后的 SHA-256 完全一致，标签修改数为 0。

## 后续授权动作

在本只读复核完成后，用户另行明确授权以 Sol 替换此前 Luna-derived 数据。
Dev 和 Internal-test 已生成新的 Sol-authoritative 版本：五分类直接替换，
`Unclear` 排除；医生 Gold 保持不变。详见
[Sol 权威标签替换状态](PRTA_CXR_Sol权威标签替换状态_CN.md)。本节不改变上文
对“只读复核阶段”的历史描述。

Git-safe 完整性哈希：

- `final_audit_receipt.json`：`8614bd6bb64e777425aa254e38f8d674fe0b3acd4ae2b92bfead4b04b204bf4c`
- `aggregate_summary.json`：`75cd95ecacd1f51dfbc3b2847964a236ddd5b822fa4596f7c954a3341bfa3f58`
- `all_review_results.jsonl`：`b93a07ac4f57473736cdc7cc2205cbcf48b71459d0ec713b9940ac2329cde37c`
- `all_flagged_for_review.csv`：`9ff37d8bb498d5ff986f938623cccaeb667bc26ba300cc5108496bf0d813d026`
- `dev_high_risk_sol_agrees.csv`：`cb933361b495f80d6271a8788b2aaff2ce8c7be8a8fa0ac02a457e2e695bf195`
