# PRTA-CXR Sol 全风险标签替换状态

日期：2026-08-04

状态：`ACTIVE_SOL_AUTHORITATIVE_ALL_RISK_NOT_TRAINED`

## 结论

用户已明确授权把 Tier B/C 的 Sol 盲审结果直接替换此前 Luna-derived Train
标签。本次按已有冻结语义执行：Sol 明确五分类成为权威标签，Sol `Unclear`
从新活动版本排除；历史清单保留，不做原地覆盖。

本次精确目标集合为 5,981 条：5,968 条新完成的 Tier B/C 全量复核，加上
13 条此前 pilot 已复核但尚未权威化的 Train Tier B/C 样本。结果为：

- Sol 明确五分类：4,616 条；
- Sol `Unclear` 排除：1,365 条；
- 相对当前活动 Train 实际改类：1,093 条；
- 标签值相同、仅切换为 Sol 权威：3,523 条；
- 非目标 Train 原始字节保持不变：84,790 条。

其中 2 条 pilot 历史 Luna 标签与当前活动 Train 标签不同。系统没有静默忽略：
私有 provenance 同时记录历史复核标签和当前活动标签，并按用户授权以 Sol 为准，
所以这 2 条计入实际改类。

## 新活动版本

私有运行根：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\poststop_audits\sol_authoritative_all_risk_v1`

未来命令应显式设置：

```powershell
$env:PRTA_CXR_SOL_LABEL_ROOT = `
  'H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\poststop_audits\sol_authoritative_all_risk_v1'

$SOL_TRAIN_DEV = `
  "$env:PRTA_CXR_SOL_LABEL_ROOT\private\train_dev_sol_authoritative_all_risk_v1.jsonl"
$SOL_INTERNAL_TEST = `
  "$env:PRTA_CXR_SOL_LABEL_ROOT\private\internal_test_sol_authoritative_v1.jsonl"
```

活动行数：

| 队列 | 行数 | 本次是否改动 |
|---|---:|---|
| Train | 89,406 | Tier B/C Sol 替换及 Unclear 排除 |
| Dev | 13,420 | 否，逐字节复制原 Sol 活动版 |
| Train+Dev | 102,826 | 新 Train 加未改动 Dev |
| Internal-test | 13,588 | 否，逐字节复制原 Sol 活动版 |
| 医生 Gold | 250 | 否，仍为两位资深医生共识 |

## 哈希与独立审计

- Train：`3aa67f2a09f0907ca35ea410b78a18e5feb7d8871d311154da71ee49ade3889a`
- Train+Dev：`a39e03e64ac43faed9348d3f8aabe79eede8bf2e398bff7cb2b795673ca1aa41`
- Dev：`89ea77c121036f79a556875052852744928b5a39e419b3dc4cd1d9c687d60e0c`
- Internal-test：`fe76a30e63430b0ce2fa1b40f194b83cb1b31938f6b89a6d1136b4b924b44305`
- 医生 Gold：`e027916db1fb0a31f66cd5b72a60893ee538ff465ac97b9cdcf1246fe519f91d`
- Materialization receipt：`91f18fb1c57999c369ea3363001f00d7e0bb332342473cfacd3ce749c65c7527`
- Independent audit：`dbe8de25c33a3591ff14da3c188e71ebb0783ff699309eaada16a1b7ab7e3fdb`
- Active pointer：`2230f65b3ef754054b813167fa66edc21d14fd2b9f67a3a95f13782c6e26c664`

独立审计重新构建目标集合并确认：新 Train ID 集等于旧 Train ID 减去所有
Sol `Unclear`；目标行只改变 `progression_label` 与 `label_source`；非目标行内容
不变；Dev、Internal-test 和医生 Gold 哈希不变。

## 边界

本次没有训练模型、没有推理、没有计算替换后的模型指标，也没有改动 split。
旧 checkpoint 和旧指标不能被重新解释为新标签版本结果。若以后需要新指标，
必须另行授权并从本活动清单开始新的训练/评价流程。
