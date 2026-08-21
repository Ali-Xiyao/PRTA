# Phase20 服务器产物归档与清理协议

> 目的：在不影响 comparator、B1、B2 和 finalizer 的前提下，把服务器上已完成且仅用于复现的产物迁移到本地校验归档，释放服务器空间。本文不授权删除任何仍被下游引用的文件。

## 1. 分类

| 类别 | 定义 | 处理 |
|---|---|---|
| `ACTIVE` | 正在写入或被活动进程打开 | 不读取大文件、不迁移、不删除 |
| `DOWNSTREAM_REQUIRED` | comparator、B1、B2、finalizer、最终汇总仍会读取 | 原位保留，直到 evidence finalizer PASS |
| `ARCHIVE_SAFE` | 已 terminal、无下游引用、无活动句柄，仅为复现保留 | 可续传到本地，SHA256 一致后删除服务器原副本 |
| `DELETE_FORBIDDEN` | 数据、影像、报告、患者级预测、凭据或来源不明文件 | 不进入 Git；未经单独审计不得删除 |
| `GIT_SAFE` | 代码、配置、测试、聚合结果、去私有路径的清单与哈希 | 可进入主分支 |

## 2. 当前依赖边界

- 24-cell comparator 的三 Seed checkpoint、receipt 与 queue 是 B2 的输入，B2 evidence finalizer PASS 前均为 `DOWNSTREAM_REQUIRED`。
- Slim-S1 三 Seed checkpoint、B1 probability receipt、calibration/subgroup/state-efficiency 结果是 B2/finalizer 输入，不能提前归档清理。
- 运行中日志、锁、状态文件和 source freeze 不得移动。
- 普通 Git 仓库不是 checkpoint 存储：checkpoint、患者级预测、影像、报告和原始日志一律不提交。

## 3. 迁移与删除门

每个服务器原件只有同时满足以下条件才可删除：

1. 使用精确绝对路径列入 inventory，不使用宽泛通配符；
2. 依赖扫描结果为零，且不属于当前冻结 queue/input manifest；
3. 没有活动 PID、锁或打开句柄；
4. 本地目标盘在归档完成后仍至少保留 50 GB 空间；
5. 复制支持断点续传，失败不得覆盖或截断服务器原件；
6. 本地和服务器文件大小一致；
7. 全文件 SHA256 一致；
8. 已写入包含时间、大小、哈希、来源类别和恢复说明的归档 receipt。

任一条件不满足时均保留服务器原件，并在 inventory 中标记阻塞原因。

## 4. 本地归档结构

本地私有归档目录不写入 Git。建议结构：

```text
phase20_server_reproducibility_YYYYMMDD/
├── manifest.private.json
├── sha256sums.private.txt
├── transfer_receipt.private.json
├── comparator/
├── phase20_b1/
├── phase20_b2/
└── source_freezes/
```

Git 中只保留去除服务器、本地绝对路径和敏感字段后的聚合清单，例如按实验族统计的文件数、总字节数、归档状态与哈希清单摘要。

## 5. 自动接力后的清理顺序

1. comparator 24/24 PASS 并完成 comparator finalizer；
2. B1 6/6 PASS；
3. B2 28/28 PASS 并完成 evidence finalizer；
4. 生成最终依赖图和 server inventory；
5. 先迁移 `ARCHIVE_SAFE`，逐项校验；
6. 仅删除已经校验通过的精确服务器副本；
7. 更新释放空间、保留项和恢复说明；
8. 最后推送 Git-safe 代码、测试、聚合结果和文档。

## 6. 自动化

线程 heartbeat `prta-cxr-phase20-b1-b2` 每 30 分钟检查一次接力状态。它必须复用现有 watcher/lock，禁止重复启动科学任务；遇到活动 SSH 会话时只做本地只读检查，不叠加第二条服务器连接。
