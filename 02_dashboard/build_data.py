#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
构建看板数据文件（02_dashboard/data.js）。

为什么要有这个脚本
------------------
看板是纯静态页面，双击用 file:// 打开。但 file:// 协议下浏览器会拦截
fetch 本地 JSON（CORS 限制），所以数据不能靠「页面去读 json」。
本脚本把数据写成 `window.DASHBOARD_DATA = {...}`，页面用
<script src="data.js"> 引入——script 标签不受该限制，双击即可用。

数据流
------
    01_datagen/config.json  (kpi.monthly_revenue_by_month)  ┐
                                                            ├─→ 02_dashboard/data.js
    data/game.db            (daily_metrics)                 ┘

脚本只负责「搬运原始数据」，不在构建期把 KPI 进度算死——
当前月、累计进度、缺口全部由页面用 JS 现算，这样「今天」一变，
看板会自己跟着走，不需要重新构建。

用法
----
    python build_data.py                    构建（「今天」取系统日期）
    python build_data.py --today 2026-10-16 手动指定「今天」，便于复现某一天的看板
    python build_data.py --check            只打印核算摘要，不写文件
"""

import argparse
import calendar
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH_DIR = ROOT / "02_dashboard"
DB_PATH = ROOT / "data" / "game.db"
CFG_PATH = ROOT / "01_datagen" / "config.json"
SCHED_PATH = ROOT / "01_datagen" / "schedule.json"     # 活动排期台账（模块③ 引擎产出）
SUGGEST_PATH = ROOT / "01_datagen" / "suggestions.json"  # 配置建议（模块③ 引擎产出）
PUBLOG_PATH = ROOT / "data" / "export" / "config" / "_发布记录.json"  # 发布流水（真实执行记录）
CONFIG_SQL_PATH = ROOT / "03_activity_agent" / "config_tables.sql"    # 27 张表的 DDL + 当前值
KB_PATH = ROOT / "05_cs_rag" / "kb.json"                              # 客服知识库（模块⑤）
SENT_PATH = ROOT / "06_sentiment" / "sentiment.json"                  # 舆情语料（模块⑥）
OUT_PATH = DASH_DIR / "data.js"

# 配置字段中文名（与 config_io.CFG_LABEL 保持一致，避免跨目录 import）
CFG_LABEL = {
    "price_tiers": "价格档位", "reward_desc": "奖励内容", "limit_per_user": "单人限购",
    "stock": "库存", "cycle": "周期", "trigger_cond": "触发条件",
    "pity_times": "保底次数", "multiplier": "倍率", "rank_metric": "排行指标",
    "extra": "附加参数",
}


def parse_args():
    ap = argparse.ArgumentParser(description="构建看板数据文件 data.js")
    ap.add_argument("--today", help="指定「今天」（YYYY-MM-DD），默认取系统日期")
    ap.add_argument("--db", default=str(DB_PATH), help="数据库路径")
    ap.add_argument("--config", default=str(CFG_PATH), help="生成规则配置路径")
    ap.add_argument("--out", default=str(OUT_PATH), help="输出文件路径")
    ap.add_argument("--check", action="store_true", help="只打印核算摘要，不写文件")
    return ap.parse_args()


def load_daily(conn):
    """读大盘日表：取看板需要的列，pay_rate / revenue 做定长舍入避免浮点毛刺。"""
    cur = conn.execute(
        "SELECT date, new_users, stock_active, dau, pay_users, "
        "       ROUND(pay_rate, 4), ROUND(revenue, 2) "
        "FROM daily_metrics ORDER BY date"
    )
    return [
        {
            "date": r[0],
            "new_users": r[1],
            "stock_active": r[2],
            "dau": r[3],
            "pay_users": r[4],
            "pay_rate": r[5],
            "revenue": r[6],
        }
        for r in cur
    ]


def load_tiers(conn):
    """读付费分层日表（区块02 用）：全部日期全量搬，页面自己挑「昨日」。"""
    cur = conn.execute(
        "SELECT date, tier_code, tier_name, sort_order, users, "
        "       ROUND(arppu, 2), ROUND(revenue, 2) "
        "FROM revenue_tiers ORDER BY date, sort_order"
    )
    return [
        {
            "date": r[0], "code": r[1], "name": r[2],
            "sort": r[3], "users": r[4], "arppu": r[5], "revenue": r[6],
        }
        for r in cur
    ]


def load_recent(conn, daily, today, days=7):
    """近 N 日日数据（区块01b 用）。

    一行 = 一个自然日，同时携带两类口径不同的指标：
      · 规模与变现（新增/DAU/流水/付费率/付费人数/ARPU/ARPPU）取「当日」日表；
      · 留存（D1/D3/D7/D15/D30）取「该日新增队列」在 retention_cohorts 里的对应行，
        即"这一天进来的用户，第 n 天还剩多少人"。
    ARPU / ARPPU 在这里算好，页面不再做除法，避免两端口径漂移。
    """
    by_date = {r["date"]: r for r in daily}
    window = [d for d in by_date if d <= today]
    window = sorted(window)[-days:]

    cur = conn.execute(
        "SELECT cohort_date, day_n, rate FROM retention_cohorts "
        "WHERE day_n IN (1, 3, 7, 15, 30)"
    )
    ret = {(r[0], r[1]): r[2] for r in cur}

    WD = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    rows = []
    for d in window:
        m = by_date[d]
        dau = m["dau"] or 0
        pay_users = m["pay_users"] or 0
        revenue = m["revenue"] or 0
        row = {
            "date": d,
            "weekday": WD[dt.date.fromisoformat(d).weekday()],
            "new_users": m["new_users"],
            "dau": dau,
            "revenue": round(revenue, 2),
            "pay_rate": m["pay_rate"],
            "pay_users": pay_users,
            "arpu": round(revenue / dau, 2) if dau else None,
            "arppu": round(revenue / pay_users, 2) if pay_users else None,
        }
        for n, key in ((1, "d1"), (3, "d3"), (7, "d7"), (15, "d15"), (30, "d30")):
            v = ret.get((d, n))
            row[key] = round(v, 4) if v is not None else None
        rows.append(row)

    return {
        "days": len(rows),
        "start": rows[0]["date"] if rows else today,
        "end": rows[-1]["date"] if rows else today,
        "rows": rows,
    }


def load_schedule(cfg):
    """排期数据：优先读模块③ 引擎产出的台账，缺失时回落到 config.json 的内嵌排期。"""
    if SCHED_PATH.exists():
        text = SCHED_PATH.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("//")]
        try:
            ledger = json.loads("\n".join(lines))
            if ledger.get("items"):
                return ledger["items"], {
                    "source": "engine",
                    "generated_at": ledger.get("generated_at"),
                    "lock_rule": ledger.get("lock_rule"),
                }
        except json.JSONDecodeError:
            print("  [WARN] schedule.json 解析失败，回落到 config.json 的内嵌排期")
    items = (cfg.get("activity_schedule") or {}).get("items") or []
    return items, {"source": "config", "generated_at": None, "lock_rule": None}


def load_suggest():
    """配置建议（区块04）：读引擎产出的 suggestions.json，缺失时给空壳。"""
    empty = {"items": [], "skipped": [], "diag": {}, "rule_book": {}, "generated_at": None}
    if not SUGGEST_PATH.exists():
        return empty
    try:
        data = json.loads(SUGGEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("  [WARN] suggestions.json 解析失败，区块04 将显示为空")
        return empty
    return data


def _sql_insert_line(table):
    """从 config_tables.sql 取某张配置表的 INSERT 行（发布后的真实语句）。"""
    if not CONFIG_SQL_PATH.exists():
        return None
    try:
        text = CONFIG_SQL_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(
        r"INSERT OR REPLACE INTO " + re.escape(table) + r" \([^)]*\)\s*VALUES \([^;]*\);",
        text,
    )
    return re.sub(r"\s+", " ", m.group(0)) if m else None


def load_demo(conn, suggest):
    """静态演示素材（区块04）。

    单文件版没有本地服务，四步写盘操作没法真跑；这里取**最近一次真实发布**的
    流水作为回放素材——变更前后的值、规则编号、生成的 SQL 语句、提交命令，
    全部来自磁盘上真实存在的产物，不是编的示例数据。
    """
    demo = {
        "batch": None, "published_at": None, "changes": [], "activities": 0,
        "files": [], "git_lines": [], "sql_lines": [], "pending": 0, "locked": 0,
    }

    # --- 27 个活动的 Excel 清单（文件命名规则与 config_io 一致） ---
    try:
        rows = conn.execute(
            """
            SELECT m.activity_id, m.name, m.type, m.config_table,
                   (SELECT COUNT(*) FROM activity_schedule s
                     WHERE s.activity_id = m.activity_id AND s.frozen = 1) AS frz
              FROM activity_master m
             ORDER BY m.activity_id
            """
        ).fetchall()
    except sqlite3.Error:
        rows = []
    for aid, name, typ, table, frz in rows:
        demo["files"].append({
            "activity_id": aid, "name": name, "type": typ,
            "file": aid + ".xlsx", "table": table, "locked": bool(frz),
        })
    demo["locked"] = sum(1 for f in demo["files"] if f["locked"])

    # --- 待执行建议（当前缺口下引擎给出的条数） ---
    demo["pending"] = len(suggest.get("items") or [])

    # --- 最近一次真实发布 ---
    batch = None
    if PUBLOG_PATH.exists():
        try:
            log = json.loads(PUBLOG_PATH.read_text(encoding="utf-8"))
            bs = log.get("batches") or []
            if bs:
                batch = bs[-1]
        except json.JSONDecodeError:
            print("  [WARN] _发布记录.json 解析失败，演示素材改用变更流水表")

    changes, batch_id, published_at = [], None, None
    if batch:
        batch_id = batch.get("batch")
        published_at = batch.get("published_at")
        changes = batch.get("changes") or []
    else:
        try:
            cur = conn.execute(
                "SELECT l.batch, l.changed_at, l.activity_id, m.name, l.field, "
                "       l.old_value, l.new_value, l.source, l.rule_code "
                "  FROM config_change_log l "
                "  LEFT JOIN activity_master m ON m.activity_id = l.activity_id "
                " ORDER BY l.id"
            )
            for b, ts, aid, name, field, old, new, src, rule in cur.fetchall():
                if batch_id is None:
                    batch_id, published_at = b, ts
                if b != batch_id:
                    continue
                changes.append({"activity_id": aid, "name": name, "field": field,
                                "old": old, "new": new, "source": src, "rule_code": rule})
        except sqlite3.Error:
            pass

    acts = sorted({c.get("activity_id") for c in changes if c.get("activity_id")})
    demo["batch"] = batch_id
    demo["published_at"] = published_at
    demo["activities"] = len(acts)
    demo["changes"] = [{
        "activity_id": c.get("activity_id"),
        "name": c.get("name"),
        "field": c.get("field"),
        "label": CFG_LABEL.get(c.get("field"), c.get("field")),
        "old": c.get("old"),
        "new": c.get("new"),
        "source": c.get("source") or "suggestion",
        "rule_code": c.get("rule_code") or "",
    } for c in changes]

    # --- 这批变更落在 config_tables.sql 里的真实语句 ---
    for aid in acts:
        table = "cfg_" + aid.lower().replace("-", "_")
        line = _sql_insert_line(table)
        if line:
            demo["sql_lines"].append({"activity_id": aid, "table": table, "line": line})

    # --- 提交命令（格式与 config_io.git_commands 完全一致） ---
    day = (published_at or dt.date.today().isoformat())[:10]
    if changes:
        msg = "config: %s 更新 %d 个活动配置（%d 处字段）" % (day, len(acts), len(changes))
    else:
        msg = "config: %s 同步活动配置" % day
    demo["git_lines"] = [
        'cd /d "%s"' % ROOT,
        "git add -A",
        'git commit -m "%s"' % msg,
        "git log --oneline -1",
    ]
    return demo


def load_kb():
    """客服知识库（区块05）：读模块⑤切好的知识块，缺失时给空壳。"""
    empty = {"chunks": [], "stats": {}, "categories": [], "source": None}
    if not KB_PATH.exists():
        print("  [WARN] 05_cs_rag/kb.json 不存在，区块05 客服对话无知识可检索")
        print("         先运行 python 05_cs_rag/build_kb.py")
        return empty
    try:
        return json.loads(KB_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("  [WARN] kb.json 解析失败，区块05 将显示为空")
        return empty


def load_sentiment():
    """舆情语料（区块06）：模块⑥ 生成器产出的模拟论坛帖与群消息。"""
    empty = {"meta": {"is_virtual": True}, "strip": {}, "buckets": [],
             "topics": [], "alerts": [], "events": [], "posts": []}
    if not SENT_PATH.exists():
        print("  [WARN] 06_sentiment/sentiment.json 不存在，区块06 无数据")
        print("         先运行 python 06_sentiment/gen_sentiment.py")
        return empty
    try:
        return json.loads(SENT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("  [WARN] sentiment.json 解析失败，区块06 将显示为空")
        return empty


def month_summary(daily, today, kpi_cfg):
    """算当前月的 KPI 进度，用于打印核算摘要（页面里有一套等价逻辑）。"""
    month = today[:7]
    year, mon = int(month[:4]), int(month[5:7])
    days_in_month = calendar.monthrange(year, mon)[1]
    days_elapsed = int(today[8:10])

    kpi_map = kpi_cfg.get("monthly_revenue_by_month") or {}
    target = kpi_map.get(month) or kpi_cfg.get("monthly_revenue_target")

    rows = [r for r in daily if r["date"][:7] == month and r["date"] <= today]
    cum = sum(r["revenue"] for r in rows)

    info = {
        "month": month,
        "target": target,
        "days_in_month": days_in_month,
        "days_elapsed": days_elapsed,
        "days_left": days_in_month - days_elapsed,
        "days_with_data": len(rows),
        "cum_revenue": cum,
    }
    if target:
        info["progress_time"] = days_elapsed / days_in_month
        info["progress_kpi"] = cum / target
        info["diff_pp"] = (info["progress_time"] - info["progress_kpi"]) * 100
        info["gap_pace"] = target * info["progress_time"] - cum
        info["gap_total"] = target - cum
        if info["days_left"] > 0:
            info["need_daily"] = info["gap_total"] / info["days_left"]
        if info["days_with_data"] > 0:
            info["cur_daily"] = cum / info["days_with_data"]
    return info


def format_summary(info, today):
    lines = []
    push = lines.append
    push(f"  今天        {today}")
    push(f"  当前月      {info['month']}（{info['days_in_month']} 天，已过 {info['days_elapsed']} 天，"
         f"其中 {info['days_with_data']} 天有数据）")
    if not info.get("target"):
        push("  [提示] 该月未配置 KPI 目标，看板将隐藏缺口部分。")
        return lines
    p = lambda v: f"{v * 100:.2f}%"          # noqa: E731
    push(f"  当月目标    ¥{info['target']:,.0f}")
    push(f"  已累计      ¥{info['cum_revenue']:,.2f}")
    push(f"  时间进度    {p(info['progress_time'])}  （{info['days_elapsed']}/{info['days_in_month']}）")
    push(f"  KPI 完成度  {p(info['progress_kpi'])}")
    push(f"  两者差值    {info['diff_pp']:+.2f} 个百分点"
         f"（{'进度落后' if info['diff_pp'] > 0 else '进度领先'}）")
    push(f"  KPI 缺口    ¥{info['gap_pace']:,.2f}   ← 对齐时间进度应完成而未完成的部分")
    push(f"  距月目标还差 ¥{info['gap_total']:,.2f}")
    if info.get("need_daily"):
        push(f"  剩余 {info['days_left']} 天需日均 ¥{info['need_daily']:,.0f}"
             f"（当前日均 ¥{info.get('cur_daily', 0):,.0f}）")
    return lines


def main():
    args = parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[ERROR] 数据库不存在：{db}")
        print("        先运行 start.bat 生成数据，再构建看板数据。")
        return 1

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    kpi_cfg = cfg.get("kpi") or {}

    conn = sqlite3.connect(db)
    daily = load_daily(conn)
    tiers = load_tiers(conn)
    suggest = load_suggest()
    demo = load_demo(conn, suggest)          # 静态版回放素材（取最近一次真实发布）
    if not daily:
        print("[ERROR] daily_metrics 没有数据，先运行生成器。")
        return 1

    data_start, data_end = daily[0]["date"], daily[-1]["date"]

    # 「今天」：默认取系统日期，并钳制在数据覆盖范围内
    today = args.today or dt.date.today().isoformat()
    if today < data_start:
        today = data_start
    if today > data_end:
        today = data_end

    recent = load_recent(conn, daily, today)  # 近 7 日明细（区块01b），依赖 today
    conn.close()

    info = month_summary(daily, today, kpi_cfg)

    print("看板数据构建")
    print(f"  数据库      {db}")
    print(f"  数据区间    {data_start} ~ {data_end}（{len(daily)} 天）")
    print()
    print("核算摘要")
    for line in format_summary(info, today):
        print(line)

    if args.check:
        print()
        print("（--check 模式，未写入文件）")
        return 0

    schedule, schedule_meta = load_schedule(cfg)
    kb = load_kb()
    sentiment = load_sentiment()

    payload = {
        "meta": {
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_start": data_start,
            "data_end": data_end,
            "today": today,
        },
        "kpi": {
            "monthly_revenue_by_month": kpi_cfg.get("monthly_revenue_by_month") or {},
            "monthly_revenue_default": kpi_cfg.get("monthly_revenue_target"),
        },
        "tier_target": (kpi_cfg.get("tier_structure_target") or {}).get("tiers") or [],
        "tier_swing_pp": (kpi_cfg.get("tier_structure_target") or {}).get("swing_pp") or 5,
        "schedule": schedule,
        "schedule_meta": schedule_meta,
        "suggest": suggest,
        "demo": demo,
        "kb": kb,
        "sentiment": sentiment,
        "tiers": tiers,
        "daily": daily,
        "daily_recent": recent,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # 紧凑输出：785 条舆情语料用 indent=2 会多出 200KB，单文件交付吃不消
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    out.write_text(
        "// 本文件由 02_dashboard/build_data.py 自动生成，请勿手动修改。\n"
        "// 数据源：data/game.db + 01_datagen/config.json\n"
        f"// 生成时间：{payload['meta']['generated_at']}\n"
        "window.DASHBOARD_DATA = " + body + ";\n",
        encoding="utf-8",
    )

    size_kb = out.stat().st_size / 1024
    print()
    print(f"  [OUT ] {out.name}  {size_kb:.1f} KB  （{len(daily)} 天日数据 + KPI 目标）")
    print()
    print("完成。直接双击 02_dashboard/index.html 查看看板。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
