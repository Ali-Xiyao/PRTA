# PRTA-CXR 论文材料工作区

本目录保存最终非外部实验的 Git-safe 聚合结果与论文叙事。论文方法统一写作
**PRTA-CXR**；`Slim-S1` 仅作为冻结配置身份。目录不包含 checkpoint、患者级预测、
影像、报告、原始日志、凭据或私有绝对路径。

## 当前状态

| 证据层 | 正式状态 |
| --- | --- |
| Phase20-A | 88/88 PASS |
| Comparator | 24/24 PASS |
| Phase20-B1 | 6/6 PASS |
| Phase20-B2 | 28/28 PASS |
| Evidence finalizer | PASS；no selection |

ReXGradient/独立外部验证已经退役，不进入论文结果；正文泛化证据使用双向
MIMIC-CXR/CheXpert Plus source-held，并统一称为 cross-source domain
generalization。Internal-test、Gold、医生人工与 reader study 均未打开或执行。

## 建议阅读顺序

1. [证据状态总览](00_证据状态总览_CN.md)
2. [论文叙事与摘要骨架](01_论文叙事与摘要骨架_CN.md)
3. [Information Fusion 方法](02_Information_Fusion方法_CN.md)
4. [主结果与消融](03_主结果与消融_CN.md)
5. [统计与报告协议](05_统计与报告协议_CN.md)
6. [讨论与局限](06_讨论与局限_CN.md)
7. [最终路线图](07_后续实验路线图_CN.md)
8. [最终实验数据总表](17_论文实验数据总表与待跑清单_CN.md)
9. [最终证据与论文叙事](18_Phase20最终证据与论文叙事_CN.md)

## 最终聚合数据

- [Phase20-A 三 Seed正式聚合](data/12_Phase20-A三Seed正式聚合.json)
- [24-cell comparator 最终聚合](data/14_Phase20-comparator最终聚合.json)
- [Phase20-B1 正式聚合](data/15_Phase20-B1正式聚合.json)
- [Phase20-B2 配对统计](data/16_Phase20-B2配对统计.json)
- [Phase20 最终证据凭据](data/17_Phase20最终证据凭据.json)
- [论文材料清单与 SHA256](data/07_论文材料清单与哈希.md)

旧 14/24 comparator 阶段快照已经移入 VisualVIT 历史仓库，不能作为当前结果引用。
