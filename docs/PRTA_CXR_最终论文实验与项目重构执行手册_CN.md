# PRTA-CXR 最终论文实验与项目重构执行手册（ViT 主线版）

> 版本：v1.0  
> 日期：2026-08-01  
> 目标：Information Fusion 特刊 “Trustworthy Multimodal Information Fusion for Healthcare”  
> 主线：原生纵向 ViT 分类器；VLM 仅为最终附加部署展示  
> 旧项目：`Ali-Xiyao/VisualVIT`  
> 新主项目建议名称：`PRTA-CXR`

---

## 0. 最终决策

### 0.1 正式论文只保留一条主方法主线

```text
PRIOR 胸片 + CURRENT 胸片 + finding query
        ↓
医学 ViT patch token
        ↓
PRTA finding-conditioned 跨时间对齐
        ↓
Current state + directional transition + aligned prior evidence
        ↓
原生五分类头
        ↓
Stable / Improved / Worse / New / Resolved
```

正式论文不再保留 matched-representation benchmark，也不把 Qwen/VLM 当作主方法。论文只比较各方法在其合理原生实现下的纵向五分类性能。

VLM 只在全部 ViT 实验完成后做一次附加部署：

```text
冻结后的最终 PRTA 表征
        ↓
固定视觉 token 接口 / 轻量 projector
        ↓
一个冻结或轻量 post-trained VLM
        ↓
结构化 progression 或简短比较句
```

这部分只回答“PRTA 表征能否迁移到 VLM”，不做 VLM 基线大矩阵，不把其他方法强行部署成 VLM，也不让 VLM 结果反向牵引主方法。

### 0.2 独立交集 Silver 标签的正式名称

使用规则程序与 rule-blind AI 独立判断并只保留一致交集，是可行的大规模数据构建方案，论文中应称为：

- `rule–AI agreement silver labels`；
- `independently cross-checked pseudo-labels`；
- `report-derived weak supervision`。

不能将自动一致标签直接称为人工 Gold 或声称必然正确。最低人工环节是在全量完成后按来源与五类做 200–300 条分层准确率抽检，而不是重新人工标注整套训练集。

### 0.3 最终执行顺序

```text
新项目重构与 parity
→ 扩大纵向样本、rule-blind AI 交集、医生抽检
→ 仅在 Train/Dev 上把主 ViT 指标做上去
→ 冻结数据、方法、指标和测试协议
→ 正式 baseline
→ 正式 ablation
→ 可信性、校准、亚组和可视化
→ 最后补一次 PRTA→VLM 附加部署
→ 一次性运行现有 expert Gold（若完整可用）
```

---

## 1. 论文故事主线

### 1.1 核心科学问题

纵向胸片模型即使预测正确，也可能主要依赖 CURRENT 图像、类别分布或全局外观，而没有真正利用同一患者、正确时间点的 PRIOR。

本文研究的不是普通的单图疾病识别，而是：

> 给定 PRIOR、CURRENT 和一个具体 finding，模型能否利用正确历史证据，识别该 finding 的方向性变化，并在错误、缺失或反转的历史信息下表现出可解释的退化？

### 1.2 一句话方法

> PRTA-CXR 在医学 ViT patch 表征上，使用 finding-conditioned cross-time attention 将 CURRENT token 与相关 PRIOR 证据软对齐，显式分离当前状态与方向性变化，并通过错误 PRIOR、时间反转和状态保持约束学习可信的纵向表示。

### 1.3 建议贡献点

1. **PRTA 时间融合结构**：finding-conditioned patch-level alignment，显式组织 CURRENT、aligned PRIOR、signed difference、absolute difference 和 token interaction。
2. **State/Transition 解耦**：分别学习“当前是什么”与“发生了什么变化”，避免两类信息被混入一个全局向量。
3. **Correct-prior responsiveness**：使用 Current-Matched Counterfactual Prior、时间反转和 state preservation，抑制只看 CURRENT 的 shortcut。
4. **可扩展报告监督**：使用规则候选 + Luna 证据审核 + 冲突拒绝构建高置信弱监督训练集，并以少量医生抽检量化标签质量。
5. **附加迁移能力**：最终 PRTA 表征可进一步接入 VLM，但该结果只作为额外部署展示。

