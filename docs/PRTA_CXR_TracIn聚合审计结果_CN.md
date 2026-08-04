# PRTA-CXR 全量近似 TracIn 聚合审计结果

## 结论边界

本次任务以只读方式完成，结果只能解释为“高风险候选”，不能解释为已证明的错标、有害样本或删除后可提升指标的因果证据。没有修改标签、样本、数据划分或 checkpoint，没有启动重训，也没有读取 Internal-test 或 Gold。

正式程序原有结论保持为 `STOP_DEVELOPMENT_GATE`；本审计不产生新的科学 GO/HOLD 结论。

## 数量守恒

| 项目 | 数量 |
|---|---:|
| Train 全量分数 | 91,065 |
| Dev 全量分数 | 16,666 |
| 分层 Dev 探针 | 300 |
| 全部高风险候选 | 17,200 |
| Train 候选 | 9,847 |
| Dev 候选 | 7,353 |
| Context（仍保留在全量表） | 90,531 |

| 风险层级 | 数量 |
|---|---:|
| Tier A | 3,866 |
| Tier B | 2,921 |
| Tier C | 10,413 |

| 数据源 | 候选数 |
|---|---:|
| CheXpert Plus | 9,475 |
| MIMIC-CXR-JPG | 7,725 |

| Luna 标签 | 候选数 |
|---|---:|
| Improved | 3,068 |
| Worse | 3,535 |
| New | 3,861 |
| Resolved | 601 |
| Stable | 6,135 |

## 主要触发原因

同一候选可触发多个原因，因此下表数量不可相加为候选总数。

| 原因 | 数量 |
|---|---:|
| 至少两个 seed 误分类 | 11,013 |
| 至少两个 seed 的负向影响位于层内前 5% | 4,001 |
| 至少两个 seed 的 Self-influence 位于层内前 5% | 2,786 |
| Self-influence 位于层内前 10% | 2,983 |
| 三 seed 预测高度分歧 | 2,637 |
| Train 平均 NLL 位于层内前 5% | 863 |
| Dev 平均 NLL 位于层内前 5% | 839 |

末层与分类头加四层 LoRA Adapter 的层内 Top-5 重叠中位数分别为：Seed 17 = 0.639458、Seed 29 = 0.712349、Seed 43 = 0.751785。三个值均不低于预设的 0.60 全局不稳定阈值。

## 验收结果

- Train 和 Dev 全量表分别精确覆盖 91,065 和 16,666 个唯一 sample ID，无重复、空 ID、错 split、NaN 或 Inf。
- 17,200 个 Tier A/B/C 候选在候选 CSV、逐病例 JSONL 和逐病例 Markdown 中一一对应；Markdown 含 17,200 条记录，无 Top-K 截断。
- 三个 seed 均独立完成 `best.pt` 与 `last.pt` 两个 checkpoint；正向影响非负、负向影响非正、Self-influence 非负。
- 输入清单、缓存、权重及六个 checkpoint 的审计前后哈希完全一致。
- `protected_outcome_read_count=0`、`training_started=false`、`optimizer_step_called=false`、`internal_test_opened=false`、`gold_opened=false`。
- 聚合 JSON 不含 sample ID、patient ID、日期、报告、study/image ID 或路径；所有逐病例敏感字段只保存在 Git 外的私有输出目录。

## 私有输出哈希

| 文件 | SHA256 |
|---|---|
| `train_all_scores.csv` | `7d5347d63a4274f0c972b8fcdc4d5ddc4de2b877b687764040fb808075fa3a6d` |
| `dev_all_scores.csv` | `dde71f193b841edfd39a53b77836565cad6e0729b1dabfa5bedf731f9fe723c2` |
| `all_flagged_candidates.csv` | `ad0ef849781feef1d28997df0fdb9da65d646aea4360149b81a68e99a86330ad` |
| `case_details.jsonl` | `adce4ba50f74b6e586544c036b3cea49c4bb27521dc8e26e2802f75b0efcb571` |
| `PRTA_CXR_TracIn全部高风险样本内部审计.md` | `c07146bf8464b0631aee798a25c3ea8ad029d8dbf8b44b2b2fa2efdc9f3eeb80` |
| `aggregate_summary.json` | `3a57b1bd84ad238ffee1a8820c2509ebc6f84b3986186b692773d51aa0619863` |
| `audit_receipt.json` | `4393493902270c76284f3357366e2fc6f84ff3ba6faeb71e742d81f34356c6a5` |

审计回执绑定实现提交 `3f9dafa112f937d32e4e4331ab962e89e3e7c175`。完整逐病例文件不进入 Git。
