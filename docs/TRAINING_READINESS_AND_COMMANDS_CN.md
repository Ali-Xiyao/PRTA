# PRTA-CXR 训练就绪状态与执行命令

状态：`PAIR_POOL_READY__LABEL_SPLIT_CACHE_TRAIN_HOLD`

日期：2026-08-02

## 结论

当前项目已经具备从 source manifest 到正式训练、断点和内部测试的代码路径，
且真实 source manifest、hash-only exclusions 和全量 adjacent pair pool 已构建并审计。
但现在还不能理解为“插入 GPU 就会自动开始训练”。在首次正式运行前仍必须完成：

1. 对已冻结的 238,511 个 pair 生成规则候选并完成 Luna 审核；
2. 完成标签规模、五类覆盖、冲突拒绝和小规模人工抽检门；
3. 从新的合规候选池重新冻结 patient-disjoint 80/10/10 split；
4. 指定本地 BiomedCLIP 模型目录和 GPU，生成新的 Block-8 与文本缓存；
5. 用户单独授权具体的缓存或训练运行。

当前真实数据证据、计数和哈希见
[真实数据准备状态](REAL_DATA_PREPARATION_STATUS_CN.md)。

旧的 debug、小 cohort、R 编号临时 roster 不再作为训练规模上限，也不能直接
复制为新 split。揭示过结果的 test、protected gold、external confirmation 和
不满足治理条件的数据仍不能进入训练或模型选择。

## 安全预检（现在可以运行）

这些命令不会读取真实数据或启动训练：

```powershell
python scripts/00_preflight.py
python scripts/01_build_pairs.py --mode preflight
python scripts/02_prepare_luna_batches.py --mode preflight
python scripts/03_run_luna_labeling.py --mode preflight
python scripts/04_merge_and_audit_labels.py --mode preflight
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
确认值；Luna 还额外要求 `--execute`，内部测试还额外要求
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

### 2. 标注与合并

```powershell
python scripts/02_prepare_luna_batches.py --mode formal --formal `
  --pairs manifests/pairs/full_candidate_pairs.jsonl `
  --candidate-output manifests/labels/rule_candidates.jsonl `
  --batch-dir manifests/labels/luna_batches `
  --receipt-output manifests/receipts/luna_prepare.json

python scripts/03_run_luna_labeling.py --mode formal --formal --execute `
  --batch-dir manifests/labels/luna_batches `
  --output-dir manifests/labels/luna_outputs `
  --receipt-output manifests/receipts/luna_run.json

python scripts/04_merge_and_audit_labels.py --mode formal --formal `
  --candidates manifests/labels/rule_candidates.jsonl `
  --luna-dir manifests/labels/luna_outputs `
  --output manifests/labels/verified_samples.jsonl `
  --audit-output manifests/receipts/label_merge.json
```

### 3. 从头冻结新 split

```powershell
python scripts/05_freeze_splits.py --mode formal --formal `
  --input manifests/labels/verified_samples.jsonl `
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
- 未生成真实规则/Luna 标签、split 或缓存；
- 未调用 Luna；
- 未启动 GPU 训练；
- 未打开 internal-test、protected gold 或 external confirmation；
- 未产生任何可用于论文结论的数字。
