# 题1② 火焰图生成与热点分析

`perf record -F 99 -g` + [FlameGraph](https://github.com/brendangregg/FlameGraph) 工具链，对 ≥2 种负载生成 CPU 火焰图，分析尖塔/扁平形态与内核态函数成因。

## 工具链

```
perf record -F 99 -g -- <负载>
perf script > perf_<负载>.data
./FlameGraph/stackcollapse-perf.pl perf_<负载>.data | ./FlameGraph/flamegraph.pl > <负载>_flame.svg
```

## 分析要点

- 计算密集 → 火焰图"尖塔"（热点集中）；访存/分支 → "扁平"（热点分散）
- 内核态函数（`__do_page_fault` / `copy_page` / TLB refill）出现要解释成因

## 复现

### 前置条件
- ARM Linux（鲲鹏 920 / KVM 透传 PMU），`perf_event_paranoid = -1`
- FlameGraph 工具链：`git clone https://github.com/brendangregg/FlameGraph.git`

### 单负载火焰图（以 matrixprod 为例）
```bash
# 1. 采样（-F 99 避共振，-g 抓调用栈）
taskset -c 0 perf record -F 99 -g -- stress-ng --cpu 1 --cpu-method matrixprod -t 30s

# 2. 导出采样数据
perf script > perf_matrixprod.data

# 3. 生成火焰图
./FlameGraph/stackcollapse-perf.pl perf_matrixprod.data | ./FlameGraph/flamegraph.pl > matrixprod_flame.svg
```

### rand-set 火焰图（同流程）
```bash
taskset -c 0 perf record -F 99 -g -- stress-ng --vm 1 --vm-bytes 512M --vm-method rand-set -t 30s
perf script > perf_rand-set.data
./FlameGraph/stackcollapse-perf.pl perf_rand-set.data | ./FlameGraph/flamegraph.pl > rand-set_flame.svg
```

## 结果

- `flamegraphs/` —— SVG 火焰图
- `report.pdf` —— 对比分析（阶段2 产出）
