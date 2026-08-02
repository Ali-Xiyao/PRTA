# PRTA-CXR 训练就绪状态与执行命令

状态：`LUNA_PRIMARY_LABELING_COMPLETE__HUMAN_AUDIT_SPLIT_CACHE_TRAIN_HOLD`

日期：2026-08-02

## 结论

当前项目已经具备从 source manifest 到正式训练、断点和内部测试的代码路径，
且真实 source manifest、hash-only exclusions 和全量 adjacent pair pool 已构建并审计。
但现在还不能理解为“插入 GPU 就会自动开始训练”。在首次正式运行前仍必须完成：

1. 完成 250 条 source × 五类 Luna Silver 人工准确率审核门；
2. 确认每条 Gold 候选均经人工复核后，才可称为 Gold；
3. 从新的合规候选池重新冻结 patient-disjoint 80/10/10 split；
4. 指定本地 BiomedCLIP 模型目录和 GPU，生成新的 Block-8 与文本缓存；
5. 用户单独授权具体的缓存或训练运行。

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
python scripts/05_freeze_splits.py --mode preflight
python scripts/06_cache_vit_tokens.py --mode preflight
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

### 3. 从头冻结新 split

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
  --output results/runs/prta_seed17 `
  --device cuda:0
```

断点恢复使用 `--resume PATH_TO_LAST.pt`，仍写入一个新的输出目录，避免覆盖旧证据。

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
- 未完成人工准确率抽检、split 或缓存；
- 未启动 GPU 训练；
- 未打开 internal-test、protected gold 或 external confirmation；
- pilot 数字仅用于工程与流程决策，不是论文科学结论。