### 1.4 明确不做的内容

- 不把自动标签称为人工 Gold；
- 不宣称已经达到临床部署水平；
- 不把自由报告生成作为主任务；
- 不做 matched-representation benchmark；
- 不要求所有 baseline 接入 VLM；
- 不重新使用已经揭示的历史 test cohort 做调参；
- 不把模型输入干预称为真实世界临床因果推断。

---

## 2. 最终方法学设计

### 2.1 输入、输出与数据字段

每条 patient-finding 样本至少包含：

```text
sample_id
patient_id_hash
source
prior_study_id
current_study_id
prior_image_path
current_image_path
prior_report
current_report
prior_datetime
current_datetime
interval_days
prior_view
current_view
finding
progression_label
label_source
label_tier
```

五类固定为：

```text
Stable / Improved / Worse / New / Resolved
```

时间反转映射固定为：

```text
Stable   → Stable
Improved ↔ Worse
New      ↔ Resolved
```

### 2.2 报告监督与独立交集 Silver Pipeline

```text
原始纵向 study
    ↓
患者内按时间排序
    ↓
相邻合格 PRIOR–CURRENT 配对
    ↓
规则程序生成候选 progression（仅本地保存）
    ↓
AI 只读取 finding、PRIOR 报告、CURRENT 报告
    ↓
AI 独立输出五类标签之一或 Unclear
    ↓
本地比较 Rule Label 与 AI Label
    ↓
完全一致且非 Unclear → Silver；否则排除
    ↓
完成 source × 五类的 200–300 条人工准确率抽检
    ↓
患者级 Train / Dev / Internal-test 划分
```

#### AI 强制输出的 JSON 字段

```json
{
  "sample_id": "short-batch-local-alias",
  "ai_label": "Improved"
}
```

`ai_label` 只能为：

```text
Stable / Improved / Worse / New / Resolved / Unclear
```

外发请求中严禁包含规则候选标签、患者标识、原始 sample hash 或
alias-to-original 映射。AI 不输出理由、置信度或原文证据；代码必须拒绝缺行、
多行、重复 ID、未知标签和任何额外字段。

#### Silver：主训练候选

同时满足：

- 规则与 AI 相互独立；
- AI 输出不是 `Unclear`；
- `rule_label == ai_label` 完全一致；
- 样本通过 ID、schema、来源和患者隔离检查。

#### Excluded

以下样本不进入 silver 训练清单：

- 规则与 AI 标签不一致；
- AI 输出 `Unclear`；
- AI 输出缺失、重复、未知或 schema/ID 不合法。

规则与 AI 一致只表示标签可信度较高，不证明标签一定正确。不得把自动一致率
写成 gold accuracy，也不得人工逐条修补后回填为自动 silver。

#### 2026-08-02 Sol 盲审后的候选政策更新（待确认）

同一冻结150条中，Luna 与 Sol 在双方明确的124条上五类一致115条
（92.74%，κ=0.908）；30条规则–Luna分歧中，Sol支持Luna 21条、规则4条。
这支持把后续候选政策改为：自动程序负责结构与finding，Luna负责五类标签，
Luna=`Unclear`排除，规则标签只用于审计而非Silver硬准入。

在用户正式确认该政策之前，本节上方的 Rule∩AI 准入仍是当前冻结实现；Sol结果
不自动授权全量标注。无论采用哪一方案，200–300条人工准确率门禁不变。完整
结果见 `docs/SOL_BLIND_REVIEW_STATUS_CN.md`。

### 2.3 临床抽检最小方案

不新增人工大规模标注集。全量自动标注完成后，按
`数据源 × 五类 Silver 标签` 固定随机种子分层抽取 200–300 条：

- MIMIC-CXR 与 CheXpert Plus 分别覆盖，不能用总体结果替代来源结果；
- 五类均须覆盖，尽量同时覆盖不同 finding；
- 医生只判断“报告是否支持该 finding 的该 progression”；
- 第二位医生仅复核第一位医生判为错误、无法判断或存在争议的样本。

