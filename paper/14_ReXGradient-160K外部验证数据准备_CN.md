# ReXGradient-160K 外部验证数据准备

> 状态：`DATA_STAGED / EVAL_CODE_READY / EVAL_NOT_STARTED`
> 角色：Slim-S1 的独立纵向外部验证数据；不参与模型、checkpoint 或阈值选择。

## 1. 数据边界

ReXGradient-160K 按发布方协议获得，只用于非商业研究。原始影像、报告、患者/检查
标识、私有 manifest、HMAC 盐和下载凭据均留在私有 runtime，不进入 Git、论文材料
包或公开结果。Git 只保存可复现的选择/迁移代码、无身份聚合计数和完整性哈希。

官方元数据提供报告和时间/view 信息，但没有与本项目直接等价的五分类纵向进展标签。
因此，本阶段只完成 outcome-blind 数据准备，不能写成外部性能已经产生。

## 2. 冻结的 outcome-blind 选择合同

validation 与 public test 分开处理。每个 split 内按患者与 StudyDate 排序，只保留日期
严格递增的相邻检查；当前与既往检查都必须至少有一张 frontal 影像（AP、PA 或
POSTERO_ANTERIOR）。若两次检查存在同一 frontal view，确定性优先选择同 view；否则
按固定 view 优先级选择 cross-frontal 配对。

选择过程不读取 Findings、Impression 或任何派生结局。导出的 patient、study 和 image
键均为私有盐 HMAC；PNG 使用内容哈希命名并扁平化存储。归档内元数据路径与 PNG
完整前缀不一致，因此迁移器只在 PNG basename 全局唯一时连接；发现碰撞即失败，
不得静默选择。

## 3. 已暂存规模

| Split | 原始 studies | 原始 patients | 可用纵向对 | 入选 patients | 唯一 PNG |
| --- | ---: | ---: | ---: | ---: | ---: |
| validation | 10,000 | 6,964 | 1,981 | 1,691 | 3,672 |
| public test（封存） | 10,000 | 6,807 | 2,102 | 1,804 | 3,907 |
| **合计** | **20,000** | — | **4,083** | — | **7,579** |

- 同 view 配对：3,167；cross-frontal 配对：916。
- 暂存 PNG 总大小：4,184,238,808 bytes。
- validation 与 test 的 patient overlap：0。
- 十个原始大分片均与发布方 LFS SHA256 一致；迁移没有物化约 155 GB 的合并 tar，
  而是对 split Zstandard tar 进行串流解压和选择性提取。
- 选择集合 SHA256：
  `f594b44f955256cda784bd901a281ff7d47da86a40eaf3e9a923ea1ff5905a2f`。
- 影像清单 SHA256：
  `73c8e178b5f3c53fa1a0854b95fcc0598762c5ab283ab3fa4900611da0cc55fb`。

## 4. 正式评估前的剩余门控

1. 只在 validation 冻结 12-finding 到五分类进展标签的映射和无法判定规则；
2. 对内部数据与 ReXGradient 执行患者标识、像素哈希和感知哈希严格去重；
3. 冻结 Slim-S1 checkpoint roster、预处理、主要/次要终点、patient-cluster
   bootstrap seed、置信区间和 excluded-row rules；
4. 写入不可变门控凭据后，才对 public test 执行一次正式推理与统计；
5. 外部结果只用于验证，不允许重新选择模型、调整阈值或改变标签映射。

在上述四个技术门完成前，论文只能写“ReXGradient 数据已准备，外部性能待评估”，
不能报告或暗示外部泛化结论。

## 5. 当前可审计结论

数据下载和选择性迁移已经完成，十个大分片通过发布方哈希核验，正式迁移回执为
`PASS_REXGRADIENT_SELECTED_SUBSET_MIGRATED`。本次准备未复制 train 影像、未生成
进展标签、未启动外部推理，也未读取 public-test 结局用于开发。

## 6. 已准备但尚未执行的评估程序

项目已实现独立的 ReXGradient 外部评估程序，包含：

1. 内部/外部影像 SHA256 与 dHash64 严格去重，候选默认保守排除；
2. 只接受明确时间变化线索的 12-finding × 五分类 External-Silver 映射；
3. 仅基于 validation 标签计数冻结映射、排除规则、三 Seed Slim-S1 checkpoint
   roster、主要终点与 patient-cluster bootstrap；
4. 与 Tail8 一致的 Block-4 PNG 缓存、S17/S28/S43 独立推理和三 Seed 汇总；
5. public test 的单协议访问 claim、可恢复的同协议执行和不可重复 final seal；
6. 两张 GPU 的 13-job 依赖队列。纯 GPU 估时均为约 5,100 s；去重是
   前置 CPU/I/O 门，不占用第二张 GPU。

代码就绪不等于门控已经通过。当前没有创建 test access claim、没有缓存外部特征、
没有载入 Slim-S1 checkpoint，也没有产生任何 validation/test 指标。
