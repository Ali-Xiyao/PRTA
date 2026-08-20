# Phase20 阶段结果与 ReXGradient 外部验证中期汇总

> 状态：2026-08-20 中期快照。只纳入 terminal PASS 且三 Seed 齐全的聚合回执；
> Phase20 全局 finalizer 尚未运行，因此本页不得直接作为投稿终表。患者级预测、
> checkpoint、原始日志、Internal-test、Gold 和医生人工数据均未纳入。

## 当前判断

内部证据总体乐观：冻结的 full-Train `Slim-S1` 稳定复现历史 V2 的性能区间，
三 Seed 方差较小；finding conditioning 与 relation residual 的结构消融出现大幅、
跨 Seed 一致的退化；数据量曲线单调改善；正确 PRIOR 相对 matched-wrong PRIOR
保持稳定优势。

外部证据必须谨慎：ReXGradient 正式 public test 已按一次性封存协议完成，但
绝对性能偏低且有类别召回为零。当前结果能证明评估链真实、可审计，不能支持
“跨域泛化良好”或“临床可迁移”的强结论。

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

## ReXGradient 正式外部验证

协议状态：validation 与一次性 public-test finalizer 均为 terminal PASS；public test
仅访问一次，未做 checkpoint 重新选择、阈值调优或结果驱动协议修改。

| 指标 | 结果 |
|---|---:|
| Public-test rows / patients | 203 / 142 |
| 三 Seed patient-balanced Macro-F1 | **0.193942 ± 0.018689** |
| Ensemble ordinary Macro-F1 | 0.196790 |
| Ensemble patient-balanced Macro-F1 | 0.200965 |
| Ensemble patient-balanced balanced accuracy | 0.291736 |
| Ensemble patient-balanced ODER | 0.097418 |
| Ensemble min class recall | **0.000000** |
| Patient-cluster bootstrap Macro-F1 95% CI | [0.162511, 0.240389] |

该外部结果的积极面是三 Seed、严格去重、冻结映射、患者聚类统计与一次性测试协议
均真实完成。风险面是绝对性能低、类别不均衡明显、至少一个类别没有被有效识别，
且 ODER 显著高于内部 Dev。论文应将其写成跨数据源标签语义、病例谱和纵向报告风格
迁移困难的直接证据，不应包装成外部成功。

## 尚不能收口的部分

- label-noise：5%/10% plausible 已有服务器两 Seed，但本地 Seed43 仍在队列；
  20% 与 symmetric 系列仍在运行，暂不形成三 Seed结论；
- source-held-out：各源训练表面已完成，但跨源 evaluation receipt 尚未全部 terminal，
  不使用训练表面高低来宣称跨源泛化；
- Phase20 全局结果：当前约 68/88 job terminal PASS，四卡仍在推进；
- 配对 bootstrap、效应量、95% CI、p 值及论文终表必须等待全局 finalizer。

## 论文叙事建议

1. 主张 Slim-S1 在删除 standalone Prototype CE 后保持了 full-Train 内部性能与方向
   错误控制，同时以更精简结构复现历史 V2 区间。
2. 把 finding conditioning、relation residual 和数据规模曲线作为最强正面证据。
3. 对 CMCP、ODC、state anchor 使用“较小/待配对统计确认”的措辞。
4. 明确承认 F02 在 Macro-F1 上更高，但 Slim-S1 的 ODER 更好；避免全面 SOTA 叙事。
5. 把 ReXGradient 写成严格外部压力测试揭示的泛化缺口，并将标签映射、样本规模、
   类别不均衡与跨域语义差异列为主要局限。

综合判断：**内部机制与主线结果乐观，外部可迁移性不乐观；整篇论文仍有价值，
但价值更适合落在“方向感知纵向融合机制 + 严格失败边界”，而不是“已解决跨域临床
泛化”。**
