"""命名约定 —— 文件总线的单一真相源。

所有涉及采样文件 / 火焰图文件名的逻辑，必须走本模块的函数，
禁止在别处字符串拼接文件名。约定改了只动这里。

约定（见 docs/架构设计.md 第三节）：
    采样文件：  /data/perf/perf-<start>-<end>.data
    火焰图：    /data/svg/flame-<start>-<end>.svg
    时间格式：  本地时区 YYYYmmdd_HHMMSS（下划线分隔，文件名安全）

例：perf-20260617_031200-20260617_031300.data  # 03:12:00 ~ 03:13:00 一分钟
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# 时间戳格式：本地时区，文件名安全（无冒号）
_TS_FMT = "%Y%m%d_%H%M%S"

# 采样文件名正则：perf-<start>-<end>.data
# 时间戳形如 20260617_031200，用 \d{8}_\d{6} 精确匹配
_DATA_RE = re.compile(r"^perf-(\d{8}_\d{6})-(\d{8}_\d{6})\.data$")
_SVG_RE = re.compile(r"^flame-(\d{8}_\d{6})-(\d{8}_\d{6})\.svg$")

DATA_SUFFIX = ".data"
SVG_SUFFIX = ".svg"


class NamingError(ValueError):
    """文件名不符合命名约定。"""


def fmt_ts(dt: datetime) -> str:
    """datetime → 文件名时间戳串（YYYYmmdd_HHMMSS）。"""
    return dt.strftime(_TS_FMT)


def parse_ts(s: str) -> datetime:
    """文件名时间戳串 → datetime。格式不符抛 NamingError。"""
    try:
        return datetime.strptime(s, _TS_FMT)
    except ValueError as e:
        raise NamingError(f"非法时间戳 {s!r}，应为 YYYYmmdd_HHMMSS") from e


def data_filename(start: datetime, end: datetime) -> str:
    """时间段 → 采样文件名（不含目录）。"""
    if end < start:
        raise NamingError(f"end {end} 早于 start {start}")
    return f"perf-{fmt_ts(start)}-{fmt_ts(end)}{DATA_SUFFIX}"


def svg_filename(start: datetime, end: datetime) -> str:
    """时间段 → 火焰图文件名（不含目录）。"""
    if end < start:
        raise NamingError(f"end {end} 早于 start {start}")
    return f"flame-{fmt_ts(start)}-{fmt_ts(end)}{SVG_SUFFIX}"


def parse_data_filename(name: str) -> tuple[datetime, datetime]:
    """采样文件名 → (start, end)。不含目录，传文件名即可。

    例：parse_data_filename('perf-20260617_031200-20260617_031300.data')
    """
    m = _DATA_RE.match(name)
    if not m:
        raise NamingError(f"非法采样文件名 {name!r}")
    return parse_ts(m.group(1)), parse_ts(m.group(2))


def parse_svg_filename(name: str) -> tuple[datetime, datetime]:
    """火焰图文件名 → (start, end)。"""
    m = _SVG_RE.match(name)
    if not m:
        raise NamingError(f"非法火焰图文件名 {name!r}")
    return parse_ts(m.group(1)), parse_ts(m.group(2))


def overlaps(a_start: datetime, a_end: datetime,
             b_start: datetime, b_end: datetime) -> bool:
    """两个时间段 [a_start,a_end) 与 [b_start,b_end) 是否相交。

    回查时用：判断某个采样文件的时间段是否覆盖查询区间。
    半开区间，端点恰好相等不算相交。
    """
    return a_start < b_end and b_start < a_end
