"""C3 回查核心 —— 时间段 → 定位命中的采样文件（库 + CLI 双入口）。

设计（见 docs/架构设计.md）：
- 文件总线消费者：扫 <data_dir>，按文件名时间戳判断"采样文件时段"是否与
  "查询区间"相交（naming.overlaps）。不依赖 collector，解耦。
- 库接口：locate_files(start, end) -> list[Path]，供 C4/C5 复用。
- CLI 接口：python -m profiler.query "2026-06-17 19:09:41" "2026-06-17 19:10:06"

输入时间段格式：'YYYY-MM-DD HH:MM:SS'（容错，支持 'YYYY-MM-DD_HHMMSS'）。
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from . import naming
from .config import Config
from .log import setup_logging

log = logging.getLogger("profiler.query")

# 输入时间段解析的多种格式（容错）
_TS_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d_%H%M%S",
    "%Y%m%d_%H%M%S",
]


class QueryError(ValueError):
    """回查相关错误。"""


def parse_time_arg(s: str) -> datetime:
    """解析用户输入的时间字符串（多种格式容错）。"""
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    raise QueryError(f"无法解析时间 {s!r}，支持格式: 'YYYY-MM-DD HH:MM:SS'")


def locate_files(start: datetime, end: datetime,
                 data_dir: Path | None = None) -> list[Path]:
    """查询区间 [start,end) → 命中的采样文件列表（按时间排序）。

    一个采样文件被命中，当且仅当它的时段与查询区间相交。
    跨多个轮转文件会被全部返回（合并由 C4 处理）。
    """
    if end < start:
        raise QueryError(f"end {end} 早于 start {start}")
    data_dir = data_dir or Config.from_env().data_dir

    hits: list[tuple[datetime, Path]] = []
    if not data_dir.exists():
        return []

    for f in data_dir.iterdir():
        if not f.is_file() or f.suffix != naming.DATA_SUFFIX:
            continue
        try:
            f_start, f_end = naming.parse_data_filename(f.name)
        except naming.NamingError:
            continue
        if naming.overlaps(f_start, f_end, start, end):
            hits.append((f_start, f))

    hits.sort(key=lambda x: x[0])
    return [p for _, p in hits]


def main(argv: list[str] | None = None) -> int:
    """CLI：python -m profiler.query <start> <end>"""
    setup_logging()
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print(f"用法: python -m profiler.query <start> <end>\n"
              f"  例: python -m profiler.query \"2026-06-17 19:09:41\" \"2026-06-17 19:10:06\"",
              file=sys.stderr)
        return 1
    try:
        start = parse_time_arg(argv[0])
        end = parse_time_arg(argv[1])
    except QueryError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    files = locate_files(start, end)
    print(f"查询区间 [{start} ~ {end})，命中 {len(files)} 个采样文件：")
    for f in files:
        fs, fe = naming.parse_data_filename(f.name)
        size_kb = f.stat().st_size // 1024
        print(f"  {f.name}  ({fs} ~ {fe}, {size_kb}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
