# 题1① 五场景 perf stat 结果汇总

## 测试环境

- **CPU**：鲲鹏 920（TaiShan v110 微架构），aarch64，4 核 @2.6GHz
- **缓存**：L1d/i 256KiB / L2 2MiB / L3 128MiB
- **虚拟化**：KVM guest；`perf_event_paranoid = -1`
- **工具**：perf 4.19.90（LLC/branch 事件用 raw code）、stress-ng 0.21.03
- **采集条件**：`taskset -c 0` 钉核 0，每负载 30s

## 衍生指标对比表

| 场景 | IPC | L1 Miss % | LLC Miss % | 分支失败 % | dTLB Miss % | 内核占比 |
|---|---|---|---|---|---|---|
| int64（ALU 整数）| 2.22 | 0.0016 | 0.00019 | 0.031 | 0.0023 | ~0 |
| matrixprod（FPU 矩阵）| 2.44 | **5.07** | 0.0053 | 0.90 | 0.0091 | ~0 |
| read64（顺序访存）| 2.49 | 0.020 | 0.0020 | 0.011 | 0.013 | 2.7 |
| rand-set（随机访存）| 2.62 | 0.82 | **0.36** | 0.032 | **0.166** | 30 |
| queens（分支密集）| **1.52** | 0.0014 | 0.00015 | **12.19** | 0.0013 | ~0 |

> 衍生指标计算：IPC = instructions/cycles；L1/LLC/TLB Miss% = 对应 miss 数 / cache-references × 100；分支失败% = branch-misses/branch-instructions × 100；内核占比 = sys time / elapsed time。

## 关键观察

1. **`cache-misses` ≡ `L1-dcache-load-misses`**：5 场景数值完全相同，perf 4.19 在 ARM 上把这两个通用名映射到同一 PMU 事件（L1d refill），二者冗余，分析取其一。
2. **raw code 事件验证成功**：`LLC-load-misses`（0x037）和 `branch-instructions`（0x021）均采到真实非零计数。
3. **访存型负载有内核态开销**：rand-set sys 占 30%（512M 随机写触发内存管理），read64 占 2.7%（1GB 分配 page fault）；计算型几乎纯用户态。
4. **每种负载精准压出对应子系统瓶颈**：
   - queens → 分支预测器（IPC 1.52 + 分支失败 12%）
   - rand-set → LLC + TLB 容量限制（512M ≫ L3 128MiB）
   - matrixprod → L1 局部性（5% L1 miss）
   - int64 → 纯 ALU，IPC 2.22、miss 极低

## 原始输出

- `int64.txt` / `matrixprod.txt` / `read64.txt` / `rand-set.txt` / `queens.txt`（perf stat 完整输出）
