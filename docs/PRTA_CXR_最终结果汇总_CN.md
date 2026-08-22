# PRTA-CXR Historical Tail8 Outcome Summary（历史记录，已由 V2 最终文档取代）

> **历史/已取代：** 本文记录的是 2026-08-10 冻结的旧 Tail8 方法及其当时已消费的评估证据，不是当前 PRTA-CXR V2。
>
> 当前唯一论文与仓库结果权威为 [PRTA-CXR V2 最终方法与 Train/Dev 结果](PRTA_CXR_V2_FINAL_METHOD_AND_RESULTS_CN.md)。旧方法的 Internal-test/Gold 数字不得迁移、折算或归属于 V2；本文其余内容保持原样，以保留历史审计链。

> 冻结日期：2026-08-10
>
> 适用范围：当前 PRTA-CXR 项目的论文结果、项目验收和复现实验索引。
>
> 正式口径：医生最终筛选后的 12,219 例是正式 Internal-test；13,219 例仅是医生复核前的数据质量基线。

## 1. 结论

当前方法学流程已经跑通，并完成了可用数据上的最终评估：

1. 冻结的 Tail8 方法在三 Seed 条件适配器范围消融中取得最高 Dev Macro-F1 均值：`0.548138 ± 0.001455`。
2. 在医生最终确认的正式 Internal-test（12,219 例）上，Tail8 三个 Seed 的 Macro-F1 均超过 `0.5460939601`，均值为 `0.556188 ± 0.001791`，按当前 Macro-F1-only 规则判定为 **PASS**。
3. 在一次性 Gold（175 例）上，Tail8 三 Seed Macro-F1 均值为 `0.548708 ± 0.017999`，超过冻结均值门槛 `0.5460939601`，判定为 **PASS**。
4. ODER 按用户最终规则仅作描述，不参与 PASS/HOLD。它必须继续报告，但不能推翻上述 Macro-F1 判定。
5. 当前 Internal-test 与 Gold 均已使用完毕，不再在现有数据上继续筛选、调参或重复测试。

因此，项目当前的正式结论是：**Tail8 为最终保留方法；正式 Internal-test 和一次性 Gold 均通过当前 Macro-F1 判定规则。**

## 2. 结果证据层级

| 层级 | 数据/实验 | 正式用途 | 当前结论 |
|---|---|---|---|
| 方法选择 | Wave033，医生清洗后 Train 80,402 / Dev 11,201，Tail4/Tail6/Tail8 × Seeds17/28/43 | 条件适配器范围消融 | Tail8 的三 Seed Dev 均值最高；保留 Tail8 |
| 正式内部测试 | 医生最终确认的 12,219 例 Internal-test | 论文正式 Internal-test 主结果 | Tail8 三 Seed 全部超过 Macro-F1 目标，PASS |
| 最终可用测试 | 一次性 Gold，175 例 | 当前数据条件下的最终测试 | Tail8 三 Seed均值超过 Macro-F1 目标，PASS |
| 历史基线 | 医生复核前的 13,219 例 Internal-test | 仅说明数据清洗前后差异 | 非正式结果，不作为最终性能结论 |

历史 Wave039 文件名仍保留 `posthoc` 字样，这是为了保持既有收据不可篡改；本汇总依据用户最终确认，将医生筛选后的 12,219 例定义为项目正式 Internal-test。旧收据名称和旧状态不被改写，但不再决定论文的正式数据口径。

### 2.1 后续实验统一数据契约

Wave033 适配器层范围消融已经使用医生清洗后冻结的 Train 80,402 / Dev 11,201 行完成。Tail4 使用 Block-8 缓存，Tail6/Tail8 使用 Block-4 缓存，这是模型入口要求造成的无标签特征边界差异；三个范围使用的是同一清洗后病例行集合，因此不需要重跑层范围消融。

所有后续基线、组件消融、效率测试和需要重新训练的分析，必须继续绑定同一清洗后 Train/Dev manifest，SHA-256 为 `45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89`。清洗前 manifest、历史调试划分、医生排除样本、Internal-test 和 Gold 一律不得进入训练或开发。完整约束见《PRTA_CXR_后续实验清洗数据统一协议_CN.md》。

