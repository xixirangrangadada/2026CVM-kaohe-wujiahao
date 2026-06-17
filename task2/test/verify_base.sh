#!/bin/bash
# ════════════════════════════════════════════════════════════════
# 题2 地基验证脚本 verify_base.sh（三道关卡式，v2）
#
# 三道关卡（由浅入深）：
#   关卡1  Docker PMU 开放？   特权容器内 perf stat 能否跑出 cycles 计数
#   关卡2  能采到别的进程？    --pid=host 下 perf record 能否采到 stress-ng
#   关卡3  符号能解析？        栈里能否解出 stress-ng 用户态符号
#
# v2 修正：
#   ① 关卡2 时序：perf 必须先于 stress-ng 启动（捕获 stress 的 MMAP 事件，
#      否则地址解不出符号，全 [unknown]）—— 这是容器+常驻采集的关键坑
#   ② 关卡3 判定：stressor 方法名 matrixprod 不会出现在栈里，真实热点是
#      软浮点 __multf3/__addtf3（题1② 已验证）。判定改成"有名字的符号数"
# ════════════════════════════════════════════════════════════════
set -uo pipefail

# ---- 配置 ----
IMG="openeuler:20.03"
STRESS_DUR=20          # stress-ng 时长
PERF_SLEEP=30          # perf 容器 sleep（> STRESS_DUR + 缓冲，保证覆盖整个飙升期）
SAMPLE_FREQ=99
WORKDIR="/root/cvm/task2-base-test"
FLAMEGRAPH_DIR="/root/cvm/FlameGraph"

# 公共挂载（perf 二进制 + 依赖库 + 内核符号）
MOUNTS=(
  -v /usr/bin/perf:/usr/bin/perf:ro
  -v /usr/lib64:/usr/lib64-host:ro
  -v /lib/modules:/lib/modules:ro
  -v /sys:/sys
)
LD_HOST="/usr/lib64-host"

mkdir -p "$WORKDIR"; cd "$WORKDIR"
PASS_CNT=0

echo "══════════ 题2 地基验证（三道关卡 v2）══════════"
echo "镜像: $IMG"
echo

# ── 关卡 1：Docker PMU 是否开放 ──
echo "══ 关卡 1：Docker PMU 是否开放 ══"
G1_LOG="$WORKDIR/g1_pmu.log"
docker run --rm --privileged "${MOUNTS[@]}" "$IMG" sh -c "
  export LD_LIBRARY_PATH=$LD_HOST:\$LD_LIBRARY_PATH
  perf stat -e cycles,instructions -a -- sleep 1
" > "$G1_LOG" 2>&1
if grep -qi "Performance counter stats" "$G1_LOG" && grep -qE "[0-9]{5,}" "$G1_LOG"; then
  echo "✅ PASS —— 容器内 perf 跑出计数（Docker PMU 开放）"
  grep -E 'cycles|instructions' "$G1_LOG" | head -2 | sed 's/^/   /'
  PASS_CNT=$((PASS_CNT+1))
else
  echo "❌ FAIL —— Docker 隔离挡住 PMU"
  grep -iE "error|not permitted|denied" "$G1_LOG" | head -3 | sed 's/^/   /'
  echo ">>> 关卡1 挂，终止。"
  exit 1
fi
echo

# ── 关卡 2：能采到别的进程（关键时序：perf 先启动）──
echo "══ 关卡 2：能否采到别的进程（--pid=host）══"
echo "  ① 先启动 perf 采集容器（后台，准备捕获 stress 的 MMAP 事件）..."
docker rm -f perf-base 2>/dev/null
G2_LOG="$WORKDIR/g2_record.log"
docker run -d --name perf-base --privileged --pid=host --network=host "${MOUNTS[@]}" \
  -v "$WORKDIR:/work" "$IMG" sh -c "
    export LD_LIBRARY_PATH=$LD_HOST:\$LD_LIBRARY_PATH
    cd /work
    perf record -F ${SAMPLE_FREQ} -a -g -o perf_base.data -- sleep ${PERF_SLEEP}
  " > "$G2_LOG" 2>&1
