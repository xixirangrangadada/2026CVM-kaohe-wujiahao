"""C5 HTTP API + 前端托管（Flask）—— P1 加分项。

接口：
  GET  /            前端单页 index.html
  GET  /api/files   采样文件列表（时间线）
  POST /api/flame   按时间段生成火焰图，返回 SVG 路径
  GET  /api/status  采集状态 + 磁盘占用 + 文件数
  GET  /svg/<name>  取生成的 SVG（供 iframe 嵌入）

复用 C3 query / C4 flamegraph / naming，不重复实现。
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import naming
from .config import Config
from .flamegraph import FlamegraphError, generate
from .log import setup_logging
from .query import QueryError, locate_files, parse_time_arg

log = logging.getLogger("profiler.server")

# 前端静态文件目录（镜像内 /opt/app/web）
WEB_DIR = Path(os.environ.get("WEB_DIR", "/opt/app/web"))

app = Flask(__name__, static_folder=None)
cfg = Config.from_env()


def _is_collecting() -> bool:
    """collector 是否在跑（看 perf 进程在不在）。"""
    try:
        r = subprocess.run(["pgrep", "-x", "perf"], capture_output=True)
        return r.returncode == 0
    except OSError:
        return False


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/api/files")
def api_files():
    """列出所有采样文件（按时间排序）。供前端时间线展示。"""
    items = []
    if cfg.data_dir.exists():
        for f in sorted(cfg.data_dir.glob(f"*{naming.DATA_SUFFIX}")):
            try:
                s, e = naming.parse_data_filename(f.name)
            except naming.NamingError:
                continue
            items.append({
                "file": f.name,
                "start": s.strftime("%Y-%m-%d %H:%M:%S"),
                "end": e.strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": f.stat().st_size // 1024,
            })
    return jsonify(items)


@app.route("/api/flame", methods=["POST"])
def api_flame():
    """时间段 → 生成火焰图。body: {"start": "...", "end": "..."}"""
    data = request.get_json(silent=True) or {}
    try:
        start = parse_time_arg(data.get("start", ""))
        end = parse_time_arg(data.get("end", ""))
    except QueryError as e:
        return jsonify({"error": str(e)}), 400

    files = locate_files(start, end, cfg.data_dir)
    if not files:
        return jsonify({"error": "该时段无采样文件"}), 404

    out = cfg.svg_dir / naming.svg_filename(start, end)
    try:
        generate(files, out)
    except FlamegraphError as e:
        return jsonify({"error": str(e)}), 500
    log.info("前端请求火焰图 %s ~ %s → %s", start, end, out.name)
    return jsonify({"svg": out.name})


@app.route("/api/status")
def api_status():
    """采集状态 + 磁盘 + 文件数。"""
    usage = shutil.disk_usage(cfg.data_dir.parent if cfg.data_dir.exists() else "/")
    n_files = len(list(cfg.data_dir.glob(f"*{naming.DATA_SUFFIX}"))) if cfg.data_dir.exists() else 0
    return jsonify({
        "collecting": _is_collecting(),
        "files": n_files,
        "disk_total_gb": round(usage.total / 1e9, 1),
        "disk_used_gb": round(usage.used / 1e9, 1),
        "disk_free_gb": round(usage.free / 1e9, 1),
        "data_dir": str(cfg.data_dir),
    })


@app.route("/svg/<name>")
def svg(name):
    """取生成的 SVG（iframe src 用）。"""
    return send_from_directory(cfg.svg_dir, name)


def main() -> int:
    setup_logging()
    port = int(os.environ.get("PORT", "8080"))
    log.info("HTTP 服务启动 0.0.0.0:%d | web=%s", port, WEB_DIR)
    # debug=False：生产模式，不被 reloader 双开（supervisord 已管进程）
    app.run(host="0.0.0.0", port=port, debug=False)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
