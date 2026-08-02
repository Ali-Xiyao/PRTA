# PRTA-CXR 全量数据重划分政策

状态：`ACTIVE_FOR_IMPLEMENTATION__EXECUTION_NOT_STARTED`

日期：2026-08-02

## 用户决定

新项目不继承旧项目为了调试、smoke、路线筛选而建立的小 cohort 和临时数据隔离。
此前使用过的数据集统一重新进入候选源目录，重新做资格检查、去重、患者隔离和划分，
尽可能扩大合规训练数据量。正式 PRTA 模型不沿用旧 debug roster 训练。

## “解除旧隔离”的准确含义

以下旧边界不再限制新训练池：

- 仅用于 debug/smoke 的样本数量上限；
- 旧 R 编号路线的 train/calibration 临时划分；
- 为比较某个旧方法而建立的 matched 小 cohort；
- 已废弃路线的模型选择子集；
- 只因旧脚本/显存/运行时间而暂时未纳入的数据。

这些数据需要从原始、可追溯的数据源重新生成，不直接拼接旧 roster。

## 仍然必须保留的边界

以下不是“调试隔离”，不得解除：

- 许可、DUA、隐私、去标识或处理权限不满足的数据；
- 已揭示结果的历史 test 患者；
- protected gold / clinician audit 患者；
- external confirmation cohort；
- 同一患者、同一 study 或同一图像的跨源重复；
- 官方 test split，除非协议明确证明其从未用于结果查看且获得单独批准；
- 缺少稳定 patient lineage、时间顺序、图像或报告的数据。

## 新划分原则

1. 从所有已激活且合规的 source manifest 构建统一候选池；
2. source 内选择合格 frontal study，患者内按时间排序并构建相邻 pair；
3. 先做跨源 patient/study/image lineage 去重与 protected registry 排除；
4. patient 是不可分割划分单位；
5. 从头生成 Train / Dev / Internal-test，默认比例 80% / 10% / 10%；
6. 划分器同时平衡 source、finding 和五类 progression 支持；
7. Internal-test 在 freeze 后只读取一次；Gold/External 不参与选择；
8. 每个 source catalog、exclusion registry、pair manifest、label manifest 和
   split manifest 都保存 SHA-256 与审计收据；
9. 新 split 不得使用旧 revealed test 指标、旧最佳 seed 或旧 checkpoint 调整。

## 执行门

代码完成和 synthetic end-to-end 通过后，真实数据执行仍需：

- 明确的数据根目录与 source manifest；
- 每个 source 的治理字段全部通过；
- protected/revealed/external patient registry 可用；
- 用户单独批准该次正式数据构建；
- `--formal` 与 `PRTA_CXR_ALLOW_FORMAL` 双重确认。

本文件是后续数据代码、配置和运行审计的长期依据。
