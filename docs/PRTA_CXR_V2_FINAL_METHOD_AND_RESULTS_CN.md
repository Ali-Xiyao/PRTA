# PRTA-CXR V2 最终方法与 Train/Dev 结果（唯一权威版本）

> 状态：`FROZEN_MAIN_METHOD_TRAIN_DEV_CONFIRMED_PENDING_INDEPENDENT_UNTOUCHED_TEST`
>
> 冻结日期：2026-08-14
>
> 本文是 PRTA-CXR V2 的唯一论文与仓库结果权威。它只汇总 physician-confirmed cleaned Train/Dev 证据，不包含、复用或推断 Internal-test、Gold 或任何其他受保护结果，也不含患者级预测或私有运行时产物。

## 1. 最终结论与边界

最终主方法正式冻结为：

> **PRTA-CXR V2：Tail8/H0 PRTA + Finding-Conditioned State Anchoring + Cross-Time Transition Representation + Prototype Supervision + Matched-Hard CMCP。**

冻结后的方法关系如下：

| 版本 | 定义 | 最终角色 |
|---|---|---|
| V0 | Tail8/H0 PRTA 核心，不含 prototype 与 CMCP | 核心参照 |
| V1 | V0 + prototype supervision | 预注册回退方法 |
| V2 | V1 + matched-hard CMCP | **冻结主方法** |
| V3 | V2 + learned residual scale | 拒绝，不再扩展 |
| V4 | V3 + PRIOR reliability gate | 拒绝，不再扩展 |
| V5 | V4 + selective state anchor | 拒绝，不再扩展 |
| H4 | 非 H0 的辅助头路线 | 仅附录，不与主方法合并 |

冻结不是基于某一个 seed 的最高点，也不是对结果表逐项挑选。Wave047 按预注册的 Train/Dev 决策规则确认 V2；之后停止结构搜索。本文不宣称 V2 相对 V0/V1 达到统计显著提升。

## 2. 方法定义

### 2.1 输入、缓存与时序窗口

- 输入为同一患者的 prior CXR、current CXR 与 finding text。
- 图像编码器为冻结的 BiomedCLIP ViT。
- 训练读取冻结的 Block-4 token cache，不微调 backbone。
- 使用最近八次可用历史检查，即 Tail8。
- 标签空间固定为五类：`Stable / Improved / Worse / New / Resolved`。

### 2.2 表征路径

1. Finding conditioning 将文本 finding 注入状态建模。
2. State tokens 保存与当前疾病状态相关的表征。
3. Cross-time transition tokens 表达 prior 到 current 的变化。
4. H0 仅以 transition representation 作为最终分类路径。
5. State tokens 通过训练期约束提供状态保持与锚定，但不应被描述成第二个预测分支。

因此，论文中宜使用“**State-Anchored Transition Representation**”描述 V2，而不宜把 H0 写成双分支预测或双头集成。

### 2.3 训练期辅助监督

- Prototype supervision：对五类变化状态提供类原型约束。
- Matched-hard CMCP：使用预先冻结的 `offline_hard_v1` 匹配图，在相同训练身份下构造 hard counterparts，并施加 margin 约束。
- 类原型和 matched-hard map 仅在训练时使用；部署推理不需要它们。

### 2.4 推理边界

推理时只需要 prior CXR、current CXR 与 finding text。模型不需要患者级检索库、训练样本、类原型文件或 hard map。本文没有执行独立 untouched test；该步骤仍是唯一允许的后续科学评估。

## 3. 冻结配置

| 项目 | 冻结值 |
|---|---:|
| Backbone | frozen BiomedCLIP ViT |
| Cache entry | Block-4 |
| Temporal window | Tail8 |
| Head | H0 |
| Hidden width | 768 |
| Low-rank dimension | 32 |
| Attention heads | 12 |
| State tokens | 20 |
| Transition tokens | 20 |
| Dropout | 0.1 |
| Batch size | 16 |
| Learning rate | 1e-4, constant |
| Weight decay | 0.01 |
| Gradient clip | 1.0 |
| EMA | 0.999 |
| Maximum epochs | 20 |
| Minimum epochs | 6 |
| Early-stop patience | 4 |
| Early-stop minimum delta | 0.001 |
| Formal seeds | 17 / 28 / 43 |

### 3.1 冻结损失

