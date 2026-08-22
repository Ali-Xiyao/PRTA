# Phase20 阶段结果中期汇总

> **历史快照**：本页已由 2026-08-21 的
> [Phase20-A 正式收口与三 Seed 汇总](15_Phase20-A正式收口与三Seed汇总_CN.md)
> 取代。以下文字保留用于审计当时的中期判断，不再代表当前完成状态。

> 状态：2026-08-20 中期快照。只纳入 terminal PASS 且三 Seed 齐全的聚合回执；
> Phase20 全局 finalizer 尚未运行，因此本页不得直接作为投稿终表。患者级预测、
> checkpoint、原始日志、Internal-test、Gold 和医生人工数据均未纳入。

> **终态补记（2026-08-22）**：当时所列 source-held、label-noise、comparator、
> B1/B2 与全局 finalizer 后续均已完成；最终状态以 `paper/17` 为准。

## 当前判断

冻结的 full-Train `Slim-S1` 稳定复现历史 V2 的性能区间，三 Seed 方差较小；
finding conditioning 与 relation residual 的结构消融出现大幅、跨 Seed 一致的
退化；数据量曲线单调改善；正确 PRIOR 相对 matched-wrong PRIOR 保持稳定优势。

最终方法继续锁定为 **PRTA-CXR**（冻结配置身份 `Slim-S1`）。当时后续只补齐跨数据来源泛化、label-noise、
比较器与可信性统计，不再根据结果修改方法、权重、Seed 或阈值。

## full-Train Slim-S1 三 Seed

| 指标 | mean ± sample SD |
|---|---:|
| Official-Dev Macro-F1 ↑ | **0.552013 ± 0.001096** |
| Balanced accuracy ↑ | **0.552594 ± 0.002461** |
| Min class recall ↑ | **0.486625 ± 0.006074** |
| ODER ↓ | **0.003779 ± 0.000287** |
| NLL ↓ | **0.914677 ± 0.002709** |
| Patient-balanced Macro-F1 ↑ | **0.579514 ± 0.000541** |
| True − matched-wrong PRIOR Macro-F1 gap ↑ | **0.175667 ± 0.001147** |

历史 Full V2 的 Macro-F1 为 `0.551821 ± 0.006574`、ODER 为
`0.003720 ± 0.000743`。新 Slim-S1 的 Macro-F1 位于同一水平，方差更小；ODER
也处于同一量级。该比较只用于说明复现区间，不替代完成后的正式配对统计。

## 已齐全的三 Seed 主消融与融合对比

| 变体 | Macro-F1 ↑ | Δ vs Slim-S1 | ODER ↓ |
|---|---:|---:|---:|
| **Slim-S1** | **0.552013 ± 0.001096** | — | **0.003779 ± 0.000287** |
| w/o CMCP | 0.547637 ± 0.006325 | −0.004376 | 0.003660 ± 0.000966 |
| w/o ODC | 0.548039 ± 0.001053 | −0.003975 | 0.003720 ± 0.000225 |
| w/o state anchor | 0.549878 ± 0.002597 | −0.002135 | 0.003571 ± 0.000155 |
| F01-DMW0 | 0.547761 ± 0.002295 | −0.004252 | 0.005297 ± 0.001003 |
| F02-DMW0 | **0.555738 ± 0.002648** | +0.003724 | 0.004226 ± 0.000492 |
| w/o cross-time alignment | 0.544054 ± 0.001210 | −0.007959 | 0.004583 ± 0.000052 |
| w/o finding conditioning | 0.451827 ± 0.001116 | −0.100187 | 0.006845 ± 0.001035 |
| w/o relation residual | 0.412409 ± 0.000317 | −0.139605 | 0.034521 ± 0.001301 |

阶段性解释：

- finding conditioning 与 relation residual 是最强、最稳定的必要结构证据；
- alignment 提供中等幅度的一致收益；
- CMCP、ODC、state anchor 的单独效应较小，最终必须等待配对 CI/p 值；
- F02-DMW0 的 Macro-F1 高于 Slim-S1，但 ODER 更差，因此 Slim-S1 是面向方向错误
  控制的折中选择，不能写成所有指标全面领先；
- w/o relation 的三 Seed true-minus-wrong PRIOR gap 都为零，提供了关系分支确实承载
  PRIOR/时间方向信息的直接机制证据。

## 数据规模曲线

| full-Train 比例 | Macro-F1 ↑ | ODER ↓ |
|---:|---:|---:|
| 10% | 0.500096 ± 0.000295 | 0.019730 ± 0.001609 |
| 25% | 0.517809 ± 0.001709 | 0.012558 ± 0.000449 |
| 50% | 0.532961 ± 0.002134 | 0.007737 ± 0.000287 |
| 75% | 0.539841 ± 0.002189 | 0.005119 ± 0.001206 |
| 100% / Slim-S1 | 0.552013 ± 0.001096 | 0.003779 ± 0.000287 |

Macro-F1 随数据量严格单调增加，ODER 总体严格下降。这是当前最干净的稳健性证据
之一，也说明模型仍明显受益于更多纵向训练样本，尚未进入性能饱和区。

## 跨数据来源泛化：正文主要泛化实验

正文使用任务和标签空间一致的双向 source-held 评估：

| 训练来源 | 评估来源 | Seeds | 当前状态 |
|---|---|---|---|
| MIMIC-CXR | CheXpert Plus | 17 / 28 / 43 | 训练完成；等待跨源评估回执齐全 |
| CheXpert Plus | MIMIC-CXR | 17 / 28 / 43 | 训练完成；等待跨源评估回执齐全 |

每个方向必须报告 Macro-F1、Balanced Accuracy、ODER、五类 F1/Recall、患者聚类
bootstrap 95% CI，以及 in-domain 与 cross-source 的性能差。由于 source-held 使用
`S1-core / no-CMCP`，公平的 full-source 参考优先使用 `P20-ABL-NOCMCP`，不能只与
带 CMCP 的 full Slim-S1 比较。

该证据只能命名为 **cross-source domain generalization**，不能称为独立外部临床
验证。六个跨源 evaluation receipt 全部 terminal PASS 前，不报告方向性结论。

## 当时尚不能收口的部分（现均已完成）

- label-noise plausible/symmetric 各比例三 Seed 后续已齐全；
- source-held-out 六个跨源 evaluation receipt 后续已 terminal PASS；
- Phase20 全局 finalizer、配对 bootstrap、效应量、95% CI、p 值及论文终表已完成；
- 24-cell 比较器与 B1/B2 可信性证据链均已完成。

## 论文叙事建议

1. 主张 Slim-S1 在删除 standalone Prototype CE 后保持了 full-Train 内部性能与方向
   错误控制，同时以更精简结构复现历史 V2 区间。
2. 把 finding conditioning、relation residual 和数据规模曲线作为最强正面证据。
3. 对 CMCP、ODC、state anchor 使用“较小/待配对统计确认”的措辞。
4. 明确承认 F02 在 Macro-F1 上更高，但 Slim-S1 的 ODER 更好；避免全面 SOTA 叙事。
5. 将双向 MIMIC-CXR/CheXpert Plus source-held 结果作为正文泛化证据，并准确限定为
   跨来源域泛化，不写成独立外部或临床验证。

该中期判断已被最终收口替代；跨来源双向三 Seed评估已经完成。
