#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
导出虚拟数据库（data/game.db）的内容，供查看 / 交付 / 二次分析。

用法
----
    python export_data.py                导出 CSV + Excel（默认）
    python export_data.py --csv-only     只导出 CSV（不需要 openpyxl）
    python export_data.py --out 目录      指定输出目录
    python export_data.py --list         列出可导出的数据源

输出（默认写到 data/export/）
---------------------------
    游戏运营数据.xlsx      多工作表汇总，双击即可用 Excel 打开
    CSV/*.csv             每个数据源一个文件，UTF-8 带 BOM，Excel 打开不乱码
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "game.db"
DEFAULT_OUT = ROOT / "data" / "export"

# (工作表名, 数据源, 排序, 说明)
DATASETS = [
    ("A_大盘指标", "v_daily_kpi", "date",
     "日粒度大盘：新增 / 非新增活跃 / DAU / 付费率 / 付费用户 / 流水 / ARPU / ARPPU"),
    ("A_大盘原始", "daily_metrics", "date",
     "daily_metrics 原始表"),
    ("B_付费分层", "v_tier_daily", "date, sort_order",
     "各档付费用户 / 人均付费 / 流水 / 人数占比 / 流水占比"),
    ("B_分层原始", "revenue_tiers", "date, sort_order",
     "revenue_tiers 原始表"),
    ("C_留存宽表", "v_retention_wide", "cohort_date",
     "每个新增队列的 D1~D30 留存率"),
    ("C_留存明细", "retention_cohorts", "cohort_date, day_n",
     "留存长表：队列日期 × 天数"),
    ("D_剧本事件", "story_events", "day_index",
     "剧本事件及其影响参数"),
]


def pct_columns(cols):
    """判断哪些列是比率（用于 Excel 里显示成百分比）。"""
    hits = []
    for i, c in enumerate(cols):
        lc = str(c).lower()
        if lc.endswith("rate") or lc.endswith("share"):
            hits.append(i)
        elif lc.startswith("d") and lc[1:].isdigit():
            hits.append(i)
    return hits


def display_width(text):
    """中文按 2 个字符宽度计算，用于设置 Excel 列宽。"""
    return sum(2 if ord(ch) > 127 else 1 for ch in str(text))


def fetch(conn, name, order_by):
    cur = conn.execute(f'SELECT * FROM "{name}" ORDER BY {order_by}')
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


def write_xlsx(path, datasets):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    for label, cols, rows in datasets:
        ws = wb.create_sheet(title=label[:31])
        ws.append(list(cols))
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        for r in rows:
            ws.append(list(r))
        for i in pct_columns(cols):
            for row in range(2, ws.max_row + 1):
                ws.cell(row=row, column=i + 1).number_format = "0.00%"
        for i, name in enumerate(cols, start=1):
            width = display_width(name) + 4
            ws.column_dimensions[get_column_letter(i)].width = min(max(width, 10), 24)
        ws.freeze_panes = "A2"
    wb.save(path)


def main():
    ap = argparse.ArgumentParser(description="导出虚拟数据库内容")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="数据库路径")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    ap.add_argument("--csv-only", action="store_true", help="只导出 CSV，不生成 Excel")
    ap.add_argument("--list", action="store_true", help="列出可导出的数据源")
    args = ap.parse_args()

    if args.list:
        print("可导出的数据源：")
        for label, name, _order, desc in DATASETS:
            print(f"  {label:<10} <- {name:<20} {desc}")
        return 0

    db = Path(args.db)
    if not db.exists():
        print(f"[ERROR] 数据库不存在：{db}")
        print("        先运行 start.bat 生成数据，再导出。")
        return 1

    out = Path(args.out)
    csv_dir = out / "CSV"
    csv_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db)
    print("数据源 :", db)
    print("输出到 :", out)
    print()

    collected = []
    for label, name, order_by, _desc in DATASETS:
        try:
            cols, rows = fetch(conn, name, order_by)
        except sqlite3.Error as exc:
            print(f"  [跳过] {label:<10} {exc}")
            continue
        write_csv(csv_dir / f"{label}.csv", cols, rows)
        collected.append((label, cols, rows))
        print(f"  [CSV ] {label:<10} {len(rows):>5} 行 × {len(cols):>2} 列")
    conn.close()

    if not args.csv_only:
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            print()
            print("  [提示] 未安装 openpyxl，跳过 Excel 汇总（CSV 已导出）。")
            print("         需要 Excel 汇总请先运行：python -m pip install openpyxl")
        else:
            xlsx = out / "游戏运营数据.xlsx"
            write_xlsx(xlsx, collected)
            print()
            print(f"  [XLSX] 游戏运营数据.xlsx  （{len(collected)} 个工作表）")

    print()
    print("完成。用 Excel 打开 data/export/ 下的文件即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