| 损失/机制 | 冻结值 |
|---|---:|
| Class-balanced focal | `gamma=1`, `beta=0.9999` |
| Direction margin | 0.01 |
| ODC | 0.05 |
| State preservation | 0.025 |
| Prototype supervision | 0.01 |
| Prototype temperature | 0.07 |
| Matched-hard CMCP | 0.01 |
| CMCP margin | 0.2 |
| CMCP matching | `offline_hard_v1` |
| Alignment / batch InfoNCE | 0 |
| Temporal inversion | 0 |
| Branch decorrelation | 0 |
| Learned residual scale | disabled |
| PRIOR reliability gate | disabled |
| Selective state anchor | disabled |

## 4. V0/V1/V2 三 seed Dev 结果

下表为三个正式 seed 的均值 ± 样本标准差。ODER 越低越好，Macro-F1 与 balanced accuracy 越高越好。

| 方法 | Macro-F1 | Balanced accuracy | ODER |
|---|---:|---:|---:|
| V0 | 0.547960 ± 0.003767 | 0.549136 ± 0.004465 | 0.003779 ± 0.000492 |
| V1 | 0.549378 ± 0.003213 | 0.549582 ± 0.003087 | 0.003065 ± 0.000545 |
| **V2** | **0.551821 ± 0.006574** | **0.552606 ± 0.004177** | **0.003720 ± 0.000743** |

### 4.1 每 seed 结果

| 方法 | Seed | Macro-F1 | Balanced accuracy | ODER |
|---|---:|---:|---:|---:|
| V0 | 17 | 0.552193 | — | 0.003750 |
| V0 | 28 | 0.544975 | — | 0.004285 |
| V0 | 43 | 0.546713 | — | 0.003303 |
| V1 | 17 | 0.548981 | — | 0.002946 |
| V1 | 28 | 0.552771 | — | 0.002589 |
| V1 | 43 | 0.546381 | — | 0.003660 |
| V2 | 17 | 0.548093 | — | 0.004553 |
| V2 | 28 | 0.559411 | — | 0.003125 |
| V2 | 43 | 0.547960 | — | 0.003482 |

`—` 表示当前 Git-safe 汇总没有发布该 seed 的该项标量；没有从私有预测块补填。

### 4.2 逐 seed 配对增量

| 对比 | Δ Macro-F1 | Δ ODER |
|---|---:|---:|
| V1 − V0 | +0.001417 ± 0.005708 | −0.000714 ± 0.001030 |
| V2 − V1 | +0.002443 ± 0.003838 | +0.000655 ± 0.000899 |

这些差值说明 prototype 与 matched-hard CMCP 在三 seed 平均上提供了小幅 Macro-F1 增量，但 ODER 不呈单调改善。因此 V2 的结论是“按预注册规则冻结的 Train/Dev 主方法”，不是“所有指标均占优”。

## 5. Wave047 配对患者簇 bootstrap

bootstrap 使用预注册的 patient-cluster paired Dev protocol，10,000 次重采样，RNG seed `20260814`。V2 相对 V0 的结果如下：

| 指标 | 点估计差值 | 95% CI | 双侧 p 值 |
|---|---:|---:|---:|
| Macro-F1 | +0.003861 | [−0.000749, +0.008395] | 0.09999 |
| Balanced accuracy | +0.003469 | [−0.001168, +0.008130] | 0.15158 |
| ODER | −0.000060 | [−0.000743, +0.000620] | 0.87251 |

### 5.1 V2 − V0 类别 F1

| 类别 | 点估计差值 | 95% CI |
|---|---:|---:|
| Stable | +0.001977 | [−0.001125, +0.005182] |
| Improved | +0.003985 | [−0.004401, +0.012363] |
| Worse | +0.004413 | [−0.003787, +0.012638] |
| New | +0.007248 | [−0.001198, +0.015604] |
| Resolved | +0.001680 | [−0.011965, +0.015340] |

所有区间均跨过 0。正确表述是：V2 的点估计方向整体为正，且按照冻结规则被确认为主方法；当前 Dev 证据不足以支持“显著优于 V0”的说法。

## 6. Wave046 原生基线与公平比较器

### 6.1 三 seed 总体指标

