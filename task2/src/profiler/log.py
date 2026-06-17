"""统一日志配置 —— stdout + 文件双输出，便于实时查看与历史排查。

设计：
- stdout：docker logs 实时可见
- 文件 /data/log/profiler.log：持久化，7×24 排查历史问题
- 文件轮转：单文件 5MB，保留 3 个，避免爆盘
- 统一格式：时间 [级别] 组件名: 消息
- 各组件用 logging.getLogger("profiler.xxx")，自动继承本配置

用法（各组件 main 调一次）：
    from .log import setup_logging
    setup_logging()
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_DEFAULT_LOG_DIR = Path("/data/log")
_DEFAULT_LEVEL = logging.INFO
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(log_dir: Path | str | None = None,
                  level: int = _DEFAULT_LEVEL) -> None:
    """配置 root logger：stdout + 轮转文件。幂等（重复调用不叠加 handler）。"""
    log_dir = Path(log_dir or os.environ.get("LOG_DIR", _DEFAULT_LOG_DIR))

    root = logging.getLogger()
    root.setLevel(level)

    # 幂等：已配置过则跳过（避免 supervisor 重启 program 时叠加 handler）
    if getattr(root, "_profiler_configured", False):
        return
    root._profiler_configured = True  # type: ignore

    formatter = logging.Formatter(_FORMAT)

    # stdout（docker logs 可见）
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    root.addHandler(sh)

    # 文件（持久化排查，轮转防爆）
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / "profiler.log",
            maxBytes=5 * 1024 * 1024,   # 5MB
            backupCount=3,              # 保留 3 个历史
            encoding="utf-8",
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except OSError:
        # 文件不可写（如只读环境）时退化为仅 stdout，不阻断采集
        root.warning("无法写日志文件 %s，退化为仅 stdout", log_dir)
