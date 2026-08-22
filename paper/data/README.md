# PRTA-CXR 最终 Git-safe 聚合数据

本目录只保留最终论文需要的 Git-safe 权威 JSON：

| 文件 | 内容 | 正式状态 |
| --- | --- | --- |
| `12_Phase20-A三Seed正式聚合.json` | 主结果、消融、scaling、noise、source-held | 88/88 PASS |
| `14_Phase20-comparator最终聚合.json` | 8 systems × 3 Seeds comparator | 24/24 PASS |
| `15_Phase20-B1正式聚合.json` | 校准、亚组、state-pruning、效率 | 6/6 PASS |
| `16_Phase20-B2配对统计.json` | paired bootstrap、Holm、risk-coverage | 28/28 PASS |
| `17_Phase20最终证据凭据.json` | 完成门、protected reads、no-selection | finalizer PASS |
| `18_Phase21校准与Finding-Progression联合单元.json` | 三 Seed reliability bins、12×5 联合 cells 与抑制门 | aggregate-only PASS |
| `19_Figure5_attention_flow_aggregate.json` | 两例平均后的 A_bar/r_current/r_prior/edge 与 rankwise route weights | aggregate-only PASS |
| `20_FigureS3_query_sensitivity_aggregate.json` | 全量 multi-finding pairs 的 query/seed JSD 中位数与 patient-clustered 95% CI | aggregate-only PASS |

旧 V2、Phase15/16、历史 PRIOR/效率/校准 Markdown 已迁入 VisualVIT 归档，不在
本仓库重复保存，以避免被误当成最终 S1 数字。这里不包含 patient-level prediction、
checkpoint、影像、报告或原始日志。