| 方法 | Macro-F1 | Balanced accuracy | ODER |
|---|---:|---:|---:|
| B401 Current-only | 0.412872 ± 0.007166 | 0.419796 ± 0.003347 | 0.035116 ± 0.004222 |
| B402 Siamese signed/absolute difference | 0.522895 ± 0.002953 | 0.535741 ± 0.016064 | 0.007053 ± 0.001437 |
| B403 TILA / strong temporal attention Tail4 | 0.524565 ± 0.003460 | 0.534292 ± 0.015098 | 0.006279 ± 0.001690 |
| TILA Tail8 fairness comparator | 0.528645 ± 0.003539 | 0.537958 ± 0.015500 | 0.006339 ± 0.001486 |
| **PRTA-CXR V2 Tail8/H0** | **0.551821 ± 0.006574** | **0.552606 ± 0.004177** | **0.003720 ± 0.000743** |

TILA Tail8 是窗口长度公平比较器，不是 V2 的结构消融。B401–B403 与 TILA Tail8 均独立于 V3–V5 的结构搜索。

### 6.2 基线每 seed 结果

| 方法 | Seed | Macro-F1 | Balanced accuracy | ODER | Hardware |
|---|---:|---:|---:|---:|---|
| B401 | 17 | 0.404719 | 0.419326 | 0.038657 | A800 |
| B401 | 28 | 0.418172 | 0.423353 | 0.036247 | RTX 3090 |
| B401 | 43 | 0.415726 | 0.416708 | 0.030444 | RTX 3090 |
| B402 | 17 | 0.524022 | 0.537757 | 0.006607 | reused terminal local run |
| B402 | 28 | 0.525119 | 0.550701 | 0.008660 | RTX 3090 |
| B402 | 43 | 0.519544 | 0.518765 | 0.005892 | RTX 3090 |
| B403 | 17 | 0.526094 | 0.529336 | 0.005535 | reused terminal local run |
| B403 | 28 | 0.526998 | 0.551245 | 0.008214 | reused terminal local run |
| B403 | 43 | 0.520605 | 0.522296 | 0.005089 | reused terminal local run |
| TILA Tail8 | 17 | 0.528611 | 0.525599 | 0.005267 | RTX 3090 |
| TILA Tail8 | 28 | 0.532200 | 0.555348 | 0.008035 | RTX 3090 |
| TILA Tail8 | 43 | 0.525123 | 0.532928 | 0.005714 | A800 |

### 6.3 基线类别指标（三 seed 均值 ± 标准差）

| 方法 | 类别 | F1 | Recall |
|---|---|---:|---:|
| B401 | Stable | 0.696193 ± 0.004435 | 0.702659 ± 0.013591 |
| B401 | Improved | 0.300259 ± 0.024330 | 0.283688 ± 0.057826 |
| B401 | Worse | 0.408090 ± 0.007585 | 0.437867 ± 0.025505 |
| B401 | New | 0.250424 ± 0.048808 | 0.235534 ± 0.079745 |
| B401 | Resolved | 0.409396 ± 0.011763 | 0.439230 ± 0.021761 |
| B402 | Stable | 0.731477 ± 0.009969 | 0.744181 ± 0.032505 |
| B402 | Improved | 0.487238 ± 0.003844 | 0.483559 ± 0.011623 |
| B402 | Worse | 0.443551 ± 0.035821 | 0.399111 ± 0.070888 |
| B402 | New | 0.507525 ± 0.006513 | 0.525981 ± 0.034391 |
| B402 | Resolved | 0.444682 ± 0.027290 | 0.525872 ± 0.054071 |
| B403 | Stable | 0.737116 ± 0.005289 | 0.764251 ± 0.025280 |
| B403 | Improved | 0.466872 ± 0.011412 | 0.438427 ± 0.008382 |
| B403 | Worse | 0.459292 ± 0.030674 | 0.420800 ± 0.059511 |
| B403 | New | 0.515440 ± 0.004915 | 0.506467 ± 0.044311 |
| B403 | Resolved | 0.444107 ± 0.021517 | 0.541516 ± 0.043770 |
| TILA Tail8 | Stable | 0.737717 ± 0.005642 | 0.762758 ± 0.021226 |
| TILA Tail8 | Improved | 0.485626 ± 0.012175 | 0.468515 ± 0.015180 |
| TILA Tail8 | Worse | 0.463812 ± 0.025912 | 0.426489 ± 0.051340 |
| TILA Tail8 | New | 0.508755 ± 0.019348 | 0.491718 ± 0.056202 |
| TILA Tail8 | Resolved | 0.447312 ± 0.009956 | 0.540313 ± 0.056199 |

