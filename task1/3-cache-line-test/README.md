# 题1③ AI 辅助 Cache Line 微基准

C 语言 **pointer chasing** 程序：构造链表节点、节点间距 = stride、沿指针链遍历（绕过硬件预取器），不同 stride（1/2/4/8/16/32/64/128/256 字节）测延迟，验证 cache line 对性能的影响。

> ⚠️ 不能用朴素 `for i: sum += a[i*stride]`——硬件预取器会抹平 cache line 效应，曲线看不到拐点。必须 pointer chasing。

## 拐点（本机 cache line）

- **64B**：L1/L2 cache line 边界
- **128B**：L3 cache line 边界（鲲鹏 920 的 L3 line=128B，是本机特色，报告需标注双拐点）

## 目录

- `src/cache_line_test.c` —— 微基准源码（AI 辅助编写 + 人工 review）
- `results/` —— 各 stride 的 perf 输出 + 性能数据
- `flamegraphs/` —— stride=1 vs stride=64 火焰图
- `report.pdf` —— 步长 vs 延迟曲线 + 拐点微架构分析
- `ai-chat-log/` —— AI 工具对话记录

## 复现

### 前置条件
- ARM Linux（鲲鹏 920 / KVM 透传 PMU），`perf_event_paranoid = -1`
- gcc（编译 C 源码）

### 编译
```bash
gcc -O2 -o cache_line_test src/cache_line_test.c
```

### 运行（扫描所有 stride，输出延迟曲线）
```bash
taskset -c 0 ./cache_line_test
# 产出：stride vs latency_ns 曲线（stdout，重定向到 results/latency.txt）
```

### 单 stride + perf stat（以 stride=64 为例）
```bash
taskset -c 0 perf stat \
  -e L1-dcache-load-misses,\
armv8_pmuv3_0/event=0x037,name=LLC-load-misses/,\
cache-references \
  -o results/perf/stride_64.txt \
  -- ./cache_line_test 64
```

### 火焰图（stride=8 vs stride=64）
```bash
taskset -c 0 perf record -F 99 -g -- ./cache_line_test 8
perf script | ./FlameGraph/stackcollapse-perf.pl | ./FlameGraph/flamegraph.pl > flamegraphs/stride8_flame.svg

taskset -c 0 perf record -F 99 -g -- ./cache_line_test 64
perf script | ./FlameGraph/stackcollapse-perf.pl | ./FlameGraph/flamegraph.pl > flamegraphs/stride64_flame.svg
```
