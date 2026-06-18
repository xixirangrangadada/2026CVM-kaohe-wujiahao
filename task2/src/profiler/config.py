"""配置 —— 窗口/保留期/采样频率可调（对应考题"配置化"要求）。

走环境变量，Docker 用 -e 传参，不硬编码。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# perf stat 采集的 PMU 事件集（呼应题1①）。preflight 自检 + collector 指标采集共享，
# 改这里两处同步。衍生率（IPC / LLC miss / 分支预测失败率）在 server 算。
DEFAULT_STAT_EVENTS = [
    "cycles",
    "instructions",          # → IPC = instructions / cycles
    "cache-misses",
    "cache-references",      # → LLC miss rate = cache-misses / cache-references
    "L1-dcache-load-misses",
    "branch-misses",
    "branches",              # → 分支预测失败率 = branch-misses / branches
    "dTLB-load-misses",
]


@dataclass
class Config:
    data_dir: Path = Path("/data/perf")     # 采样文件目录（文件总线）
    svg_dir: Path = Path("/data/svg")        # 火焰图输出目录
    rotate_seconds: int = 60                 # 轮转窗口（秒）
    retain_hours: int = 24                   # 保留时长（小时），超期由 janitor 清理
    sample_freq: int = 99                    # perf 采样频率 Hz
    perf_extra: list[str] = field(default_factory=list)  # 额外 perf record 参数
    stat_events: list[str] = field(default_factory=lambda: list(DEFAULT_STAT_EVENTS))  # perf stat 事件集

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载，缺省用默认值。"""
        def env(name: str, default: str) -> str:
            return os.environ.get(name, default)

        extra_raw = env("PERF_EXTRA", "")
        perf_extra = extra_raw.split() if extra_raw else []
        events_raw = env("PERF_EVENTS", "")
        stat_events = [e.strip() for e in events_raw.split(",") if e.strip()] or list(DEFAULT_STAT_EVENTS)
        return cls(
            data_dir=Path(env("DATA_DIR", "/data/perf")),
            svg_dir=Path(env("SVG_DIR", "/data/svg")),
            rotate_seconds=int(env("ROTATE_SECONDS", "60")),
            retain_hours=int(env("RETAIN_HOURS", "24")),
            sample_freq=int(env("SAMPLE_FREQ", "99")),
            perf_extra=perf_extra,
            stat_events=stat_events,
        )
