#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模块③ 配置工作台 · 本地桥服务

为什么需要它
------------
看板是 HTML，浏览器不能写本地文件、也不能跑 git。这个服务只监听 127.0.0.1，
给看板提供四个接口，把「点击」变成「真实落盘」：

    GET  /api/status      服务状态：Excel 数量、待发布变更、锁定活动、git 状态
    POST /api/apply       一键配置：把建议写进 data/export/config/*.xlsx
    POST /api/open-dir    打开配置目录，人工核验
    POST /api/publish     一键发布：Excel → 种子 → 27 张表 → config_tables.sql
    GET  /api/git-cmd     给出可直接复制的提交命令（不执行）

同时它也是静态服务器：页面从 http://127.0.0.1:8765 打开，按钮才有写盘能力。
直接双击 index.html（file://）也能看，写盘按钮进入「静态快照」演示模式，
回放最近一次真实发布的产出。

用法
----
    python serve.py                起服务并自动打开浏览器
    python serve.py --no-open      只起服务
    python serve.py --port 8899    指定端口
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(ROOT / "03_activity_agent"))

import config_io  # noqa: E402
import activity_engine as eng  # noqa: E402

BUILD = ROOT / "02_dashboard" / "build_data.py"


def pyexe():
    return sys.executable


def git_info():
    """只看状态，不做任何写操作。"""
    try:
        br = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True, timeout=8)
        st = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                            capture_output=True, text=True, timeout=8)
        dirty = [ln for ln in st.stdout.splitlines() if ln.strip()]
        return {"ok": br.returncode == 0, "branch": br.stdout.strip() or "—",
                "dirty": len(dirty), "sample": dirty[:12]}
    except Exception as e:  # git 未安装 / 非仓库
        return {"ok": False, "branch": "—", "dirty": 0, "error": str(e)}


def api_status():
    has = config_io._import_openpyxl()
    files = sorted(config_io.EXCEL_DIR.glob("*.xlsx")) if config_io.EXCEL_DIR.exists() else []
    changes, skipped, errors = [], [], []
    if has and config_io.DB_PATH.exists():
        try:
            changes, skipped, errors, _ = config_io.collect()
        except Exception as e:
            errors = [str(e)]
    sugg = config_io.load_json(config_io.SUGGEST_PATH) or {}
    log = config_io.load_json(config_io.LOG_PATH, {}) or {}
    last = (log.get("batches") or [{}])[-1]
    return {
        "ok": True, "service": "up", "openpyxl": has,
        "excel_dir": str(config_io.EXCEL_DIR),
        "excel_count": len(files), "expected": 27,
        "pending": len(changes),
        "pending_by_activity": sorted({c["activity_id"] for c in changes}),
        "suggestions": len(sugg.get("items") or []),
        "skipped": len(skipped), "errors": errors,
        "last_publish": {"batch": last.get("batch"), "when": last.get("published_at"),
                         "changes": len(last.get("changes") or [])} if last else None,
        "git": git_info(),
        "root": str(ROOT),
    }


def api_apply(ids=None):
    r = config_io.apply_suggestions(ids)
    r["status"] = api_status()
    return r


def api_publish(dry=False):
    r = config_io.publish(dry=dry)
    if r.get("ok") and r.get("batch"):
        # 发布后重建看板数据，页面刷新即可看到「待发布变更归零」
        subprocess.run([pyexe(), str(BUILD)], cwd=str(ROOT), capture_output=True, text=True)
        r["git_lines"] = config_io.git_commands(r)
    r["status"] = api_status()
    return r


def api_open_dir(target="config"):
    path = config_io.EXCEL_DIR if target == "config" else (ROOT / "data" / "export")
    path.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(path)}
    return {"ok": True, "path": str(path)}


class Handler(SimpleHTTPRequestHandler):
    server_version = "ConfigBridge/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(BASE), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        if self.path.startswith("/api/status"):
            return self._json(api_status())
        if self.path.startswith("/api/git-cmd"):
            return self._json({"ok": True, "lines": config_io.git_commands()})
        if self.path.startswith("/api/ping"):
            return self._json({"ok": True})
        return super().do_GET()

    def do_POST(self):
        body = self._body()
        try:
            if self.path.startswith("/api/apply"):
                return self._json(api_apply(body.get("ids")))
            if self.path.startswith("/api/open-dir"):
                return self._json(api_open_dir(body.get("target") or "config"))
            if self.path.startswith("/api/publish"):
                return self._json(api_publish(dry=bool(body.get("dry"))))
            if self.path.startswith("/api/git-cmd"):
                return self._json({"ok": True, "lines": config_io.git_commands()})
        except Exception as e:
            return self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)
        return self._json({"ok": False, "error": "unknown endpoint"}, 404)


def pick_port(start):
    for p in range(start, start + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def main():
    ap = argparse.ArgumentParser(description="配置工作台本地桥服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    port = pick_port(args.port)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port

    print("=" * 56)
    print("  活动配置工作台 · 本地服务")
    print("=" * 56)
    print("  地址   %s" % url)
    print("  目录   %s" % config_io.EXCEL_DIR)
    print("  依赖   openpyxl %s" % ("已安装" if config_io._import_openpyxl() else "缺失（Excel 功能不可用）"))
    print()
    print("  看板从这里打开，按钮才有写盘能力。")
    print("  关闭本窗口 = 停止服务（看板仍可用，写盘按钮回到静态快照模式）。")
    print("=" * 56)

    if not args.no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
