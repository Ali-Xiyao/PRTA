# ReXGradient 冻结对比补充结果

## 当前状态

截至 2026-08-20，ReXGradient 的正式 Slim-S1 三 Seed 外部评估已经封存；追加的
冻结配置对比目前只完成 `F01-DMW0-S28` 一个单元。当前没有其他 ReXGradient
对比推理在运行。本地 GPU 上仍在执行的任务属于 Phase20 label-noise 主队列，
不属于本补充比较。

本补充属于看到 Slim-S1 外部结果后追加的 `post-hoc fixed-config comparison`：
F01 checkpoint、标签映射、严格去重结果、缓存、推理参数与指标均在运行前固定，
没有使用 ReXGradient 训练、微调、选择 checkpoint 或调整阈值。

## 同 Seed、同队列结果

两行使用完全相同的 203 个观察、142 名患者、标签清单、排除清单和指标实现。

| 方法 | Seed | 患者平衡 Macro-F1 | 患者平衡 Balanced Accuracy | 患者平衡 ODER |
|---|---:|---:|---:|---:|
| Slim-S1 | 28 | 0.172982 | **0.255463** | **0.071596** |
| F01-DMW0 | 28 | **0.225934** | 0.250225 | 0.077297 |
| F01 − Slim-S1 | 28 | +0.052951 | −0.005238 | +0.005701 |

F01 的同 Seed Macro-F1 高于 Slim-S1，但 balanced accuracy 更低且 ODER 更高；两者均有至少
一个类别召回率为零，绝对泛化性能仍然较弱。因此这不是“F01 已经优于 Slim-S1”
的正式三 Seed结论，而是提示外部低性能可能同时包含显著域/标签偏移和
Slim-S1 特有的 OOD 敏感性。

### F01-S28 类别表现

| 类别 | 患者平衡 F1 | 患者平衡召回率 |
|---|---:|---:|
| Stable | 0.722414 | 0.594105 |
| Improved | 0.021293 | 0.016756 |
| Worse | 0.295833 | 0.244660 |
| New | 0.090129 | 0.395604 |
| Resolved | 0.000000 | 0.000000 |

## 补充矩阵完成度

| 系统 | 当前 ReXGradient 状态 | 说明 |
|---|---|---|
| Slim-S1 | 3/3 Seed，正式封存 | 原始一次性外部主评估 |
| F01-DMW0 | 1/3 Seed | 仅 S28 checkpoint 当前可用 |
| F02-DMW0 | 0/3 Seed | 等待正式 checkpoint 到位 |
| Current-only / B401 | 0/3 Seed | 历史私有 checkpoint 已按清理合同删除，需重建 |
| Siamese / B402 | 0/3 Seed | 历史私有 checkpoint 已按清理合同删除，需重建 |
| TILA8 | 0/3 Seed | 历史私有 checkpoint 已按清理合同删除，需重建 |

正式比较至少需要先补齐 F01/F02 三 Seed。在其余固定配置对比器也具有重新构建的
checkpoint 后，可以复用相同外部队列各运行一次；不得根据本结果调整结构、阈值
或挑选 Seed。

## Git-safe 证据身份

- 外部协议 SHA-256：`66a39cfb8f792f524fcb418f2c454649cc3f567a537d71c03805c39558a3a754`
- F01-S28 config SHA-256：`d0ef2bc3ac10d87c62c9875346b81730280265e2df728edaa842eee9ea977167`
- F01-S28 checkpoint SHA-256：`e75db5c39653e7b03327e1784e20b4fdb1ef326adf1a961fde72aa3a1efb136a`
- F01-S28 推理 receipt SHA-256：`6d77b5d9c0358fd99fe10c395ce7abb9b4369367f4a4540ada0527549bf79e85`
- Slim-S1-S28 推理 receipt SHA-256：`450f3df6a5f8a2f97e562933a4bedcab4f76ce5d3d729a3a1dddbab8b6b1e3dd`

仓库只保存本页和聚合 JSON；checkpoint、患者级预测、影像、报告、缓存、原始日志
及本机运行路径均不进入 Git。
