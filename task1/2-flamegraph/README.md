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

<TODO：阶段2 填>

## 结果

- `flamegraphs/` —— SVG 火焰图
- `report.pdf` —— 对比分析（阶段2 产出）
