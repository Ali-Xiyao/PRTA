# PRTA-CXR 资深医生 Luna 辅助 Gold 冻结状态

日期：2026-08-03

状态：`PASS_SENIOR_LUNA_ASSISTED_PANEL_CONSENSUS_GOLD_FROZEN`

## 结论

冻结的 250 条 `source × Luna 五类` roster 已由两名临床资历均超过 5 年的医生复核。
医生在可见 Luna 标签的条件下共同形成一列最终标签，因此本结果属于
**Luna 辅助资深医生小组共识**，不是两份独立盲审，也不能用于计算医生间一致率。

回传工作簿只保留 A-H 八列。程序没有补写或修改医生标签，而是通过单独的用户声明
文件记录审核人数、资历和单列共识方式。250 个 `review_id`、数据源、finding、前后
报告和显示的 Luna 标签均与冻结 roster 精确绑定，错误为 0。

## 结果

| 项目 | 结果 |
|---|---:|
| 复核行数 | 250 |
| 有效五分类医生标签 | 250 |
| `Unclear` / `Unusable` | 0 / 0 |
| Luna 与医生共识一致 | 246/250（98.4%） |
| 医生修正 Luna | 4/250（1.6%） |
| Gold 行数 / 患者数 | 250 / 250 |
| 排除行数 | 0 |
| Gold–训练候选患者重叠 | 0 |

两个来源均为 123/125（98.4%）一致。按 Luna 原标签统计：Improved 48/50、New
50/50、Resolved 50/50、Stable 49/50、Worse 49/50。最终 Gold 标签分布为
Improved 48、New 50、Resolved 51、Stable 52、Worse 49。

四条医生修正为：

| review_id | 数据源 | finding | Luna | 医生共识 Gold |
|---|---|---|---|---|
| `review_0071` | MIMIC-CXR | Pleural Effusion | Stable | Resolved |
| `review_0093` | CheXpert Plus | Atelectasis | Improved | Stable |
| `review_0194` | MIMIC-CXR | Atelectasis | Worse | Stable |
| `review_0213` | CheXpert Plus | Pleural Effusion | Improved | Stable |

98.4% 应表述为 **Luna 标签在可见预标签复核中的医生确认率**，不能表述为独立盲审
准确率。250 条医生共识标签可以作为当前 Gold 评价标签；其余未经逐条人工确认的
Silver 不能称为 Gold。

## 隔离与哈希

- 完整 Luna Silver：126,727 行。
- Gold roster 患者相关 Silver：2,297 行，继续全部隔离。
- 唯一训练候选入口：124,430 行。
- Gold 与训练候选患者交集：0。
- 回传工作簿 SHA-256：
  `b2caf74888a31ef26df8d89df6632e8a4f8ee884d1c91fe9145e140c4071c429`。
- Gold manifest SHA-256：
  `564d9b389b6c0f80354a5880ed30aabfdb66281535d14b2f3626f9fa14a8bcad`。
- 比较 manifest SHA-256：
  `cfebe3ea795ed67882914156021e195207e356e0466020b7f3a7b60d1b1d3a70`。
- 审计文件 SHA-256：
  `26f4f2e5e9b74840c222882311af44d5a6a2202888906f9c878efab6a739b10b`。

运行目录：
`<private-local-runtime>\luna_primary_full_v1\senior_panel_gold_v1`

## 当前边界

Gold 标签冻结已经完成，但本次授权不包含新的 train/dev/internal-test 划分、图像缓存、
GPU 训练或测试集评估。下一步应从 124,430 条训练候选重新冻结 patient-disjoint
split，并在单独授权后才生成缓存或训练。
