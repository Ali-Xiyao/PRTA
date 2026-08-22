# PRTA-CXR Luna Pilot 状态

状态：`PASS_ENGINEERING_PILOT__HOLD_FULL_LUNA_EXPANSION`

日期：2026-08-02

## 结论

150 条分层 Luna pilot 已完成，但不应立即扩大到全部 148,798 条规则候选。
结构化输出、ID 恢复和最终 Tier-A 原文证据门已经跑通；当前 HOLD 原因是批次失败率、
来源接受率差异、全量顺序执行成本，以及医生抽检尚未完成。未冻结 split、未缓存、
未训练。

## 冻结 Authority

- Model：`gpt-5.6-luna`
- Codex CLI：`0.144.6`
- Pilot candidates：150 条、150 名不同患者、118 个 strata
- MIMIC / CheXpert Plus：75 / 75
- Calendar / within-patient ordinal：75 / 75
- Prompt SHA-256：`e36f91dad486640c488d7024337c9d3ef83870326c099697300c0e0a017417ea`
- Schema SHA-256：`c65db59e92142034fe2b36414c8760f021949bc5a0deacf666187b27a7b3e81f`
- Pilot candidate canonical SHA-256：`c7a44d86c5f160e3f4d667557b3956a2016517ad64154421be29fc2b807858f9`
- Final label canonical SHA-256：`9b7ba10d3b4f693f31e441960c68d8cb9dce478c28177ee7c949646a47267dbd`
- Final label file SHA-256：`59a230b2d824fa501e512ab040a04531fc751faf203bcfe276c094d1cc8ab4b7`

运行根目录：
`<private-local-runtime>\labels_v1`

## Pilot 结果

| 检查项 | 结果 | 判定 |
|---|---:|---|
| 最终 JSON/schema/ID 合法率 | 150/150 | PASS |
| 重复或未知正式 sample ID | 0 | PASS |
| 规则标签与 Luna 标签一致 | 142/150（94.67%） | 记录 |
| Model accept | 46/150 | 记录 |
| 最终 Tier-A | 45/150（30.00%） | 记录 |
| 最终 Reject | 105/150（70.00%） | 记录 |
| Tier-B | 0 | 记录 |
| 非 extractive accept 确定性降级 | 1 | PASS_FAIL_CLOSED |
| 最终 Tier-A 三段原文命中 | 45/45（100%） | PASS |
| v6 外部尝试 | 10 | 记录 |
| 严格门拒绝的批次尝试 | 2/10（20%） | HOLD |

短批内 alias 仅发送给 Luna；alias-to-original 映射不进入外部 payload。runner 对
alias 集合做精确校验后在本地恢复原 64 位 sample ID。正式输出中 alias 残留为 0。
原始 Luna 行不人工修改；`accept + conflict/mismatch/non-extractive evidence` 只会被
确定性标签门降为 Reject，并记录原因。

## 来源差异

| Source | Pilot | Tier-A | Reject | Tier-A rate |
|---|---:|---:|---:|---:|
| MIMIC-CXR-JPG | 75 | 35 | 40 | 46.67% |
| CheXpert Plus | 75 | 10 | 65 | 13.33% |

该差异说明两个来源的报告比较语义不能被视为等价。CheXpert Plus 同时只有患者内
ordinal 时间，不能把较低接受率解释为真实时间间隔效应。全量前需要决定是否：

1. 仅在报告明确绑定 selected prior 的候选上运行 Luna；
2. 分来源修订但冻结规则，再重新做同一分层 pilot；
3. 将 CheXpert Plus 保留为规模/来源敏感性实验，而非默认混入主 Tier-A。

## 吞吐与下一道门

v6 共 10 次外部尝试才得到 8 个最终批次，观测总执行时间约 851 秒。按 20 条批次、
当前失败/重试率和串行吞吐外推，148,798 条全量候选约需 9–10 天连续运行。直接启动
约 7,440 个最终批次在当前 runner/额度证据下不合理。

恢复全量 Luna 前至少需要：

- 明确并发数、额度/费用和失败重试预算；
- 解决或接受 MIMIC/CheXpert Plus 的 Tier-A 保留率差异；
- 冻结 source-aware 候选策略后重新通过 100–200 条 pilot；
- 为后续约 250 Accept + 50 Reject 的医生抽检准备独立 roster。

本 pilot 不是医生 Gold，也不是论文模型结果。Internal test、protected gold、缓存、
GPU 训练和评估均未打开。
