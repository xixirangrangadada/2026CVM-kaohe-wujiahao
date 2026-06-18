"""C6 环境自检 —— 容器自带的环境体检（呼应考题 task2"地基验证三关卡"）。

为什么需要：容器化 perf 有内核/硬件耦合——perf 二进制要能解析**宿主机** `/lib/modules`
的内核符号（版本不匹配则栈全 [unknown]），PMU 事件可用性依赖 CPU 微架构（换 x86 可能
`<not supported>`）。换机器跑可能**静默失败**。本模块启动时/按需跑一遍体检，输出可读
报告 + 卡住时的修复建议，让用户"换机器就知道哪里不对、怎么修"。

检查项（8 项）：
  1. perf_binary      perf 二进制存在 + 版本
  2. perf_paranoid    perf_event_paranoid 权限（≤1 或 root）
  3. sampling         perf 能否真采到样本（1s 空采样，perf.data 非空）
  4. kernel_symbols   内核符号能否解析（采样里 [unknown] 占比）
  5. pmu_events       关键 PMU 事件可用性（哪些 <not supported>，和 metrics 共享事件集）
  6. pid_host         --pid=host 是否生效（PID 1 是宿主机 init 而非容器自己）
  7. flamegraph       FlameGraph 工具链（stackcollapse-perf.pl + flamegraph.pl）
  8. disk             /data 磁盘空间

用法：
    python -m profiler.preflight            # 人类可读报告（退出码：有 FAIL → 1）
    python -m profiler.preflight --json     # JSON（供 Web /api/preflight）

本地（无 perf / 非 Linux）各项 SKIP，可验证逻辑结构；端到端在容器内跑。
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Config
from .log import setup_logging

log = logging.getLogger("profiler.preflight")

PERF = "perf"

# 状态枚举
PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
_SYMBOLS = {PASS: "✅", FAIL: "❌", WARN: "⚠️", SKIP: "⏭️"}


@dataclass
class CheckResult:
    """单项检查结果。"""
    name: str           # 检查项 id（如 "perf_binary"）
    title: str          # 中文标题
    status: str         # PASS / FAIL / WARN / SKIP
    detail: str         # 结果详情
    hint: str = ""      # FAIL/WARN 时的修复建议


class Preflight:
    """环境自检。一个实例对应一次体检。"""

    def __init__(self, config: Config | None = None) -> None:
        self.cfg = config or Config.from_env()
        self._sample_path: Path | None = None  # check 3 产出，check 4 复用

    # ---- 通用工具 ----
    @staticmethod
    def _run_perf(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess | None:
        """跑一个 perf 子进程。无 perf 返回 None（让调用方 SKIP）。"""
        try:
            return subprocess.run([PERF, *args], capture_output=True,
                                  text=True, timeout=timeout)
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            return None
        except OSError:
            return None

    # ---- 1. perf 二进制 ----
    def check_perf_binary(self) -> CheckResult:
        r = self._run_perf(["--version"], timeout=10)
        if r is None:
            return CheckResult("perf_binary", "perf 二进制", SKIP,
                               f"找不到 {PERF}（本地无 perf？）",
                               "容器内 dnf install perf；本地无此项")
        if r.returncode != 0:
            return CheckResult("perf_binary", "perf 二进制", FAIL,
                               f"perf --version 退出码 {r.returncode}",
                               "确认 perf 已正确安装")
        ver = (r.stdout or r.stderr).strip().splitlines()[0]
        return CheckResult("perf_binary", "perf 二进制", PASS, ver)

    # ---- 2. perf_event_paranoid 权限 ----
    def check_perf_paranoid(self) -> CheckResult:
        path = Path("/proc/sys/kernel/perf_event_paranoid")
        try:
            val = int(path.read_text().strip())
        except (OSError, ValueError):
            return CheckResult("perf_paranoid", "PMU 权限(perf_event_paranoid)", SKIP,
                               f"读不到 {path}（非 Linux？）")
        is_root = os.geteuid() == 0
        if val <= 1 or is_root:
            return CheckResult("perf_paranoid", "PMU 权限(perf_event_paranoid)", PASS,
                               f"perf_event_paranoid={val}（root={is_root}）")
        return CheckResult("perf_paranoid", "PMU 权限(perf_event_paranoid)", FAIL,
                           f"perf_event_paranoid={val}，非 root 采不到",
                           "容器用 --privileged；或 sysctl -w kernel.perf_event_paranoid=1")

    # ---- 3. perf 能否真采到样本 ----
    def check_sampling(self) -> CheckResult:
        tmp = Path(tempfile.gettempdir()) / "preflight.data"
        if tmp.exists():
            tmp.unlink()
        r = self._run_perf(["record", "-a", "-F", "99", "-o", str(tmp),
                            "--", "sleep", "1"], timeout=20)
        if r is None:
            return CheckResult("sampling", "perf 采样能力", SKIP,
                               "无 perf（本地？）")
        if r.returncode != 0:
            return CheckResult("sampling", "perf 采样能力", FAIL,
                               f"perf record 退出码 {r.returncode}。stderr: {(r.stderr or '')[-200:].strip()}",
                               "确认 --privileged + PMU 支持；看 perf_paranoid")
        if not tmp.exists() or tmp.stat().st_size == 0:
            return CheckResult("sampling", "perf 采样能力", FAIL,
                               "perf record 成功但无数据",
                               "内核可能不支持硬件 PMU；换支持 PMU 的环境")
        self._sample_path = tmp  # 留给 check 4
        return CheckResult("sampling", "perf 采样能力", PASS,
                           f"采到 {tmp.stat().st_size // 1024}KB 样本")

    # ---- 4. 内核符号解析（[unknown] 占比）----
    def check_kernel_symbols(self) -> CheckResult:
        sample = self._sample_path
        if not sample or not sample.exists():
            return CheckResult("kernel_symbols", "内核符号解析", SKIP,
                               "无可用样本（采样检查未通过）",
                               "先解决采样问题")
        r = self._run_perf(["script", "-i", str(sample)], timeout=30)
        if r is None or r.returncode != 0:
            return CheckResult("kernel_symbols", "内核符号解析", SKIP,
                               "perf script 无法执行")
        lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
        if not lines:
            return CheckResult("kernel_symbols", "内核符号解析", WARN,
                               "perf script 无输出",
                               "样本太小或符号缺失，重跑或加长采样")
        unknown = sum(1 for l in lines if "[unknown]" in l)
        pct = unknown * 100 // len(lines)
        if pct > 70:
            return CheckResult("kernel_symbols", "内核符号解析", FAIL,
                               f"[unknown] 占比 {pct}%（内核符号未解析）",
                               "docker run 加 -v /lib/modules:/lib/modules:ro；"
                               "确认 perf 版本匹配宿主机内核")
        if pct > 30:
            return CheckResult("kernel_symbols", "内核符号解析", WARN,
                               f"[unknown] 占比 {pct}%",
                               "部分符号缺失，建议挂载 /lib/modules")
        return CheckResult("kernel_symbols", "内核符号解析", PASS,
                           f"[unknown] 占比 {pct}%（符号解析正常）")

    # ---- 5. 关键 PMU 事件可用性 ----
    def check_pmu_events(self) -> CheckResult:
        events = self.cfg.stat_events
        r = self._run_perf(["stat", "-x", ",", "-e", ",".join(events),
                            "-a", "--", "sleep", "1"], timeout=20)
        if r is None:
            return CheckResult("pmu_events", "PMU 事件可用性", SKIP,
                               "无 perf（本地？）")
        supported, unsupported, notcounted = [], [], []
        for line in (r.stdout or "").splitlines():
            parts = line.split(",")
            if len(parts) < 3:
                continue
            val, ev = parts[0].strip(), parts[2].strip()
            # 不依赖 events 精确匹配：raw 事件（如 branches 用 raw code）输出名是 name=
            # 指定的短名，与 events 里的长串不一致；只跳过汇总行/空名。
            if not ev or ev == "seconds time elapsed":
                continue
            if "<not supported>" in val:
                unsupported.append(ev)
            elif "<not counted>" in val:
                notcounted.append(ev)
            else:
                supported.append(ev)
        if unsupported:
            sev = FAIL if len(unsupported) > len(events) // 2 else WARN
            return CheckResult("pmu_events", "PMU 事件可用性", sev,
                               f"不支持: {unsupported}；未计数: {notcounted}；支持: {supported}",
                               "这些事件在当前 CPU 微架构不可用，CPU 指标面板对应项将显示 N/A")
        extra = f"（未计数: {notcounted}）" if notcounted else ""
        return CheckResult("pmu_events", "PMU 事件可用性", PASS,
                           f"全部 {len(events)} 个事件可用{extra}")

    # ---- 6. --pid=host 是否生效 ----
    def check_pid_host(self) -> CheckResult:
        try:
            comm = Path("/proc/1/comm").read_text().strip()
        except OSError:
            return CheckResult("pid_host", "--pid=host 共享", SKIP,
                               "读不到 /proc/1/comm（非 Linux？）")
        # --pid=host 时 PID 1 是宿主机 init（systemd/init/...）；
        # 否则 PID 1 是容器自己的进程管理器（supervisord 等）。
        container_inits = {"supervisord", "python", "python3", "bash", "sh", "tini"}
        if comm in container_inits:
            return CheckResult("pid_host", "--pid=host 共享", WARN,
                               f"PID 1 = {comm}（疑似未用 --pid=host）",
                               "docker run 加 --pid=host 才能采宿主机/其他容器进程")
        return CheckResult("pid_host", "--pid=host 共享", PASS,
                           f"PID 1 = {comm}（--pid=host 生效）")

    # ---- 7. FlameGraph 工具链 ----
    def check_flamegraph(self) -> CheckResult:
        fg_dir = Path(os.environ.get("FLAMEGRAPH_DIR", "/opt/FlameGraph"))
        needed = ["stackcollapse-perf.pl", "flamegraph.pl"]
        missing = [f for f in needed if not (fg_dir / f).exists()]
        if missing:
            return CheckResult("flamegraph", "FlameGraph 工具链", FAIL,
                               f"缺失: {missing}（dir={fg_dir}）",
                               "确认镜像 COPY FlameGraph 完整；或 git clone 到 FLAMEGRAPH_DIR")
        return CheckResult("flamegraph", "FlameGraph 工具链", PASS,
                           f"工具链就绪（{fg_dir}）")

    # ---- 8. 磁盘空间 ----
    def check_disk(self) -> CheckResult:
        target = self.cfg.data_dir.parent if self.cfg.data_dir.exists() else self.cfg.data_dir
        try:
            usage = shutil.disk_usage(str(target))
        except OSError:
            return CheckResult("disk", "磁盘空间", SKIP,
                               f"读不到磁盘 {target}")
        free_gb = usage.free / 1e9
        if free_gb < 0.1:
            return CheckResult("disk", "磁盘空间", FAIL,
                               f"剩余 {free_gb:.2f}GB（<0.1GB）",
                               "清理 /data 或扩容卷")
        if free_gb < 1:
            return CheckResult("disk", "磁盘空间", WARN,
                               f"剩余 {free_gb:.2f}GB（<1GB）",
                               "采样文件会快速占用，建议加大 /data 或缩短 RETAIN_HOURS")
        return CheckResult("disk", "磁盘空间", PASS,
                           f"剩余 {free_gb:.1f}GB / 共 {usage.total / 1e9:.1f}GB")

    # ---- 汇总 ----
    def run_all(self) -> list[CheckResult]:
        """按依赖顺序跑全部检查（kernel_symbols 依赖 sampling 的样本）。"""
        checks = [
            self.check_perf_binary,
            self.check_perf_paranoid,
            self.check_sampling,
            self.check_kernel_symbols,
            self.check_pmu_events,
            self.check_pid_host,
            self.check_flamegraph,
            self.check_disk,
        ]
        results: list[CheckResult] = []
        for chk in checks:
            try:
                results.append(chk())
            except Exception as e:  # 单项异常不拖垮整体
                results.append(CheckResult(chk.__name__, chk.__name__, FAIL,
                                           f"检查异常: {e}", "查看日志"))
        return results

    @staticmethod
    def report_text(results: list[CheckResult]) -> str:
        n = lambda s: sum(1 for r in results if r.status == s)
        lines = ["环境自检报告", "=" * 52,
                 f"汇总：✅{n(PASS)} 通过   ❌{n(FAIL)} 失败   ⚠️{n(WARN)} 警告   ⏭️{n(SKIP)} 跳过", ""]
        for r in results:
            lines.append(f"{_SYMBOLS.get(r.status, '?')} [{r.status}] {r.title}")
            lines.append(f"    {r.detail}")
            if r.hint:
                lines.append(f"    💡 {r.hint}")
        lines.append("")
        if n(FAIL):
            lines.append(f"结论：{n(FAIL)} 项未通过，按 💡 提示修复后重跑。")
        elif n(WARN):
            lines.append("结论：无致命问题，但建议关注警告项。")
        else:
            lines.append("结论：环境就绪，可正常采集。")
        return "\n".join(lines)

    @staticmethod
    def report_json(results: list[CheckResult]) -> dict:
        n = lambda s: sum(1 for r in results if r.status == s)
        return {
            "summary": {"pass": n(PASS), "fail": n(FAIL), "warn": n(WARN),
                        "skip": n(SKIP), "ready": n(FAIL) == 0},
            "checks": [asdict(r) for r in results],
        }


def main() -> int:
    import argparse
    import json
    setup_logging()
    parser = argparse.ArgumentParser(description="容器环境自检")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 Web）")
    args = parser.parse_args()

    results = Preflight().run_all()
    if args.json:
        print(json.dumps(Preflight.report_json(results), ensure_ascii=False, indent=2))
    else:
        print(Preflight.report_text(results))
    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
