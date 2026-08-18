# PRTA-CXR Slim-S1 最终主线锁定与确认实验协议

> 状态：`FROZEN_PHASE20_SLIM_S1_MAINLINE / PHASE20_RUNNING`
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
| Full V2 三 Seed | 开发父方法与历史对照 | Git-safe 汇总冻结；旧私有运行数据已清理 |
| Slim 12-cell | S1 模块选择依据 | Git-safe 汇总冻结，不重跑；旧 checkpoint 已清理 |
| IF-A10 | full-data S0 的历史语义证据 | Git-safe 审计保留；私有 checkpoint 已删除，正式患者级重分析需重建 |
| TILA8 | DMW 不适用的历史比较器 | Git-safe 聚合保留；正式患者级重分析需重建 |
| Current-only / Siamese | 方法无关历史比较器 | Git-safe 聚合保留；正式 safety/paired 分析需重建 |
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
| 精确结构消融 | w/o visual finding-query conditioning、w/o alignment、w/o relation | 9 |
| 公平融合比较 | F01-DMW0、F02-DMW0 | 6 |
| source-held | S1-core/no-CMCP，双向单源训练/异源 Dev | 6 |
| data scaling | 10/25/50/75% | 12 |
| label noise | symmetric/plausible × 5/10/20% | 18 |

实验 ID、配置、队列与依赖均由 `phase20_program.py` 一次性生成。所有新结果写入
独立 Phase20 命名空间，不得覆盖 V2、IF 或 Slim 历史目录。

旧私有 checkpoint 按用户授权删除后，过去的“直接继承”仅剩 Git-safe 聚合结论，
不足以完成患者级 paired bootstrap、safety routing 与最终方法同协议比较。因此另行
冻结 **8 systems × 3 Seeds = 24 个 comparator rebuild 单元**：V2、S0、B401、
B402、TILA8、BioViL-T-style、CheXRelNet-inspired 与 `TILAPaper`
paper-based reimplementation。后三者明确是内部/独立复现，不冒充官方实现。该重建队列只在
**Phase20-A 全局 finalizer PASS** 后接力，不影响正在跑的 63-cell 主队列，也不使用
预留 GPU。单条 lane completion 不能替代 63-cell/88-job 的跨 retry、跨主机唯一性与
输出哈希对账。

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

2026-08-18 的正式 program 共 88 个依赖 job，其中 63 个为训练单元。三条活动
lane 为 `a800_3066`、`a800_9929` 与 `rtx3090_0`；`rtx3090_1` 明确保留为空闲卡。
首次 A800 `nohup srun` 尝试因终端耦合在零结果状态被 Slurm 撤销，失败收据已保留；
修复后的 `setsid -f` step `3066.188`/`9929.148` 与本地 lane 均已进入正式训练。

接力队列同样只允许上述三条活动 lane，并使用 LPT 估时均衡。它必须等待 server/local
host finalizer shard 合并出 `PASS_PHASE20_A_FINAL_NO_SELECTION_AGGREGATE`，不能停止、迁移或抢占
当前任务；接力自身也按
源码提交、输入哈希、配置哈希和 queue hash fail closed。
`phase20_continuation_watcher.py` v2 仅在 CPU 上轮询全局 finalizer，并以无 shell 的 argv
启动下一队列；若前序 lane 含失败、身份漂移或任一哈希不符，则写出 BLOCK/FAILED
收据并拒绝接力。

## 5. full S1 完成后的 B1/B2 证据链

Phase20-B1/B2 与三层 finalizer 代码已构建并通过测试；仅在各自上游 PASS 后，
使用 official Dev 按三 Seed重新生成：

1. PRIOR true/matched-hard/null/reversed 与修订后的 older/view/token 条件；
2. finding 的 zero text embedding、真正 post-projection zero query、错误/临床同义
   表达和 current corruption；
3. calibration、risk-coverage、selective referral；
4. progression/finding/source/view/interval/long-tail 描述性亚组；
5. state-pruning、参数量、FLOPs、延迟、吞吐与显存；
6. safety routing、三 Seed disagreement 与 10,000 次 patient-cluster paired
   bootstrap。

