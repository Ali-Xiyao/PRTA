# PRTA-CXR 训练就绪状态与执行命令

状态：`SPLIT_COMPLETE__CACHE_IN_PROGRESS__TRAIN_QUEUE_PREPARED`

日期：2026-08-03

## 结论

> 2026-08-04 标签版本更新：未来训练/评价的活动标签表面已切换为
> `configs/labeling/sol_authoritative_all_risk_v1.json` 所冻结的全风险 Sol 版本。
> Train+Dev 为 102,826 行，Internal-test 为 13,588 行；Sol `Unclear` 已排除，
> 医生 Gold 250 条不变。旧 `formal_program_v1` 命令仅用于历史复现，不能作为
> 新一轮活动标签入口。详见
> [Sol 全风险标签替换状态](PRTA_CXR_Sol全风险标签替换状态_CN.md)。

当前项目已经具备从 source manifest 到正式训练、断点和内部测试的代码路径，
且真实 source manifest、hash-only exclusions 和全量 adjacent pair pool 已构建并审计。
资深医生 Gold 门已完成：250 条全部为明确五分类，246 条确认 Luna、4 条修正，
Gold 与训练候选患者交集为 0。现在仍不能理解为“插入 GPU 就会自动开始训练”，
正式 split 已完成并通过独立泄漏复算。首次正式训练前还必须完成：

1. 完成正在运行的、本地 BiomedCLIP outcome-free Block-8 与文本缓存；
2. 完成缓存哈希、形状、有限值和样本覆盖审计，并从已验证 shard 构建连续
   FP16 memory-mapped 训练访问存储；
3. 由已冻结的双 GPU keeper 按正式 Run Registry 启动仅使用 Train/Dev 的开发训练。

初始开发队列已冻结为 D201-D205（Luna-primary 10/25/50/75/100% patient-level
嵌套子集）和 M301-H1/H2；H0 复用 D205。规则标签不参与任何训练。

当前真实数据证据、计数和哈希见
[真实数据准备状态](REAL_DATA_PREPARATION_STATUS_CN.md)。
当前独立交集 pilot 的来源一致率、吞吐和全量 HOLD 依据见
[Independent Silver Pilot 状态](INDEPENDENT_SILVER_PILOT_STATUS_CN.md)。历史
证据型流程见 [Luna Pilot 状态](LUNA_PILOT_STATUS_CN.md)，不再作为全量方案。
同一150条的 Sol 盲审结果见
[Sol Blind Review 状态](SOL_BLIND_REVIEW_STATUS_CN.md)：明确五类一致率92.74%。
用户已据此冻结并授权 Luna-primary 全量政策；该结果仍不是医学准确率，人工门不变。
完整全量计数、哈希、训练隔离和 Gold 状态见
[Luna-primary 全量标签状态](LUNA_PRIMARY_FULL_LABELING_STATUS_CN.md)。
资深医生确认/修正、Gold 哈希和患者隔离见
[资深医生 Gold 状态](SENIOR_LUNA_ASSISTED_GOLD_STATUS_CN.md)。

旧的 debug、小 cohort、R 编号临时 roster 不再作为训练规模上限，也不能直接
复制为新 split。揭示过结果的 test、protected gold、external confirmation 和
不满足治理条件的数据仍不能进入训练或模型选择。

## 安全预检（现在可以运行）

这些命令不会读取真实数据或启动训练：

```powershell
python scripts/00_preflight.py
python scripts/01_build_pairs.py --mode preflight
python scripts/02b_prepare_independent_pilot.py --mode preflight
python scripts/02c_prepare_independent_batches.py --mode preflight
python scripts/03b_run_independent_labeling.py --mode preflight
python scripts/04b_merge_independent_silver.py --mode preflight
python scripts/04c_compare_sol_review.py --mode preflight
python scripts/04d_merge_luna_primary.py --mode preflight
python scripts/04e_prepare_gold_audit_roster.py --mode preflight
python scripts/04f_finalize_human_review.py --mode preflight
python scripts/05_freeze_splits.py --mode preflight
python scripts/06_cache_vit_tokens.py --mode preflight
python scripts/06b_build_training_store.py --mode preflight
python scripts/07a_prepare_development_queue.py --mode preflight
python scripts/07b_run_development_queue.py --mode preflight
python scripts/07_train.py --mode preflight
python scripts/08_evaluate.py --mode preflight
```

合成闭环也不会打开真实数据：

```powershell
python scripts/06_cache_vit_tokens.py --mode synthetic --output results/smoke/cache
python scripts/07_train.py --mode smoke --output results/smoke/checkpoint.pt
python scripts/08_evaluate.py --mode synthetic --output results/smoke/evaluation
```

