# 校准曲线与 Finding × Progression 联合热图

## 证据状态

这两张图现在都有真实、可复核的三 Seed 聚合数据，不再需要患者级文件，也不使用
插值或手工补点。权威机器可读入口为
[`data/18_Phase21校准与Finding-Progression联合单元.json`](data/18_Phase21校准与Finding-Progression联合单元.json)，
状态为 `PASS_CALIBRATION_JOINT_CELLS_COMPLETE`。

- 冻结系统：PRTA-CXR（配置身份 `Slim-S1`）；
- Seeds：17、28、43；每 Seed 11,201 条冻结 selection-Dev 记录；
- 数据范围：不打开 Internal-test、Gold、外部数据或医生人工数据；
- Git 只保留聚合 bins/cells，不包含患者标识或患者级预测。

## Reliability curve

JSON 同时保留未校准和五折 cross-fitted temperature scaling 后的 15 个 fixed-width
bins、adaptive equal-count bins 及 5 类 classwise bins。由 fixed-width bins 重构的
ECE 与正式 B1 标量完全一致：

| 状态 | S17 | S28 | S43 | mean ± sample SD |
| --- | ---: | ---: | ---: | ---: |
| 未校准 | 0.031871 | 0.031540 | 0.038273 | 0.033895 ± 0.003795 |
| Cross-fitted calibrated | 0.027947 | 0.030165 | 0.027478 | 0.028530 ± 0.001436 |

绘图点是同一置信区间内三 Seed 的 mean confidence 与 mean accuracy，误差线为
accuracy 的 three-seed sample SD。正式图预声明只连接 `count_mean ≥ 20` 的 bins；
一个 `count_mean=0.33` 的极稀疏 bin 仍完整保留在 JSON，但不进入连线，避免单个样本
造成视觉误导。该门只影响可视化，不改变 ECE 计算。

准确叙事仍是：cross-fitted temperature scaling 改善 ECE，但 NLL 与 AURC 没有同步
改善，因此不能写成“全面改善校准与安全性”。

## Finding × progression heatmap

联合矩阵覆盖 12 findings × 5 progression labels，共 60 个 cell。公开门为每个 cell
`rows ≥ 30` 且 `patients ≥ 20`：37 个 cell 可报告 recall/置信度/方向错误率，23 个
稀疏 cell 仅保留 rows/patients 和 `suppressed=true`，热图显示为灰色破折号。
Rows/patients 是三个 Seed 共用的同一冻结 cohort 计数，不能乘以三。

热图说明误差高度依赖 finding 与 progression 的组合。例如 Cardiomegaly Stable
recall 接近 0.99，但 Cardiomegaly Improved/Worse 很低；Pneumothorax Stable 约 0.70，
Worse 为 0。它们是描述性 error characterization，不是公平性检验、因果结论或临床
安全保证。稀疏 cell 不能被补零，也不能用边际 finding/progression 数字代替。

## 图与复现入口

- [Reliability PNG](figures/PRTA_CXR_reliability_curve.png) / [SVG](figures/PRTA_CXR_reliability_curve.svg)
- [Joint heatmap PNG](figures/PRTA_CXR_finding_progression_heatmap.png) / [SVG](figures/PRTA_CXR_finding_progression_heatmap.svg)
- 聚合生成：`scripts/104_build_calibration_joint_cells.py`
- 聚合绘图：`scripts/105_plot_calibration_joint_cells.py`
- Figure manifest：`figures/aggregate_figure_manifest.json`

论文图注必须注明：three-seed mean bins、Dev descriptive analysis、cell suppression
threshold，以及 gray cells 为 suppressed 而不是 recall=0。
