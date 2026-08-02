# PRTA-CXR Gold 候选人工盲审规则

版本：v1.0

日期：2026-08-02

适用范围：`gold_pending_human_review_roster.jsonl` 中固定抽取的 250 条候选

## 1. 目的与边界

本轮人工复核用于：

1. 独立判断目标病灶在前后两次胸片报告之间的纵向变化；
2. 估计 Luna-primary Silver 标签的准确性；
3. 将经人工确认且可判定的样本冻结为 Gold 候选；
4. 识别并排除含糊、错误配对、缺失或不适合用于评估的样本。

人工复核人员不得看到 Luna 标签，也不使用任何自动规则标签。复核时只依据工作簿中
给出的 `finding`、`PRIOR_REPORT` 和 `CURRENT_REPORT` 独立判断。

本规则仅用于科研数据质量审核，不能替代临床诊断或患者照护决策。

## 2. 审核单位

每一行代表一个纵向比较任务：

- `finding`：本行需要判断的唯一目标病灶；
- `PRIOR_REPORT`：时间较早的报告；
- `CURRENT_REPORT`：时间较晚的报告；
- `human_label`：人工对目标病灶纵向变化的判断。

只判断指定的 `finding`，不要因为报告中的其他病灶发生变化而改变本行标签。

## 3. 允许标签

### `Improved`

目标病灶在 PRIOR 中存在，CURRENT 中仍可见但程度、范围、数量或严重性明确减轻。

典型表达包括：decreased、improved、less conspicuous、mildly reduced、interval
improvement。不能仅凭报告整体语气变好而判定，变化必须能对应到目标病灶。

### `Worse`

目标病灶在 PRIOR 中存在，CURRENT 中程度、范围、数量或严重性明确增加。

典型表达包括：increased、worsened、progressed、more prominent、enlarging。新出现的
目标病灶应标为 `New`，不标为 `Worse`。

### `New`

PRIOR 中目标病灶明确不存在或未见，CURRENT 中明确新出现。

如果 PRIOR 没有提到该病灶，但无法判断它当时是否确实不存在，应使用 `Unclear`，
不能仅凭“前次未提及”自动判为 `New`。

### `Resolved`

目标病灶在 PRIOR 中存在，CURRENT 中明确消失、完全缓解或不再可见。

如果只是减轻但仍存在，应标为 `Improved`；如果 CURRENT 仅未提及且无法确认消失，
应标为 `Unclear`。

### `Stable`

目标病灶在 PRIOR 和 CURRENT 中均存在，且明确无实质变化。

典型表达包括：stable、unchanged、similar、no significant interval change。两次报告均
明确阴性不属于 `Stable`，此类样本应标为 `Unusable`；单纯两次都未提及也不能判为
`Stable`。

### `Unclear`

报告和配对本身可读，但现有文字不足以在五类之间作出可靠判断。常见情形包括：

- PRIOR 未提及目标病灶，CURRENT 提及，但无法确认是否真正新发；
- CURRENT 未提及 PRIOR 中的病灶，但无法确认是否已经消失；
- 报告使用“可能、不能排除、疑似”等不确定表达，无法确定病灶是否存在；
- 报告内部矛盾，或前后比较方向不明确；
- 治疗、手术或技术因素使目标病灶的纵向变化无法可靠比较；
- 无法区分 `Improved` 与 `Resolved`、`New` 与 `Worse`、`Stable` 与其他类别。

### `Unusable`

样本结构或内容本身不适合用于纵向评估。必须同时填写 `unusable_reason`。常见情形包括：

- 缺少 PRIOR 或 CURRENT 报告；
- 报告文本损坏、截断或明显错配；
- `finding` 与报告内容完全无关；
- 前后记录不可比较或时间方向明显错误；
- 两次报告对目标病灶均明确阴性；
- 重复样本或其他数据质量问题。

## 4. 判定顺序

对每一行按以下顺序操作：

1. 确认 PRIOR 和 CURRENT 报告均完整可读，且时间方向为前者早、后者晚；
2. 只定位指定 `finding` 在两份报告中的状态；
3. 判断 PRIOR 和 CURRENT 中该病灶是否明确存在、明确不存在或不确定；
4. 若两次均可可靠判断，选择五类之一；
5. 若报告可用但变化方向不足以确定，选择 `Unclear`；
6. 若样本结构或内容不合格，选择 `Unusable` 并填写原因；
7. 填写审核人和审核日期。备注仅在确有必要时填写。

不要使用患者年龄、其他病灶变化、治疗预期或常识推测补足报告中不存在的信息。

## 5. 重点边界案例

| PRIOR | CURRENT | 标签 |
|---|---|---|
| 病灶存在 | 病灶减轻但仍存在 | `Improved` |
| 病灶存在 | 病灶明确消失 | `Resolved` |
| 病灶不存在 | 病灶明确出现 | `New` |
| 病灶存在 | 病灶明确加重 | `Worse` |
| 病灶存在 | 明确无变化 | `Stable` |
| PRIOR 未提及 | CURRENT 提及，但没有“新发”证据 | `Unclear` |
| PRIOR 提及 | CURRENT 未提及，但没有“消失”证据 | `Unclear` |
| 两次均明确阴性 | 两次均明确阴性 | `Unusable` |
| 报告缺失、错配或损坏 | 任意 | `Unusable` |

## 6. 盲审与解盲流程

1. 审核人员只接收 `PRTA_CXR_Gold人工盲审表_v1.xlsx`；
2. 表中不包含 Luna 标签、规则标签、患者标识或原始样本 ID；
3. 审核人员完成全部 250 行并检查“质量检查”页为全部完成；
4. 回收工作簿后，由项目程序使用 `review_id` 与冻结 roster 对照解盲；
5. 分别报告总体、两个数据源、五个 Luna 标签以及 `Worse` 的一致率；
6. `Unclear` 和 `Unusable` 不进入 Gold；五分类人工标签才可进入最终 Gold；
7. Gold 所属患者继续与训练、开发和模型选择数据保持隔离。

## 7. 完成标准

工作簿只有同时满足以下条件才可进入解盲：

- 250 行均填写 `human_label`；
- 每行均填写 `reviewer_id` 和 `review_date`；
- 所有 `Unusable` 行均填写 `unusable_reason`；
- `review_id` 未被修改、删除或重复；
- 审核期间未接触 Luna 标签或规则标签。

人工复核完成并不自动授权训练。解盲统计、Gold 冻结、patient-disjoint split 和缓存仍需
分别审计，正式训练需另行授权。