## 正式执行顺序（仅在逐阶段授权后）

下面是命令模板，不是本次运行授权。所有正式入口都要求 `--formal` 和精确环境
确认值；独立 AI runner 还额外要求 `--execute`，内部测试还额外要求
`--open-internal-test`。

### 1. 构建全量候选 pair

source catalog 中的 manifest 环境变量必须指向统一 JSONL。每行必须包含：
`patient_id, study_id, image_id, image_path, report, study_datetime, view,
official_split, time_basis`。`time_basis` 必须区分真实 `calendar` 和
`within_patient_ordinal`；后者只能支持患者内先后顺序，不能支持真实天数分析。

```powershell
$env:PRTA_CXR_ALLOW_FORMAL='I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN'
$env:PRTA_MIMIC_STUDY_MANIFEST='PATH_TO_MIMIC_STUDIES.jsonl'
$env:PRTA_CHEXPERT_PLUS_STUDY_MANIFEST='PATH_TO_CHEXPERT_PLUS_STUDIES.jsonl'
python scripts/01_build_pairs.py --mode formal --formal `
  --catalog configs/data/source_catalog_v1.json `
  --exclusions manifests/protected/excluded_patient_hashes.json `
  --output manifests/pairs/full_candidate_pairs.jsonl `
  --audit-output manifests/receipts/pair_build.json
```

### 2. Luna-primary 标注与合并

以下命令对应已经单独授权的全量标签阶段。运行配置固定候选哈希、模型、prompt、
schema 和 148,798 行；多进程必须使用不重叠的 `--start-batch/--max-batches`，并
共享 `--resume` 输出目录。该授权不包含后续 split、缓存或训练。

```powershell
python scripts/02c_prepare_independent_batches.py --mode formal --formal `
  --candidates manifests/labels/rule_candidates.jsonl `
  --batch-dir manifests/labels/independent_batches `
  --receipt-output manifests/receipts/independent_prepare.json

python scripts/03b_run_independent_labeling.py --mode formal --scope full `
  --formal --execute --resume `
  --config configs/labeling/luna_primary_full_v1.json `
  --preparation-receipt manifests/receipts/independent_prepare.json `
  --batch-dir manifests/labels/independent_batches `
  --output-dir manifests/labels/independent_outputs `
  --receipt-output manifests/receipts/independent_run.json

python scripts/04d_merge_luna_primary.py --mode formal --formal `
  --candidates manifests/labels/rule_candidates.jsonl `
  --batch-dir manifests/labels/independent_batches `
  --luna-output-dir manifests/labels/independent_outputs `
  --accepted-output manifests/labels/luna_primary_silver.jsonl `
  --discarded-output manifests/labels/luna_unclear.jsonl `
  --audit-output manifests/receipts/luna_primary_merge.json

python scripts/04e_prepare_gold_audit_roster.py --mode formal --formal `
  --silver manifests/labels/luna_primary_silver.jsonl `
  --roster-output manifests/audit/gold_pending_human_review.jsonl `
  --quarantine-output manifests/protected/gold_audit_patient_quarantine.jsonl `
  --training-eligible-output manifests/labels/luna_primary_training_eligible.jsonl `
  --quarantined-silver-output manifests/protected/gold_audit_all_patient_rows.jsonl `
  --audit-output manifests/receipts/gold_audit_roster.json `
  --roster-size 250
```

### 3. 从头冻结新 split（已完成）

正式结果：Train/Dev/Internal-test 患者数为 26,045 / 3,256 / 3,256，行数为
91,065 / 16,666 / 16,699；三者及 250 名 Gold 患者之间交集均为 0。canonical
manifest SHA-256 为
`9eb2fadf8d5c568b701f6cfebd75fc06d3bd2bf3fb20f889f20f5f47cf93283b`。

```powershell
python scripts/05_freeze_splits.py --mode formal --formal `
  --input manifests/labels/luna_primary_training_eligible.jsonl `
  --output manifests/splits/full_repartition_v1.jsonl `
  --audit-output manifests/receipts/full_repartition_v1.json
```

### 4. 缓存同一冻结 BiomedCLIP 的输入

`MODEL_ROOT` 必须包含 `open_clip_config.json`、本地 tokenizer 文件和
`open_clip_pytorch_model.bin`。缓存输出同时生成 `cache_manifest.json`、
Block-8 shards、`text_cache.pt` 和对应 receipt。

```powershell
python scripts/06_cache_vit_tokens.py --mode formal --formal `
  --sample-manifest manifests/splits/full_repartition_v1.jsonl `
  --model-root MODEL_ROOT `
  --weights MODEL_ROOT/open_clip_pytorch_model.bin `
  --output results/cache/full_repartition_v1 `
  --device cuda:0
```

