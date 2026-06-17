"""配置 —— 窗口/保留期/采样频率可调（对应考题"配置化"要求）。

走环境变量，Docker 用 -e 传参，不硬编码。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    data_dir: Path = Path("/data/perf")     # 采样文件目录（文件总线）
    svg_dir: Path = Path("/data/svg")        # 火焰图输出目录
    rotate_seconds: int = 60                 # 轮转窗口（秒）
    retain_hours: int = 24                   # 保留时长（小时），超期由 janitor 清理
    sample_freq: int = 99                    # perf 采样频率 Hz
    perf_extra: list[str] = field(default_factory=list)  # 额外 perf record 参数

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载，缺省用默认值。"""
        def env(name: str, default: str) -> str:
            return os.environ.get(name, default)

        extra_raw = env("PERF_EXTRA", "")
        perf_extra = extra_raw.split() if extra_raw else []
        return cls(
            data_dir=Path(env("DATA_DIR", "/data/perf")),
            svg_dir=Path(env("SVG_DIR", "/data/svg")),
            rotate_seconds=int(env("ROTATE_SECONDS", "60")),
            retain_hours=int(env("RETAIN_HOURS", "24")),
            sample_freq=int(env("SAMPLE_FREQ", "99")),
            perf_extra=perf_extra,
        )
