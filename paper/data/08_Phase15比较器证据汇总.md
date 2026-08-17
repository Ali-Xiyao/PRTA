# Phase 15 比较器证据汇总

## 完成状态

- GPU 矩阵：16/16（12 个三 Seed true-PRIOR 概率导出 + 4 个 Seed43 同 A800 效率）。
- CPU 聚合：4/4 系统校准 + 4/4 系统描述性亚组。
- Seeds：17、28、43；每 Seed 11,201 个 frozen Dev 观察。
- 正式读取：Internal-test 0，Gold 0，protected outcome 0。
- 本地可复算运行时：`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\phase15_comparator_evidence_20260816_v1`。

## 完整 Markdown

| 系统 | 校准与选择性预测 | 描述性亚组 |
|---|---|---|
| B401 | [完整表](phase15/B401_calibration.md) | [完整表](phase15/B401_subgroups.md) |
| TILA8 | [完整表](phase15/TILA8_calibration.md) | [完整表](phase15/TILA8_subgroups.md) |
| IF-F01 | [完整表](phase15/IF-F01_calibration.md) | [完整表](phase15/IF-F01_subgroups.md) |
| IF-F02 | [完整表](phase15/IF-F02_calibration.md) | [完整表](phase15/IF-F02_subgroups.md) |

## SHA-256（Markdown）

| 文件 | SHA-256 |
|---|---|
| B401_calibration.md | `381e23efe3056154e849458d248072023fe5dd76e616bf13e14ee717c78d2832` |
| B401_subgroups.md | `76a392f68d7a0b7e5acc698acfff45cfaeae16eb2fd54b75d21bfac469e986f3` |
| TILA8_calibration.md | `f20bd9a235b2231d7f1f11a4a233328de96c517fd7d01f917a3a9057f20558b8` |
| TILA8_subgroups.md | `506c09c7b8027c4f64580fb6f7bcf2480d88b2d157004e52cf40ff8689919b74` |
| IF-F01_calibration.md | `065ea5ba0c5a3f7855b2a989cabcb6c3d5a2639584a8adee9f6ce78eb1b4cee0` |
| IF-F01_subgroups.md | `339a9f21aeb413d1453a35bad5501b3a4886c1aae781ddaf5a177fff4b28924b` |
| IF-F02_calibration.md | `d4453d66b6ed8b4fea6ed07b472257a01451fcb61f56b21c79b73e81f5eb0adf` |
| IF-F02_subgroups.md | `97ba3f741cbfe0944d616a53d6bb6ad11264fa28ab0e97f0a3cdad60619e1e56` |

## 解释限制

所有结果均为冻结 Dev characterization；亚组没有确认性 p 值，效率仅覆盖预载缓存
特征后的模型计算，不含影像解码、视觉编码器全流程或临床工作流延迟。
