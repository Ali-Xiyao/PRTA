# PRTA-CXR ReXGradient 历史执行协议（已退役）

> **退役决定（2026-08-20）**：本协议不再是活跃实验授权。ReXGradient 不进入
> 当前论文、模型选择、阈值、方法修改或后续比较器队列；不得据此启动新的正式运行。
> 历史代码与私有密封产物只为审计和复现边界保留。正文泛化证据改为双向
> MIMIC-CXR/CheXpert Plus source-held domain generalization，且不得称为独立外部
> 临床验证。

## 1. 状态和授权边界

当前状态为 `HISTORICAL_PROTOCOL / EXECUTION_RETIRED / DO_NOT_REPORT`。本协议和
历史代码不授权正式去重、标签派生、缓存、推理或 public-test 访问；此前的形式化运行
开关也不再构成启动授权。

ReXGradient 仅作为历史审计对象保留，不再作为冻结 Slim-S1 的活跃论文证据，也不参与
checkpoint、阈值、标签规则或方法选择。原始影像、报告、私有 manifest、路径和预测
均不得进入 Git。

## 2. 冻结映射

映射规范位于 `configs/external/rexgradient_mapping_v1.json`，固定 12 个 finding 和
`Stable / Improved / Worse / New / Resolved` 五类。实现复用
`prta-cxr-report-transition-v1`：只接受当前报告中与 finding 同句、距离受限的明确时间
变化线索；不确定、否定变化、技术伪影、冲突标签、无显式线索均排除。

validation 只用于检查五类最低支持数并冻结规则。public test 必须复用相同映射文件、
代码规则哈希、去重回执和 checkpoint roster，不允许根据 test 调整任何规则。

## 3. 严格去重

去重比较外部 7,579 张入选影像与冻结内部 manifest 的唯一影像集合：

- SHA256 完全相同：排除外部影像及所有引用该影像的 pair；
- grayscale dHash64 Hamming 距离不大于 4：同样保守排除；
- 私有候选清单只记录内部键哈希，不写内部原始路径；
- 未解决候选数必须为 0，protocol freeze 才能继续。

## 4. checkpoint 门控

协议必须同时绑定 `P20-FINAL-S1-S17/S28/S43` 的 terminal PASS checkpoint 与 training
receipt。程序逐项核验 Slim-S1、final-mainline axis、PRTA/Tail8/H0/rank32、finding/
alignment/relation、state=0.025、ODC=0.05、offline-hard CMCP=0.01、standalone
Prototype CE=0 以及训练输入哈希。中间或消融 checkpoint 一律拒绝。

## 5. 13-job 双卡图

```text
dedup -> label-validation -> freeze-protocol
                                |-> GPU0: cache-validation -> infer val S17/S28/S43
                                `-> GPU1: label-test -> cache-test
                                                     |-> GPU0: infer test S17/S43
                                                     `-> GPU1: infer test S28
                                                           -> finalize-test
```

13 个 job 包含 1 个去重门、2 个标签阶段、1 个协议冻结、2 个 Block-4 cache、6 个
三 Seed split 推理和 1 个 test finalizer。两条 lane 的纯 GPU 冻结估时均约 5,100 s；
去重约 7,200 s，主要是
CPU/I/O，不应解读为 GPU 不均衡。

## 6. 一次性 public-test 语义

首次 test 阶段会在私有数据根写入协议身份 claim。同一协议因进程故障可以恢复，但不同
协议、不同映射或不同 checkpoint roster 不能复用该 claim。最终统计成功后写入 immutable
completion seal；存在 seal 时禁止第二次 finalization。

最终结果包括每 Seed patient-balanced 指标、三 Seed mean ± SD、平均概率 ensemble、
五分类逐类结果、ODER，以及固定 10,000 次 patient-cluster bootstrap 95% CI。结果不触发
重新选模或阈值调整。

## 7. 入口

- 数据选择迁移：`scripts/127_prepare_rexgradient_external.py`
- 各评估阶段：`scripts/128_rexgradient_external_evaluation.py`
- 构建不可变双卡程序：`scripts/129_prepare_rexgradient_evaluation.py`
- 运行单条 lane：`scripts/130_run_rexgradient_evaluation_queue.py`

正式程序只能在三个 final Slim-S1 checkpoint 全部 terminal PASS 后构建。运行时路径写入
私有 platform JSON；仓库只保存 role template，不保存任何本机或服务器绝对路径。