## 3. 正式 Internal-test 主结果

正式 Internal-test 是医生最终确认后的 12,219 例。Tail8 为正式方法，Tail4 为冻结的范围对照。

| Scope | Seed | Macro-F1 | Accuracy | Balanced Accuracy | Min Recall | ODER（描述） |
|---|---:|---:|---:|---:|---:|---:|
| Tail8 | 17 | 0.554201 | 0.636386 | 0.545437 | 0.481870 | 0.010475 |
| Tail8 | 28 | 0.557680 | 0.638841 | 0.551923 | 0.478812 | 0.009984 |
| Tail8 | 43 | 0.556683 | 0.638023 | 0.548540 | 0.480431 | 0.009002 |
| **Tail8** | **三 Seed 均值 ± 样本标准差** | **0.556188 ± 0.001791** | — | — | — | **0.009821 ± 0.000750** |
| Tail4 | 17 | 0.547200 | 0.634258 | 0.539705 | 0.459152 | 0.013749 |
| Tail4 | 28 | 0.543191 | 0.632867 | 0.539443 | 0.466251 | 0.011949 |
| Tail4 | 43 | 0.544704 | 0.629757 | 0.540603 | 0.463415 | 0.013749 |
| **Tail4** | **三 Seed 均值 ± 样本标准差** | **0.545032 ± 0.002025** | — | — | — | **0.013149 ± 0.001040** |

正式结论：Tail8 三个 Seed 的 Macro-F1 均超过 `0.5460939601`，而 Tail4 的三 Seed 均值低于该目标。Tail8 是正式保留方法。

## 4. 一次性 Gold 结果

Gold 的正式有效队列为医生清洗后的 175 例。为确保标签打开前预测已经冻结，三个 Seed 先对 250 例无标签候选全集完成预测，再在唯一一次授权标签读取中对齐到最终 175 例。

| Scope | Seed | Macro-F1 | Accuracy | Balanced Accuracy | ODER（描述） |
|---|---:|---:|---:|---:|---:|
| Tail8 | 17 | 0.539981 | 0.537143 | 0.532190 | 0.051429 |
| Tail8 | 28 | 0.569407 | 0.560000 | 0.557098 | 0.040000 |
| Tail8 | 43 | 0.536737 | 0.525714 | 0.528211 | 0.045714 |
| **Tail8** | **三 Seed 均值 ± 样本标准差** | **0.548708 ± 0.017999** | — | — | **0.045714 ± 0.005714** |

冻结的 Gold Macro-F1 均值门槛为 `0.5460939601`，实际均值高出约 `0.002614`，因此按 Macro-F1-only 规则为 **PASS**。Seed17 和 Seed43 单独低于该数值，且三 Seed 标准差较大，所以论文必须同时报告每个 Seed，不能只报告均值。

## 5. 条件适配器范围消融

Wave033 在结果揭示前冻结全部九个格子，保持 H0、rank32、EMA0.999、DMW0.01、直接反方向代价0.05、state辅助0.025、恒定学习率、Train/Dev 行、优化器、batch、epoch预算和早停一致，仅改变适配器范围及其必需缓存边界。

| Scope | Macro-F1 均值 ± 样本标准差 | ODER 均值 ± 样本标准差 | 可训练参数 | 平均壁钟时间 | 结论 |
|---|---:|---:|---:|---:|---|
| no-tail | 待运行 | 待运行 | 待测 | 待测 | 新增范围对照 |
| Tail2 | 待运行 | 待运行 | 待测 | 待测 | 新增浅层adapter对照 |
| Tail4 | 0.542447 ± 0.000882 | 0.004077 ± 0.000594 | 16,399,630 | 1.146 h | 范围对照 |
| Tail6 | 0.545286 ± 0.002206 | 0.003690 ± 0.000103 | 16,501,008 | 1.924 h | 优于 Tail4，但低于 Tail8 |
| **Tail8** | **0.548138 ± 0.001455** | **0.003303 ± 0.000000** | **16,602,386** | **2.019 h** | **最终保留范围** |
| Tail10 | 待运行 | 待运行 | 待测 | 待测 | 新增深层adapter对照；需Block-2缓存 |

