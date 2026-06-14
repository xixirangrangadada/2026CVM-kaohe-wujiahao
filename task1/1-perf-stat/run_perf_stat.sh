#!/bin/bash
# 题1① 多场景微架构指标采集
# 环境：鲲鹏 920 (TaiShan v110) / aarch64 / perf 4.19.90 / stress-ng 0.21.03
# PMU 事件：通用名 + 2 个 ARM raw code（perf 4.19 不认 pmu/符号名/）
set -uo pipefail

RESULTS_DIR="$(cd "$(dirname "$0")" && pwd)/results"
mkdir -p "$RESULTS_DIR"

CORE=0          # taskset 钉核，避免线程迁移噪声（鲲鹏920 同构 4 核）
DURATION=30     # 每负载运行时长（秒）

# 13 个事件：通用名 + 2 个 ARM PMU raw code 替代（perf 4.19 限制）
EVENTS="cycles,instructions,cache-references,cache-misses,\
L1-dcache-load-misses,L1-icache-load-misses,\
armv8_pmuv3_0/event=0x037,name=LLC-load-misses/,\
branch-misses,\
armv8_pmuv3_0/event=0x021,name=branch-instructions/,\
dTLB-load-misses,iTLB-load-misses,\
context-switches,cpu-migrations"

# 5 场景负载（名称 / 命令，下标一一对应）
NAMES=(int64 matrixprod read64 rand-set queens)
CMDS=(
  "stress-ng --cpu 1 --cpu-method int64 -t ${DURATION}s"
  "stress-ng --cpu 1 --cpu-method matrixprod -t ${DURATION}s"
  "stress-ng --vm 1 --vm-bytes 1G --vm-method read64 --vm-keep -t ${DURATION}s"
  "stress-ng --vm 1 --vm-bytes 512M --vm-method rand-set -t ${DURATION}s"
  "stress-ng --cpu 1 --cpu-method queens -t ${DURATION}s"
)

echo "==== 题1① perf stat 五场景采集 ===="
echo "事件集: $EVENTS"
echo "钉核: CPU $CORE | 时长: ${DURATION}s/负载"
echo

for i in "${!NAMES[@]}"; do
  name="${NAMES[$i]}"
  cmd="${CMDS[$i]}"
  out="$RESULTS_DIR/${name}.txt"
  echo "[$((i+1))/5] $name"
  echo "    命令: $cmd"
  taskset -c "$CORE" perf stat -e "$EVENTS" -o "$out" -- $cmd
  echo "    → $out"
  echo
done

echo "==== 全部完成，结果在 $RESULTS_DIR ===="
ls -la "$RESULTS_DIR"
