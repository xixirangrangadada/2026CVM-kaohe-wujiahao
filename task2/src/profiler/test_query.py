"""query.py 单测 —— 回查核心：时间解析容错 + 时段命中定位。

运行：python -m pytest test_query.py（或 python test_query.py）
纯标准库 + 临时目录，不依赖 perf。
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, ".")
from profiler import naming, query


class TestParseTimeArg(unittest.TestCase):
    def test_multi_formats(self):
        """多种输入格式都解析成同一时刻（前端/CLI 容错）。"""
        cases = [
            "2026-06-17 03:12:00",
            "2026-06-17 03:12",
            "2026-06-17_031200",
            "20260617_031200",
        ]
        expect = datetime(2026, 6, 17, 3, 12, 0)
        for s in cases:
            self.assertEqual(query.parse_time_arg(s), expect, f"应解析 {s}")

    def test_strip_whitespace(self):
        """前后空格容错。"""
        self.assertEqual(query.parse_time_arg("  2026-06-17 03:12:00  "),
                         datetime(2026, 6, 17, 3, 12, 0))

    def test_illegal(self):
        """非法输入抛 QueryError。"""
        for bad in ["", "garbage", "2026/06/17", "03:12:00", "2026-13-40 99:99:99"]:
            with self.assertRaises(query.QueryError):
                query.parse_time_arg(bad)


class TestLocateFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        base = datetime(2026, 6, 17, 3, 12, 0)
        self.slots = []
        for i in range(3):  # 03:12 / 03:13 / 03:14 各一分钟
            s = base + timedelta(minutes=i)
            e = s + timedelta(seconds=60)
            (self.tmp / naming.data_filename(s, e)).touch()
            self.slots.append((s, e))

    def test_hit_one(self):
        """查询区间落在单个文件内 → 命中该文件。"""
        s, e = self.slots[1]
        hits = query.locate_files(
            datetime(2026, 6, 17, 3, 13, 30), datetime(2026, 6, 17, 3, 13, 40), self.tmp)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].name, naming.data_filename(s, e))

    def test_hit_multiple_sorted(self):
        """大查询区间命中多个文件，按时间排序返回。"""
        hits = query.locate_files(
            datetime(2026, 6, 17, 3, 0, 0), datetime(2026, 6, 17, 4, 0, 0), self.tmp)
        self.assertEqual([h.name for h in hits],
                         [naming.data_filename(s, e) for s, e in self.slots])

    def test_no_hit_boundary(self):
        """半开区间：查询端点恰好等于文件端点 → 不命中。"""
        # 文件 03:12:00~03:13:00；查 03:00~03:12:00（右端贴文件左端）→ 不相交
        hits = query.locate_files(
            datetime(2026, 6, 17, 3, 0, 0), datetime(2026, 6, 17, 3, 12, 0), self.tmp)
        self.assertEqual(hits, [])

    def test_empty_dir(self):
        """空目录返回 []。"""
        empty = Path(tempfile.mkdtemp())
        self.assertEqual(query.locate_files(
            datetime(2026, 6, 17, 0, 0, 0), datetime(2026, 6, 17, 23, 0, 0), empty), [])

    def test_nonexistent_dir(self):
        """目录不存在返回 []（不抛）。"""
        self.assertEqual(query.locate_files(
            datetime(2026, 6, 17, 0, 0, 0), datetime(2026, 6, 17, 23, 0, 0),
            Path("/no/such/dir/xyz")), [])

    def test_ignores_non_data_and_misnamed(self):
        """忽略 metrics csv / 杂项 / 命名不符的 .data。"""
        (self.tmp / "metrics-20260617_031200-20260617_031300.csv").touch()
        (self.tmp / "garbage.txt").touch()
        (self.tmp / "perf-bad.data").touch()
        hits = query.locate_files(
            datetime(2026, 6, 17, 3, 0, 0), datetime(2026, 6, 17, 4, 0, 0), self.tmp)
        self.assertEqual(len(hits), 3)  # 只命中 3 个合法 .data

    def test_end_before_start(self):
        """end 早于 start 抛 QueryError。"""
        with self.assertRaises(query.QueryError):
            query.locate_files(
                datetime(2026, 6, 17, 4, 0, 0), datetime(2026, 6, 17, 3, 0, 0), self.tmp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
