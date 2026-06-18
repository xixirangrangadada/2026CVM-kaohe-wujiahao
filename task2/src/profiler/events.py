"""C8 事件标记 —— Web 上标记"关注时刻"，事后一键回溯诊断（库 + API 用）。

契合"7×24 黑匣子"定位：**不做 start/stop 采集**（会偏离考题——常驻是题眼），只在 Web 上
点一下"🎬 标记事件"，记下时间戳 + 名称（如"开始跑负载 X"）。事后事件在时间线高亮，
点它即定位到该时段，一键出火焰图 + CPU 指标——把"标记 → 回查 → 诊断"全链路图形化，
且不破坏常驻采集。

存储：/data/events.json，原子写（临时文件 + os.replace）防并发损坏。
结构：[{"id","name","ts","note"}]，ts = 本地时区 "YYYY-MM-DD HH:MM:SS"。
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
from datetime import datetime
from pathlib import Path

from .config import Config
from .log import setup_logging

log = logging.getLogger("profiler.events")


def events_path(data_dir: Path | None = None) -> Path:
    """events.json 路径（与 perf/svg 同卷，/data/events.json）。"""
    data_dir = data_dir or Config.from_env().data_dir
    return data_dir.parent / "events.json"


def load_events(path: Path | None = None) -> list[dict]:
    """读全部事件（按时间排序）。文件不存在/损坏返回 []。"""
    path = path or events_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return sorted(data, key=lambda e: e.get("ts", ""))
    except (OSError, json.JSONDecodeError):
        log.warning("events.json 读取失败/损坏，按空处理")
    return []


def _save(events: list[dict], path: Path) -> None:
    """原子写：临时文件 + os.replace（rename 同卷原子）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def add_event(name: str, note: str = "", path: Path | None = None) -> dict:
    """记录一个事件（时间戳 = 当前）。返回新事件。"""
    path = path or events_path()
    events = load_events(path)
    ev = {
        "id": secrets.token_hex(4),  # 8 字符 id
        "name": (name or "").strip()[:64] or "未命名事件",
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": (note or "").strip()[:200],
    }
    events.append(ev)
    _save(events, path)
    log.info("标记事件 %s @ %s", ev["name"], ev["ts"])
    return ev


def delete_event(eid: str, path: Path | None = None) -> bool:
    """删一个事件。返回是否实际删除。"""
    path = path or events_path()
    events = load_events(path)
    new = [e for e in events if e.get("id") != eid]
    if len(new) == len(events):
        return False
    _save(new, path)
    return True


def main() -> int:
    """CLI：python -m profiler.events —— 列出所有事件。"""
    setup_logging()
    for e in load_events():
        print(f"{e['ts']}  [{e['id']}] {e['name']}  {e['note']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
