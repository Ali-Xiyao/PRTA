# PRTA-CXR Sol 盲审 Luna Pilot 状态

日期：2026-08-02

状态：`SOL_BLIND_REVIEW_PASS__SUPPORT_LUNA_PRIMARY_PILOT_ONLY__HUMAN_AUDIT_REQUIRED`

## 结论

Sol 已在与 Luna 完全相同的冻结150条样本上完成盲审。Sol只看到了短批次别名、
目标 finding、PRIOR 报告和 CURRENT 报告；没有看到规则标签、Luna标签、患者ID
或私有 alias 映射。

当 Luna 与 Sol 都输出明确五类时，二者一致115/124（92.74%），Cohen's
κ=0.908。两个来源的明确五类一致率都超过90%，五个 Luna 标签的明确一致率均
不低于85.71%。在规则与 Luna 不一致的30条中，Sol支持Luna 21条、支持规则
4条、选择第三标签1条、输出 `Unclear` 4条。

因此，这个 pilot **支持在现有 rule-extractable 候选池内，让 Luna 成为主要五类
标签生成器，并取消“规则标签必须与 Luna 一致”的 Silver 准入条件**。但这只是
模型间一致性证据，不是 Luna 的医学准确率，也不自动激活该政策或全量标注。
200–300条人工准确率抽检仍是正式训练和论文使用的硬门。

## 工程完整性

| 项目 | 结果 |
|---|---:|
| Model | `gpt-5.6-sol` |
| 冻结样本 | 150 |
| Candidate SHA-256 | `c7a44d86c5f160e3f4d667557b3956a2016517ad64154421be29fc2b807858f9` |
| Sol batches | 8/8 |
| Schema/ID 合法 | 150/150 |
| 唯一输出 ID | 150 |
| 失败输出 / 重试 | 0 / 0 |
| Sol 总调用时间 | 378.974 秒 |
| 平均每批 | 47.372 秒 |
| Comparison SHA-256 | `b2665d8f864c37ba731533162c630be9af1c6055aa4f8d2c8c43e9324b5bdbb6` |

## Luna–Sol 一致性

| 口径 | Denominator | Exact | Agreement | Cohen's κ | Wilson 95% CI |
|---|---:|---:|---:|---:|---|
| 六类，`Unclear`作为第六类 | 150 | 121 | 80.67% | 0.765 | 73.61%–86.19% |
| 双方均明确的五类 | 124 | 115 | 92.74% | 0.908 | 86.78%–96.13% |

两种口径必须同时报告。92.74%只适用于双方均明确的124条，不能把它写成150条
覆盖率或医学准确率。

## 分来源

| Source | Rows | 六类一致 | 六类率 | 双方明确 | 五类一致 | 五类率 | κ（五类） |
|---|---:|---:|---:|---:|---:|---:|---:|
| MIMIC-CXR-JPG | 75 | 61 | 81.33% | 61 | 58 | 95.08% | 0.938 |
| CheXpert Plus | 75 | 60 | 80.00% | 63 | 57 | 90.48% | 0.878 |

来源间没有被总体结果掩盖；CheXpert Plus 的明确五类一致率低于 MIMIC 约4.60
个百分点，正式全量后仍需分来源抽检。

## 按 Luna 标签

| Luna label | Rows | Sol相同 | 含Sol-Unclear一致率 | Sol明确Rows | 明确五类一致率 |
|---|---:|---:|---:|---:|---:|
| Improved | 27 | 23 | 85.19% | 24 | 95.83% |
| New | 36 | 30 | 83.33% | 35 | 85.71% |
| Resolved | 20 | 19 | 95.00% | 20 | 95.00% |
| Stable | 27 | 24 | 88.89% | 25 | 96.00% |
| Worse | 23 | 19 | 82.61% | 20 | 95.00% |

`Worse`细查：23条 Luna-Worse 中，Sol输出 Worse 19、`Unclear` 3、New 1。
因此按全部 Luna-Worse 行是82.61%，按 Sol 明确的20条是95.00%。唯一明确分歧
是 MIMIC Cardiomegaly 的 Worse-versus-New；没有出现 Worse-versus-Improved
的直接反向分歧。最低明确五类一致率实际是 New（85.71%）。

## 规则–Luna 分歧的 Sol 取向

| 30条分歧 | Total | MIMIC | CheXpert Plus |
|---|---:|---:|---:|
| Sol支持Luna | 21 | 9 | 12 |
| Sol支持规则 | 4 | 1 | 3 |
| Sol选择第三标签 | 1 | 0 | 1 |
| Sol输出Unclear | 4 | 3 | 1 |

Sol支持Luna与支持规则之比为21:4。另一方面，原先103条规则–Luna一致样本中，
Sol确认94条、明确给出不同标签4条、输出 `Unclear` 5条。这说明三方交集更纯但
会继续损失覆盖；若目标是大规模训练标签，规则更适合作为审计信号而非硬准入门。

## Luna Unclear

Luna 的17条 `Unclear` 中，Sol输出：`Unclear` 6、New 5、Stable 4、Improved 1、
Worse 1。Sol给出明确标签不能自动“救回”这些行；在 Luna-primary 方案下仍应排除
Luna=`Unclear`，除非以后另行冻结人工或双模型裁决协议。

## 解释边界与下一门

- 本结果测量 Luna–Sol 一致性，不测量真实医学正确率。
- 两个模型可能共享偏差并对同一句含糊报告犯相同错误。
- 这150条按规则候选层分层，只代表当前规则可提取候选池。
- 自动程序仍负责配对、finding、结构/否定/不确定性过滤、ID、来源和患者审计。
- 是否把主线从 Rule∩Luna 改为 Luna-primary 需要用户单独确认。
- 即使确认，`Luna Unclear` 仍排除；全量后必须完成人工200–300条
  `source × 五类`准确率审核，审核通过前不得正式训练或用于论文结论。

## 产物

本地运行根：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\sol_blind_review_v1`

关键文件：

- `pilot_prepare_receipt.json`
- `pilot_run_receipt.json`
- `outputs/batch_*.json`
- `rule_luna_sol_comparison_v2.jsonl`
- `sol_review_audit_v2.json`

当前锁：Sol pilot 已完成并重新关闭；Sol full、Luna full、split、cache、training、
internal-test、gold 和 external confirmation 全部保持 HOLD/CLOSED。
