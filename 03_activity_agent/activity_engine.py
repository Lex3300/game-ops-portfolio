#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模块③ 活动 Agent · 排期引擎

它解决什么
----------
把「诊断 → 归因 → 选牌 → 排期」这套动作从人工判断变成可复现的代码：
读活动库 + 当期诊断，按活动运营的硬规则算出应排活动，再与排期台账比对，
只对「未上线」的排期做增改，已定档（已上线）的一律不动。

三条铁律（写死在代码里，不靠自觉）
----------------------------------
1. 已定档不动：start_date <= 今天 的排期自动 frozen=1，之后任何一次运行都不会改它
2. 不编数据：诊断数字全部来自 data/game.db；无法量化的一律留空，不拍脑袋
3. 规则可解释：每条排期都带 rule_code + rule_note，能回答「为什么排这个」

数据流
------
    data/game.db（诊断）  ┐
    config.json（KPI目标）├→ activity_engine.py ─→ 01_datagen/schedule.json（台账）
    arsenal_seed.json（库）┘                    ├→ game.db 的 activity_* 表
                                                └→ 03_activity_agent/排期说明.md

用法
----
    python activity_engine.py all              建表+灌库+排期+说明（推荐，dashboard.bat 调这个）
    python activity_engine.py init             只建表灌库
    python activity_engine.py plan             只排期
    python activity_engine.py report           只重生成说明文档
    python activity_engine.py all --check      只打印诊断与计划，不写任何文件
    python activity_engine.py all --today 2026-10-17   指定「今天」，便于复现
