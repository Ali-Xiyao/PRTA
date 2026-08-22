# Figure S3：Query 特异性与 Attention 稳定性

## 写作结论

固定完全相同的 prior/current CXR 后，finding query 改变造成的 joint attention-flow
JSD 为 0.577177 [0.568510, 0.585631]，明显高于同 query 的跨 Seed 变化
0.415839 [0.413229, 0.418475]。预先冻结的 CI 非重叠门通过，因此可以写
“supports query-sensitive routing”。不要写成 finding query 提供了因果解释、病灶
分割或医生确认的 localization。

## 直接引用

| 项目 | 数值 |
| --- | ---: |
| Eligible pairs / rows / patient clusters | 1,743 / 3,791 / 600 |
| Between-query units | 7,182 |
| Between-seed units | 11,373 |
| Joint between-query | 0.577177 [0.568510, 0.585631] |
| Joint between-seed | 0.415839 [0.413229, 0.418475] |
| Bootstrap | patient-clustered, 10,000, RNG 20260818 |

权威机器入口是 `evidence/20_FigureS3_query_sensitivity_aggregate.json`；完整协议、三个
map 结果、图注与哈希见仓库 `paper/21_FigureS3_Query_specificity_and_attention_stability_CN.md`。

## 图件边界

内部像素图已经生成并通过 QA，SHA-256 为
`1757ae753f9e13f2468e866409e87e077c955d7fe10ea422b6d7455bee6651ee`。
因为病例来自 MIMIC-CXR-JPG，未取得单独公开像素许可前，不要从 Git 缺图误判为
“实验未完成”，也不要自行使用 Grad-CAM、合成影像或手绘热图替代。