缓存完成后，正式训练前还必须构建顺序等价的连续访问存储；该步骤逐 shard 验证
SHA-256、shape 和有限值，并记录 41.175 GiB 文件自身的 SHA-256：

```powershell
python scripts/06b_build_training_store.py --mode formal --formal `
  --cache-root results/cache/full_repartition_v1
```

### 5. 训练

训练只读取 `train` 和 `dev`；训练 receipt 明确记录
`internal_test_opened=false`。每个正式 run 应使用新的输出目录。

```powershell
python scripts/07_train.py --mode formal --formal `
  --config configs/training/prta_full_v1.json `
  --split-manifest manifests/splits/full_repartition_v1.jsonl `
  --cache-root results/cache/full_repartition_v1 `
  --text-cache results/cache/full_repartition_v1/text_cache.pt `
  --weights MODEL_ROOT/open_clip_pytorch_model.bin `
  --label-quality-audit manifests/receipts/human_silver_accuracy_audit.json `
  --run-registry results/run_registry.jsonl `
  --output results/runs/prta_seed17 `
  --device cuda:0
```

断点恢复使用 `--resume SAME_OUTPUT_ROOT/last.pt`，必须回到同一输出目录并通过
config/input hash 身份核验；只原子更新 `training_progress.json` 和 Registry，已有
checkpoint、最终 receipt、预测和指标仍拒绝覆盖。

### 6. 一次性内部测试

只有模型选择冻结且用户单独批准后才能执行：

```powershell
python scripts/08_evaluate.py --mode formal --formal --open-internal-test `
  --checkpoint results/runs/prta_seed17/best.pt `
  --split-manifest manifests/splits/full_repartition_v1.jsonl `
  --cache-root results/cache/full_repartition_v1 `
  --text-cache results/cache/full_repartition_v1/text_cache.pt `
  --weights MODEL_ROOT/open_clip_pytorch_model.bin `
  --output results/evaluation/prta_seed17_internal `
  --device cuda:0
```

## 当前已完成与未执行事项

- 已读取允许范围内的真实报告、检查图像存在性并生成真实 source/pair manifest；
- 未读取真实图像像素；
- 已生成 148,798 个真实规则候选；独立 AI pilot 已完成 150 条并保留 103 条 Silver；
- 已完成 148,798 条全量 Luna-primary 标注：126,727 条 Silver、22,071 条
  `Unclear` 排除；250 条人工审核/Gold 候选 roster 已生成；
- 已完成两名 >5 年资历医生的 Luna 辅助单列共识复核：250 条 Gold，246 条确认、
  4 条修正、排除 0；2,297 条 roster 患者相关 Silver 继续隔离；
- split 已冻结并独立审计；outcome-free 全量缓存正在进行，训练访问存储待缓存完成
  后自动构建；
- 七个初始 Train/Dev 开发配置已准备，双 GPU keeper 代码与 20 分钟任务监控已就绪；
- 未启动 GPU 训练；
- 未打开 internal-test、protected gold 或 external confirmation；
- pilot 数字仅用于工程与流程决策，不是论文科学结论。

## 正式结果、图表与 VLM 附加部署（新增冻结命令面）

开发门、正式矩阵与全部训练完成后，`07e` 冻结协议时必须额外绑定可视化、
VLM 协议和本地 Qwen 资产。配置中不写死本机路径；模型根目录由下面两个
受哈希保护的文件共同确定，协议冻结器还会自动哈希 index 引用的全部权重分片
以及 tokenizer 资产：

```powershell
python scripts/07e_freeze_protocol.py --mode formal --formal `
  ...原有全部冻结参数... `
  --case-selection-config configs/experiments/visualizations/case_selection_v1.json `
  --vlm-config configs/experiments/vlm_additional/protocol_v1.json `
  --vlm-model-config QWEN_MODEL_ROOT/config.json `
  --vlm-model-index QWEN_MODEL_ROOT/model.safetensors.index.json `
  --output FORMAL_ROOT/receipts/protocol_freeze_v1.json
