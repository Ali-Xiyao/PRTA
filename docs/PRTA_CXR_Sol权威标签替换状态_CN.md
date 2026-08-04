# PRTA-CXR Sol 权威标签替换状态

> 此版本已被 2026-08-04 的
> [Sol 全风险标签版本](PRTA_CXR_Sol全风险标签替换状态_CN.md)取代；本文件仅保留
> 作为 Dev/Internal-test 首次 Sol 权威化的历史审计记录。

日期：2026-08-04

状态：`ACTIVE_SOL_AUTHORITATIVE_NOT_TRAINED`

## 结论

用户已明确授权使用完整 `gpt-5.6-sol` 盲审结果替换此前 Luna-derived
Dev 和 Internal-test 标签。新版本已经物化并通过独立磁盘审计：

- Sol 明确五分类直接成为新 `progression_label`；
- Sol `Unclear` 按既有策略排除，不强制映射为任何五分类；
- 所有保留行的 `label_source` 切换为
  `gpt-5.6-sol_blind_authoritative_2026-08-04`；
- 原始 manifest 不原地销毁，作为历史实验和回退证据保持不变；
- Gold 当前是两位资深医生共识，不是 Luna 标签，因此 250 条医生 Gold 全部保持不变；
- 未启动训练，也未使用新标签重新计算任何模型指标。

## 行数与替换动作

| 队列 | 原行数 | Sol明确保留 | 标签值变化 | 同值权威重绑定 | Sol Unclear排除 |
|---|---:|---:|---:|---:|---:|
| Dev | 16,666 | 13,420 | 1,347 | 12,073 | 3,246 |
| Internal-test | 16,699 | 13,588 | 1,433 | 12,155 | 3,111 |

新活动数据表面：

- Train：90,771（沿用此前 Sol-authoritative Train）；
- Train+Dev：104,191；
- Internal-test：13,588；
- Gold：250 条医生共识，不变。

## 活动入口

私有运行根：

`H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\poststop_audits\sol_authoritative_protected_v1`

未来命令应设置：

```powershell
$env:PRTA_CXR_SOL_LABEL_ROOT = `
  'H:\VisualVIT_runtime\050_routeD\prta_cxr_clean_v1\poststop_audits\sol_authoritative_protected_v1'

$SOL_TRAIN_DEV = `
  "$env:PRTA_CXR_SOL_LABEL_ROOT\private\train_dev_sol_authoritative_v2.jsonl"
$SOL_INTERNAL_TEST = `
  "$env:PRTA_CXR_SOL_LABEL_ROOT\private\internal_test_sol_authoritative_v1.jsonl"
```

后续训练、protocol freeze 和评价入口必须显式使用 `$SOL_TRAIN_DEV` 与
`$SOL_INTERNAL_TEST`；不得继续把旧 `formal_program_v1` 的 Luna 标签表面当作
当前活动版本。

## 守恒与哈希

- Train+Dev：`478e7cce0d4d25e7343ddbcc910a5b5a3e4e72e570a60fe07cea2f1078a4cd21`
- Dev：`89ea77c121036f79a556875052852744928b5a39e419b3dc4cd1d9c687d60e0c`
- Internal-test：`fe76a30e63430b0ce2fa1b40f194b83cb1b31938f6b89a6d1136b4b924b44305`
- Provenance：`77137a5e5eecef30637286255eb7c830a519b1b87c178a8537689418bdddc9ec`
- Unclear exclusions：`cf5ade9839e78f6a82f79fd99dd10256390403455c2520d7066cb7fe870dfcfa`
- 正式物化回执：`63b9fc6e62703d95112a5a2aeeb0eaec2726d38ded548b378b4c59b786998ae9`
- 独立审计：`891048930be8e7d02ded54fa7135da542a314d1ef4ae30a03a0b83084c807c64`
- 医生 Gold：`e027916db1fb0a31f66cd5b72a60893ee538ff465ac97b9cdcf1246fe519f91d`

独立审计确认：新 ID 集等于源 ID 减 Sol Unclear；所有非标签字段不变；
组合 manifest 的 Train 部分与既有 Sol Train 逐字节一致；输入前后哈希不变；
医生 Gold 修改数为 0。

## 解释边界

这是一个新的标签版本。旧 checkpoint 和旧指标是在旧 Dev/Internal-test 标签下
产生的，不能被重新解释为新版本结果。若要报告新版本指标，必须另行授权后从新
活动 manifest 重新训练/推理，并把新旧标签版本和访问历史写入论文方法与限制。
