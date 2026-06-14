# 题1① 多场景微架构指标采集

使用 `perf stat` 对 5 种典型负载采集微架构关键指标，计算衍生指标（IPC / L1·LLC·TLB Miss Rate / 分支预测失败率），五场景横向对比 + 差异分析。

## 五场景负载

| # | 负载 | 命令 | 考察点 |
|---|---|---|---|
| ① | 纯计算（整数）| `stress-ng --cpu 1 --cpu-method int64 -t 30s` | ALU 流水线 |
| ② | 纯计算（浮点/矩阵）| `stress-ng --cpu 1 --cpu-method matrixprod -t 30s` | FPU / SIMD |
| ③ | 访存密集 | `stress-ng --vm 1 --vm-bytes 1G --vm-method read64 --vm-keep -t 30s` | Cache 层级 / 内存带宽 |
| ④ | 随机访存 | `stress-ng --vm 1 --vm-bytes 512M --vm-method rand-set -t 30s` | TLB / Cache Miss |
| ⑤ | 分支密集 | `stress-ng --cpu 1 --cpu-method queens -t 30s` | 分支预测器 |

## 事件集（鲲鹏 920 / perf 4.19）

通用名 + 2 个 ARM PMU 原生事件（raw code 引用）：
- `LLC-load-misses` → `armv8_pmuv3_0/event=0x037,name=LLC-load-misses/` (ll_cache_miss_rd)
- `branch-instructions` → `armv8_pmuv3_0/event=0x021,name=branch-instructions/` (br_retired)

## 复现

<TODO：采集脚本 + 命令，阶段1 填>

## 结果

- `results/` —— 5 场景 perf stat 原始输出（int64/matrixprod/read64/rand-set/queens）
- `report.pdf` —— 五场景对比表 + 差异分析（阶段1 产出）
