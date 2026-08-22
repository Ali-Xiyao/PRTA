# Figure 5 时序 Attention Flow 写作卡

真实 attention 与内部成图均已完成，案例选择、公式、hash 和图注见
`../paper/20_Figure5_Finding-conditioned_temporal_attention_flow_CN.md`。

## 写作可直接使用

- 两例在查看 attention 前按固定规则选择，之后未更换；
- 使用 seed-43 原生 per-head post-softmax attention；
- `W_align=[12,197,197]`，`W_trans=[12,20,197]`；
- 去 CLS 并在 196 patches 上重归一化；
- 全图共用一个 p99 色阶，每例最多 6 条 one-patch-NMS route；
- 公开 aggregate 与权威 hash 位于 `evidence/19_Figure5_attention_flow_aggregate.json`
  和 `figures/attention_export_manifest.json`。

## 当前不能做

目标 PRTA GitHub 仓库是公开仓库。两例来自 MIMIC-CXR-JPG，当前没有单独的
书面影像发表/公开再分发许可，因此含四张 CXR 的 PNG、单例完整 W tensor、路径、
样本 ID 与概率不能放入公开交接包。内部 PNG 已由 SHA-256 固定，不会丢失或被
替换；取得许可后可由 `scripts/108_render_attention_flow.py` 原样再生成。

## 推荐正文表述

“Qualitative analysis of native attention showed that the finding-conditioned
temporal adapter concentrated transition relevance on a small set of current
patches and routed this evidence to sparse prior regions under a shared
visualization scale.”

紧接一句限制：attention 是模型内部路由的描述性证据，并非病灶分割或临床因果解释。
