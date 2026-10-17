#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把看板打成单文件 HTML（对外交付形态）。

面试官拿到手的是一个 作品集.html：双击即看，不用解压文件夹、不用装 Python。
ECharts 与看板数据全部内联进这一个文件；没有本地服务时，工作台按钮自动
进入「静态快照」模式，回放最近一次真实发布（批次 PUB-*）的产出。

与线上版的区别只在执行层：本地 dashboard.bat 是真写盘，单文件版是回放，
页面顶部的说明条会写清楚这一点，不会出现「服务未连接」这类减分文案。

用法
----
    python build_single.py                 输出到项目根 index.html
    python build_single.py --out 路径      指定输出位置

输出名用 index.html 而不是中文文件名：GitHub 仓库根目录的 index.html 可被
GitHub Pages / htmlpreview 等在线预览方案直接当首页渲染，URL 也不用做中文编码。

注意：改完 index.html 或重建 data.js 后要重跑本脚本，单文件不会自己更新。
"""

import argparse
import datetime as dt
from pathlib import Path

DASH = Path(__file__).resolve().parent
ROOT = DASH.parent
INDEX = DASH / "index.html"
ECHARTS = DASH / "assets" / "echarts.min.js"
DATA = DASH / "data.js"
RAG = DASH / "rag.js"

# 单文件版打开时自动展开四步真实产出（面试官第一眼就看到完整闭环）
AUTO_DEMO = '<script>if(!location.hash)location.hash="#demo";</script>'


def inline_script(html: str, tag: str, path: Path) -> str:
    """把 <script src="..."> 替换成内联脚本。"""
    body = path.read_text(encoding="utf-8")
    if "</script" in body.lower():
        raise SystemExit(f"[ERROR] {path.name} 里含 </script>，直接内联会截断，先转义再打包")
    if tag not in html:
        raise SystemExit(f"[ERROR] index.html 里找不到 {tag}，脚本标签是否被改过？")
    return html.replace(tag, "<script>\n" + body + "\n</script>")


def main():
    ap = argparse.ArgumentParser(description="打包单文件看板")
    ap.add_argument("--out", default=str(ROOT / "index.html"), help="输出路径")
    args = ap.parse_args()

    for p in (INDEX, ECHARTS, DATA, RAG):
        if not p.exists():
            raise SystemExit(f"[ERROR] 缺少 {p}，先跑 build_data.py 生成 data.js")

    html = INDEX.read_text(encoding="utf-8")
    html = inline_script(html, '<script src="assets/echarts.min.js"></script>', ECHARTS)
    html = inline_script(html, '<script src="data.js"></script>', DATA)
    html = inline_script(html, '<script src="rag.js"></script>', RAG)

    # 注意：echarts.min.js 内部字符串里也出现 "</body>"（图片导出模板），
    # 必须从最后一个 </body> 前插入，用 replace(...,1) 会注入进 echarts 源码中间。
    idx = html.rfind("</body>")
    if idx < 0:
        raise SystemExit("[ERROR] index.html 里找不到 </body>")
    html = html[:idx] + AUTO_DEMO + "\n" + html[idx:]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    size_mb = out.stat().st_size / 1024 / 1024
    print("单文件打包完成")
    print(f"  输出   {out}")
    print(f"  体积   {size_mb:.2f} MB")
    print(f"  时间   {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  双击即可打开；发给别人直接传这一个文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
