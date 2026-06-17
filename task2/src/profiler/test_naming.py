"""naming.py 单测 —— 验证 build/parse 互逆 + 边界情况。

运行：python -m pytest test_naming.py  （或 python test_naming.py）
无第三方依赖，纯标准库，可直接 python 运行。
"""
import sys
import unittest
from datetime import datetime

sys.path.insert(0, ".")
from profiler import naming


class TestTimestamp(unittest.TestCase):
    def test_fmt_parse_roundtrip(self):
        """格式化 → 解析 往返一致。"""
        dt = datetime(2026, 6, 17, 3, 12, 0)
        self.assertEqual(naming.parse_ts(naming.fmt_ts(dt)), dt)

    def test_parse_illegal(self):
        """非法时间戳抛 NamingError。"""
        for bad in ["20260617", "2026-06-17_03:12:00", "garbage", "20260617_031200_00"]:
            with self.assertRaises(naming.NamingError, msg=f"应拒绝 {bad}"):
                naming.parse_ts(bad)


class TestDataFilename(unittest.TestCase):
    def test_build_format(self):
        """文件名格式正确：perf-<start>-<end>.data。"""
        s, e = datetime(2026, 6, 17, 3, 12, 0), datetime(2026, 6, 17, 3, 13, 0)
        self.assertEqual(naming.data_filename(s, e),
                         "perf-20260617_031200-20260617_031300.data")

    def test_build_parse_roundtrip(self):
        """build → parse 往返一致。"""
        s, e = datetime(2026, 6, 17, 3, 12, 0), datetime(2026, 6, 17, 3, 13, 0)
        ps, pe = naming.parse_data_filename(naming.data_filename(s, e))
        self.assertEqual((ps, pe), (s, e))

    def test_parse_with_dirpath(self):
        """parse 能处理带目录前缀的全路径。"""
        full = "/data/perf/perf-20260617_031200-20260617_031300.data"
        # 注意：parse 只匹配文件名，传全路径要先 basename
        from pathlib import Path
        ps, pe = naming.parse_data_filename(Path(full).name)
        self.assertEqual(ps, datetime(2026, 6, 17, 3, 12, 0))
        self.assertEqual(pe, datetime(2026, 6, 17, 3, 13, 0))

    def test_parse_illegal_name(self):
        """非法文件名抛 NamingError。"""
        for bad in ["perf-xxx.data", "20260617.data", "perf-20260617_031200.data",
                    "matrixprod.data"]:
            with self.assertRaises(naming.NamingError):
                naming.parse_data_filename(bad)

    def test_end_before_start(self):
        """end 早于 start 抛 NamingError。"""
        s, e = datetime(2026, 6, 17, 3, 13, 0), datetime(2026, 6, 17, 3, 12, 0)
        with self.assertRaises(naming.NamingError):
            naming.data_filename(s, e)


class TestSvgFilename(unittest.TestCase):
    def test_build_format(self):
        s, e = datetime(2026, 6, 17, 3, 12, 0), datetime(2026, 6, 17, 3, 13, 0)
        self.assertEqual(naming.svg_filename(s, e),
                         "flame-20260617_031200-20260617_031300.svg")

    def test_roundtrip(self):
        s, e = datetime(2026, 6, 17, 3, 12, 0), datetime(2026, 6, 17, 3, 13, 0)
        self.assertEqual(naming.parse_svg_filename(naming.svg_filename(s, e)), (s, e))


class TestOverlaps(unittest.TestCase):
    """时间段相交判定 —— 回查定位采样文件用。"""
    def setUp(self):
        # 基准：一个采样文件覆盖 03:12:00 ~ 03:13:00
        self.s = datetime(2026, 6, 17, 3, 12, 0)
        self.e = datetime(2026, 6, 17, 3, 13, 0)

    def test_query_inside(self):
        """查询区间在文件时段内 → 相交。"""
        q = (datetime(2026, 6, 17, 3, 12, 30), datetime(2026, 6, 17, 3, 12, 40))
        self.assertTrue(naming.overlaps(self.s, self.e, *q))

    def test_query_contains_file(self):
        """查询区间包住文件时段 → 相交。"""
        q = (datetime(2026, 6, 17, 3, 0, 0), datetime(2026, 6, 17, 4, 0, 0))
        self.assertTrue(naming.overlaps(self.s, self.e, *q))

    def test_query_partial_overlap(self):
        """查询区间与文件时段部分重叠 → 相交。"""
        q1 = (datetime(2026, 6, 17, 3, 10, 0), datetime(2026, 6, 17, 3, 12, 30))  # 左跨
        q2 = (datetime(2026, 6, 17, 3, 12, 30), datetime(2026, 6, 17, 3, 15, 0))  # 右跨
        self.assertTrue(naming.overlaps(self.s, self.e, *q1))
        self.assertTrue(naming.overlaps(self.s, self.e, *q2))

    def test_query_no_overlap(self):
        """查询区间在文件时段外 → 不相交。"""
        q1 = (datetime(2026, 6, 17, 3, 0, 0), datetime(2026, 6, 17, 3, 12, 0))   # 紧贴左端
        q2 = (datetime(2026, 6, 17, 3, 13, 0), datetime(2026, 6, 17, 3, 14, 0))  # 紧贴右端
        q3 = (datetime(2026, 6, 17, 5, 0, 0), datetime(2026, 6, 17, 6, 0, 0))    # 完全在外
        self.assertFalse(naming.overlaps(self.s, self.e, *q1))
        self.assertFalse(naming.overlaps(self.s, self.e, *q2))
        self.assertFalse(naming.overlaps(self.s, self.e, *q3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
