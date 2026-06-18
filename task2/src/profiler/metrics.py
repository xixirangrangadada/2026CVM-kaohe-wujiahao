"""C7 指标解析 —— perf stat CSV → 结构化 CPU 指标 + 衍生率（库 + CLI）。

读 collector 产出的 metrics-<start>-<end>.csv（perf stat -x , 格式），解析原始计数，
算衍生率：IPC / LLC miss rate / 分支预测失败率。呼应题1① 的 perf stat 指标分析。
供 server /api/metrics + 前端趋势面板复用。

perf stat -x , 每行格式：<value>,<unit>,<event>,<runtime>,<pct>
  value 可能是数字，或 <not supported> / <not counted>（当前 CPU 微架构不可用的事件）。

衍生率（不可用事件 → None，前端显示 N/A）：
  IPC            = instructions / cycles           （趋向 >1 为计算密集）
  LLC miss rate  = cache-misses / cache-references （越低越好）
  分支预测失败率 = branch-misses / branches         （越低越好）
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from . import naming
from .config import Config
from .log import setup_logging

log = logging.getLogger("profiler.metrics")


class MetricsError(ValueError):
    """指标解析相关错误。"""


def parse_csv(text: str) -> dict[str, float | None]:
    """解析 perf stat -x , 输出文本 → {event: value | None}。

    value 为 None 表示该事件 <not supported> / <not counted>（不可用）。
    非事件行（如汇总行 seconds time elapsed）被忽略（解析失败即跳过）。
    """
    result: dict[str, float | None] = {}
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 3:
            continue
        val_raw, ev = parts[0].strip(), parts[2].strip()
        if not ev:
            continue
        if "<not" in val_raw:  # <not supported> / <not counted>
            result[ev] = None
            continue
        try:
            result[ev] = float(val_raw)
        except ValueError:
            continue
    return result


def _safe_div(num: float | None, den: float | None) -> float | None:
    """安全除法：任一为 None 或除数 0 → None。"""
    if num is None or den is None or den == 0:
        return None
    return num / den


def derive(counts: dict[str, float | None]) -> dict[str, float | None]:
    """从原始计数算衍生率。不可用事件对应的衍生率为 None（前端显示 N/A）。"""
    ipc = _safe_div(counts.get("instructions"), counts.get("cycles"))
    llc = _safe_div(counts.get("cache-misses"), counts.get("cache-references"))
    branch = _safe_div(counts.get("branch-misses"), counts.get("branches"))
    return {
        "ipc": round(ipc, 3) if ipc is not None else None,
        "llc_miss_rate": round(llc, 4) if llc is not None else None,
        "branch_miss_rate": round(branch, 4) if branch is not None else None,
        "l1_dcache_load_misses": counts.get("L1-dcache-load-misses"),
        "dtlb_load_misses": counts.get("dTLB-load-misses"),
    }


def read_metrics_file(path: Path) -> dict | None:
    """读一个 metrics CSV → {start, end, raw, derived}。命名不符/读失败返回 None。"""
    try:
        s, e = naming.parse_metrics_filename(path.name)
    except naming.NamingError:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    counts = parse_csv(text)
    return {
        "start": s.strftime("%Y-%m-%d %H:%M:%S"),
        "end": e.strftime("%Y-%m-%d %H:%M:%S"),
        "raw": counts,
        "derived": derive(counts),
    }


def read_recent(data_dir: Path | None = None, limit: int = 20) -> list[dict]:
    """读最近 limit 个 metrics 文件（按时间排序，旧的在前）。供前端趋势折线。"""
    data_dir = data_dir or Config.from_env().data_dir
    if not data_dir.exists():
        return []
    files = sorted(data_dir.glob(f"*{naming.METRICS_SUFFIX}"))
    results: list[dict] = []
    for f in files[-limit:]:
        r = read_metrics_file(f)
        if r is not None:
            results.append(r)
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI：python -m profiler.metrics [limit] —— 打印最近窗口的指标。"""
    setup_logging()
    argv = argv if argv is not None else sys.argv[1:]
    limit = int(argv[0]) if argv else 10
    items = read_recent(limit=limit)
    if not items:
        print("（暂无指标文件）")
        return 0
    for it in items[-limit:]:
        d = it["derived"]
        ipc = d["ipc"] if d["ipc"] is not None else "N/A"
        llc = f"{d['llc_miss_rate']:.2%}" if d["llc_miss_rate"] is not None else "N/A"
        br = f"{d['branch_miss_rate']:.2%}" if d["branch_miss_rate"] is not None else "N/A"
        print(f"{it['start']} ~ {it['end']}  IPC={ipc}  LLC miss={llc}  分支失败={br}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
