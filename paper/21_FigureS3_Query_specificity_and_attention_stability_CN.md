# Figure S3：Query specificity and attention stability

## 结论

Figure S3 已按预注册式协议完成。固定完全相同的 prior/current CXR 后，更换 finding
query 所产生的 attention-flow 差异，明显高于保持 query 不变而只更换训练 Seed 的
差异。按事先冻结的非重叠置信区间门，可以写作：**结果支持 query-sensitive
routing**。这是一项模型机制证据，不等于临床因果解释、病灶分割或医生确认定位。

## 冻结协议

- 数据范围：Dev 中所有 finding×progression support≥100 的 multi-finding pair；
- 汇总不按预测正确与否筛选，避免产生有利的结果选择；
- 定性病例在查看影像/attention 前，用 salt `PRTA_ATTN_20260818` 排序，并要求
  S17/S28/S43 对展示 finding 均一致预测正确；优先选择含不同 progression state 的
  pair；
- 最终汇总含 1,743 个 pair、3,791 个 finding rows、600 个 patient clusters；
- 定性 pair 固定展示 `Lung Opacity / New` 与
  `Enlarged Cardiomediastinum / Stable`，使用 seed 43；
- 原生 post-softmax per-head MHA attention，`need_weights=True`、
  `average_attn_weights=False`，去除 CLS 后在 196 patches 上重新归一化；
- 批量 attention replay 绝对误差门为 `2e-4`，独立五类概率 replay 门为 `2e-5`；
  三 Seed 最大概率漂移均不超过 `3.70e-6`。

## JSD 与 bootstrap

主分布为等权拼接：

```text
flow = concat(0.5 * r_current, 0.5 * r_prior)
```

Jensen–Shannon divergence 使用 base 2，范围 `[0,1]`。另外分别对 196 维
`r_current` 和 `r_prior` 做敏感性分析。Between-query 是同 pair、同 Seed、不同
finding；between-seed 是同 pair、同 finding、不同 Seed。中位数的 95% CI 以患者为
cluster 重采样 10,000 次，RNG seed=`20260818`。

| Map | Between-query median [95% CI] | Between-seed median [95% CI] |
| --- | ---: | ---: |
| Joint flow（主分析） | 0.577177 [0.568510, 0.585631] | 0.415839 [0.413229, 0.418475] |
| Current relevance | 0.751727 [0.742347, 0.759352] | 0.575801 [0.569935, 0.581347] |
| Prior propagated flow | 0.386032 [0.374111, 0.397670] | 0.272458 [0.269454, 0.275371] |

主分析含 7,182 个 between-query 与 11,373 个 between-seed comparison units。预设
claim gate 为 `between-query lower CI > between-seed upper CI`；实际为
`0.568510 > 0.418475`，因此通过。

## 定性图与版式

内部受控图为两行：上行为 prior propagated flow，下行为 current relevance；每列只
更换 finding query。所有 query 列固定 seed-43 checkpoint、同一 pair、同一
Resize(224)+CenterCrop(224)、bilinear interpolation、magma、alpha=0.40，并共用
p99 clipping=`0.08029880494` 与单一 colorbar。右侧 boxplot 汇总全量 pair，并标注
patient-clustered CI。

## Artifact 身份与公开边界

- cohort receipt SHA-256：
  `6b6aff99a61a907033d425279b4ebf0583a19bd0f5b056f6d3420b6b48b6594f`
- S17/S28/S43 checkpoints：
  `42bdefcf...bb77` / `02cee988...ab4c` / `d7673c8c...2140`
- private JSD units SHA-256：
  `04a71446b4931408d96200fb38eb6bf4689d963f6597b7907f05d790f36e329e`
- private Figure S3 PNG SHA-256：
  `1757ae753f9e13f2468e866409e87e077c955d7fe10ea422b6d7455bee6651ee`
- Git-safe aggregate：`data/20_FigureS3_query_sensitivity_aggregate.json`
- 统一 attention provenance：`figures/attention_export_manifest.json`

定性病例来自 MIMIC-CXR-JPG。当前没有单独的像素再分发许可，因此请求的
`figures/supp_figure_s3_query_sensitivity.png` 已在受控内部环境生成，但不能提交到
公开 GitHub；公开仓库保存代码、统计、哈希、图注和 restricted notice。

## 图注草案

**Figure S3 | Query specificity and attention stability.** Holding the prior
and current radiographs fixed, native post-softmax attention flow changed with
the finding query. Across all reportable multi-finding development pairs,
between-query divergence exceeded same-query between-seed variation. Medians
are accompanied by 95% confidence intervals from 10,000 patient-clustered
bootstrap resamples. The result supports query-sensitive routing but does not
establish clinically validated localization or causal explanation.