建议质量门：

- Silver 总体医生一致率建议 ≥ 90%；
- 任一类别医生一致率 ≥ 80%；
- 必须报告 MIMIC-CXR 与 CheXpert Plus 各自准确率和置信区间；
- 若未通过，冻结训练，修订规则、prompt 或接受门；
- prompt 或规则修订后必须重新运行全量标注，不能逐行人工修补错误标签。

若只有一名医生，称为 `clinician-audited subset`；若两名医生独立审核并裁决分歧，可称为 `expert reference subset`。

### 2.4 PRTA 主干

#### 医学 ViT

优先保留当前已验证的医学 ViT/ BiomedCLIP backbone 与中间 patch-token 入口。早期层冻结；后期层使用共享的参数高效 adapter。是否扩大 adapter 作用范围只能在开发阶段做有限比较。

#### Finding query

```text
q_f = MLP(TextEncoder(finding))
```

文本编码器冻结，finding projection 可训练。

#### Query-conditioned cross-time alignment

```text
A = MHA(
    Q = LN(C + q_f),
    K = LN(P + q_f),
    V = LN(P)
)
```

A 表示对每个 CURRENT token，从 PRIOR 中检索到的、与指定 finding 相关的历史证据。

#### 关系特征

```text
R = [C, A, C-A, |C-A|, C⊙A]
U = C + RelationMLP(R)
```

#### State / Transition 双分支

```text
S = StateResampler(C, q_f)
T = TransitionResampler(U, q_f)
```

- S：当前 finding 的状态表示；
- T：相对匹配 PRIOR 的方向性变化表示。

### 2.5 原生五分类头

主论文不使用 fixed-64 flatten head。开发阶段只比较三个原生 head，并在 Dev 上一次性选定：

| Head | 结构 | 用途 |
|---|---|---|
| H0 | `mean(T) → LayerNorm → Linear → 5` | 当前简洁基线 |
| H1 | `[mean(S), mean(T), S⊙T, q_f] → MLP → 5` | 首选候选 |
| H2 | query-attentive pooling(S,T) → H1-style MLP | 仅当 H1 明显不足 |

H1 建议形式：

```text
s = mean(S)
t = mean(T)
h = [s, t, s⊙t, q_f]
LayerNorm → Linear(3072→768) → GELU → Dropout → Linear(768→5)
```

采用规则：

- Seed 17 做 H0/H1/H2 screening；
- 最优 head 相对 H0 Dev Macro-F1 至少提高 1.5 pp，且 matched-wrong-prior 指标不恶化，才进入三 Seed 确认；
- 未达到门槛则保留 H0，避免为了指标无效增复杂度。

### 2.6 训练目标

```text
L = L_cls
  + λ_align L_transition-text
  + λ_cmcp L_CMCP
  + λ_state L_state-preservation
  + λ_inv L_temporal-inversion
```

类别不平衡策略只允许有限比较：

- Weighted Cross Entropy；
- Balanced Softmax；
- Class-balanced Focal Loss。

先单 Seed screening，再对唯一入选方案做三 Seed，不进行无边界网格搜索。

### 2.7 VLM 附加部署

全部 ViT 结果冻结后才开始：

```text
最终 PRTA checkpoint
    ↓
固定 token 打包
    ↓
轻量 projector / 小规模 post-training
    ↓
一个 VLM
    ↓
结构化 progression 或一句比较描述
```

只报告同一最终 PRTA 的 ViT 主结果和 VLM 部署结果；不引入 VLM baseline 矩阵；不重新做完整 VLM 消融。

---

## 3. 新主项目重构

### 3.1 新建独立项目

建议在旧仓库同级新建：

```text
PRTA-CXR/
```

旧 `VisualVIT` 进入只读状态，仅作为历史证据库。新项目不复制 R1–R52 的历史编号和失败路线。

### 3.2 建议目录

