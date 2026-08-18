# PRTA-CXR-Slim 正式收口记录

日期：2026-08-18（Asia/Shanghai）

## 结论

PRTA-CXR-Slim 4 Arms × 3 Seeds 最小矩阵已由服务器正式 finalizer 收口：

- 状态：`PASS_SLIM_MATRIX_SELECTED`；
- 选择：`Slim-S1`；
- 解释：删除独立 Prototype CE，保留 State anchor；
- admissible Arms：`Slim-S0`、`Slim-S1`；
- `Slim-S2`、`Slim-S3` 未通过逐类别 recall 冻结门；
- Internal-test、Gold、external 与 protected outcome 读取次数均为 0。

## 阻塞根因与代码修复

冻结训练入口会在读取 Train/Dev 选择面后，用实际 Train 类别计数确定性补全
`classification_loss.class_counts`，训练收据记录的是补全后的 effective config
SHA-256。旧 finalizer 却把它直接与补全前的 source config SHA-256 比较，导致原生
和 offload 结果都会被错误判为配置漂移。

修复后的 finalizer 依次校验：

1. config 文件字节哈希；
2. source config canonical SHA-256；
3. 冻结 selection manifest SHA-256；
4. 与正式训练相同的 source filter、nested fraction、可选 label-noise 和类别计数补全；
5. recomputed effective config SHA-256 与 training receipt；
6. 原始 queue SHA、lane completion、offload reconciliation 与 protected-read flags。

最终公共结果同时记录 config file、source config、effective config 三类身份，避免后续
再次混淆。

## Seed43 导入与重复隔离

冻结硬件分工为 Seeds 17/28 使用 A800，Seed43 使用 RTX3090。四个本地 Seed43
terminal receipts 均能由服务器冻结配置与选择面精确重算得到相同 effective hash。

导入前执行了以下边界：

- 精确证明两个 Slim queue controller 已停止且不再能安全续跑；
- 只退休这两个过期控制器，不终止任何训练进程；
- Phase16 两个 queue parent 在操作前后均保持 `T`；
- 服务器重复 S1-S43 与中断 S3-S43 目录、旧 shared state 被移动到可恢复 quarantine；
- 四个权威 Seed43 收据按原始 server lane 身份导入；
- S0-S17 的陈旧 RUNNING state 只依据已有 terminal PASS receipt 修复；
- 两条原始队列分别以 7/7 与 6/6 PASS 关闭。

checkpoint 未上传 GitHub。四个本地 best-checkpoint SHA-256 已写入服务器
reconciliation 和本地归档清单，供未来恢复或推理使用。

## 不可变凭据

| 产物 | SHA-256 |
|---|---|
| 服务器 final JSON | `2fc88e884c01cdc247a0815b90ea007f6c0dd5167e110e94cb1161be4539e47d` |
| 服务器 final Markdown | `89db5220a9f4f0b9f97ddd6209e0d2fd08d082263cc3f9ff29d4b4d896b9fe6e` |
| offload reconciliation | `33cb928ca4a35257b3a3e6fc6ac848e5c0bf6c2edb07601291111becb80c187d` |
| A800-3066 lane completion | `0bcf3c3dee5791c7d65dec98ba3021a21aa8c0f6893c8b1222513355f7609cb6` |
| A800-9929 lane completion | `9e17f17b44b9df428db4ac0a7648a2600ff3d286076423e0054e3904effaa531` |
| controller retirement | `b637121ff018d9cc8b59a9346a6af02369cb4f8ee12eb86914da8d7fa923e103` |
| fixed finalizer module | `4af1f9226eeabbe6b6687cf235a3c7ff18fb4f9e75fe2fda1143b8fd048c911e` |

GitHub 的 [公共结果 JSON](../../paper/data/09_PRTA-CXR-Slim最终结果.json) 只包含
聚合结果、逐 Seed 指标和公共哈希，不包含患者行、预测、checkpoint、账号或服务器
绝对路径。

## 当前服务器状态

- Slim queue/training/finalizer 进程：无；
- Phase16 queue parents：保持 `T`；
- 后续实验：未自动恢复；
- 轻量 terminal supervisor：仅等待暂停队列的未来显式处理，不占用 GPU。

恢复 Phase16 必须有新的明确指令，并重新校验 PID 身份、进程状态、queue SHA、
输入凭据与 GPU 边界；不得仅因为 Slim finalizer 已 PASS 就自动 `SIGCONT`。
