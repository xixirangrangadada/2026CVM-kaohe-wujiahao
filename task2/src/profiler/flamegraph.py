"""C4 火焰图器 —— 采样文件 → SVG 火焰图（库 + CLI 双入口）。

设计（见 docs/架构设计.md）：
- 工具链：perf script（多文件合并输出栈）→ stackcollapse-perf.pl → flamegraph.pl → SVG
- 多文件合并：回查常跨多个轮转文件，perf script 接受多个 -i，自动合并栈数据。
- 火焰图工具链路径可配（容器内装在固定路径；宿主机题1 clone 在 /root/cvm/FlameGraph）。
- 库接口：generate(files, out_svg)，供 C5 HTTP 调用。

依赖外部命令：perf、perl、FlameGraph（stackcollapse-perf.pl + flamegraph.pl）。
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from . import naming
from .log import setup_logging

log = logging.getLogger("profiler.flamegraph")

# FlameGraph 工具链路径（环境变量覆盖；默认容器内路径）
DEFAULT_FLAMEGRAPH_DIR = "/opt/FlameGraph"


class FlamegraphError(RuntimeError):
    """火焰图生成失败。"""


def _flamegraph_dir() -> Path:
    return Path(os.environ.get("FLAMEGRAPH_DIR", DEFAULT_FLAMEGRAPH_DIR))


def _check_tools(files: list[Path]) -> None:
    """前置检查：perf 可用、文件存在、FlameGraph 工具链就位。"""
    if not files:
        raise FlamegraphError("无采样文件")
    for f in files:
        if not f.exists():
            raise FlamegraphError(f"采样文件不存在: {f}")
    d = _flamegraph_dir()
    if not (d / "stackcollapse-perf.pl").exists() or not (d / "flamegraph.pl").exists():
        raise FlamegraphError(f"FlameGraph 工具链不在 {d}（设 FLAMEGRAPH_DIR 环境变量）")


def generate(files: list[Path], out_svg: Path, title: str | None = None) -> Path:
    """对多个采样文件合并生成火焰图 SVG。

    files: 采样文件列表（通常来自 query.locate_files）
    out_svg: 输出 SVG 路径
    title: 火焰图标题（默认用文件时间范围）
    返回 out_svg。
    """
    _check_tools(files)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    fg = _flamegraph_dir()

    # 计算标题（用最早/最晚文件的时间范围）
    if title is None:
        spans = []
        for f in files:
            try:
                s, e = naming.parse_data_filename(f.name)
                spans.append((s, e))
            except naming.NamingError:
                pass
        if spans:
            gs, ge = min(s for s, _ in spans), max(e for _, e in spans)
            title = f"CPU flame {naming.fmt_ts(gs)} ~ {naming.fmt_ts(ge)}"
        else:
            title = "CPU flame"

    # 1. perf script 合并多文件输出栈
    cmd_script = ["perf", "script"]
    for f in files:
        cmd_script += ["-i", str(f)]
    log.info("perf script 合并 %d 个文件", len(files))
    proc_script = subprocess.run(cmd_script, capture_output=True, text=True)
    if proc_script.returncode != 0:
        raise FlamegraphError(f"perf script 失败: {proc_script.stderr[:200]}")

    # 2. stackcollapse-perf.pl
    collapse = fg / "stackcollapse-perf.pl"
    proc_collapse = subprocess.run(
        ["perl", str(collapse)],
        input=proc_script.stdout, capture_output=True, text=True)
    if proc_collapse.returncode != 0:
        raise FlamegraphError(f"stackcollapse 失败: {proc_collapse.stderr[:200]}")

    # 3. flamegraph.pl
    flame = fg / "flamegraph.pl"
    proc_flame = subprocess.run(
        ["perl", str(flame), "--title", title],
        input=proc_collapse.stdout, capture_output=True, text=True)
    if proc_flame.returncode != 0:
        raise FlamegraphError(f"flamegraph 失败: {proc_flame.stderr[:200]}")

    out_svg.write_text(proc_flame.stdout, encoding="utf-8")
    log.info("火焰图已生成 %s (%d KB)", out_svg, out_svg.stat().st_size // 1024)
    return out_svg


def main(argv: list[str] | None = None) -> int:
    """CLI：python -m profiler.flamegraph <start> <end> [--out svg]

    按时间段回查（复用 query）再生成火焰图。
    """
    setup_logging()
    argv = argv if argv is not None else sys.argv[1:]

    # 解析参数：<start> <end> [--out PATH]
    out_idx = argv.index("--out") if "--out" in argv else -1
    if out_idx >= 0:
        time_args = argv[:out_idx]
        out_svg = Path(argv[out_idx + 1])
    else:
        time_args = argv
        out_svg = None

    if len(time_args) != 2:
        print('用法: python -m profiler.flamegraph <start> <end> [--out svg.svg]', file=sys.stderr)
        return 1

    from .query import locate_files, parse_time_arg  # 延迟导入，避免循环
    from .config import Config
    try:
        start = parse_time_arg(time_args[0])
        end = parse_time_arg(time_args[1])
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    files = locate_files(start, end)
    if not files:
        print(f"[{start} ~ {end}] 无命中采样文件", file=sys.stderr)
        return 1

    cfg = Config.from_env()
    if out_svg is None:
        out_svg = cfg.svg_dir / naming.svg_filename(start, end)

    try:
        generate(files, out_svg)
        print(f"✅ 火焰图: {out_svg}")
        return 0
    except FlamegraphError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