```

完成一次性 outcome session 和信任审计后，生成 V701–V708。入口同时输出
PNG、SVG、逐文件 SHA-256、Figure 8 的 5 桶 × 5 例固定哈希抽样清单；不能
人工替换案例，也不把注意力图声称为内部因果证据：

```powershell
python scripts/10_make_figures.py --mode formal --formal `
  --protocol-freeze FORMAL_ROOT/receipts/protocol_freeze_v1.json `
  --outcome-session FORMAL_ROOT/formal_outcome/session_receipt.json `
  --predictions-root FORMAL_ROOT/formal_outcome/predictions `
  --trust-audit FORMAL_ROOT/trust/trust_audit.json `
  --development-root FORMAL_ROOT/development/runs `
  --quality-audit FORMAL_ROOT/receipts/human_silver_accuracy_audit.json `
  --case-selection configs/experiments/visualizations/case_selection_v1.json `
  --output FORMAL_ROOT/figures
```

X801–X806 永远最后运行。它只使用冻结 B404 Seed 17，固定 2,500 条 Train
Silver 训练一个 projector，Qwen3-VL-4B 参数全部冻结，并在同一 outcome
session 已打开的 250 条资深医生 Gold 上做结构化五分类。该结果不建立 VLM
baseline 矩阵，也不得反向修改 PRTA；失败时按冻结阈值省略附加小节：

```powershell
python scripts/11_vlm_additional.py --mode formal --formal `
  --protocol-freeze FORMAL_ROOT/receipts/protocol_freeze_v1.json `
  --outcome-session FORMAL_ROOT/formal_outcome/session_receipt.json `
  --output FORMAL_ROOT/vlm_additional `
  --device cuda:0
```

中断后仅允许原身份恢复：在同一命令上加 `--resume`。VLM 结果收据明确记录
64-token/60-active+4-reserved、零可训练 VLM 参数、无像素旁路、结构有效率、
finding 一致性、时间矛盾率，以及 `prta_changed_after_vlm=false`。

最后由下列命令自动复算 Table 1–8 和 Expert Gold 附表。它要求图表和 VLM
均已形成终态收据（VLM 可以是 `HOLD_OMIT_ADDITIONAL`），并输出 JSON、中文
Markdown 和最终化 SHA-256 收据：

```powershell
python scripts/12_build_paper_tables.py --mode formal --formal `
  --protocol-freeze FORMAL_ROOT/receipts/protocol_freeze_v1.json `
  --outcome-session FORMAL_ROOT/formal_outcome/session_receipt.json `
  --trust-audit FORMAL_ROOT/trust/trust_audit.json `
  --figure-manifest FORMAL_ROOT/figures/figure_manifest.json `
  --vlm-result FORMAL_ROOT/vlm_additional/result.json `
  --output FORMAL_ROOT/paper_results
```

上述全流程可由 `13_run_formal_program_keeper.py` 在后台串联。它不会接管或
重复启动当前初始队列，而是等待其 `scheduler_receipt.json`；所有后续阶段仍
逐一执行相同 GO/HOLD、协议冻结和一次性 outcome 门。关键路径必须传入真实
冻结 artifact，模型只通过 config/index 定位：

```powershell
python scripts/13_run_formal_program_keeper.py --mode formal --formal `
  --output FORMAL_ROOT/program_keeper_v1 `
  --initial-queue FORMAL_ROOT/development/initial_queue_v1/run_queue.json `
  --split-manifest $SOL_TRAIN_DEV `
  --sealed-internal-test $SOL_INTERNAL_TEST `
  --gold-manifest GOLD_MANIFEST.jsonl `
  --cache-root FORMAL_ROOT/cache/full_repartition_v1 `
  --gold-cache-root FORMAL_ROOT/cache/gold_candidate_v1 `
  --weights BIOMEDCLIP_ROOT/open_clip_pytorch_model.bin `
  --quality-audit FORMAL_ROOT/receipts/human_silver_accuracy_audit.json `
  --run-registry FORMAL_ROOT/run_registry.jsonl `
  --development-runs-root FORMAL_ROOT/development/runs `
  --formal-runs-root FORMAL_ROOT/formal_runs `
  --protocol-config configs/experiments/formal_protocol_v1.json `
  --trust-config configs/experiments/trust_audits/protocol_v1.json `
  --case-selection-config configs/experiments/visualizations/case_selection_v1.json `
  --vlm-config configs/experiments/vlm_additional/protocol_v1.json `
  --vlm-model-config QWEN_MODEL_ROOT/config.json `
  --vlm-model-index QWEN_MODEL_ROOT/model.safetensors.index.json `
  --devices cuda:0,cuda:1 --outcome-device cuda:0 --poll-seconds 30
```

`program_state.json` 是可变进度面，`program_receipt.json` 只在全程序正式完成
时产生。Dev gate 为 HOLD/STOP 时不会创建 protocol freeze 或读取 outcome。