## 7. PRIOR 机制诊断的正确解释

Wave045 的 V3/V4/V5 checkpoint-only intervention diagnostics 在 `true / matched-hard / null / reversed PRIOR` 条件下全部按冻结协议完成，且没有新增训练或结果选择。它们支持以下有限结论：

- PRIOR 输入会改变模型内部响应与部分预测；
- 额外 residual scale、reliability gate 与 selective anchor 没有形成稳定、可复现的整体收益，因此不进入 V2；
- 这些干预是机制敏感性诊断，不是自然发生的混杂控制实验；
- 不能据此宣称 PRIOR 因果有效、可靠性估计已校准或模型已在独立分布上验证。

## 8. 允许与禁止的论文表述

### 8.1 可支持

- V2 是按预注册 Train/Dev 规则冻结的最终主方法。
- V2 在三 seed Dev 上相对 V0/V1 和原生比较器呈现更高的 Macro-F1 点估计。
- V2 的 matched-hard CMCP 是对 V1 的小幅增量，不应被描述成单独决定性能的组件。
- Tail8/H0 是最终主干；V3–V5 的额外机制未带来稳定贡献。
- 推理只需要影像对与 finding text，训练期原型和 hard map 不进入部署路径。

### 8.2 不可支持

- “V2 显著优于 V0/V1”或“全面优于所有基线”。
- “PRIOR 的作用具有因果性”或“reliability gate 已被验证可靠”。
- “已完成独立测试/外部验证”。
- 将旧 Tail8 方法的 Internal-test/Gold 结果迁移、折算或归属于 V2。
- 继续依据当前 Dev 结果调结构、调权重、挑 seed 或新增结果导向比较。

## 9. 可复现性与审计哈希

| 产物 | SHA-256 / commit |
|---|---|
| Wave045 scientific source | `e4788f028caf9ba2f712a6a13c674738bd7bb740` |
| Wave045 preparation | `0c53524cfdc89d2a112f0fee91c9ee9283aeaa61d8b59e80e5e6a60d458616a5` |
| Matched-hard map | `276f1d4d37f656631bbfc89ad3d9a73f2b6c7c4c4c65787a80bec63cfc23924e` |
| Wave045 finalization receipt | `a91f1c1535a516b2b03917a9c5e6c7660535f64b7a98e11d867f52e9243b64d1` |
| Wave045 progressive aggregate | `b72e11083e265bce41018bf9c4efe364cb2ba8e1c42712a5b2e1f9de5bb19b2b` |
| Wave045 mechanism aggregate | `1120beb2465d121e7e6a9d7db82bace6023d5325474942a61e1872710a174748` |
| Wave046 scientific source | `62235ff46fb26e4ccf05e3c9073188a84ca39119` |
| Wave046 native-baseline aggregate | `9ab86761963805d89e654b3d1a1de1e968bc4032ea036bcdc7ca655b69ef56e1` |
| Wave047 scientific source | `384ecc19645edaf799da62594ee4294a693754f6` |
| Wave047 preparation | `b0b6e81676b701c35b5a36bf159ff6c22f8463a54501529263c7bb0edd67218b` |
| Wave047 candidate aggregate | `fb622508ab636238b1da6b58f3e13ae404b91a9426f6d5cc3e25e2fc6156f3ed` |
| Wave047 bootstrap result/receipt | `18e17e5dc63c97b2fe1cb59854e0d55465c60636b5e207c22659098f3e1cd0eb` |
| Frozen V2 decision receipt | `2d323971ac3f59c13dd4d96e3d2bc919aac117480c53a64d8c9d823c218a409f` |
| Wave046/047 close-out receipt | `a596aad07d970b450eddc55d334ae28695c83e1e68ece0cefcf178444adfc4dd` |

所有正式训练、诊断、bootstrap 与聚合均记录为零 protected reads。Git 中只保留聚合数字、配置与哈希；患者级预测块和私有运行时继续位于 Git 外。

## 10. 后续唯一科学步骤

V2 已冻结，当前阶段不再进行主方法搜索、权重调整、结果导向消融或受保护集预览。若获得单独授权，唯一允许的下一步是：对这个完全冻结的 V2 执行一次独立、未触碰的测试评估，并将其与当前 Train/Dev 证据严格分开报告。