sleep 3   # ← 关键：等 perf 起来开始系统级采集

echo "  ② 再启动 stress-ng matrixprod（${STRESS_DUR}s，此时 perf 正在采）..."
stress-ng --cpu 2 --cpu-method matrixprod -t ${STRESS_DUR}s >/dev/null 2>&1
echo "  ③ stress 结束，等 perf 容器收尾（sleep 剩余时间）..."
docker wait perf-base >> "$G2_LOG" 2>&1
docker logs perf-base 2>&1 | tail -4 >> "$G2_LOG"
docker rm -f perf-base >/dev/null 2>&1

DATA_SIZE=$(stat -c%s "$WORKDIR/perf_base.data" 2>/dev/null || echo 0)
if [ "$DATA_SIZE" -gt 50000 ] && grep -qiE "samples|captured|wrote" "$G2_LOG"; then
  echo "✅ PASS —— 容器 perf record 采到样本（perf.data = $((DATA_SIZE/1024)) KB）"
  grep -iE "samples|captured" "$G2_LOG" | tail -2 | sed 's/^/   /'
  PASS_CNT=$((PASS_CNT+1))
else
  echo "❌ FAIL —— perf.data 无样本（$DATA_SIZE 字节）"
  tail -6 "$G2_LOG" | sed 's/^/   /'
  echo ">>> 关卡2 挂，终止。"
  exit 1
fi
echo

# ── 关卡 3：符号能否解析 ──
echo "══ 关卡 3：符号能否解析 ══"
perf script -i "$WORKDIR/perf_base.data" > "$WORKDIR/perf_base.txt" 2>/dev/null
"$FLAMEGRAPH_DIR/stackcollapse-perf.pl" "$WORKDIR/perf_base.txt" \
  | "$FLAMEGRAPH_DIR/flamegraph.pl" > "$WORKDIR/base_flame.svg" 2>/dev/null

# 判定：能解出名字的用户态符号数（+0x 偏移形式，非 [unknown]）
NAMED=$(grep -cE "[a-zA-Z_][a-zA-Z_0-9]+\+0x[0-9a-f]+" "$WORKDIR/perf_base.txt")
UNK=$(grep -c "\[unknown\]" "$WORKDIR/perf_base.txt")
echo "   符号统计：有名字 ${NAMED} 个 / [unknown] ${UNK} 个"
if [ "$NAMED" -gt 50 ]; then
  echo "✅ PASS —— 成功解析出用户态符号"
  echo "   热点 top5（stress-ng 真实热点，题1② 见过软浮点）："
  grep -oE "[a-zA-Z_][a-zA-Z_0-9]+\+0x" "$WORKDIR/perf_base.txt" \
    | sed 's/+0x//' | sort | uniq -c | sort -rn | head -5 | sed 's/^/     /'
  PASS_CNT=$((PASS_CNT+1))
else
  echo "❌ FAIL —— 仍全是 [unknown]，符号解析失败"
  echo "   栈样本（前 12 行）："
  head -12 "$WORKDIR/perf_base.txt" 2>/dev/null | sed 's/^/   /'
  echo "   → 解法：检查 stress-ng 二进制是否带符号表 / perf MMAP 事件是否捕获"
fi
echo

# ── 总结 ──
echo "══════════ 地基验证总结 ══════════"
echo "  关卡1 Docker PMU 开放：  $([ $PASS_CNT -ge 1 ] && echo PASS || echo FAIL)"
echo "  关卡2 采到别的进程：     $([ $PASS_CNT -ge 2 ] && echo PASS || echo FAIL)"
echo "  关卡3 符号能解析：       $([ $PASS_CNT -ge 3 ] && echo PASS || echo FAIL)"
echo "  通过 $PASS_CNT/3"
if [ $PASS_CNT -eq 3 ]; then
  echo "  🎉 地基全通！题2 容器化方案成立，可继续 C1-C6。"
else
  echo "  ⚠️ 有关卡未通过，按上面定位查解法。"
fi
echo "  产物：$WORKDIR/{perf_base.data, perf_base.txt, base_flame.svg}"
