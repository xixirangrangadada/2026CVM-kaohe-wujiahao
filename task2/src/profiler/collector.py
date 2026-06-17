"""C1 采集器 —— perf record 后台持续采集 + 定时轮转 + SIGTERM 优雅停。

设计（见 docs/架构设计.md）：
- 轮转方式：外层循环 subprocess。每窗口 `perf record -F <freq> -a -g -- sleep <rotate>`
  跑完，Python 用 naming.py 归档命名，进入下一窗口。命名可控、信号好处理、易测。
  不选 perf --switch-output（其切片命名不可控）。窗口切换间隙（几百 ms perf 重启）
  对"黑匣子"场景可接受。
- 优雅停：SIGTERM/SIGINT → 设 stop flag + 给当前 perf 子进程转发 SIGINT（不是 SIGTERM！
  perf 对 SIGINT 优雅退出、写完 perf.data；对 SIGTERM 会丢数据）→ 归档最后窗口。
- 产物：每窗口 perf.data → <data_dir>/perf-<start>-<end>.data（naming 约定）。

用法：
    python -m profiler.collect                      # 前台跑，SIGTERM/Ctrl-C 停
    ROTATE_SECONDS=10 python -m profiler.collect    # 测试用短窗口
"""
from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from . import naming
from .config import Config
from .log import setup_logging

log = logging.getLogger("profiler.collector")

# perf 二进制名（PATH 中查找；容器内若装了 perf 即可）
PERF = "perf"


class Collector:
    """持续采集器。一个实例对应一次常驻运行。"""

    def __init__(self, config: Config | None = None) -> None:
        self.cfg = config or Config.from_env()
        self.cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self._stop = False
        self._proc: subprocess.Popen | None = None

    # ---- 信号 ----
    def _install_signal_handlers(self) -> None:
        """SIGTERM/SIGINT → 优雅停。Docker stop 默认发 SIGTERM。"""
        def handler(signum, _frame):
            log.info("收到信号 %s，开始优雅停止...", signal.Signals(signum).name)
            self._stop = True
            self._interrupt_current()
        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)

    def _interrupt_current(self) -> None:
        """给当前 perf 子进程发 SIGINT（优雅写完 perf.data 后退出）。"""
        if self._proc and self._proc.poll() is None:
            log.info("向 perf 子进程转发 SIGINT（优雅写盘）")
            self._proc.send_signal(signal.SIGINT)

    # ---- 单窗口采集 ----
    def _collect_window(self, start: datetime) -> datetime:
        """采集一个轮转窗口。返回窗口结束时间。"""
        tmp = Path(tempfile.gettempdir()) / "perf_current.data"
        if tmp.exists():
            tmp.unlink()

        cmd = [
            PERF, "record",
            "-F", str(self.cfg.sample_freq),
            "-a", "-g",
            "-o", str(tmp),
            *self.cfg.perf_extra,
            "--", "sleep", str(self.cfg.rotate_seconds),
        ]
        log.info("窗口开始 %s | 时长 %ds | cmd: %s",
                 naming.fmt_ts(start), self.cfg.rotate_seconds, " ".join(cmd))

        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)  # DEVNULL：避免 PIPE 不读致 perf 写满缓冲死锁
            self._proc.wait()
            rc = self._proc.returncode
        finally:
            self._proc = None

        if rc != 0:
            log.warning("perf record 退出码 %d（窗口 %s），数据可能不完整", rc, naming.fmt_ts(start))
        end = datetime.now()
        self._archive(tmp, start, end)
        return end

    def _archive(self, src: Path, start: datetime, end: datetime) -> None:
        """把单窗口 perf.data 归档为命名约定格式。"""
        if not src.exists() or src.stat().st_size == 0:
            log.warning("窗口 %s 无数据，跳过归档", naming.fmt_ts(start))
            return
        dst = self.cfg.data_dir / naming.data_filename(start, end)
        shutil.move(str(src), str(dst))  # 跨设备安全（rename 只支持同文件系统）
        log.info("已归档 %s (%d KB)", dst.name, dst.stat().st_size // 1024)

    # ---- 主循环 ----
    def run(self) -> int:
        """持续采集直到收到停止信号。返回退出码。"""
        self._install_signal_handlers()
        log.info("采集器启动 | data_dir=%s | 窗口=%ds | 频率=%dHz | 保留=%dh",
                 self.cfg.data_dir, self.cfg.rotate_seconds,
                 self.cfg.sample_freq, self.cfg.retain_hours)
        windows = 0
        while not self._stop:
            start = datetime.now()
            try:
                self._collect_window(start)
                windows += 1
            except FileNotFoundError:
                log.error("找不到 perf 命令（%s），请确认已安装", PERF)
                return 2
            except Exception:
                log.exception("窗口采集异常")
                time.sleep(1)  # 异常后退避，避免死循环打爆日志
        log.info("采集器停止，共完成 %d 个窗口", windows)
        return 0


def main() -> int:
    setup_logging()
    return Collector().run()


if __name__ == "__main__":
    sys.exit(main())