Wave033 已完成并审计 Tail4/Tail6/Tail8。扩展矩阵新增 no-tail/Tail2/Tail10，
三者均只在相同清洗后 Train/Dev 上运行；Tail10 需先建立 Block-2 无标签缓存。
扩展结果只补充 Dev 层范围曲线，不追溯性修改已冻结并完成正式评估的 Tail8。

这是一项“条件适配器范围消融”，不是无偏架构搜索。no-tail/Tail2/Tail4
依赖 Block-8，Tail6/Tail8 依赖 Block-4，Tail10 依赖 Block-2，因此范围和
必要缓存入口共同变化，但病例行集合保持一致。

## 6. 冻结方法配置

| 项目 | 最终值 |
|---|---|
| 源代码提交 | `821e8040aec9b47536f3755c4ede7fc5aef008d4` |
| 模型/原生头 | PRTA / H0 |
| 适配器范围 | Tail8 |
| Adapter rank | 32 |
| 宽度 / heads | 768 / 12 |
| State / transition tokens | 20 / 20 |
| Dropout | 0.1 |
| 分类损失 | class-balanced focal，gamma=1.0，beta=0.9999 |
| 损失权重 | classification=1.0；DMW=0.01；ODC=0.05；state=0.025；其余辅助项=0 |
| 优化 | LR=1e-4，恒定学习率，weight decay=0.01，gradient clip=1.0 |
| EMA | 0.999 |
| Batch / 最大 epoch | 16 / 20 |
| 早停 | minimum epochs=6；patience=4；min delta=0.001 |
| 推理温度 | 1.0 |
| 正式 Seeds | 17、28、43；不选择“最佳 Seed” |

三个正式 Tail8 `best.pt` checkpoint SHA-256：

- Seed17：`3cc886488f533d2b9bb6f8102cc5bdb200bcbae0ee6d381501824c3321d8b67c`
- Seed28：`a771b07e7ced97dda4e6cb9f9ecf0a8b2054b6f78726cfaf16b730c1d8d79bb5`
- Seed43：`d4f0666743f749b95b6f78a57bfcdfdfd015063d51d50ee9c9e6ac65d258fd77`

## 7. 医生复核前基线的正确用途

医生复核前 13,219 例上的 Tail8 Macro-F1 为 `0.500504 ± 0.001915`，Tail4 为 `0.495076 ± 0.001201`。这些结果只用于记录数据质量复核前后的变化，不应出现在论文摘要或主结论中作为正式 Internal-test 性能。

论文中可将该结果放入数据清洗流程或附录，并明确标注为“pre-review baseline”。正式主表必须使用医生最终确认的 12,219 例结果。

## 8. 论文可以和不可以声称的内容

可以声称：

- Tail8 在冻结的三 Seed 条件消融中取得最高 Dev Macro-F1 均值。
- 在医生最终确认的正式 Internal-test 上，Tail8 三个 Seed 均超过当前 Macro-F1 目标。
- 在一次性 175 例 Gold 上，Tail8 三 Seed Macro-F1 均值超过冻结门槛。
- ODER 始终完整报告，但按最终规则不参与通过判定。

不应声称：

- 结果已经构成多中心、外部或临床部署验证。
- Gold 上每个 Seed 都超过了均值门槛。
- 医生数据筛选过程与模型错误完全无关。医生最终筛选后的集合是本项目正式 Internal-test，但论文仍应披露其来源于医生对存疑样本的复核。
- 历史峰值 GPU 显存已被准确记录。该字段不可恢复，不能估算或补跑。

## 9. 复现与收据索引

