# Information Fusion 方法

## 任务定义

给定患者当前胸片表示、既往胸片表示和目标 finding 文本，预测五类纵向状态：
Stable、Improved、Worse、New、Resolved。开发集包含 2,427 名患者的 11,201 条
观察；所有统计以患者为聚类单位，避免把同一患者多条记录视为独立样本。

## Full V2 的信息流

论文方法部分建议把 V2 描述为四个相互联系的层次：

1. **Finding-conditioned visual query**：finding 语义决定视觉路径应该关注和
   比较的异常/解剖证据。
2. **Cross-time alignment**：使用跨时间注意力将 prior 表示与 current 查询对齐，
   避免直接比较未对齐 token。
3. **Temporal relation residual**：显式构造 prior-current relation，并以 residual
   形式注入 transition representation。
4. **Training-time semantic and directional constraints**：prototype classification、
   matched-hard CMCP、state anchoring、DMW 与 ODC 共同约束语义、历史特异性和
   方向一致性。

不要把 Tail8 写成“只取最后 8 个 token”。Tail8 是冻结的 adapter/scope 配置，
应按代码与原执行手册中的修正定义描述。

## 消融与融合对照

| ID | 论文名称 | 相对 Full V2 的唯一变化 |
|---|---|---|
| IF-A01 | w/o visual finding query | 视觉路径 finding query 置零；prototype/CMCP 保留 |
| IF-A02 | w/o cross-time attention | `aligned_prior = prior`，不执行 cross-attention |
| IF-A03 | w/o temporal relation residual | `transition_source = current` |
| IF-A04 | w/o state anchoring | state preservation loss 置零，state branch 保留 |
| IF-A05 | w/o directional regularization | DMW=0 且 ODC=0 |
| IF-A06 | w/o prototype classification | prototype loss 置零，CMCP 保留 |
| IF-A08 | random CMCP | matched-hard negative 换为确定性合法随机 negative |
| IF-A10 | w/o DMW | DMW=0，ODC 保留 |
| IF-A11 | w/o ODC | ODC=0，DMW 保留 |
| IF-F01 | early token concatenation | prior/current tokens 拼接后统一 attention/pooling |
| IF-F02 | symmetric cross-attention | prior→current 与 current→prior 双向 attention 后池化 |

IF-A07 等价于已冻结 V1，IF-A09 等价于已冻结 V0，因此复用旧证据而不重复训练。

## 公平性契约

所有新变体固定使用：

- 相同 cleaned Train/Dev；
- 相同 backbone、Tail8 scope 和 finding encoder；
- 相同 batch、学习率、EMA、early stopping 和 class-balanced focal loss；
- Seeds 17、28、43；
- 不根据中间 Seed 或单个变体的结果改变后续矩阵；
- Internal-test/Gold 始终关闭。

## PRIOR 受控干预

对每个冻结 checkpoint 导出四个患者/观察严格对齐的预测块：

| 条件 | 定义 | 目的 |
|---|---|---|
| true | 使用真实患者历史 | 参照性能 |
| matched-hard | 同 finding、不同患者/标签的困难历史 | 历史特异性 |
| null | 移除/归零历史条件 | 历史依赖性 |
| reversed | 反转历史时序条件 | 方向敏感性 |

每块均包含 11,201 行，记录匿名 patient ID、observation ID、target 和 prediction；
论文资料包只保存聚合统计，不复制这些患者级行。

## 统计分析

- 主结果：三 Seed mean ± sample SD。
- 配对比较：Full V2 与每个新变体进行 patient-cluster paired bootstrap。
- 重采样：每次有放回抽取 2,427 个患者簇，患者内观察共同进入样本。
- Replicates：10,000；固定 RNG seed `20260814`。
- 报告：ΔMacro-F1、ΔBalanced Accuracy、ΔODER、95% percentile CI 和 empirical
  two-sided p。
- Δ 定义为 `V2 − variant`；对于 ODER，负值表示 V2 的方向错误率更低。
- 三个训练 Seed 作为固定 confirmatory blocks，在每次患者重采样内分别计算后
  再取 seed 平均。

## 冻结与审计

训练矩阵、诊断预测和 bootstrap 均由不可变 receipt 与 SHA256 绑定。33 个 IF
诊断单元的 true-PRIOR Macro-F1 与相应训练最佳 Dev Macro-F1 精确一致；正式
bootstrap 读取 0 次 protected/Internal-test/Gold outcome，且没有执行模型选择。
