# PRTA-CXR-Slim-S1 最终主线与重跑矩阵

## 最终决定

最终投稿主线锁定为 `Slim-S1`：保留 finding conditioning、cross-time alignment、
temporal relation residual、state anchor 0.025、ODC 0.05、matched-hard CMCP 0.01
和 Tail8/H0；删除 standalone Prototype CE 与 DMW。

这不是从 official Dev 二次选模型。S1 来自已经冻结并完成的 Train-only Slim
矩阵；本轮 full Train / official Dev 实验只做确认与论文证据补全。

## 重跑盘点

| 类型 | 内容 | 结论 |
|---|---|---|
| 继承 | IF-A10 作为 S0、TILA8、Current-only、Siamese | 不重复训练 |
| 新训练 | full S1、精确损失/结构消融、F01/F02-DMW0 | 必须重跑 |
| 新训练 | source-held、scaling、symmetric/plausible noise | 必须按 S1 重跑 |
| 新推理 | 模态压力、校准/选择性预测、亚组、效率/剪枝、安全路由 | full S1 checkpoint 后执行 |
| 历史保留 | V2 及其既有表格/诊断 | 只作开发父方法证据 |
| 延后 | 外部验证 | 数据合同解决后最后执行 |
| 封存 | Internal-test、Gold、医生人工 | 本阶段不做 |

新训练固定 63 单元：S1 3、loss ablation 9、structural ablation 9、F01/F02-
DMW0 6、source-held 6、scaling 12、label noise 18。Seeds 固定为 17/28/43。

## 论文写法

当前可写：“Train-only 模块选择按冻结容差选择了更精简的 S1；随后在 full Train /
official Dev 上进行独立确认与可信性重评估。”在 Phase20 finalizer 完成前，不得写
“S1 在 official Dev 优于 S0/V2”，也不得把 Slim 的 0.560520 当成最终主表数字。

完整机器协议见
[Slim-S1 最终主线锁定与确认实验协议](../docs/PRTA_CXR_Slim-S1最终主线锁定与确认实验协议_CN.md)。
