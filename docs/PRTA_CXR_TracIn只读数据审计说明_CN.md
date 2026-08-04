# PRTA-CXR 全量近似 TracIn 只读数据审计说明

## 1. 定位与结论边界

本审计是 `STOP_DEVELOPMENT_GATE` 之后的独立数据质量检查，不会改变该
STOP，也不产生新的科学 GO/HOLD。所有命中结果只能称为“高风险候选”，
不能称为已证明错标、已证明有害或删除后必然提升指标。

审计只允许读取开放的 91,065 条 Train 和 16,666 条 Dev。Internal-test、
Gold、封存标签、封存报告和封存预测均不属于输入面：程序参数没有这些入口，
路径防火墙会在文件打开前拒绝相关拼写，最终 receipt 的封存读取计数必须为 0。

审计程序没有训练循环或参数更新调用，不会修改标签、样本、患者划分、缓存、
源 manifest 或检查点，也不会执行删除样本后的反事实重训。

## 2. 冻结输入

三条轨迹严格按 seed 分开：

| Seed | 冻结运行 | 检查点 |
|---:|---|---|
| 17 | M302-CBF | `best.pt`、`last.pt` |
| 29 | M304-S29 | `best.pt`、`last.pt` |
| 43 | M304-S43 | `best.pt`、`last.pt` |

不同 seed 的检查点贡献不会相加成同一条训练轨迹。每个 seed 内先合并自己的
best/last，再在“来源 × Luna 标签”层内转为百分位，最终使用三 seed 稳定性
判定风险层级。因为每条轨迹只有两个稀疏检查点，交付名称固定为“近似
TracIn”。

## 3. 计算方法

1. 三个 best checkpoint 对全部 Dev 推理，保存预测、置信度、真实标签 NLL、
   方向相反错误和 seed 分歧。
2. 从 Dev 错误中按“来源 × 五类 Luna 标签”各取 30 条，共 300 条探针；排序
   顺序依次为方向相反错误、至少两个 seed 错误、平均 NLL、seed 分歧和稳定
   sample-ID 次序。
3. Captum 0.8 `TracInCPFast` 计算分类器最后线性层的精确梯度点积。程序按
   checkpoint 外循环流式处理，不保留 300 × 91,065 的完整矩阵，并分别累加
   signed、positive、negative 和 self-influence。
4. 对分类头和四个 adapter 计算所有 300 个探针的合计梯度方向。由于当前
   PyTorch/CUDA efficient-attention 不支持 forward-mode AD，复核分支使用该
   方向上的对称中心有限差分；它只负责排序稳定性确认，Captum 末层结果仍是
   主影响指标。
5. Adapter 与末层在层内 Top 5% 的中位重叠若低于 60%，只标记
   `UNSTABLE_INFLUENCE`，不得强化为“有害数据”结论。

影响符号按 Dev 真实标签损失定义：负向 opponent 是主要可能有害指标；正向
proponent 单独保存，不能把两者绝对值混为一个分数。

## 4. 风险层级

- Tier A：至少两个 seed 的负向影响进入本层前 5%，且 Self-influence 前
  10% 或至少两个 seed 误分类。
- Tier B：至少两个 seed 的负向影响前 5%，或至少两个 seed 的
  Self-influence 前 5%。
- Tier C：高损失、高 seed 分歧、时间/配对/图像结构异常，或 Adapter 与末层
  排序不稳定，但不满足 Tier A/B。
- Context：其余样本；仍逐条保留在全量表。

Dev 没有训练样本影响分数，因此只按重复错误、高 NLL、三 seed 分歧和结构
异常进入 Tier C；其余为 Context。

## 5. 私有交付物

真实日期、样本 ID、patient hash、study/image ID、原始路径、报告和逐病例
分数只写入 Git 外部的私有输出目录：

- `train_all_scores.csv`：91,065 条；
- `dev_all_scores.csv`：16,666 条；
- `all_flagged_candidates.csv`：全部 Tier A/B/C，无 Top-K；
- `PRTA_CXR_TracIn全部高风险样本内部审计.md`：逐条内部复核文档；
- `case_details.jsonl`：全部候选完整内部字段；
- `aggregate_summary.json`：无病例 ID/日期/路径/报告的聚合统计；
- `audit_receipt.json`：输入、代码和输出哈希、数量守恒、封存读取计数。

Git 只允许保存实现、测试、本文档、无身份聚合数量和私有输出哈希；不得提交
上述逐病例文件或 `_work` 中间件，也不得推送云端。

## 6. 执行与断点续跑

入口为 `scripts/14_run_tracin_audit.py`，阶段依次为 `dev`、`probes`、三个
`seed` 和 `assemble`。每个 seed 的 Train 预测、best contribution、last
contribution 分开原子保存；`--resume` 只在完整输入哈希契约一致时复用。

`scripts/15_keep_tracin_audit.py` 是显存安全 keeper。它先等待两张卡低于配置
阈值，再并行执行 Seed 17/29，随后执行 Seed 43 并自动 assemble。任何子进程
失败都会保留日志与已完成 contribution，keeper 转为 HOLD，不删除失败运行。

验收必须同时通过：数量守恒、sample-ID 唯一与顺序映射、无 NaN、六个检查点
前后哈希一致、Captum 与直接梯度点积一致、合成错标符号测试、Adapter 中心
差分与直接梯度点积一致、训练调用静态扫描，以及封存路径打开次数为 0。
