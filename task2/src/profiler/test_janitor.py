"""janitor.py 单测 —— 过期清理：删过期、不误删未过期/非约定文件。

运行：python -m pytest test_janitor.py（或 python test_janitor.py）
纯标准库 + 临时目录，不依赖 perf。janitor 是**误删高风险点**，重点测边界。
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, ".")
from profiler import naming
from profiler.config import Config
from profiler.janitor import Janitor


def _make_cfg(data_dir: Path, retain_hours: int = 24) -> Config:
    return Config(data_dir=data_dir, retain_hours=retain_hours)


def _touch(data_dir: Path, start: datetime) -> Path:
    """在 data_dir 造一个 perf-<start>-<start+60s>.data 空文件，返回路径。"""
    p = data_dir / naming.data_filename(start, start + timedelta(seconds=60))
    p.touch()
    return p


class TestPurgeOnce(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.now = datetime(2026, 6, 17, 12, 0, 0)  # 固定"现在"

    def test_delete_expired_keep_fresh(self):
        """start 早于 cutoff 的删，未过期的不删。"""
        cfg = _make_cfg(self.tmp, retain_hours=1)
        old = _touch(self.tmp, self.now - timedelta(hours=2))      # 过期
        fresh = _touch(self.tmp, self.now - timedelta(minutes=5))  # 未过期
        n = Janitor(cfg).purge_once(now=self.now)
        self.assertEqual(n, 1)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_keep_within_retain(self):
        """retain=24h，5h 前的不删。"""
        cfg = _make_cfg(self.tmp, retain_hours=24)
        p = _touch(self.tmp, self.now - timedelta(hours=5))
        self.assertEqual(Janitor(cfg).purge_once(now=self.now), 0)
        self.assertTrue(p.exists())

    def test_boundary_exactly_cutoff_kept(self):
        """恰好 cutoff（start == cutoff）不删——只有 start < cutoff 才删。"""
        cfg = _make_cfg(self.tmp, retain_hours=1)  # cutoff = now - 1h
        boundary = _touch(self.tmp, self.now - timedelta(hours=1))  # start 恰好 = cutoff
        self.assertEqual(Janitor(cfg).purge_once(now=self.now), 0)
        self.assertTrue(boundary.exists())

    def test_ignores_non_data_files(self):
        """不删 metrics csv / svg / 杂项文件。"""
        cfg = _make_cfg(self.tmp, retain_hours=1)
        _touch(self.tmp, self.now - timedelta(hours=2))  # 过期 data，应删
        csv_s = self.now - timedelta(hours=2)
        csv = self.tmp / naming.metrics_filename(csv_s, csv_s + timedelta(seconds=60))
        csv.touch()
        svg = self.tmp / "flame-20260617_120000-20260617_120100.svg"; svg.touch()
        txt = self.tmp / "notes.txt"; txt.touch()
        n = Janitor(cfg).purge_once(now=self.now)
        self.assertEqual(n, 1)
        self.assertTrue(csv.exists() and svg.exists() and txt.exists())

    def test_ignores_misnamed_data(self):
        """命名不符的 .data 文件不碰（避免误删他人文件）。"""
        cfg = _make_cfg(self.tmp, retain_hours=1)
        bad = self.tmp / "perf-strange.data"; bad.touch()
        _touch(self.tmp, self.now - timedelta(hours=2))
        n = Janitor(cfg).purge_once(now=self.now)
        self.assertEqual(n, 1)  # 只删合法过期文件
        self.assertTrue(bad.exists())

    def test_uses_filename_ts_not_mtime(self):
        """按文件名 start 判断过期，不看 mtime（归档耗时致 mtime 偏晚也能正确清理）。"""
        cfg = _make_cfg(self.tmp, retain_hours=1)
        # 文件名 start = 2h 前（过期），但 mtime 由 touch 设为真实当前时间（很新）
        p = _touch(self.tmp, self.now - timedelta(hours=2))
        self.assertEqual(Janitor(cfg).purge_once(now=self.now), 1)
        self.assertFalse(p.exists())

    def test_empty_dir(self):
        """空目录返回 0。"""
        cfg = _make_cfg(self.tmp, retain_hours=24)
        self.assertEqual(Janitor(cfg).purge_once(now=self.now), 0)

    def test_nonexistent_dir(self):
        """目录不存在返回 0（不抛）。"""
        cfg = _make_cfg(Path("/no/such/dir/xyz"), retain_hours=24)
        self.assertEqual(Janitor(cfg).purge_once(now=self.now), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