| 证据 | 位置 | SHA-256 |
|---|---|---|
| Wave033 九格条件消融终态 | `.../wave033_conditional_adapter_scope_ablation_v1_attempt2/final_nine_cell_aggregate.json` | `606e10c0168bd662fee07999f40e8d9c32134d039c049a5b992fea626d6f221d` |
| 医生复核前 Internal-test 基线 | `.../wave035_tail8_internal_test_once_v1/outcome_attempt1/internal_test_terminal_receipt.json` | `7e7940252f7549eb0ae5320621489f3069fcb52faf72c974ba935c135a14a5d6` |
| 正式医生确认 Internal-test | `<private-local-runtime>\formal_internal_test_doctor_filtered_posthoc_v3_attempt2\outcome\doctor_rereview_filtered_posthoc_v3_attempt2_terminal_receipt.json` | `32c59e49dad3028841976d86a7a879868035cbc1252a1cb8db66e386319423e9` |
| 正式 Internal-test 独立审计 | `<private-local-runtime>\formal_internal_test_doctor_filtered_posthoc_v3_attempt2\audit\independent_audit_receipt.json` | `8ceb92c5fbf4279585a8b77c3cbde1d94546f63a50cc742698a602835fcb3846` |
| 一次性 Gold 终态 | `.../wave040_tail8_gold_once_v1/outcome_attempt1/gold_terminal_receipt.json` | `ba7885b290192b4f3917d317f220b37faa8033309db40dcec28576f67e076297` |
| Gold 独立审计 | `.../wave040_tail8_gold_once_v1/independent_audit_v1/independent_audit_receipt.json` | `de25ed33ec09c343b21605b625eeccaeffd67fcada4a117179b2bed7553916fc` |
| Gold 正式清洗后 manifest | 私有运行时，不进入 Git | `6a9c868d07ac1bfd40b2c5b0de039868eb0723f695453bc1bdc7c5ee4cf269ad` |

`...` 表示服务器根目录：
`<private-server-runtime>`。

## 10. 下一步

1. 停止在现有 Internal-test 和 Gold 上继续实验；两者均作为已消耗评估面封存。
2. 以本文件和配套 CSV/XLSX 作为论文结果数字的唯一汇总入口。
3. 将正式 Internal-test、Gold、条件消融分别写入论文主结果、最终测试和消融章节。
4. 在限制部分披露：Gold 样本量为175、Seed波动较大、ODER较高但非门槛、医生复核数据的形成过程，以及缺少新的外部队列。
5. 如果未来新增完全独立的数据，只允许对当前冻结 Tail8 三 Seed 做一次前瞻性验证；不再用现有结果重新调参。

## 11. Wave041 完整消融执行状态

2026-08-10 已冻结并启动完整清洗数据消融。范围轴为 no-tail/tail2/tail4/tail6/tail8/tail10，其中 tail4/tail6/tail8 复用 Wave033，no-tail/tail2/tail10 各运行 Seeds17/28/43。组件轴固定在 Tail8，新增运行 w/o Finding Conditioning、w/o Cross-time Alignment、w/o Dual Branch、w/o Direction Margin、w/o Opposite-direction Cost、w/o State Preservation、Classification-only，各运行 Seeds17/28/43。

Full 方法的 semantic-alignment、CMCP、temporal-inversion 损失权重本来为 0，因此三个对应删除项记录为恒等 `N/A`，不重复训练。Wave041 共 30 个新增训练格、15 个固定阶段；当前仅允许用 Dev 汇总 Macro-F1/ODER、参数量、峰值显存和墙钟时间，不得读取 Internal-test/Gold，也不得根据中间结果改变队列。

| 审计项 | 值 |
|---|---|
| 源提交 | `8ccace5b64d3a084f8cd919d2cfc2906d81b4136` |
| 冻结回执 SHA-256 | `af802481cd5da93f8564f59942cfa1a35a412e2e1fb7a86373d41ea304567ce7` |
| 冻结控制器 SHA-256 | `c230a772b70ea399995aeb2b40d383d16d2805b192ae0ffb3dae4eeea9b37be8` |
| 新增/复用/恒等 N/A | 30 / 9 / 3 |
| 当前状态 | 已启动；固定队列自动运行中 |