执行拆为两个不可混淆的阶段：

- **Phase20-B1（20 jobs）**：仅依赖 Final S1，完成 PRIOR/modality、calibration、
  risk-coverage、subgroup、state-pruning 与 cached-feature efficiency；corruption
  cache 显式绑定 `raw-image-root`，三种 condition 必须共享 split/roster/count hash。
- **Phase20-B2（28 jobs）**：等待 Phase20-A finalizer 与 24-cell comparator
  finalizer 均 PASS 后，先导出 9 个比较系统 × 3 Seeds 的 true-PRIOR 概率，再自动运行
  safety routing、三 Seed disagreement、risk-coverage comparison、exclusive
  correct/wrong 与 10,000 次 patient-cluster paired bootstrap。预先固定的
  S1-vs-S0/V2/F02-DMW0/TILA8 主对照组成 Holm family；按 Dev Macro-F1 排出的最强
  兼容比较器只作 outcome-ranked exploratory 对照，不包装成预注册推断。

统计比较固定包括 S1 vs A10/S0、V2、F02-DMW0、TILA8 和最强兼容独立比较器。
Dev 上的非选择性 S1-vs-S0 只报告 effect/CI，不改写 Train-only 选择结论。

对应 B1 入口为 `phase20_evidence_program.py` / `scripts/118_prepare_phase20_evidence.py`
与 `phase20_evidence_runner.py` / `scripts/119_run_phase20_evidence.py`；B2 入口为
`phase20_b2_program.py` / `scripts/125_prepare_phase20_b2.py` 和
`phase20_b2_statistics.py` / `scripts/124_run_phase20_b2_statistics.py`。最终只接受
`phase20_training_finalize.py`、`phase20_comparator_finalize.py` 与
`phase20_evidence_finalize.py` 的连续 PASS。中间 checkpoint 不能进入证据队列。

## 6. 历史资产与清理边界

旧 V2/Slim 的 Git-safe 源码、配置历史、聚合结论和叙事固定保存在 GitHub 分支
`codex/archive-v2-history-before-phase20`，冻结提交为
`6f471d93421b743fed446b650d7e2fd5f71ef24d`。该分支不包含 checkpoint、患者级
预测、报告、图像、缓存或凭据。

在 Phase20 三条 lane 健康后，本地和服务器的旧运行目录、旧 checkpoint、失败
副本与传输包均已按 allowlist 永久删除。仅保留当前 Phase20、cleaned Train/Dev、
Block4/Tail8 cache、BiomedCLIP 权重、matched-hard map 与 label-quality audit。
本地和服务器分别写出 `PASS_PHASE20_OLD_LOCAL_RUNTIME_DELETED` 与
`PASS_PHASE20_OLD_SERVER_RUNTIME_DELETED` 私有收据。Phase20 运行中产生的
旧 checkpoint 的删除规则不适用于本轮新生成的论文复现资产。至少保留 Final S1、
S0、F02-DMW0、TILA8 与最强兼容 paper-based comparator 的 Seeds 17/28/43，并记录
checkpoint/config/receipt/input/best-epoch/source/hardware SHA 与身份，直到 Phase20-B1/B2、
外部验证、最终图表和潜在审稿补实验全部结束。未经这一保留门不得清理。

## 7. 明确排除

- 外部/跨源独立数据：因数据合同问题最后执行，本阶段不下载、不运行；
- Internal-test 与 Gold：继续封存；
- 医生 reader study/新增人工标注：不做；
- bbox/lung grounding、真正 official baseline 与 raw-image end-to-end latency：当前
  不冒充已完成，分别随外部标注/官方资产/端到端计时条件后置；
- 基于 Phase20 outcome 的新结构、权重、Seed、容差或 best-seed 选择：禁止。

V2 文档和数值仍是历史开发证据；从本协议生效起，不得再把 V2 写成最终投稿
主方法。S1 的 full-Train 结果未完成前，论文表格应标为 `RUNNING/PENDING`，不得把
Slim Train-only 均值填入 official Dev 主表。
