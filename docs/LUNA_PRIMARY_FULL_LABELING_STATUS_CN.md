# PRTA-CXR Luna-primary 全量标签状态

日期：2026-08-02

## 结论

冻结的 148,798 条候选已经完成 Luna-primary 全量标注和 fail-closed 合并。有效的
五分类 Luna 输出进入 Silver；`Unclear` 被单独排除。规则标签仅保留为诊断，未参与
Silver 准入、否决或回填。训练、split、缓存、内部测试和论文结果仍未启动。

| 项目 | 结果 |
|---|---:|
| 冻结候选 | 148,798 |
| 输入/输出批次 | 7,440 / 7,440 |
| Luna-primary Silver | 126,727 (85.17%) |
| `Unclear` 排除 | 22,071 (14.83%) |
| 历史失败尝试 | 52（全部重试恢复） |
| 规则–Luna 诊断一致 | 95,681（不作为准确率或准入） |

五类 Luna 标签计数为 Improved 18,535、New 22,246、Resolved 3,263、Stable 59,372、
Worse 23,311。Silver manifest SHA-256 为
`71ac2b7bfabff1d0781b919190001d1b0ac980edc05f1feb05116259d7b99159`。

## 人工审核与 Gold 边界

已按 `source × Luna 五类` 固定抽取 250 条：两个来源各五类、每层 25 条；250 位
患者唯一。其所有 2,297 条 Silver 行均已从训练可用清单移除，训练可用 Silver 为
124,430 条，患者交集为 0。

该 roster 状态为 `GOLD_PENDING_SENIOR_REVIEW`，`gold_rows=0`。第一轮医生填写结果已
按用户要求清除，未保留为 Gold 或准确率证据。当前改由资深医生在可见 Luna 标签的
条件下进行确认/修正；在 250 条全部完成并通过导入审计前，训练和论文使用仍为 HOLD。

新的资深医生交付材料已经准备完成：

- [Luna辅助复核说明](PRTA_CXR_Gold资深医生_Luna辅助复核说明_v2_CN.md)
- [标签判定规则](PRTA_CXR_Gold标签判定规则_v2_CN.md)
- [250条资深医生复核表](../outputs/gold_human_review_senior_20260802/PRTA_CXR_Gold资深医生_Luna辅助复核表_v2.xlsx)
- [可直接转交的压缩包](../outputs/gold_human_review_senior_20260802/PRTA_CXR_Gold_Senior_Doctor_Luna_Assisted_Review_Package_v2.zip)

新表显示 Luna 标签，但不包含第一位医生答案、患者哈希或原始样本 ID。本轮属于
Luna 辅助复核，不再称为独立盲审；完成全部行后，项目侧才可按 `review_id` 导入并
冻结资深医生确认/修正后的 Gold。

## 运行产物

运行目录：`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\luna_primary_full_v1`

- `merged/luna_primary_merge_audit.json`：全量合并审计。
- `merged/luna_primary_silver.jsonl`：完整 Silver，不能直接用于训练。
- `merged/luna_primary_discarded_unclear.jsonl`：`Unclear` 排除记录。
- `review/gold_pending_human_review_roster.jsonl`：250 条人工复核名单。
- `review/luna_primary_training_eligible.jsonl`：去除 roster 患者后的唯一训练候选入口。
- `review/gold_audit_roster_audit.json`：分层与患者隔离审计。