```text
PRTA-CXR/
├── README.md
├── AGENTS.md
├── pyproject.toml
├── LICENSE
├── configs/
│   ├── data/
│   ├── labeling/
│   ├── models/
│   ├── training/
│   └── experiments/
│       ├── performance_development/
│       ├── formal_baselines/
│       ├── ablations/
│       ├── trust_audits/
│       ├── visualizations/
│       └── vlm_additional/
├── prompts/
│   ├── independent_silver_label_v1.md
│   ├── luna_label_v1.md              # 历史严格 pilot
│   └── luna_verify_v1.md             # 历史严格 pilot
├── schemas/
│   ├── independent_silver_label_batch.schema.json
│   └── luna_label_batch.schema.json  # 历史严格 pilot
├── src/prta_cxr/
│   ├── data/
│   ├── models/
│   ├── training/
│   ├── evaluation/
│   ├── visualization/
│   └── vlm/
├── scripts/
│   ├── 00_preflight.py
│   ├── 01_build_pairs.py
│   ├── 02_prepare_luna_batches.py
│   ├── 02b_prepare_independent_pilot.py
│   ├── 02c_prepare_independent_batches.py
│   ├── 03_run_luna_labeling.py
│   ├── 03b_run_independent_labeling.py
│   ├── 04_merge_and_audit_labels.py
│   ├── 04b_merge_independent_silver.py
│   ├── 05_freeze_splits.py
│   ├── 06_cache_vit_tokens.py
│   ├── 07_train.py
│   ├── 08_evaluate.py
│   ├── 09_run_trust_audits.py
│   ├── 10_make_figures.py
│   └── 11_vlm_additional.py
├── manifests/
│   ├── exclusions/
│   ├── splits/
│   ├── labels/
│   └── receipts/
├── tests/
├── results/
├── paper/
└── docs/
```

### 3.3 从旧项目迁移什么

只迁移经过验证的最小核心：

- PRTA adapter、alignment、resampler 和 losses；
- BiomedCLIP token cache；
- CMCP 构造；
- patient-cluster bootstrap、指标与统计脚本；
- 时间反转映射；
- 仍有效的数据 pairing 和报告规则；
- fixed-token/VLM projector 仅在最后阶段迁移。

不迁移：

- 旧 R 编号 launcher；
- 失败路线；
- 历史 frozen roster；
- matched-representation benchmark；
- 旧 Qwen SFT 尝试；
- 与最终论文无关的 reports/history。

### 3.4 重构完成门

进入新实验前必须满足：

1. 新项目可独立安装；
2. 单元测试全部通过；
3. 在相同旧 checkpoint/小 cohort 上，新旧代码预测逐行一致，或指标差异落在预先允许的浮点误差内；
4. patient leakage 检查为 0；
5. Luna schema/parser 对非法输出 fail-closed；
6. 所有 split、prompt、schema 和 config 均记录 SHA256；
7. 每次运行保存 commit、config、split hash、label manifest hash、环境和随机种子。

---

## 4. 具体实验执行顺序

### Phase 0：项目重构与旧结果 parity

**目标**：得到一个干净、可独立运行的 `PRTA-CXR` 项目。

任务：

- 创建新 Git repository；
- 白名单迁移核心模块；
- 统一 config 和 CLI；
- 建立 tests；
- 在旧小 cohort 上复现一次 A6/native-head 结果；
- 旧仓库冻结为只读。

产出：

- `v0.1.0-refactor`；
- migration receipt；
- parity report；
- 测试与环境报告。

未通过 parity 不进入数据扩展。

### Phase 1：数据扩展、独立交集 Silver 与医生抽检

**目标**：在不新增人工大规模标注的前提下，扩大训练数据并提高标签精度。

顺序：

1. 扩大已批准公开数据源中的合格纵向 pair；
2. 规则提取候选；
3. AI 在看不到规则标签的前提下批量输出单一标签；
4. 本地取规则与 AI 的非 `Unclear` 完全一致交集；
5. 分来源统计一致率并排除 mismatch/`Unclear`；
6. 全量完成后分层抽取 200–300 条做人工准确率检查；
7. 必要时修订并冻结 prompt/规则后重新运行全量标签；
8. 排除历史 test、医生审计集和现有 Gold；
9. 按患者冻结 Train/Dev/Internal-test。

