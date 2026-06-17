"""C2 清理器 —— 定时删除过期采样文件，避免磁盘爆满。

设计（见 docs/架构设计.md）：
- 文件总线消费者：只认 <data_dir>/perf-<start>-<end>.data，按文件名时间戳判断过期，
  不依赖 collector（解耦）。collector 挂了清理器照常工作，反之亦然。
- 用文件名里的 start 时间戳（而非 mtime）判断过期——文件名时间戳是"数据所属时段"，
  语义更准（归档耗时会导致 mtime 偏晚）。
- 只删符合命名约定的文件，避免误删他人文件。

用法：
    python -m profiler.janitor                 # 前台，默认 24h 保留，每 10min 扫一次
    RETAIN_HOURS=2 JANITOR_INTERVAL=60 python -m profiler.janitor
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import naming
from .config import Config
from .log import setup_logging

log = logging.getLogger("profiler.janitor")

DEFAULT_INTERVAL = 600  # 默认扫描间隔（秒）= 10min


class Janitor:
    """过期采样文件清理器。"""

    def __init__(self, config: Config | None = None, interval: int = DEFAULT_INTERVAL) -> None:
        self.cfg = config or Config.from_env()
        self.interval = interval
        self._stop = False

    def _install_signal_handlers(self) -> None:
        import signal
        def handler(signum, _frame):
            log.info("收到信号 %s，停止清理器", signal.Signals(signum).name)
            self._stop = True
        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)

    def purge_once(self, now: datetime | None = None) -> int:
        """执行一次清理。返回删除的文件数。"""
        now = now or datetime.now()
        cutoff = now - timedelta(hours=self.cfg.retain_hours)
        deleted = 0

        if not self.cfg.data_dir.exists():
            return 0

        for f in self.cfg.data_dir.iterdir():
            if not f.is_file() or f.suffix != naming.DATA_SUFFIX:
                continue
            try:
                start, _end = naming.parse_data_filename(f.name)
            except naming.NamingError:
                continue  # 不符合命名约定，不碰
            if start < cutoff:
                size_kb = f.stat().st_size // 1024
                f.unlink()
                deleted += 1
                log.info("删除过期 %s (start=%s, %dKB)", f.name, naming.fmt_ts(start), size_kb)
        return deleted

    def run(self) -> int:
        """定时循环清理，直到收到停止信号。"""
        self._install_signal_handlers()
        log.info("清理器启动 | data_dir=%s | 保留=%dh | 间隔=%ds",
                 self.cfg.data_dir, self.cfg.retain_hours, self.interval)
        while not self._stop:
            n = self.purge_once()
            if n:
                log.info("本轮清理 %d 个过期文件", n)
            # 分段 sleep 以便及时响应停止信号
            for _ in range(self.interval):
                if self._stop:
                    break
                time.sleep(1)
        log.info("清理器停止")
        return 0


def main() -> int:
    import os
    setup_logging()
    interval = int(os.environ.get("JANITOR_INTERVAL", str(DEFAULT_INTERVAL)))
    return Janitor(interval=interval).run()


if __name__ == "__main__":
    sys.exit(main())
