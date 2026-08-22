# PRTA-CXR 最终 Git-safe 聚合数据

本目录只保留最终论文需要的五份 Phase20 权威 JSON：

| 文件 | 内容 | 正式状态 |
| --- | --- | --- |
| `12_Phase20-A三Seed正式聚合.json` | 主结果、消融、scaling、noise、source-held | 88/88 PASS |
| `14_Phase20-comparator最终聚合.json` | 8 systems × 3 Seeds comparator | 24/24 PASS |
| `15_Phase20-B1正式聚合.json` | 校准、亚组、state-pruning、效率 | 6/6 PASS |
| `16_Phase20-B2配对统计.json` | paired bootstrap、Holm、risk-coverage | 28/28 PASS |
| `17_Phase20最终证据凭据.json` | 完成门、protected reads、no-selection | finalizer PASS |

旧 V2、Phase15/16、历史 PRIOR/效率/校准 Markdown 已迁入 VisualVIT 归档，不在
本仓库重复保存，以避免被误当成最终 S1 数字。这里不包含 patient-level prediction、
checkpoint、影像、报告或原始日志。
