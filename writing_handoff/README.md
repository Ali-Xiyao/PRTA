# PRTA-CXR 论文写作交接包

更新时间：2026-08-22。

本目录是论文写作同学的单一入口。材料只覆盖最终冻结的 **PRTA-CXR**、正式聚合实验结果和可复核写作边界；不包含阶段性队列、失败路线、患者级预测、影像、报告、checkpoint 或原始日志。

## 建议阅读顺序

1. [最终故事主线](01_最终故事主线_CN.md)：先理解论文要证明什么、不证明什么。
2. [方法与贡献写作卡](02_方法与贡献写作卡_CN.md)：用于 Methods、Introduction 和 contribution list。
3. [实验结果总表](03_实验结果总表_CN.md)：正文数字的首选人工可读入口。
4. [论文结构与段落任务](04_论文结构与段落任务_CN.md)：按章节直接分工。
5. [图表落地清单](05_图表落地清单_CN.md)：表格、图和对应数据源。
6. [数字与措辞边界](06_数字引用与措辞边界_CN.md)：投稿前逐项检查。
7. [代码与复现入口](07_代码与复现入口_CN.md)：最终代码和内部 checkpoint 的边界。
8. [交接验收清单](08_交接验收清单_CN.md)：写作团队开始前和投稿前各核对一次。
9. [材料文件清单](09_材料文件清单_CN.md)：确认每类写作任务的唯一入口。
10. [数字溯源表](10_数字溯源表_CN.md)：从论文数字追到权威 JSON 与 source commit。
11. [数据来源、筛选与归档边界](11_数据来源筛选与归档边界_CN.md)：写 Data、cohort construction、cross-source protocol 与数据可用性声明。
12. [校准曲线与联合亚组热图](12_校准曲线与联合亚组热图_CN.md)：直接使用真实 bins/cells、成图与抑制规则。
13. [Figure 5 时序 Attention Flow](13_Figure5时序Attention_Flow_CN.md)：案例冻结、真实 attention、图注和公开许可边界。
14. [Figure S3 Query 特异性与 Attention 稳定性](14_FigureS3_Query特异性与Attention稳定性_CN.md)：全量 JSD、聚类 CI、图注和许可边界。

## 最终实验完成门

| 证据层 | 状态 |
| --- | --- |
| Phase20-A 主训练、消融、稳健性、跨来源 | 88/88 PASS |
| 纵向 comparator | 24/24 PASS |
| Phase20-B1 可信性 | 6/6 PASS |
| Phase20-B2 配对统计 | 28/28 PASS |
| Evidence finalizer | `PASS_PHASE20_EVIDENCE_FINAL_NO_SELECTION_AGGREGATE` |
| Protected outcome reads | 0 |
| Model re-selection | false |

## 数据目录

`evidence/` 保存写作所需的 6 份最终 Git-safe 聚合 JSON。所有数字必须追溯到该
目录或仓库 `paper/` 中的权威终稿，不得从聊天记录、服务器日志或中期快照抄写。

## 名称规则

- 论文方法名：**PRTA-CXR**。
- `Slim-S1`：仅用于冻结配置身份和实验追溯。
- `V2`：历史开发父方法，不是投稿主方法。
- `ReXGradient`：已退出论文证据，旧结果不报告。
