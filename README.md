# 2026CVM-kaohe-wujiahao

> 2026 CVM 校企合作考核项目 —— CPU 微架构性能测评。

## 个人信息

- 姓名：**吴佳豪**
- 学号：202400202108
- GitHub：[@xixirangrangadada](https://github.com/xixirangrangadada)

## 题目完成情况

| 题目 | 内容 | 状态 |
|---|---|---|
| 题1① | 多场景 perf stat 微架构指标采集 | ✅ 已完成 |
| 题1② | 火焰图生成与热点分析 | ✅ 已完成 |
| 题1③ | AI 辅助 Cache Line 微基准 | ✅ 已完成 |
| 题2 | 容器化持续 CPU Profiling（选做） | ✅ 已完成 |

## 测试环境

| 项 | 值 |
|---|---|
| CPU | 鲲鹏 920（HiSilicon，TaiShan v110 微架构），aarch64，4 核 @2.6GHz |
| 缓存 | L1d/i 256KiB / L2 2MiB / L3 128MiB（cache line：L1/L2=64B，L3=128B）|
| 虚拟化 | KVM guest |
| OS | openEuler，内核 4.19.208 |
| perf | 4.19.90（PMU 硬件事件用 raw event code 引用）|
| stress-ng | 0.21.03（源码编译：openEuler 仓库无）|
| 编译器 | gcc（cache line 微基准用 `-O2`）|

## 目录结构

```
2026CVM-kaohe-wujiahao/
├── README.md                # 本文件
├── .gitignore
├── docs/                    # 工作过程文档（环境分析、知识点、进度）
├── resume/                  # 个人简历 PDF
├── task1/
│   ├── 1-perf-stat/         # 题1① 五场景 perf stat
│   ├── 2-flamegraph/        # 题1② 火焰图
│   └── 3-cache-line-test/   # 题1③ Cache Line 微基准
└── task2/                   # 题2 容器化持续 CPU Profiling（选做，已完成）
    ├── README.md            # 题2 说明（架构/启动/示例/设计权衡）
    ├── src/                 # Dockerfile + profiler/（6 组件）+ supervisord.conf
    ├── test/                # 环境验证 + 3 场景测试 + 火焰图 SVG
    └── ai-chat-log/         # AI 协作对话导出
```

> 题2 Docker 镜像 `profiler.tar.gz`（163MB，> GitHub 100MB 限制）放在 **GitHub Release** 附件，下载后 `docker load -i profiler.tar.gz` 即可。详见 `task2/README.md`。

## 工作流

代码与文档在**本地仓库**维护（学习与版本可控），通过 `ssh` 在云端 ARM 服务器执行 perf 采集与编译，产物（perf 输出、SVG 火焰图）回传本地入库。

## 复现指南

> 环境：ARM Linux（鲲鹏 920 / TaiShan v110，KVM 透传 PMU），`perf_event_paranoid = -1`，perf 4.19.90，stress-ng 0.21.03。各子目录 README 有详细步骤，以下为顺序总览。

```bash
# 0. 前置依赖（云端 ARM 服务器）
git clone --depth 1 https://github.com/ColinIanKing/stress-ng.git && make -j4   # stress-ng 0.21.03
git clone https://github.com/brendangregg/FlameGraph.git                        # 火焰图工具链

# 1. 题1① 五场景 perf stat 采集（→ results/*.txt）
cd task1/1-perf-stat && bash run_perf_stat.sh

# 2. 题1② 火焰图（→ flamegraphs/*.svg，见该目录 README）
cd ../2-flamegraph
taskset -c 0 perf record -F 99 -g -- stress-ng --cpu 1 --cpu-method matrixprod -t 30s
perf script | ./FlameGraph/stackcollapse-perf.pl | ./FlameGraph/flamegraph.pl > flamegraphs/matrixprod_flame.svg

# 3. 题1③ Cache Line 微基准（→ results/ + flamegraphs/，见该目录 README）
cd ../3-cache-line-test
gcc -O2 -o cache_line_test src/cache_line_test.c
taskset -c 0 ./cache_line_test > results/latency.txt        # 延迟曲线
taskset -c 0 perf stat -e L1-dcache-load-misses,armv8_pmuv3_0/event=0x037,name=LLC-load-misses/,cache-references \
  -o results/perf/stride_64.txt -- ./cache_line_test 64     # 单 stride perf（按 README 循环 6 个 stride）
```

> 注：perf 4.19 在 ARM 上不认 `pmu/符号名/` 写法，LLC/branch 事件用 raw code（`event=0x037` / `event=0x021`）替代，详见各 README 说明。
