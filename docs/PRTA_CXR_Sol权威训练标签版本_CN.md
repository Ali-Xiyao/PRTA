# PRTA-CXR Sol 权威训练标签版本

> 此 90,771-row Train 版本已被 2026-08-04 的
> [Sol 全风险标签版本](PRTA_CXR_Sol全风险标签替换状态_CN.md)取代；本文件仅保留
> 作为 Tier A Sol 权威化的历史审计记录。

## 决策

根据用户确认的人工查看结果，Train Tier A 改为以 GPT-5.6 Sol 盲审判断为准。
本次只生成新的版本化训练标签文件，不覆盖旧 Luna、TracIn 或 Sol 审计产物，也不
启动训练。

处理规则：

- Sol 为五分类之一：保留样本，以 Sol 标签作为权威标签；
- Sol 为 `Unclear`：从新训练版本排除，不强制映射到五分类；
- Dev 保持原始行逐字节不变；
- Internal-test 与 Gold 不读取、不修改。

## 数量结果

| 项目 | 数量 |
|---|---:|
| 原 Train | 91,065 |
| Tier A | 3,866 |
| Sol 五分类权威 | 3,572 |
| 实际标签值改变 | 570 |
| Sol/Luna 同值但权威来源改为 Sol | 3,002 |
| Sol `Unclear` 排除 | 294 |
| 非 Tier-A Train 原样保留 | 87,199 |
| 新 Train | 90,771 |
| 原样 Dev | 16,666 |
| 新 Train+Dev | 107,437 |

新 Train 标签分布：

| 标签 | 数量 |
|---|---:|
| Improved | 13,554 |
| New | 16,160 |
| Resolved | 2,346 |
| Stable | 41,852 |
| Worse | 16,859 |

## 独立审计

独立磁盘重读验证通过：

- 新 Train ID 精确等于旧 Train ID 减去 294 个 `Unclear` ID；
- 570 个实际改标和 3,002 个同值权威重绑定均与 Sol provenance 一致；
- 87,199 个非 Tier-A Train 行完全不变；
- Train-only 与组合 manifest 的 Train 字节流一致；
- 16,666 个 Dev 原始 JSONL 行逐字节一致；
- 旧输入文件前后哈希一致；
- 未启动训练。

## 安全哈希

- 新 Train：`7306898c6b31af50956fa4ee32c5b6b8ba468751e6fc4e26f6a9353355fff219`
- 新 Train+Dev：`d798feb5adc65955add617371a38e337d9ffe721a18756e958851a50d51c897b`
- Sol provenance：`57485016e1720ee90b8c2fce5784bee585a2c96d9c8ec7de2bd8fd47148f4183`
- `Unclear` exclusions：`a0f2a81d9eec2ba964f3fa4701940d599e106c20dd475631954d4f1a9abf7e2e`
- 独立审计：`f898233c0370e9746bdc80d64f480f3c2394fe319baef6d2049b41335a1a27c5`

逐病例 ID、旧/新标签和报告只保存在 Git 外的私有审计目录。
