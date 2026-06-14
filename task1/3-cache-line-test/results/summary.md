# 题1③ Cache Line 微基准结果

## 测试环境

鲲鹏 920（TaiShan v110）；16MB 数组（>L2 2MiB、<L3 128MiB）；`gcc -O2`；`taskset -c 0` 钉核。

## 算法：pointer chasing

链表节点间距 = stride，**Fisher-Yates 随机化**节点顺序绕过硬件预取器；`memcpy(&p,p,...)` + `asm volatile` 屏障防编译器消除循环；每个 stride 跑 5 次取最小减噪声。`stride < 8` 退化为节点大小 8B。

## 延迟曲线

| stride(B) | 延迟 ns | 解读 |
|---|---|---|
| 1 / 2 / 4 / 8 | ~21 | 退化为 8B 紧邻，8 节点/line，line 复用率最高 |
| 16 | 32 | 4 节点/line（最大跳变：密集度减半）|
| 32 | 40 | 2 节点/line |
| **64** | **43.6** | **1 节点/line = cache line 边界** |
| 128 | 44 | 跨 L1/L2 line，L3 兜底 |
| 256 | 46 | 跨 L3 line（128B）|

## per-stride perf stat（L1/LLC miss rate）

| stride | L1 miss% | LLC miss% |
|---|---|---|
| 8 | 88% | 4.8% |
| 16 | 91% | 6.8% |
| 32 | 91% | 5.6% |
| 64 | 90% | 3.2% |
| 128 | 86% | 3.0% |
| 256 | 79% | 0.59% |

- **L1 miss ~80-91% 普遍高**：16MB ≫ L1(256KiB)，数据不在 L1。
- **LLC miss 反直觉（stride 小反而高）**：stride 小时 nodes 多、随机密集访问 16MB，L3 冲突/容量 miss 概率高；stride 大时有效 footprint 小，多落在 L3 命中。
- **延迟↑ 但 LLC miss↓ 不矛盾**：延迟高是 **L1/L2 miss + L3 访问开销**，不是 LLC miss（数据在 L3，没掉内存）。

## 火焰图（stride=8 vs stride=64）

- 两者都是 **`chase` ~99.85%**（纯用户态 load 循环），调用栈几乎无差异。
- **关键发现**：cache miss 由硬件处理、不进内核调用栈，所以火焰图看不出差异。cache line 的影响体现在**延迟曲线 + PMU 计数**，而非调用栈——这正是本题必须用「延迟测量 + perf stat」、不能只靠火焰图的原因。

## 拐点与诚实说明

- 主拐点 **stride=64**（每 line 正好 1 节点）；最大单步跳变在 **8→16**（节点密集度减半）。
- 数组 16MB 在 **L3(128MiB) 内**，所以 L1/L2 line(64B) cross 由 L3 兜底，没有"经典陡峭 64B 拐点"。要看经典 L1 拐点需用 <L1(256KiB) 的小数组。

## 文件

- `src/cache_line_test.c` —— pointer chasing 源码
- `results/latency.txt` —— 延迟曲线原始数据
- `results/perf/stride_*.txt` —— 每个 stride 的 perf stat 输出
- `flamegraphs/stride8_flame.svg` / `stride64_flame.svg` —— 火焰图