建议划分：

- Train：80% 患者；
- Dev：10% 患者；
- Internal test：10% 患者；
- 现有 expert Gold：独立 quarantine；
- 尽量按 source 和患者主导类别近似分层；
- 同一患者的所有 finding rows 只能出现在一个 split。

### Phase 2：先把主方法指标做上去

这一阶段只使用 Train/Dev，不运行正式 Internal-test 或 Gold。

#### 2.1 数据收益阶梯

| ID | 训练数据 | 目的 |
|---|---|---|
| D0 | 旧训练规模 + 旧规则标签 | 迁移后的基准 |
| D1 | 扩展规模 + 旧规则标签 | 分离“规模收益” |
| D2 | 扩展规模 + Rule/AI agreement Silver | 分离“质量收益” |
| D3 | 扩展规模 + Rule-only | 测试质量-数量权衡 |

#### 2.2 有限方法开发

只筛选：

- H0/H1/H2 原生分类头；
- 3 种类别不平衡 loss；
- 最多 2 个 adapter 作用范围候选。

规则：

- screening 使用 Seed 17；
- 每轮只改变一个轴；
- 入选设置必须提高 Dev Macro-F1，且 matched-wrong-prior gap 不下降；
- 最终候选使用 Seeds 17/29/43 确认；
- 连续两轮修改小于 0.5 pp 时停止架构开发。

#### 2.3 Performance-development 出口门

建议满足以下条件再冻结正式方法：

- Dev Macro-F1 ≥ 0.52；理想目标 ≥ 0.55；
- 相对最强简单 temporal baseline ≥ +3 pp；
- 最差类别 Recall ≥ 0.20；理想 ≥ 0.30；
- opposite-direction error 低于最强 baseline；
- True PRIOR 明显优于 matched-wrong PRIOR；
- 三 Seed 无单一 seed 崩溃。

若扩展数据后仍低于 0.48，应暂停正式实验，优先做标签噪声、类别混淆和 source 偏差分析，而不是立即批量跑消融。

### Phase 3：正式协议冻结

冻结：

- 数据和排除 manifest；
- Luna prompt/schema；
- Train/Dev/Internal-test；
- 最终方法 config；
- baseline config；
- 指标、seeds 与 bootstrap 规则；
- 可视化案例选择规则；
- Gold 读取条件。

从此刻起，Internal-test 只运行一次正式预测；看到结果后不再修改方法。

### Phase 4：正式主对比

不做 matched-representation benchmark。

最小正式 baseline 集：

| 方法 | 定义 | 是否必须 |
|---|---|---|
| Current-only BiomedCLIP | CURRENT + finding query | 必须 |
| Siamese Signed/Absolute Difference | 共享 ViT，融合 current/prior/signed/absolute difference | 必须 |
| TILA 或等价强 temporal attention | 合理原生实现 | 必须 |
| PRTA-CXR | 最终主方法 | 必须 |
| BioViL-T | 仅在代码、权重和数据访问稳定时 | 可选 |

公平性要求：

- 同一 Train/Dev/Internal-test；
- 同一 patient exclusions；
- 相同图像预处理和主指标；
- 相同 Seeds 17/29/43；
- 同一 class sampler/loss，除非原方法必须使用专属设置；
- 每个 baseline 使用合理原生 head；
- 报告参数量、训练时长、显存和推理延迟。

### Phase 5：正式消融

完整 PRTA 与以下单组件删除比较：

- w/o finding conditioning；
- w/o cross-time alignment；
- w/o state/transition decoupling；
- w/o CMCP；
- w/o temporal inversion；
- w/o state preservation；
- 可选：rule-only labels 替代 Rule/AI agreement Silver。

所有消融使用同一 split、同一最终 head、同一训练预算和三个 seeds；不在正式 test 上选择变体。

### Phase 6：可信性、校准与亚组

#### PRIOR 干预

对最终冻结 checkpoint 仅做推理：

- True PRIOR；
- Current-only；
- Null PRIOR；
- Random PRIOR；
- Matched-wrong PRIOR；
- Reversed pair；
- Wrong finding query。

