#!/bin/bash
# ════════════════════════════════════════════════════════════════
# 题2 测试验证 —— 构造 3 场景 CPU 飙升 → 回查 → 火焰图 → 热点断言
# 对应考题"测试验证"：构造可复现飙升场景，验证火焰图能定位热点
#
# 流程：启动 profiler 容器（常驻采集）→ 依次跑 3 场景 stress（记时段）
#       → 每场景回查命中文件 → 生成火焰图 → 提取热点 top5
# 产物：/data/svg/{matrixprod,rand-set,queens}.{svg,txt}
# ════════════════════════════════════════════════════════════════
set -uo pipefail

IMG=cpu-profiler:aarch64
SRC=/root/cvm/task2-src
FG=/root/cvm/FlameGraph
DATA=/data/perf
SVG=/data/svg
mkdir -p "$DATA" "$SVG"

# 查询命中文件（env 传参，避免引号地狱）
hits() {
  QSTART="$1" QEND="$2" QDATA="$DATA" QSRC="$SRC" python3 -c "
import os, sys; sys.path.insert(0, os.environ['QSRC'])
from profiler.query import locate_files, parse_time_arg
from pathlib import Path
for f in locate_files(parse_time_arg(os.environ['QSTART']),
                      parse_time_arg(os.environ['QEND']),
                      Path(os.environ['QDATA'])):
    print(f)
"
}

echo "════════ 题2 测试验证（3 场景）════════"
# 启动 profiler 容器（常驻采集，挂 stress-ng 供 perf 读符号）
docker rm -f cpu-profiler 2>/dev/null
rm -f "$DATA"/*.data "$SVG"/* 2>/dev/null
docker run -d --name cpu-profiler --privileged --pid=host \
  -v /lib/modules:/lib/modules:ro -v /sys:/sys \
  -v /usr/local/bin/stress-ng:/usr/local/bin/stress-ng:ro \
  -v /data:/data -p 8080:8080 -e ROTATE_SECONDS=30 \
  "$IMG"
echo "等待容器就绪..."; sleep 8
docker logs cpu-profiler 2>&1 | grep -E "RUNNING|collector" | head -2

scenario() {
  local NAME=$1 CMD=$2
  echo; echo "──── 场景 [$NAME] ────"
  local S E FILES N
  S=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$S] 启动: $CMD"
  eval "$CMD" >/dev/null 2>&1
  E=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$E] 结束，等窗口归档..."
  sleep 5

  cd "$SRC"
  FILES=$(hits "$S" "$E")
  N=$(echo "$FILES" | grep -c . 2>/dev/null || echo 0)
  echo "回查命中 $N 个采样文件"
  if [ "$N" -eq 0 ]; then echo "❌ 无命中，跳过"; return; fi

  # 火焰图
  FLAMEGRAPH_DIR=$FG python3 -m profiler.flamegraph "$S" "$E" --out "$SVG/$NAME.svg" 2>&1 \
    | grep -iE "已生成" | head -1

  # 栈 → 用户态热点 top5
  perf script $(echo "$FILES" | sed 's/^/-i /' | tr '\n' ' ') > "$SVG/$NAME.txt" 2>/dev/null
  echo "热点 top5（用户态）："
  grep -oE "[a-zA-Z_][a-zA-Z_0-9]+\+[0-9a-f]+" "$SVG/$NAME.txt" \
    | grep -v "\[unknown\]" | sed 's/+[0-9a-f]*$//' \
    | sort | uniq -c | sort -rn | head -5 | sed 's/^/     /'
  echo "  时段: $S ~ $E"
  echo "  SVG : $SVG/$NAME.svg ($(du -h "$SVG/$NAME.svg" 2>/dev/null | cut -f1))"
}

scenario matrixprod "stress-ng --cpu 2 --cpu-method matrixprod -t 25s"
scenario rand-set   "stress-ng --vm 1 --vm-bytes 512M --vm-method rand-set -t 25s"
scenario queens     "stress-ng --cpu 1 --cpu-method queens -t 25s"

echo; echo "════════ 停止容器 ════════"
docker stop cpu-profiler >/dev/null 2>&1
docker rm cpu-profiler >/dev/null 2>&1
echo; echo "产物清单："
ls -lh "$SVG/"
