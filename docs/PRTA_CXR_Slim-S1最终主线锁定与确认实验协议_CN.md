# PRTA-CXR Slim-S1 最终主线锁定与确认实验协议

> 状态：`FROZEN_PHASE20_SLIM_S1_MAINLINE`
>
> 生效日期：2026-08-18
>
> 适用范围：cleaned full Train / official Dev；不含外部数据、Internal-test、Gold

## 1. 最终方法锁定

论文最终主方法改为 **PRTA-CXR-Slim / Slim-S1**。其固定定义为：

- 保留 finding-conditioned visual query、cross-time alignment、temporal relation
  residual、Tail8/rank32/H0；
- 保留 training-only state anchor `0.025`、ODC `0.05` 与 matched-hard CMCP
  `0.01`（`offline_hard_v1`）；
- 删除 standalone Prototype CE（`prototype_alignment=0`）；
- 删除 DMW（`direction_margin=0`）。

Slim 的 4 Arms × 3 Seeds 只是在原 Train 内部 patient-disjoint 选择面上的模块选择
证据。其 checkpoint 和指标不能冒充 full Train / official Dev 最终模型。Phase20
只确认已锁定 S1，不重新比较 S0/S1、修改容差或搜索新组合。

## 2. 历史证据角色

| 历史证据 | Phase20 角色 | 处理 |
|---|---|---|
| Full V2 三 Seed | 开发父方法与历史对照 | 冻结保留，不覆盖 |
| Slim 12-cell | S1 模块选择依据 | 冻结保留，不重跑 |
| IF-A10 | full-data S0 | 三 Seed config/receipt/input hash 审计 PASS，直接继承 |
| TILA8 | DMW 不适用的比较器 | 三 Seed直接继承 |
| Current-only / Siamese | 方法无关比较器 | 直接继承 |
| IF-F01 / IF-F02 | 历史 DMW=0.01 | 必须以 DMW=0 新命名重跑 |
| V2 可信性/压力/效率结果 | 历史机制证据 | 保留；最终 S1 必须重新推理 |

IF-A10 复用证据冻结在
`configs/phase20/a10_reuse_evidence_v1.json`。三个 Seed 均为正式 PASS，配置
canonical hash 与七类输入 hash 一致，Internal-test/Gold/protected outcome 均未读。

## 3. Phase20 新训练矩阵

固定 Seeds 为 `17/28/43`，总计 **63 个唯一训练单元**：

| 轴 | 变体 | 单元数 |
|---|---|---:|
| 最终主线确认 | full-Train S1 | 3 |
| 精确损失消融 | w/o state、w/o CMCP、w/o ODC | 9 |
| 精确结构消融 | w/o finding、w/o alignment、w/o relation | 9 |
| 公平融合比较 | F01-DMW0、F02-DMW0 | 6 |
| source-held | S1-core/no-CMCP，双向单源训练/异源 Dev | 6 |
| data scaling | 10/25/50/75% | 12 |
| label noise | symmetric/plausible × 5/10/20% | 18 |

实验 ID、配置、队列与依赖均由 `phase20_program.py` 一次性生成。S0、TILA8、
Current-only、Siamese 不通过改名重复训练。所有新结果写入独立 Phase20 命名空间，
不得覆盖 V2、IF 或 Slim 历史目录。

## 4. 三卡执行与自动依赖

训练使用两张 A800 与本地 RTX3090 GPU0；本地 GPU1 固定预留，不进入科学队列。
按 A800 等效预计时长做 longest-processing-time 分配，3090 采用保守慢速系数；
每个任务只属于一条 lane。full S1 三 Seed 为
最高优先级，随后是精确损失消融和 F01/F02-DMW0，再依次执行结构、source-held、
scaling 与 noise。scaling/noise 的 matched-hard map 按 host 生成并用 hash/依赖门
复用，禁止跨 Windows/POSIX 路径引用。

正式入口必须同时具有 `--formal` 与
`PRTA_CXR_ALLOW_FORMAL=I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN`。队列、源码、配置、
输入、状态和输出全部 hash 绑定；重复 job ID、非新输出目录或受保护读取均 fail
closed。

## 5. full S1 完成后自动重推理

仅使用 official Dev，按三 Seed 重新生成：

1. PRIOR true/matched-hard/null/reversed 与修订后的 older/view/token 条件；
2. finding 缺失/错误/临床同义表达和 current corruption；
3. calibration、risk-coverage、selective referral；
4. progression/finding/source/view/interval/long-tail 描述性亚组；
5. state-pruning、参数量、FLOPs、延迟、吞吐与显存；
6. safety routing、三 Seed disagreement 与 10,000 次 patient-cluster paired
   bootstrap。

统计比较固定包括 S1 vs A10/S0、V2、F02-DMW0、TILA8 和最强兼容独立比较器。
Dev 上的非选择性 S1-vs-S0 只报告 effect/CI，不改写 Train-only 选择结论。

## 6. 明确排除

- 外部/跨源独立数据：因数据合同问题最后执行，本阶段不下载、不运行；
- Internal-test 与 Gold：继续封存；
- 医生 reader study/新增人工标注：不做；
- 基于 Phase20 outcome 的新结构、权重、Seed、容差或 best-seed 选择：禁止。

V2 文档和数值仍是历史开发证据；从本协议生效起，不得再把 V2 写成最终投稿
主方法。S1 的 full-Train 结果未完成前，论文表格应标为 `RUNNING/PENDING`，不得把
Slim Train-only 均值填入 official Dev 主表。