"""

import argparse
import calendar
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
DB_PATH = ROOT / "data" / "game.db"
CFG_PATH = ROOT / "01_datagen" / "config.json"
LEDGER_PATH = ROOT / "01_datagen" / "schedule.json"
SCHEMA_PATH = BASE / "schema_activity.sql"
SEED_PATH = BASE / "arsenal_seed.json"
NOTE_PATH = BASE / "排期说明.md"
ARSENAL_DOC_PATH = BASE / "活动库总表.md"

# 预期拉回的测算假设（写在这里，说明书里同步引用，避免口径漂移）
ASSUMED_L5_RATE = 0.65      # 冲刺活动目标把 L5 客单达成率提到 65%
ASSUMED_STRUCT_SHARE = 10.0  # 结构缺口占日均缺口 >= 10% 视为「付费活动相关」主导


def setup_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    text = p.read_text(encoding="utf-8")
    # 容忍以 // 开头的注释行（早期台账格式），保证旧文件也能读
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("//")]
    return json.loads("\n".join(lines))


def s2d(s):
    return dt.date.fromisoformat(s)


def month_bounds(month):
    y, m = (int(x) for x in month.split("-"))
    return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])


# ------------------------------------------------------------
# 1. 活动库：建表 + 灌种子（幂等 upsert；一活动一张配置表）
# ------------------------------------------------------------
# 27 张配置表的列按「活动类型」给：同类型字段一致，横向对比时对得上；
# 该活动用不到的列留 NULL，不填无意义的默认值。
CONFIG_TEMPLATES = {
    "礼包": [
        ("price_tiers", "TEXT", "价格/档位，多档用 / 分隔，如 6/30/98"),
        ("reward_desc", "TEXT", "奖励内容说明"),
        ("limit_per_user", "INTEGER", "每人限购/限领次数"),
        ("stock", "INTEGER", "库存/限量份数；NULL = 不限量"),
        ("cycle", "TEXT", "刷新周期：日/周/月/赛季/一次性"),
        ("trigger_cond", "TEXT", "触发条件；NULL = 无门槛"),
    ],
    "权益": [
        ("price_tiers", "TEXT", "购买价/档位，如 30/128"),
        ("reward_desc", "TEXT", "权益内容（每日领取 / 免费轨+付费轨 / 等级返还）"),
        ("limit_per_user", "INTEGER", "每人可购份数"),
        ("cycle", "TEXT", "生效与刷新周期：日/月/赛季"),
    ],
    "抽奖": [
        ("price_tiers", "TEXT", "单抽/十连价，如 6/68"),
        ("reward_desc", "TEXT", "奖池与大奖说明"),
        ("pity_times", "INTEGER", "保底次数：累计 N 次必得大奖"),
        ("stock", "INTEGER", "奖池限量份数；NULL = 不限量"),
        ("cycle", "TEXT", "刷新周期：日/一次性"),
    ],
    "任务": [
        ("price_tiers", "TEXT", "累计充值档位（累充任务用），如 6/30/128"),
        ("reward_desc", "TEXT", "任务奖励说明"),
        ("limit_per_user", "INTEGER", "可领取档数/次数"),
        ("cycle", "TEXT", "重置周期：日/周/一次性"),
    ],
    "排行榜": [
        ("rank_metric", "TEXT", "排行依据指标，如 战力排名 / 累计充值额"),
        ("reward_desc", "TEXT", "名次奖励与非头部参与奖"),
        ("cycle", "TEXT", "赛季/一次性"),
    ],
    "特殊": [
        ("reward_desc", "TEXT", "活动产出说明"),
        ("multiplier", "REAL", "产出倍率（限时收益 UP / 双倍掉落用）"),
        ("trigger_cond", "TEXT", "触发/参与条件"),
        ("cycle", "TEXT", "刷新周期：周/一次性"),
    ],
    "商城": [
        ("price_tiers", "TEXT", "定价方式，如 按道具定价 / 积分价"),
        ("reward_desc", "TEXT", "售卖/兑换内容"),
        ("cycle", "TEXT", "刷新周期：常驻/周"),
    ],
}

# 未登记类型时的兜底列：新类型先能落库，再回来补模板
CONFIG_FALLBACK = [
    ("price_tiers", "TEXT", "价格/档位"),
    ("reward_desc", "TEXT", "奖励/内容说明"),
    ("limit_per_user", "INTEGER", "每人限购/限领次数"),
    ("stock", "INTEGER", "库存/限量份数"),
    ("cycle", "TEXT", "刷新周期"),
    ("trigger_cond", "TEXT", "触发条件"),
    ("pity_times", "INTEGER", "保底次数"),
    ("multiplier", "REAL", "产出倍率"),
    ("rank_metric", "TEXT", "排行依据指标"),
]

CONFIG_SQL_PATH = BASE / "config_tables.sql"


def config_table(activity):
    """活动专属配置表名：cfg_ + activity_id 小写，'-' 换 '_'。"""
    return "cfg_" + activity["activity_id"].lower().replace("-", "_")


def config_columns(activity):
    """该活动的配置列：按类型取模板，未登记类型走兜底。"""
    return CONFIG_TEMPLATES.get(activity["type"]) or CONFIG_FALLBACK


def config_ddl(activity):
    """生成单张配置表的建表语句（也写进 config_tables.sql 供查阅）。"""
    tbl = config_table(activity)
    aid = activity["activity_id"]
    cols = config_columns(activity)
    width = max(len(n) for n in ["activity_id"] + [c[0] for c in cols] + ["updated_at"])
    pad = " " * (4 + width + 1)

    body = []
    body.append("    %s TEXT PRIMARY KEY" % "activity_id".ljust(width))
    body.append("%sDEFAULT '%s'" % (pad, aid))
    body.append("%sREFERENCES activity_master(activity_id) ON DELETE CASCADE," % pad)
    for name, typ, note in cols:
        head = "%s %s," % ("    " + name.ljust(width), typ)
        body.append(head.ljust(width + 15) + "-- " + note)
    body.append(("    " + "updated_at".ljust(width) + " TEXT").ljust(width + 15)
                + "-- 最近一次由引擎写入的时间")

    lines = [
        "-- " + "-" * 66,
        "-- %s · %s" % (aid, activity["name"]),
        "--   %s / %s；本表只放这一个活动的配置，改它不影响其他活动"
        % (activity["type"], activity["target"]),
        "-- " + "-" * 66,
        "CREATE TABLE IF NOT EXISTS %s (" % tbl,
    ]
    return "\n".join(lines + body + [");"])


def ensure_config_columns(conn, tbl, cols):
    """配置项新增字段时，表结构跟着长出来（老库平滑升级）。"""
    have = [r[1] for r in conn.execute("PRAGMA table_info(%s)" % tbl)]
    for name, typ, _note in cols:
        if name not in have:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (tbl, name, typ))
    if "updated_at" not in have:
        conn.execute("ALTER TABLE %s ADD COLUMN updated_at TEXT" % tbl)


def upsert_config_row(conn, tbl, activity, now):
    """把种子里的 config 写进该活动自己的表（表内只有一行）。"""
    aid = activity["activity_id"]
    cfg = activity.get("config") or {}
    fields = [(n, cfg[n]) for n, _t, _n in config_columns(activity) if n in cfg]
    if not fields:
        conn.execute(
            "INSERT OR IGNORE INTO %s (activity_id, updated_at) VALUES (?,?)" % tbl,
            (aid, now),
        )
        return
    names = [f[0] for f in fields]
    sql = (
        "INSERT INTO %s (activity_id, %s, updated_at) VALUES (%s) "
        "ON CONFLICT(activity_id) DO UPDATE SET %s, updated_at=excluded.updated_at"
        % (
            tbl,
            ", ".join(names),
            ", ".join(["?"] * (len(names) + 2)),
            ", ".join("%s=excluded.%s" % (n, n) for n in names),
        )
    )
    conn.execute(sql, [aid] + [f[1] for f in fields] + [now])


def sql_literal(v):
    """把 Python 值写成 SQL 字面量（NULL / 数字 / 转义过的字符串）。"""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def config_insert(activity, stamp="—"):
    """该活动配置的落地语句：一行 INSERT OR REPLACE，可直接执行。"""
    tbl = config_table(activity)
    cfg = activity.get("config") or {}
    fields = [(n, cfg[n]) for n, _t, _n in config_columns(activity) if n in cfg]
    names = ["activity_id"] + [f[0] for f in fields]
    vals = [sql_literal(activity["activity_id"])] + [sql_literal(f[1]) for f in fields]
    if stamp:
        names.append("updated_at")
        vals.append(sql_literal(stamp))
    return "INSERT OR REPLACE INTO %s (%s)\n  VALUES (%s);" % (
        tbl, ", ".join(names), ", ".join(vals))


def write_config_sql(acts, blocks, seed, stamp="—", header_extra=None):
    """把 27 张表的「建表语句 + 当前配置值」落成一个可读文件（配置即代码）。"""
    head = [
        "-- " + "=" * 62,
        "-- 模块③ 活动 Agent · 27 张活动配置表（引擎自动生成）",
        "-- " + "=" * 62,
        "-- 一个活动一张表：cfg_ + activity_id 小写、'-' 换 '_'",
        "--   ACT-GIFT-001 → cfg_act_gift_001",
        "--",
        "-- 本文件 = 表结构 + 当前生效配置值（配置即代码，可直接 diff / 回滚）。",
        "--   表结构 ← activity_engine.py 的 CONFIG_TEMPLATES",
        "--   配置值 ← arsenal_seed.json（由看板区块04「一键发布」从 Excel 回写）",
        "-- 查某个活动的配置 → 看它那一段的 INSERT 语句，或打开库里对应的表。",
        "--",
        "-- 活动数：%d　种子版本：%s　配置时间：%s"
        % (len(acts), seed.get("version", "—"), stamp),
    ]
    if header_extra:
        head += ["-- " + ln for ln in header_extra]
    head.append("-- " + "=" * 62)

    parts = []
    for act, ddl in zip(acts, blocks):
        parts.append(ddl + "\n" + config_insert(act, stamp))
    CONFIG_SQL_PATH.write_text(
        "\n".join(head) + "\n\n" + "\n\n".join(parts) + "\n", encoding="utf-8"
    )


def init_library(conn):
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    # 老库兼容：早期版本的 activity_schedule 没有 instance_name 列
    cols = [r[1] for r in conn.execute("PRAGMA table_info(activity_schedule)")]
    if "instance_name" not in cols:
        conn.execute("ALTER TABLE activity_schedule ADD COLUMN instance_name TEXT")
    mcols = [r[1] for r in conn.execute("PRAGMA table_info(activity_master)")]
    if "config_table" not in mcols:
        conn.execute("ALTER TABLE activity_master ADD COLUMN config_table TEXT")

    seed = load_json(SEED_PATH)
    acts = seed["activities"]
    ddl_blocks = [config_ddl(a) for a in acts]
    # 先按类型把 27 张配置表建出来（幂等），再逐表灌数据
    conn.executescript("\n\n".join(ddl_blocks))

    now = dt.datetime.now().isoformat(timespec="seconds")
    lib, alias = {}, {}
    added = updated = 0
    for a in acts:
        lib[a["activity_id"]] = a
        alias[a["name"].strip()] = a["activity_id"]
        for al in a.get("aliases") or []:
            alias[al.strip()] = a["activity_id"]

        tbl = config_table(a)
        exists = conn.execute(
            "SELECT 1 FROM activity_master WHERE activity_id=?", (a["activity_id"],)
        ).fetchone()
        added += 0 if exists else 1
        updated += 1 if exists else 0

        conn.execute(
            """
            INSERT INTO activity_master
                (activity_id, name, type, target, duration_days, cadence,
                 difficulty, risk, purpose, lever, config_table, enabled, note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(activity_id) DO UPDATE SET
                name=excluded.name, type=excluded.type, target=excluded.target,
                duration_days=excluded.duration_days, cadence=excluded.cadence,
                difficulty=excluded.difficulty, risk=excluded.risk,
                purpose=excluded.purpose, lever=excluded.lever,
                config_table=excluded.config_table,
                enabled=excluded.enabled, note=excluded.note
            """,
            (a["activity_id"], a["name"], a["type"], a["target"],
             a.get("duration_days"), a.get("cadence"), a.get("difficulty"),
             a.get("risk", "low"), a.get("purpose"), a.get("lever"),
             tbl, a.get("enabled", 1), a.get("note")),
        )
        ensure_config_columns(conn, tbl, config_columns(a))
        upsert_config_row(conn, tbl, a, now)
    conn.commit()
    write_config_sql(acts, ddl_blocks, seed, now)
    return lib, alias, added, updated


# ------------------------------------------------------------
# 2. 诊断：与看板区块01/02 完全同口径（同一套公式，Python 侧复刻）
# ------------------------------------------------------------
def diagnose(conn, cfg, today):
    month = today.strftime("%Y-%m")
    month_start, month_end = month_bounds(month)
    days_in_month = month_end.day
    days_elapsed = today.day
    days_left = days_in_month - days_elapsed

    kpi = cfg.get("kpi") or {}
    target = (kpi.get("monthly_revenue_by_month") or {}).get(month) or kpi.get("monthly_revenue_target")

    rows = conn.execute(
        "SELECT date, revenue FROM daily_metrics WHERE substr(date,1,7)=? AND date<=? ORDER BY date",
        (month, today.isoformat()),
    ).fetchall()
    cum = sum(r[1] for r in rows) if rows else 0.0
    gap_total = (target - cum) if target else None
    need_daily = (gap_total / days_left) if (gap_total is not None and days_left > 0) else None

    y = conn.execute(
        "SELECT date, revenue, dau, new_users, stock_active, pay_users "
        "FROM daily_metrics WHERE date<? ORDER BY date DESC LIMIT 1",
        (today.isoformat(),),
    ).fetchone()

    tiers_y, tt = [], (kpi.get("tier_structure_target") or {}).get("tiers") or []
    if y:
        tiers_y = conn.execute(
            "SELECT tier_code, users, revenue FROM revenue_tiers WHERE date=? ORDER BY sort_order",
            (y[0],),
        ).fetchall()

    blended_tar = sum(t["user_share"] * t["arppu"] for t in tt)
    payers = sum(t[1] for t in tiers_y)
    y_rev = sum(t[2] for t in tiers_y)
    blended_act = (y_rev / payers) if payers else 0.0
    struct_gap = payers * (blended_tar - blended_act)

    base_rows = conn.execute(
        "SELECT dau, pay_users FROM daily_metrics WHERE date<? ORDER BY date DESC LIMIT 2",
        (y[0] if y else today.isoformat(),),
    ).fetchall()
    base_heads = 0.0
    if base_rows:
        base_pr = sum(r[1] / r[0] for r in base_rows) / len(base_rows)
        base_dau = sum(r[0] for r in base_rows) / len(base_rows)
        base_heads = base_dau * base_pr
    volume_gap = max(0.0, base_heads - payers) * blended_tar

    gap_daily = (need_daily - y_rev) if need_daily else 0.0
    rest_gap = max(0.0, gap_daily - struct_gap - volume_gap)

    def seg(v):
        return (v / gap_daily * 100) if gap_daily > 0 else 0.0

    # L5 客单达成率（判断大 R 付费深度的核心指标）
    l5_users, l5_act, l5_tar, l5_rate = 0, 0.0, 0.0, 0.0
    tier_users = {r[0]: r[1] for r in tiers_y}
    tier_rev = {r[0]: r[2] for r in tiers_y}
    for t in tt:
        if t["code"] == "L5":
            l5_tar = t["arppu"]
            l5_users = tier_users.get("L5", 0)
            l5_act = tier_rev.get("L5", 0.0)
            l5_rate = ((l5_act / l5_users) / l5_tar) if (l5_users and l5_tar) else 0.0

    return {
        "today": today.isoformat(),
        "month": month,
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "days_in_month": days_in_month,
        "days_elapsed": days_elapsed,
        "days_left": days_left,
        "target": target,
        "cum": cum,
        "progress_kpi": (cum / target) if target else None,
        "progress_time": days_elapsed / days_in_month,
        "gap_total": gap_total,
        "need_daily": need_daily,
        "yesterday": y[0] if y else None,
        "y_rev": y_rev,
        "payers": payers,
        "blended_act": blended_act,
        "blended_tar": blended_tar,
        "gap_daily": gap_daily,
        "struct_gap": struct_gap,
        "volume_gap": volume_gap,
        "rest_gap": rest_gap,
        "seg_struct": seg(struct_gap),
        "seg_volume": seg(volume_gap),
        "seg_rest": seg(rest_gap),
        "l5_users": l5_users,
        "l5_arppu": l5_act / l5_users if l5_users else 0.0,
        "l5_target": l5_tar,
        "l5_rate": l5_rate,
    }


# ------------------------------------------------------------
# 3. 台账：首次从 config.activity_schedule 迁移，之后以 schedule.json 为准
# ------------------------------------------------------------
def load_ledger():
    return load_json(LEDGER_PATH)


def migrate_ledger(cfg, alias, today, lib):
    """首次运行：把 config.json 里既有的排期导入台账，视为开服定档。

    导入时按活动属性回填「这条排期本该由哪条规则产生」，让说明文档有依据可讲；
    导入之后这些排期即 frozen，规则码不再变动。
    """
    src = (cfg.get("activity_schedule") or {}).get("items") or []
    month = today.strftime("%Y-%m")

    def rule_for(aid):
        a = lib.get(aid) or {}
        if a.get("cadence") in ("常驻", "月度", "赛季", "周度"):
            return "R-BASE-01", "常驻基线：全月常驻，撑住留存与付费基本盘"
        return {
            "ACT-SPEC-002": ("R-WEEKEND-01", "周末档：周六日双倍掉落，拉周末活跃"),
            "ACT-DRAW-001": ("R-STRUCT-01", "结构缺口主导 → 定向抽奖补大R付费深度"),
            "ACT-TASK-002": ("R-CATCH-01", "承接：冲刺结束后接累充，避免流水断崖"),
            "ACT-GIFT-006": ("R-LIMIT-01", "L5 客单不足目标 → 终身限量礼包补付费跃迁"),
            "ACT-RANK-001": ("R-OPEN-01", "开服冲榜：新服首周荣誉榜，拉首周活跃"),
        }.get(aid, ("R-MIGRATE", "人工定档（自 config.json 迁移）"))

    items, unknown = [], []
    for i, it in enumerate(src, start=1):
        aid = alias.get(it["name"].strip())
        if not aid:
            unknown.append(it["name"])
            continue
        code, note = rule_for(aid)
        src_note = it.get("note")
        items.append({
            "schedule_id": "SCH-%s-%03d" % (month.replace("-", ""), i),
            "activity_id": aid,
            "name": it["name"],
            "type": it["type"],
            "target": it["target"],
            "risk": it.get("risk", "low"),
            "month": it["start"][:7],
            "start": it["start"],
            "end": it["end"],
            "rule_code": code,
            "rule_note": note + ("；" + src_note if src_note else ""),
            "frozen": 0,
            "frozen_at": None,
            "created_at": it["start"],
            "updated_at": today.isoformat(),
        })
    if unknown:
        print("  [提示] 以下活动名在活动库里找不到，已跳过：" + "、".join(unknown))
    return {"month": month, "items": items}


# ------------------------------------------------------------
# 4. 排期规则：诊断 → 应排活动
# ------------------------------------------------------------
def build_plan(lib, diag, today, ledger_items):
    tomorrow = today + dt.timedelta(days=1)
    month_end = s2d(diag["month_end"])
    month_start = s2d(diag["month_start"])
    horizon_start = max(month_start, s2d(ledger_items[0]["start"]) if ledger_items else month_start)
    if horizon_start > month_end:
        horizon_start = month_start

    plan = []

    def add(aid, start, end, code, note, allow_update=False):
        if start > end or start > month_end:
            return None
        a = lib[aid]
        plan.append({
            "activity_id": aid, "name": a["name"], "type": a["type"],
            "target": a["target"], "risk": a.get("risk", "low"),
            "start": start.isoformat(), "end": end.isoformat(),
            "rule_code": code, "rule_note": note, "allow_update": allow_update,
        })
        return plan[-1]

    # R-BASE-01 常驻基线：撑留存与付费面
    #   只从「今天 / 数据起点中较晚者」起排——引擎不补造历史，历史期由人工定档
    #   商城类不占活动坑位（常驻商品售卖、积分兑换属于常驻配置，不是活动）
    base_start = max(today, horizon_start)
    for a in lib.values():
        if a.get("cadence") == "常驻" and a.get("enabled", 1) and a.get("type") != "商城":
            add(a["activity_id"], base_start, month_end, "R-BASE-01",
                "常驻基线：自今日起常驻，撑住留存与付费基本盘")

    # R-WEEKEND-01 周末双倍：未来每个周末各一期（历史的由冻结机制保护，不会重排）
    d = max(tomorrow, month_start)
    while d <= month_end:
        if d.weekday() == 5:                       # 周六
            end = min(d + dt.timedelta(days=1), month_end)
            add("ACT-SPEC-002", d, end, "R-WEEKEND-01",
                "周末档：周六日双倍掉落，拉周末活跃（风险极低）")
            d += dt.timedelta(days=7)
        else:
            d += dt.timedelta(days=1)

    # R-STRUCT-01 结构缺口主导 → 大 R 深度活动；R-CATCH-01 承接
    draw_items = [it for it in ledger_items if it["activity_id"] == "ACT-DRAW-001"]
    if draw_items:
        draw_start = s2d(min(it["start"] for it in draw_items))
        draw_end = s2d(max(it["end"] for it in draw_items))
        add("ACT-DRAW-001", draw_start, draw_end, "R-STRUCT-01",
            "结构缺口占日均缺口 %.1f%%（≥%.0f%%）→ 排定向抽奖补大R付费深度"
            % (diag["seg_struct"], ASSUMED_STRUCT_SHARE))
        catch_start = draw_end + dt.timedelta(days=1)
        add("ACT-TASK-002", catch_start, month_end, "R-CATCH-01",
            "承接：定向抽奖结束后次日接累充冲刺，避免活动后流水断崖", allow_update=True)
    elif diag["seg_struct"] >= ASSUMED_STRUCT_SHARE and diag["days_left"] >= 6:
        p = add("ACT-DRAW-001", tomorrow, tomorrow + dt.timedelta(days=6), "R-STRUCT-01",
                "结构缺口占日均缺口 %.1f%%（≥%.0f%%）→ 排 7 天定向抽奖补大R付费深度"
                % (diag["seg_struct"], ASSUMED_STRUCT_SHARE))
        if p:
            add("ACT-TASK-002", s2d(p["end"]) + dt.timedelta(days=1), month_end, "R-CATCH-01",
                "承接：定向抽奖结束后次日接累充冲刺，避免活动后流水断崖", allow_update=True)

    # R-LIMIT-01 大 R 客单不足 → 终身限量礼包补付费跃迁（已有实例则沿用，不churn）
    limit_items = [it for it in ledger_items if it["activity_id"] == "ACT-GIFT-006"]
    if limit_items:
        for it in limit_items:
            add("ACT-GIFT-006", s2d(it["start"]), s2d(it["end"]), "R-LIMIT-01",
                "L5 客单达成 %.1f%% < 90%% → 终身限量礼包补付费跃迁（限量 3000 份）"
                % (diag["l5_rate"] * 100))
    elif diag["l5_rate"] < 0.9 and diag["days_left"] >= 5:
        add("ACT-GIFT-006", tomorrow, month_end, "R-LIMIT-01",
            "L5 客单达成 %.1f%% < 90%% → 终身限量礼包补付费跃迁（限量 3000 份）"
            % (diag["l5_rate"] * 100))

    return plan


# ------------------------------------------------------------
# 5. 比对与落库：冻结 + 只增改未上线
# ------------------------------------------------------------
def overlaps(a1, a2, b1, b2):
    return not (a2 < b1 or b2 < a1)


def next_schedule_id(items, month):
    prefix = "SCH-%s-" % month.replace("-", "")
    nums = [int(it["schedule_id"].split("-")[-1]) for it in items
            if it["schedule_id"].startswith(prefix)]
    return "%s%03d" % (prefix, (max(nums) + 1) if nums else 1)


def apply_plan(ledger_items, plan, today):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_s = today.isoformat()
    stats = {"add": 0, "update": 0, "keep": 0, "newly_frozen": 0}
    changes = []

    # 第一步：冻结（start <= 今天 即视为已上线，永久锁定）
    for it in ledger_items:
        if not it["frozen"] and it["start"] <= today_s:
            it["frozen"] = 1
            it["frozen_at"] = it["start"]
            stats["newly_frozen"] += 1

    # 第二步：按计划比对
    used = set()
    for p in plan:
        cand = [it for it in ledger_items
                if it["activity_id"] == p["activity_id"]
                and it["schedule_id"] not in used
                and overlaps(it["start"], it["end"], p["start"], p["end"])]
        if not cand:
            month = p["start"][:7]
            # 同一活动当月已有多期时，自动加「第 N 期」后缀，便于看图区分
            same = [it for it in ledger_items
                    if it["activity_id"] == p["activity_id"] and it["month"] == month]
            inst_name = p["name"] + ("·第 %d 期" % (len(same) + 1) if same else "")
            new = {
                "schedule_id": next_schedule_id(ledger_items, month),
                "activity_id": p["activity_id"], "name": inst_name,
                "type": p["type"], "target": p["target"], "risk": p["risk"],
                "month": month, "start": p["start"], "end": p["end"],
                "rule_code": p["rule_code"], "rule_note": p["rule_note"],
                "frozen": 0, "frozen_at": None,
                "created_at": now, "updated_at": now,
            }
            ledger_items.append(new)
            used.add(new["schedule_id"])
            stats["add"] += 1
            changes.append(("add", new["schedule_id"], new["name"],
                            "%s ~ %s" % (new["start"], new["end"])))
            continue

        it = cand[0]
        used.add(it["schedule_id"])
        if it["frozen"]:
            stats["keep"] += 1
            changes.append(("keep", it["schedule_id"], it["name"], "已定档，未改动"))
            continue

        changed = (it["start"] != p["start"] or it["end"] != p["end"])
        if p["allow_update"] and changed:
            detail = "%s ~ %s → %s ~ %s" % (it["start"], it["end"], p["start"], p["end"])
            it["start"], it["end"] = p["start"], p["end"]
            it["rule_code"], it["rule_note"] = p["rule_code"], p["rule_note"]
            it["updated_at"] = now
            stats["update"] += 1
            changes.append(("update", it["schedule_id"], it["name"], detail))
        else:
            stats["keep"] += 1
            changes.append(("keep", it["schedule_id"], it["name"], "未上线但无需调整"))

    for it in ledger_items:
        if it["schedule_id"] not in used:
            stats["keep"] += 1

    ledger_items.sort(key=lambda x: (x["start"], x["schedule_id"]))
    return stats, changes


def save_ledger(conn, ledger, stats, changes, today):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "_comment": "本文件由 03_activity_agent/activity_engine.py 生成，请勿手改。"
                    "已定档（frozen=1）的排期不会再被改动。",
        "month": today.strftime("%Y-%m"),
        "today": today.isoformat(),
        "generated_at": now,
        "lock_rule": "start_date <= today 的排期视为已上线，frozen=1，引擎只读不改",
        "stats": stats,
        "items": ledger["items"],
    }
    LEDGER_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    conn.execute("DELETE FROM activity_schedule")
    conn.executemany(
        "INSERT INTO activity_schedule (schedule_id, activity_id, instance_name, month, "
        "start_date, end_date, rule_code, rule_note, frozen, frozen_at, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(it["schedule_id"], it["activity_id"], it["name"], it["month"], it["start"], it["end"],
          it["rule_code"], it["rule_note"], it["frozen"], it["frozen_at"],
          it["created_at"], it["updated_at"]) for it in ledger["items"]],
    )
    conn.execute("DELETE FROM activity_change_log WHERE run_at LIKE ?", (now[:10] + "%",))
    conn.executemany(
        "INSERT INTO activity_change_log (run_at, action, schedule_id, activity_id, detail) "
        "VALUES (?,?,?,?,?)",
        [(now, a, sid, "", d) for (a, sid, _name, d) in changes],
    )
    conn.commit()
    return payload


# ------------------------------------------------------------
# 6. 排期说明文档
# ------------------------------------------------------------
def build_note(conn, diag, ledger, stats, changes):
    rows = conn.execute(
        "SELECT schedule_id, activity_id, name, type, target, risk, start_date, end_date, "
        "days, rule_code, rule_note, frozen, frozen_at FROM v_activity_schedule "
        "ORDER BY start_date, schedule_id"
    ).fetchall()
    lib_cnt = conn.execute("SELECT COUNT(*) FROM activity_master").fetchone()[0]
    cfg_tables = [r[0] for r in conn.execute(
        "SELECT config_table FROM activity_master WHERE config_table IS NOT NULL ORDER BY activity_id")]
    cfg_cnt = sum(conn.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in cfg_tables)

    L = []
    push = L.append
    push("# %s 年 %s 月 · 活动排期说明" % (diag["month"][:4], int(diag["month"][5:7])))
    push("")
    push("> 本文档由 `03_activity_agent/activity_engine.py` 自动生成，数据截至 **%s**。"
         % diag["today"])
    push("> 活动库共 **%d** 个活动，每个活动一张独立配置表（共 **%d** 张 / %d 行配置）；"
         "本期排期 **%d** 条。"
         % (lib_cnt, len(cfg_tables), cfg_cnt, len(rows)))
    push("")
    push("## 一、当期诊断（排期的依据）")
    push("")
    push("| 指标 | 数值 |")
    push("|---|---|")
    if diag["target"]:
        push("| 当月 KPI 目标 | ¥%s |" % "{:,.0f}".format(diag["target"]))
        push("| 累计收入（%d 天） | ¥%s |" % (diag["days_elapsed"], "{:,.2f}".format(diag["cum"])))
        push("| 时间进度 / KPI 完成度 | %.2f%% / %.2f%% |"
             % (diag["progress_time"] * 100, (diag["progress_kpi"] or 0) * 100))
        push("| 剩余天数需日均 | ¥%s |" % "{:,.0f}".format(diag["need_daily"] or 0))
    if diag["yesterday"]:
        push("| 昨日（%s）收入 | ¥%s |" % (diag["yesterday"], "{:,.2f}".format(diag["y_rev"])))
        push("| 昨日付费人数 / 综合客单 | %d 人 / ¥%.2f（目标 ¥%.2f） |"
             % (diag["payers"], diag["blended_act"], diag["blended_tar"]))
        push("| L5 客单达成率 | %.1f%%（昨日 ¥%s / 目标 ¥%s） |"
             % (diag["l5_rate"] * 100, "{:,.0f}".format(diag["l5_arppu"]),
                "{:,.0f}".format(diag["l5_target"])))
    if diag["gap_daily"]:
        push("| 日均缺口 | ¥%s |" % "{:,.0f}".format(diag["gap_daily"]))
        push("| ├ 结构缺口（付费活动相关） | ¥%s · %.1f%% |"
             % ("{:,.0f}".format(diag["struct_gap"]), diag["seg_struct"]))
        push("| ├ 流量/转化缺口（新增留存相关） | ¥%s · %.1f%% |"
             % ("{:,.0f}".format(diag["volume_gap"]), diag["seg_volume"]))
        push("| └ 稳态与目标的距离 | ¥%s · %.1f%% |"
             % ("{:,.0f}".format(diag["rest_gap"]), diag["seg_rest"]))
    push("")

    push("## 二、排期总表")
    push("")
    push("| 排期ID | 活动ID | 活动 | 类型 | 人群 | 起止 | 天数 | 状态 | 触发规则 |")
    push("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        status = "已定档（%s 上线）" % r[12] if r[11] else "待上线"
        push("| %s | %s | %s | %s | %s | %s ~ %s | %d | %s | %s |"
             % (r[0], r[1], r[2], r[3], r[4], r[6], r[7], r[8],
                status, r[9] or "—"))
    push("")

    push("## 三、逐条决策依据")
    push("")
    for r in rows:
        push("### %s · %s（%s / %s）" % (r[1], r[2], r[3], r[4]))
        push("")
        push("- 排期：%s ~ %s（%d 天），状态：%s"
             % (r[6], r[7], r[8], "已定档" if r[11] else "待上线"))
        push("- 触发规则：`%s` %s" % (r[9] or "—", r[10] or ""))
        lift = estimate_lift(r[1], diag)
        if lift:
            push("- 预期增量：%s" % lift)
        push("")

    push("## 四、本次变更")
    push("")
    push("| 动作 | 数量 |")
    push("|---|---|")
    push("| 新增 | %d |" % stats["add"])
    push("| 调整（仅未上线） | %d |" % stats["update"])
    push("| 保持不变 | %d |" % stats["keep"])
    push("| 本次新冻结（已上线） | %d |" % stats["newly_frozen"])
    push("")
    detail = [c for c in changes if c[0] in ("add", "update")]
    if detail:
        push("明细：")
        push("")
        for action, sid, name, d in detail:
            push("- **%s** %s %s：%s" % ("新增" if action == "add" else "调整", sid, name, d))
        push("")
    else:
        push("本次无新增或调整，全部排期保持原状。")
        push("")

    push("## 五、口径与假设")
    push("")
    push("1. **已定档不动**：`start_date <= 今天` 的排期自动锁定，引擎不会修改其日期、规则与备注；"
         "只有未上线的活动允许调整或删除重排，本引擎当前只做「新增」和「调整」，不删除。")
    push("2. **预期增量**的测算口径：仅对「大 R 向 + ARPPU 杠杆」的活动量化，"
         "公式为 `(目标客单达成率 %.0f%% − 当前达成率) × L5 目标客单 × L5 人数`，"
         "假设人数结构不变、其余档位不受影响，属于**静态测算**，不是承诺值。"
         % (ASSUMED_L5_RATE * 100))
    push("3. 其余活动（留存 / 活跃 / 回流 / 消耗杠杆）缺少可外推的对照基线，**不做数字估计**，"
         "宁缺勿编；需要评估时应做 A/B 或对照期。")
    push("4. 结构缺口占日均缺口 ≥ %.0f%% 时，判定「付费活动相关」为主导，"
         "才排大 R 冲刺活动；否则优先修留存与转化。" % ASSUMED_STRUCT_SHARE)
    push("")

    NOTE_PATH.write_text("\n".join(L), encoding="utf-8")
    return NOTE_PATH


def estimate_lift(activity_id, diag):
    """只对大R向 + ARPPU 杠杆的活动给静态测算，其余留空。"""
    if activity_id not in ("ACT-DRAW-001", "ACT-DRAW-002", "ACT-TASK-002", "ACT-DRAW-004"):
        return ""
    if not diag["l5_users"] or not diag["l5_target"]:
        return ""
    delta_rate = max(0.0, ASSUMED_L5_RATE - diag["l5_rate"])
    daily = delta_rate * diag["l5_target"] * diag["l5_users"]
    if daily <= 0:
        return "L5 客单已达标，无需额外测算"
    return ("约 ¥%s/日（假设 L5 客单达成率 %.1f%% → %.0f%%，人数不变）"
            % ("{:,.0f}".format(daily), diag["l5_rate"] * 100, ASSUMED_L5_RATE * 100))


# ------------------------------------------------------------
# 6.4 配置建议：把诊断数字翻译成「改哪个活动的哪个字段」
# ------------------------------------------------------------
SUGGEST_PATH = ROOT / "01_datagen" / "suggestions.json"

# 每条规则都挂一个可解释的触发条件；没触发的也写进 skipped，让人看见判定过程
RULE_BOOK = {
    "C-WHALE-01": "L5 客单达成率 < 80% → 高价位活动补阶梯档 + 收紧库存",
    "C-BUNDLE-01": "L5 客单达成率 < 80% → 累充顶档上探，承接大R 单日目标",
    "C-PITY-01": "结构缺口占比 ≥ 10% → 抽奖降保底，降低参与风险感",
    "C-SCARCITY-01": "结构缺口 ≥ 10% 且 L5 < 80% → 存量抽奖提价 + 限量",
    "C-BREADTH-01": "流量/转化缺口 > 0 → 低档礼包补 1 元档，拉付费率",
}


def _diff_config(act, new_cfg, notes=None):
    """只回有变化的字段，旧值-新值成对。"""
    notes = notes or {}
    old = act.get("config") or {}
    out = []
    for k, v in new_cfg.items():
        if old.get(k) != v:
            out.append({"field": k, "label": CFG_LABEL.get(k, k),
                        "old": old.get(k), "new": v, "note": notes.get(k, "")})
    return out


def build_suggestions(conn, diag, lib, ledger):
    """按诊断结果产出配置建议；已上线（有冻结期）的活动不改配置。"""
    locked = {r[0] for r in conn.execute(
        "SELECT DISTINCT activity_id FROM activity_schedule WHERE frozen=1")}
    l5 = diag["l5_rate"] or 0.0
    struct = diag["seg_struct"] or 0.0
    vol = diag["seg_volume"] or 0.0
    lift_daily = estimate_lift("ACT-GIFT-006", diag)

    items, skipped = [], []

    def add(act_id, kind, rule, reason, new_cfg, notes, expect=""):
        act = lib.get(act_id)
        if not act:
            return
        if act_id in locked:
            skipped.append({"activity_id": act_id, "name": act["name"], "rule_code": rule,
                            "why": "该活动已有上线期，配置锁定（已定档不动）"})
            return
        target = dict(act.get("config") or {})
        target.update(new_cfg)
        diffs = _diff_config(act, target, notes)
        if not diffs:
            skipped.append({"activity_id": act_id, "name": act["name"], "rule_code": rule,
                            "why": "配置已是建议值，无需变更（已发布过）"})
            return
        items.append({
            "kind": kind,
            "activity_id": act_id,
            "name": act["name"],
            "type": act["type"],
            "target": act["target"],
            "risk": act.get("risk", "low"),
            "config_table": config_table(act),
            "locked": False,
            "rule_code": rule,
            "reason": reason,
            "expect": expect,
            "diffs": diffs,
            "target_config": target,
        })

    # --- 规则 1：大R 高价档缺失 ---
    if l5 and l5 < 0.80:
        add("ACT-GIFT-006", "update", "C-WHALE-01",
            "昨日 L5 客单 ¥%s / 目标 ¥%s，达成率 %.1f%%。单档 648 离顶部太远，"
            "补 328 元档做阶梯锚点，库存收紧强化稀缺。"
            % ("{:,.0f}".format(diag["l5_arppu"]), "{:,.0f}".format(diag["l5_target"]), l5 * 100),
            {"price_tiers": "328/648", "stock": 2000},
            {"price_tiers": "原单档 648，加一档 328 让中大R 先跨一步",
             "stock": "3000 → 2000，压缩供给放大稀缺感"},
            lift_daily)
        add("ACT-TASK-002", "update", "C-BUNDLE-01",
            "累充任务是收入冲刺主承接，但顶档只到 648；L5 单日目标 ¥%s 缺少对应档位。"
            % "{:,.0f}".format(diag["l5_target"]),
            {"price_tiers": "6/30/128/328/648/1288", "limit_per_user": 6},
            {"price_tiers": "顶档上探到 1288，覆盖大R 单日目标客单",
             "limit_per_user": "5 → 6，多一档可领"},
            "定性：拉顶部付费深度，不做数字外推")
    else:
        skipped.append({"rule_code": "C-WHALE-01", "why": "L5 客单达成率 %.1f%% ≥ 80%%，无需补档"
                        % (l5 * 100)})

    # --- 规则 2：结构缺口主导 → 抽奖 ---
    if struct >= ASSUMED_STRUCT_SHARE:
        add("ACT-DRAW-002", "update", "C-PITY-01",
            "结构缺口占日均缺口 %.1f%%（≥ %.0f%%），判定付费活动相关主导。"
            "保底 50 抽门槛偏高，降到 45 抽降低风险感、提高参与。"
            % (struct, ASSUMED_STRUCT_SHARE),
            {"pity_times": 45,
             "reward_desc": "累计 N 次必得大奖（抽数进度可视化，保底跨期继承）"},
            {"pity_times": "50 → 45", "reward_desc": "补进度可视化与保底继承"},
            )
        add("ACT-DRAW-004", "update", "C-SCARCITY-01",
            "头部付费深度不足，用稀缺性拉单次爆发；该活动风险 high，排期上只给版本节点、不连排。",
            {"stock": 3000, "price_tiers": "68/328/648"},
            {"stock": "5000 → 3000", "price_tiers": "加 648 顶档"},
            )
    else:
        skipped.append({"rule_code": "C-PITY-01",
                        "why": "结构缺口占比 %.1f%% < %.0f%%，不排大R 冲刺"
                        % (struct, ASSUMED_STRUCT_SHARE)})

    # --- 规则 3：流量/转化缺口 ---
    if vol > 0:
        add("ACT-GIFT-002", "update", "C-BREADTH-01",
            "流量/转化缺口 ¥%s，付费人数不足，用 1 元档拉付费率。" % "{:,.0f}".format(diag["volume_gap"]),
            {"price_tiers": "1/6/30/68"}, {}, "")
    else:
        skipped.append({"rule_code": "C-BREADTH-01",
                        "why": "流量/转化缺口 0.0%，付费人数不缺，不建议再拉宽低价档"})

    # --- 新增类：未上线的排期实例（不改配置，只把期落到 Excel 的排期页） ---
    by_month = diag["month"]
    groups = {}
    for it in ledger["items"]:
        if it["frozen"] or not it["start"].startswith(by_month):
            continue
        act = lib.get(it["activity_id"])
        if not act:
            continue
        groups.setdefault(it["activity_id"], {"act": act, "rows": []})["rows"].append(it)

    for aid, g in groups.items():
        act, rows = g["act"], g["rows"]
        items.append({
            "kind": "enable",
            "activity_id": aid,
            "name": rows[0].get("name") or act["name"],
            "type": act["type"],
            "target": act["target"],
            "risk": act.get("risk", "low"),
            "config_table": config_table(act),
            "locked": aid in locked,
            "rule_code": rows[0].get("rule_code") or "R-BASE-01",
            "reason": rows[0].get("rule_note") or "常驻基线",
            "expect": "",
            "schedule_id": rows[0]["schedule_id"],
            "period": "、".join("%s~%s" % (r["start"][5:], r["end"][5:]) for r in rows),
            "period_count": len(rows),
            "diffs": [],
            "target_config": dict(act.get("config") or {}),
        })

    # 编号：改动类在前，新增类在后
    items.sort(key=lambda x: (0 if x["kind"] == "update" else 1, x["activity_id"]))
    for i, it in enumerate(items, 1):
        it["suggestion_id"] = "SUG-%02d" % i

    payload = {
        "_comment": "由 activity_engine.py 生成。kind=update 为配置改动，kind=enable 为未上线排期落地。"
                    "已上线（有冻结期）的活动不进建议。",
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "today": diag["today"],
        "month": diag["month"],
        "diag": {
            "need_daily": round(diag["need_daily"] or 0, 2),
            "gap_daily": round(diag["gap_daily"] or 0, 2),
            "gap_total": round(diag["gap_total"] or 0, 2),
            "seg_struct": struct, "seg_volume": vol, "seg_rest": diag["seg_rest"],
            "l5_rate": round(l5, 4),
            "struct_gap": round(diag["struct_gap"] or 0, 2),
            "volume_gap": round(diag["volume_gap"] or 0, 2),
        },
        "rule_book": RULE_BOOK,
        "items": items,
        "skipped": skipped,
    }
    SUGGEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


# ------------------------------------------------------------
# 6.5 活动库总表（27 张表不方便横向看，这里补一份可读矩阵）
# ------------------------------------------------------------
TYPE_ORDER = ["礼包", "权益", "抽奖", "任务", "排行榜", "特殊", "商城"]
CFG_LABEL = {
    "price_tiers": "价格/档位", "reward_desc": "奖励内容", "limit_per_user": "限购",
    "stock": "库存", "cycle": "周期", "trigger_cond": "触发条件",
    "pity_times": "保底次数", "multiplier": "倍率", "rank_metric": "排行指标",
}


def fmt_cfg(v):
    if v is None or v == "":
        return "—"
    if isinstance(v, float):
        return "×%g" % v
    return str(v)


def build_arsenal_doc(conn, seed):
    acts = seed["activities"]
    meta = {r[0]: r for r in conn.execute(
        "SELECT activity_id, config_table, duration_days FROM activity_master")}

    L = []
    push = L.append
    push("# 活动库总表")
    push("")
    push("> 由 `03_activity_agent/activity_engine.py` 生成。活动 ID 为主键，共 **%d** 个活动；"
         "每个活动有**一张独立配置表**，改配置只动它那张表。" % len(acts))
    push("> 27 张表的建表语句见 `config_tables.sql`，配置数据源是 `arsenal_seed.json`。")
    push("")

    push("## 一、全部活动")
    push("")
    push("| 活动ID | 活动名称 | 类型 | 人群 | 默认时长 | 节奏 | 难度 | 风险 | 杠杆 | 配置表 |")
    push("|---|---|---|---|---|---|---|---|---|---|")
    for a in acts:
        m = meta.get(a["activity_id"])
        dur = a.get("duration_days")
        push("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s | `%s` |"
             % (a["activity_id"], a["name"], a["type"], a["target"],
                ("%d 天" % dur) if dur else "常驻",
                a.get("cadence") or "—", a.get("difficulty") or "—",
                a.get("risk") or "—", a.get("lever") or "—",
                m[1] if m and m[1] else "—"))
    push("")

    push("## 二、配置一览（按类型）")
    push("")
    push("同类型字段一致，所以同类活动可以横向对比；表里只有该类型用得到的列。")
    push("")
    for tp in TYPE_ORDER:
        group = [a for a in acts if a["type"] == tp]
        if not group:
            continue
        template = CONFIG_TEMPLATES.get(tp) or CONFIG_FALLBACK
        used = [c for c in template
                if any(c[0] in (a.get("config") or {}) for a in group)]
        push("### %s（%d 个）" % (tp, len(group)))
        push("")
        push("| 活动ID | 活动 | " + " | ".join(CFG_LABEL.get(c[0], c[0]) for c in used) + " |")
        push("|---|---|" + "---|" * len(used))
        for a in group:
            cfg = a.get("config") or {}
            push("| `%s` | %s | %s |"
                 % (a["activity_id"], a["name"],
                    " | ".join(fmt_cfg(cfg.get(c[0])) for c in used)))
        push("")

    push("## 三、维护方式")
    push("")
    push("1. **加活动**：在 `arsenal_seed.json` 里加一条（指定 `activity_id` 与 `type`），"
         "重跑引擎 → 自动建表 `cfg_act_xxx`、写主数据、回填 `config_table`。")
    push("2. **改配置**：改该活动种子里的 `config` 后重跑引擎（种子是配置的唯一真源，会覆盖表内值）；"
         "临时试算也可直接 `UPDATE cfg_act_xxx SET ...`。")
    push("3. **改字段**：在引擎 `CONFIG_TEMPLATES` 里给该类型加列，重跑会自动 `ALTER TABLE` 补齐。")
    push("4. **删活动**：种子中移除后重跑，引擎不会自动删表（避免误删历史），需手工 `DROP TABLE`。")
    push("")

    ARSENAL_DOC_PATH.write_text("\n".join(L), encoding="utf-8")
    return ARSENAL_DOC_PATH


# ------------------------------------------------------------
# 7. 主流程
# ------------------------------------------------------------
def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="活动配置引擎：活动库 → 排期台账 → 说明文档")
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "init", "plan", "report"])
    ap.add_argument("--today", help="指定「今天」（YYYY-MM-DD），默认取系统日期")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--check", action="store_true", help="只打印诊断与计划，不写文件")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print("[ERROR] 数据库不存在：%s\n        先运行 start.bat 生成虚拟数据。" % db)
        return 1

    cfg = load_json(CFG_PATH, {})
    today = s2d(args.today) if args.today else dt.date.today()

    conn = sqlite3.connect(db)
    lib, alias, lib_added, lib_updated = init_library(conn)
    print("活动库     %s" % db.name)
    print("  活动总表  新增 %d / 更新 %d（共 %d 个活动）" % (lib_added, lib_updated, len(lib)))

    diag = diagnose(conn, cfg, today)
    print("  今天       %s（%s，已过 %d/%d 天）"
          % (diag["today"], diag["month"], diag["days_elapsed"], diag["days_in_month"]))
    if diag["need_daily"]:
        print("  需日均     ¥%s   日均缺口 ¥%s（结构 %.1f%% / 流量 %.1f%% / 稳态 %.1f%%）"
              % ("{:,.0f}".format(diag["need_daily"]), "{:,.0f}".format(diag["gap_daily"]),
                 diag["seg_struct"], diag["seg_volume"], diag["seg_rest"]))
    if diag["l5_users"]:
        print("  L5 客单    达成 %.1f%%（¥%s / 目标 ¥%s）"
              % (diag["l5_rate"] * 100, "{:,.0f}".format(diag["l5_arppu"]),
                 "{:,.0f}".format(diag["l5_target"])))

    ledger = load_ledger()
    if not ledger or not ledger.get("items"):
        ledger = migrate_ledger(cfg, alias, today, lib)
        print("  台账       首次建立，自 config.json 迁移 %d 条排期" % len(ledger["items"]))

    plan = build_plan(lib, diag, today, ledger["items"])
    stats, changes = apply_plan(ledger["items"], plan, today)

    for action, sid, name, detail in changes:
        if action in ("add", "update"):
            print("  [%s] %s %s：%s" % ("新增" if action == "add" else "调整",
                                        sid, name, detail))
    print("  计划 %d 条 → 新增 %d / 调整 %d / 保持 %d（本次冻结 %d）"
          % (len(plan), stats["add"], stats["update"], stats["keep"], stats["newly_frozen"]))

    if args.check:
        print("\n（--check 模式，未写入任何文件）")
        conn.close()
        return 0

    save_ledger(conn, ledger, stats, changes, today)
    sugg = build_suggestions(conn, diag, lib, ledger)
    note = build_note(conn, diag, ledger, stats, changes)
    arsenal = build_arsenal_doc(conn, load_json(SEED_PATH))
    conn.close()

    frozen = sum(1 for it in ledger["items"] if it["frozen"])
    print("  台账       %s（%d 条，其中已定档 %d 条）"
          % (LEDGER_PATH.name, len(ledger["items"]), frozen))
    print("  建议       改动 %d 条 / 新增 %d 条（跳过 %d 条）"
          % (sum(1 for x in sugg["items"] if x["kind"] == "update"),
             sum(1 for x in sugg["items"] if x["kind"] == "enable"),
             len(sugg["skipped"])))
    print("  说明       %s / %s" % (note.name, arsenal.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