报告：Macro-F1、NLL、Brier、平均置信度、prediction flip rate、Correct→Wrong、Wrong→Correct、opposite-direction error，以及 True vs wrong PRIOR 的 patient-cluster paired bootstrap CI。

#### 校准与选择性预测

- Temperature scaling 只在 Dev 拟合；
- Internal-test/Gold 只评价；
- 报告 NLL、Brier、ECE、AURC；
- 画 reliability diagram 与 risk-coverage curve；
- 报告 risk at 90%、80%、70% coverage。

#### 亚组

- progression class；
- finding；
- source；
- AP/PA；
- view match/mismatch；
- interval-days；
- rare/common labels。

亚组只用于描述，不据亚组结果修改模型。大量显著性比较使用 Holm correction。

### Phase 7：可视化与错误分析

建议正文图：

1. 方法与标签 Pipeline；
2. 数据漏斗和 Luna 拒绝原因；
3. 训练数据 scaling curve；
4. 主结果 paired-effect forest plot；
5. 五类 confusion matrix；
6. finding × progression 热力图；
7. calibration + risk-coverage；
8. True/Wrong PRIOR 与 query-swap 案例图。

案例选择必须预先冻结：

- 正确高置信；
- 正确低置信；
- 错误高置信；
- 正确 abstain。

从每个桶中随机抽取，不能只挑最好看的成功病例。若已有现成 bounding box，可增加 pointing game/CNR；没有现成框则不新增框标注数据集。

### Phase 8：VLM 附加工作

所有正式 ViT 结果完成后：

- 使用最终唯一 PRTA checkpoint；
- 训练一个小 projector 或进行轻量 post-training；
- 输出结构化 progression 或一句 finding-level comparison；
- 仅报告一张结果表和少量成功/失败案例；
- 不引入 VLM baseline 矩阵；
- 不根据 VLM 结果回头修改 PRTA。

---

## 5. 独立 AI / Codex 批处理建议

GPT-5.6 Luna 适合明确、重复、可验证的抽取与分类任务。Codex CLI 的非交互执行可通过 stdin 读取批次，并以 JSON Schema 约束输出。

建议命令模板：

```bash
cat artifacts/label_inputs/batch_0001.txt \
  | codex exec \
      -m gpt-5.6-luna \
      --ephemeral \
      --sandbox read-only \
      --ignore-user-config \
      --ignore-rules \
      --output-schema schemas/independent_silver_label_batch.schema.json \
      -o artifacts/label_outputs/batch_0001.json \
      -
```

执行约束：

- 每批 20–30 条；
- 输入仅包含短 `sample_id`、finding 和前后报告，不含规则标签或真实 patient ID；
- 只使用已去标识、许可允许处理的报告；
- 每批保存 input hash、output hash、模型名、CLI 版本、运行日期、prompt hash、schema hash；
- 非法 JSON、缺字段、重复 sample_id、未知标签全部 fail-closed；
- 失败批次可使用同一 prompt 重试，不能人工改写模型输出；
- AI 只输出单一标签；mismatch 和 `Unclear` 直接排除，不做第二次自动裁决；
- 正式运行前先以 100–200 条 pilot 验证结构化输出、速度、额度和失败率。

---

## 6. 指标与统计

### 主指标

```text
Macro-F1
```

### 次指标

- Balanced Accuracy；
- Accuracy；
- 每类 Precision/Recall/F1；
- Min-class Recall；
- Opposite-direction Error Rate（ODER）；
- NLL；
- Brier Score；
- ECE；
- AURC。

### 统计协议

- Seeds：17、29、43；
- 汇报 mean ± SD；
- 以 patient 为 cluster 做 10,000 次 paired bootstrap；
- 主比较报告 PRTA − strongest baseline 的 95% CI；
- accuracy 可补充 McNemar；
- Internal-test 只读取一次；
- Expert Gold 若完整可用，最后一次性运行；
- checkpoint、temperature 和 threshold 均只在 Dev 选择。

ODER 定义为：

```text
Improved → Worse
Worse → Improved
New → Resolved
Resolved → New
```

