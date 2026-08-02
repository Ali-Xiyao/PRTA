# PRTA-CXR 真实数据准备状态

状态：`PAIR_POOL_READY__LUNA_PILOT_COMPLETE__FULL_LABEL_HOLD`

日期：2026-08-02

## 直接结论

新的全量候选 pair 池已经从本地原始数据重新构建完成，没有继承旧 debug
roster，也没有启动训练。下一阶段仍是规则候选与 Luna 审核；完成标签审计后才可
冻结新的 patient-disjoint 80/10/10 split，之后才能生成缓存和训练。

## 已冻结的数据证据

| 项目 | MIMIC-CXR-JPG | CheXpert Plus |
|---|---:|---:|
| 官方允许范围 | train，AP/PA | train，Frontal AP/PA |
| 源 manifest studies | 213,365 | 187,474 |
| 源 patients | 63,169 | 64,510 |
| 排除与时间点去重后 studies | 175,119 | 187,474 |
| adjacent pairs | 115,547 | 122,964 |
| 时间基准 | calendar | within-patient ordinal |

合计 362,593 个合格 studies、238,511 个 adjacent pairs。含至少一个 pair 的患者
时间线共 57,960 条。CheXpert Plus 的间隔只表示患者内检查顺序，不能解释为真实
日历天数，不能进入按天数分层或论文真实时间间隔结论。

## 排除边界

- hash-only exclusion union：3,750 名 MIMIC namespace 患者；
- protected gold：690；revealed historical test：3,306；
- 旧 train-only membership 已重新激活，不因旧 debug/train roster 身份而排除；
- 正式 pair manifest 中 raw patient ID 数为 0，排除患者重叠为 0；
- official validate/test、internal test、gold outcome、external outcome 均未打开。

## 产物与哈希

外部运行根目录：
`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1`

- `sources_v1/mimic_cxr_jpg_studies.jsonl`
  - file SHA-256：`0e327327ede9fed1de565e89022c527eea718b221334af26e8daf18bb5b220f4`
- `sources_v1/chexpert_plus_studies.jsonl`
  - file SHA-256：`d66dfeb582e75d78941e0a1087b3be46468bf765f24183af994ec9eab8da5918`
- `sources_v1/patient_exclusions.json`
  - canonical registry SHA-256：`bd0e061ba116862d94d72ae04787b2b101779ab22b92b91e7ea548e6b024e618`
- `pairs_v1/candidate_pairs.jsonl`
  - rows：238,511；bytes：594,606,221
  - file SHA-256：`a006250303726bd41b51b70add312f47ce687a856b0e4aa95ff7ae145e26d424`
  - canonical row-list SHA-256：`812d707937245193f1124a54dc511323c03eb39dc025c64c30da756b5571ef17`

独立流式复核确认：pair ID 全部唯一且可重算，患者排除重叠、raw patient 字段、
非正间隔、时间基准/布尔标记矛盾、重复 edge、非相邻链计数均为 0。

## 未执行与下一道门

- 已读取允许范围内的真实报告文本，并仅检查图像文件存在性；没有读取图像像素；
- 未生成规则标签或 Luna batch，未调用 Luna；
- 未冻结 train/dev/internal-test split；
- 未生成 Block-8 或文本缓存；
- 未启动 GPU 训练；
- 未打开 internal-test、protected gold 或 external confirmation 结果；
- 本页数字是数据工程审计证据，不是论文模型结果。

规则候选与 150 条 Luna pilot 已完成，但全量扩展被 pilot 门 HOLD。具体接受率、
来源差异、失败率和吞吐证据见 [LUNA_PILOT_STATUS_CN.md](LUNA_PILOT_STATUS_CN.md)。
在该 HOLD 被新的 source-aware 策略、stress set 和执行预算解除前，不得冻结 split、
生成缓存或训练。
