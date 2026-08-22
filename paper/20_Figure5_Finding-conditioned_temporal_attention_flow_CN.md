# Figure 5：Finding-conditioned temporal attention flow

## 结论

真实 seed-43 attention 已按冻结协议导出，内部 2×5 论文图已经生成并通过视觉 QA。
这不是 Grad-CAM，也不是人工绘制的热图：`W_align` 与 `W_trans` 都来自模型原生
`MultiheadAttention` 的 post-softmax、per-head 权重。

科学状态为 PASS；公开发布状态暂为 BLOCKED。原因是两个锁定病例均来自受控
MIMIC-CXR-JPG，当前项目没有单独的书面 artifact-license receipt，不能把四张源
CXR 或包含这些像素的 PNG 提交到公开 GitHub。

## 冻结案例协议

案例在查看影像或 attention 前固定：

1. 定性图使用 seed 43；
2. seeds 17/28/43 预测一致且等于 reference label；
3. finding×progression support≥100；
4. 在 support 与一致正确门之后，按 reference progression class 计算 seed-43
   predicted-class confidence 的 q10/q90，只保留中间 80%；
5. improvement family 与 worsening family 各取一例；
6. 使用 salt `PRTA_ATTN_20260818`，按
   `SHA256(salt + "|" + sample_id)` 升序选取；
7. attention 打开后没有更换案例。

门控统计：5,855 条通过 support 与三 Seed 一致正确门，4,681 条保留在中间 80%。
不公开 raw sample ID、患者标识或单例预测表。

## Attention 计算

- `W_align` shape `[12,197,197]`；
- `W_trans` shape `[12,20,197]`；
- eval mode，`need_weights=True`，`average_attn_weights=False`；
- scientific forward 不修改，先 hook 原始 Q/K/V 与输出，再以同一 Q/K/V 重放并
  核验输出；CUDA 重放绝对误差门为 `5e-5`；
- 去除两端 CLS 后在 196 patches 上逐行重归一化；
- `A_bar`、`r_current`、`r_prior`、`edge` 严格按冻结公式计算；
- 两例四张 relevance map 共用 p99 clipping=`0.08322171984437607`；
- 每例使用 prior/current 两端 one-patch greedy NMS，最多保留 6 条路线。

## 权威 artifact 身份

- capture source commit：`3f5031fd657f7040309df5246a27fcdbd4a0f4cb`
- renderer commit：`79e181c49cdb0ce7273e2b75f85217a0da38147b`
- seed-43 checkpoint SHA-256：
  `d7673c8ce36dfac53c78a1dd2ca1adabaeb9a56b6510c81c979860981fee2140`
- private full tensor bundle SHA-256：
  `8a55c0ee4e7f1d99a36f1a89aac408a88733b26897972f6223488830752120c4`
- private rendered PNG SHA-256：
  `a1e0d02715bac1617cc0d0203585240c5e015952a9ddadb1c2c9eaa9e002b0b1`

公开可核验入口：

- `figures/attention_export_manifest.json`
- `data/19_Figure5_attention_flow_aggregate.json`
- `scripts/106_freeze_attention_cases.py`
- `scripts/107_export_attention_flow.py`
- `scripts/108_render_attention_flow.py`
- `scripts/109_publish_attention_flow_aggregate.py`

## 图注草案

**Figure 5 | Finding-conditioned temporal attention flow.** Two development
cases were selected before attention inspection using unanimous correct
predictions across three seeds, support and confidence gates, and salted-hash
ordering. For each case, native post-softmax attention was used to propagate
transition relevance from current patches through current-to-prior alignment.
All maps share one color scale; line width and opacity encode route weight.
The examples are descriptive and do not establish radiologist-validated
localization.

## 写作边界

- 可以写“finding-conditioned query 改变了模型跨时间信息路由，并且存在稀疏的
  high-weight cross-time routes”。
- 不要把 attention 写成病灶分割、因果解释或医生确认的定位。
- 在提交论文图或将 PNG 交给出版社前，必须取得书面的影像发表/再分发许可；当前
  receipt 不满足这一门。