这些是方向相反的严重时间推理错误，但在没有临床研究支持时，不直接称为“临床危险错误”。

---

## 7. 实验编号规范

| 前缀 | 模块 |
|---|---|
| R0xx | Repository refactor |
| L1xx | Luna labeling and clinician audit |
| D2xx | Data scaling and label-quality development |
| M3xx | Main-method performance development |
| B4xx | Formal baselines |
| A5xx | Ablations |
| T6xx | Trust, calibration and subgroup audits |
| V7xx | Visualizations and failure analysis |
| X8xx | Additional VLM deployment |

推荐编号：

```text
R001  New repo skeleton
R002  Legacy parity
L101  Candidate extraction
L102  Independent-label pilot
L103  Clinician audit
L104  Frozen full labeling
D201  Old-size rule labels
D202  Full-size rule labels
D203  Full-size Rule/AI agreement Silver
D204  Full-size Rule-only
M301  Head screening
M302  Loss screening
M303  Adapter-range screening
M304  Three-seed final confirmation
B401  Current-only
B402  Siamese diff
B403  TILA
B404  PRTA final
A501–A506  Component ablations
T601  PRIOR interventions
T602  Time reversal
T603  Calibration
T604  Risk coverage
T605  Subgroups
V701–V708  Paper figures
X801  PRTA-to-VLM additional deployment
```

---

## 8. 论文正式表格设计

### Table 1：数据与标签构建

| Source | Candidate patients | Candidate pairs | Candidate rows | Rule-valid | AI-labeled | Silver | Mismatch/Unclear | Final train/dev/test |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MIMIC-CXR |  |  |  |  |  |  |  |  |
| CheXpert |  |  |  |  |  |  |  |  |
| Other approved source |  |  |  |  |  |  |  |  |
| Total |  |  |  |  |  |  |  |  |

### Table 2：标签质量审计

| Label pipeline | Coverage | Clinician agreement | New PPV | Resolved PPV | Improved PPV | Stable PPV | Worse PPV | Reject precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Rule-only |  |  |  |  |  |  |  |  |
| Rule/AI agreement Silver |  |  |  |  |  |  |  |  |

### Table 3：正式主结果

| Method | Backbone | Temporal fusion | Params | Macro-F1 | Balanced Acc | Accuracy | Min recall | ODER | 95% CI |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| Current-only |  |  |  |  |  |  |  |  |  |
| Siamese Diff |  |  |  |  |  |  |  |  |  |
| TILA |  |  |  |  |  |  |  |  |  |
| PRTA-CXR |  |  |  |  |  |  |  |  |  |

### Table 4：数据规模与标签质量

| Train fraction | Patients | Rows | Label tier | Strong baseline F1 | PRTA F1 | Gain | 95% CI |
|---|---:|---:|---|---:|---:|---:|---|
| 25% |  |  |  |  |  |  |  |
| 50% |  |  |  |  |  |  |  |
| 75% |  |  |  |  |  |  |  |
| 100% |  |  |  |  |  |  |  |

### Table 5：方法消融

| Variant | Finding condition | Alignment | Dual branch | CMCP | Inversion | State preserve | Macro-F1 | Prior gap | ODER |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full PRTA | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| w/o finding |  | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| w/o alignment | ✓ |  | ✓ | ✓ | ✓ | ✓ |  |  |  |
| w/o dual branch | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |
| w/o CMCP | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |  |
| w/o inversion | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  |  |
| w/o state preserve | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |

### Table 6：可信输入干预

| Input condition | Macro-F1 | Δ vs True | NLL | Brier | Confidence | Flip rate | C→W | W→C | ODER |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| True PRIOR |  | — |  |  |  | — | — | — |  |
| Current-only |  |  |  |  |  |  |  |  |  |
| Null PRIOR |  |  |  |  |  |  |  |  |  |
| Random PRIOR |  |  |  |  |  |  |  |  |  |
| Matched-wrong PRIOR |  |  |  |  |  |  |  |  |  |
| Reversed pair |  |  |  |  |  |  |  |  |  |
| Wrong query |  |  |  |  |  |  |  |  |  |

### Table 7：校准与选择性预测

| Method | NLL | Brier | ECE | AURC | Risk@90% | Risk@80% | Risk@70% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Strongest baseline |  |  |  |  |  |  |  |
| PRTA-CXR |  |  |  |  |  |  |  |

### Table 8：VLM 附加部署

| Visual model | VLM setting | Output | Macro-F1 | Schema validity | Finding consistency | Notes |
|---|---|---|---:|---:|---:|---|
| Final PRTA-CXR | Frozen/light post-train | Structured progression |  |  |  |  |

---

## 9. 正文可视化清单

| Figure | 内容 | 核心问题 |
|---|---|---|
| Figure 1 | 方法与标签构建总 Pipeline | 方法整体如何工作 |
| Figure 2 | 数据漏斗、类别/来源/时间间隔分布、拒绝原因 | 数据如何构建、噪声如何控制 |
| Figure 3 | 数据规模 scaling curve | 低指标是否由数据不足导致 |
| Figure 4 | PRTA 相对各 baseline 的 paired-effect forest plot | 增益是否稳定、有统计不确定性 |
| Figure 5 | 五类 confusion matrix + ODER | 模型错在何处 |
| Figure 6 | finding × progression performance heatmap | 哪些 finding/变化类别最困难 |
| Figure 7 | reliability diagram + risk-coverage | 模型能否校准与拒答 |
| Figure 8 | True/Wrong PRIOR、Reversal、Wrong query 案例 | 是否真正利用正确历史和查询 |

Figure 8 建议同一病例显示：PRIOR、CURRENT、finding、注意力/贡献图、五类概率，以及更换 PRIOR/查询后的预测变化。必须包含错误高置信案例，避免仅展示成功病例。

---

## 10. 做实验同学的运行登记要求

每个 run 必须登记：

```text
experiment_id
date
owner
git_commit
config_path
config_hash
split_manifest_hash
label_manifest_hash
seed
gpu
start_time
end_time
status
checkpoint_path
prediction_path
metrics_path
log_path
notes
```

禁止：

- 只保存终端截图；
- 手工修改结果 CSV；
- 根据 test 结果换 checkpoint；
- 同一患者跨 split；
- 只报告最好 seed；
- 删除失败 run；
- 在医生抽检后逐行人工修补全量标签；
- 使用旧项目历史 test 作为新项目 Dev。

---

## 11. 最终 GO / HOLD / STOP 门

| 阶段 | GO | HOLD/修复 | STOP/重新设计 |
|---|---|---|---|
| 重构 | parity、tests、leakage 均通过 | 浮点或路径差异可解释 | 无法复现核心 PRTA |
| Luna 标签 | 总体医生一致 ≥90%，各类 ≥80% | 某类不足，修 prompt/规则后全量重跑 | 报告无法稳定支持五类标签 |
| 主方法开发 | Dev F1 ≥0.52，较强基线 ≥+3pp | 0.48–0.52，做误差诊断 | <0.48 且 scaling 饱和 |
| 正式结果 | 主效应正向、无 seed 崩溃 | CI 较宽但趋势一致 | 扩大数据后仍无稳定优势 |
| 可信性 | True PRIOR 优于 wrong/null，校准可改善 | 部分亚组异常 | 错误 PRIOR 不降反升且高置信 |
| VLM 附加 | 可读、schema 稳定、趋势合理 | 仅定性展示 | 不影响 ViT 主论文，放弃附加分支 |

---

## 12. 最终优先级

```text
P0  新项目重构与 parity
P1  扩展 pair + Luna 标签 + 医生抽检
P2  只在 Dev 上把 PRTA 原生 ViT 指标做上去
P3  冻结方法、数据和协议
P4  正式 baseline
P5  正式 ablation
P6  trust / calibration / subgroup
P7  可视化与错误分析
P8  最后补一个 PRTA→VLM 附加结果
P9  一次性读取现有 expert Gold（若完整可用）
```

核心原则：

> 先解决绝对性能和数据质量，再冻结主方法；冻结后才批量做可发表的比较、消融和可信性实验；VLM 永远不反向牵引主方法。
