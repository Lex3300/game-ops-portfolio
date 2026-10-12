#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
游戏运营数据闭环系统 · 数据生成器（模块 ①）
=================================================

职责
----
按「基线 + 拐点 + 干预」三层模型，生成一套**自洽**的游戏运营数据。

设计要点
--------
1. **自洽性**：付费分层的人数与流水必须严格加总回日粒度指标，不允许多算少算。
2. **队列成熟度**：cohort_date + day_n > 最后一天时，存 NULL（表示"未成熟"）而不是 0——
   这是手工抄日报时最容易出错的地方。
3. **剧本化**：story_events 按「距结束天数」定位，首次运行固化成绝对日期落库，
   之后每天增量生成时复用，保证剧情位置不会随日期推移而漂移。
4. **可复现**：随机种子按「种子 + 日期」派生，任意一天的数据在任何时候重跑都一致。

用法
----
    python generator.py --days 180      # 首次：补齐 180 天历史
    python generator.py                 # 日常：增量补到昨天
    python generator.py --reset         # 清库重建
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- 路径
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DB_PATH = ROOT_DIR / "data" / "game.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
CONFIG_PATH = BASE_DIR / "config.json"

RETENTION_DAYS = [1, 3, 7, 14, 30, 60, 90]
PAID_TIERS = ["小R", "中R", "大R"]
ALL_TIERS = ["非R"] + PAID_TIERS


# ================================================================
# 基础工具
# ================================================================

def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def build_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def rng_for(seed: int, d: date) -> random.Random:
    """按日期派生随机流：任意一天的数据在任何时候重跑都完全一致。"""
    return random.Random(f"{seed}:{d.isoformat()}")


def jitter(rng: random.Random, amplitude: float) -> float:
    """在 1 ± amplitude 区间内取随机扰动。"""
    return rng.uniform(1.0 - amplitude, 1.0 + amplitude)


def cfg_get(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM sim_config WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def cfg_set(conn: sqlite3.Connection, key: str, value, note: str = "") -> None:
    conn.execute(
        "INSERT INTO sim_config (key, value, note) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value, ensure_ascii=False), note),
    )


# ================================================================
# 剧本事件
# ================================================================

def plan_events(cfg: dict, anchor_end: date) -> list[dict]:
    """把配置里「距结束 N 天」的事件固化成绝对日期。"""
    planned = []
    for ev in cfg.get("story_events", []):
        ev_date = anchor_end - timedelta(days=int(ev["day_from_end"]))
        planned.append(
            {
                "event_id": ev["id"],
                "date": ev_date.isoformat(),
                "name": ev["name"],
                "description": ev.get("description", ""),
                "impact": ev.get("impact", {}),
            }
        )
    planned.sort(key=lambda e: e["date"])
    return planned


def save_events(conn: sqlite3.Connection, events: list[dict]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO story_events (event_id, event_date, name, description, impact) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (
                e["event_id"],
                e["date"],
                e["name"],
                e["description"],
                json.dumps(e["impact"], ensure_ascii=False),
            )
            for e in events
        ],
    )


def load_events(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT event_id, event_date, name, description, impact FROM story_events ORDER BY event_date"
    ).fetchall()
    return [
        {
            "event_id": r[0],
            "date": r[1],
            "name": r[2],
            "description": r[3],
            "impact": json.loads(r[4]),
        }
        for r in rows
    ]


def apply_persistent_impact(state: dict, impact: dict) -> dict:
    """把事件里的持续型影响叠加到运行状态上（此后一直生效）。"""
    applied = {}

    if "retention_mult" in impact:
        for day_n, mult in impact["retention_mult"].items():
            state["retention_mult"][day_n] = state["retention_mult"].get(day_n, 1.0) * float(mult)
        applied["留存系数"] = impact["retention_mult"]

    for key, label in (
        ("churn_mult", "日流失率"),
        ("session_min_mult", "在线时长"),
        ("pay_rate_mult", "付费率"),
        ("arppu_mult", "ARPPU"),
    ):
        if key in impact:
            state[key] = state.get(key, 1.0) * float(impact[key])
            applied[label] = impact[key]

    if "head_share_boost" in impact:
        state["head_share_boost"] = state.get("head_share_boost", 0.0) + float(impact["head_share_boost"])
        applied["头部集中度"] = f"+{impact['head_share_boost']:.0%}"

    if "whale_lost" in impact:
        state["whale_lost"] = state.get("whale_lost", 0) + int(impact["whale_lost"])
        applied["流失大R"] = f"{impact['whale_lost']} 人"

    return applied


# ================================================================
# 日粒度指标 + 付费分层
# ================================================================

def gen_day(d: date, state: dict, cfg: dict, one_shot: dict) -> tuple[dict, list[tuple]]:
    """生成一天的全部数据。返回 (日指标行, 分层行列表)。"""
    base = cfg["baseline"]
    rng = rng_for(cfg["sim"]["seed"], d)
    noise = cfg["sim"]["noise"]
    is_weekend = d.weekday() >= 5

    # ---- 新增 / 回流 ----
    new_users = base["new_users_base"]
    if is_weekend:
        new_users *= base["weekend_new_mult"]
    new_users = max(1, int(round(new_users * jitter(rng, noise))))

    returning = max(0, int(round(base["returning_base"] * jitter(rng, noise * 1.5))))

    # ---- DAU：存量衰减 + 新增 + 回流 ----
    churn = base["daily_churn"] * state["churn_mult"]
    if is_weekend:                       # 周末流失更低，自然形成 DAU 波峰
        churn /= 1.06
    prev_dau = state["dau"]
    dau = prev_dau * (1 - churn) + new_users + returning
    if "dau_shock" in one_shot:          # 剧本的一次性冲击
        dau *= (1 + one_shot["dau_shock"])
    dau = max(1, int(round(dau)))

    # ---- 付费 ----
    pay_rate = base["pay_rate"] * state["pay_rate_mult"]
    if is_weekend:
        pay_rate *= base["weekend_pay_mult"]
    pay_rate *= jitter(rng, noise * 0.8)
    pay_users = max(1, int(round(dau * pay_rate)))

    arppu = base["arppu"] * state["arppu_mult"] * jitter(rng, noise * 1.2)
    revenue = pay_users * arppu
    if "revenue_shock" in one_shot:
        revenue *= (1 + one_shot["revenue_shock"])

    # ---- 人均时长：按自然日复利衰减，再叠加剧本系数 ----
    days_in = (d - date.fromisoformat(state["plan_start"])).days
    session = (
        base["session_min"]
        * state["session_min_mult"]
        * (1 + base["session_min_decay"]) ** days_in
        * jitter(rng, noise * 0.5)
    )

    daily = {
        "date": d.isoformat(),
        "new_users": new_users,
        "dau": dau,
        "returning_users": returning,
        "pay_users": pay_users,
        "revenue": round(revenue, 2),
        "avg_session_min": round(session, 1),
    }

    # ---- 付费分层：人数与流水必须严格加总回总量 ----
    tiers = build_tiers(d, dau, pay_users, daily["revenue"], state, cfg, rng, noise)
    return daily, tiers


def build_tiers(d, dau, pay_users, revenue, state, cfg, rng, noise) -> list[tuple]:
    """构造付费分层。采用「先定大R/中R，小R取差额」的方式保证加总严格相等。"""
    shares = cfg["tiers"]["paid_user_share"]

    big_r = max(0, int(round(pay_users * shares["大R"])) - state.get("whale_lost", 0))
    mid_r = int(round(pay_users * shares["中R"]))
    mid_r = min(mid_r, max(0, pay_users - big_r))
    small_r = max(0, pay_users - big_r - mid_r)

    # 流水占比：从 start 线性漂移到 end，再叠加「头部集中度」加成
    plan_start = date.fromisoformat(state["plan_start"])
    span = max(1, (date.fromisoformat(state["plan_end"]) - plan_start).days)
    progress = min(1.0, max(0.0, (d - plan_start).days / span))

    rs_start, rs_end = cfg["tiers"]["revenue_share_start"], cfg["tiers"]["revenue_share_end"]
    share = {
        t: rs_start[t] + (rs_end[t] - rs_start[t]) * progress
        for t in PAID_TIERS
    }
    share["大R"] += state.get("head_share_boost", 0.0)
    total = sum(share.values())
    share = {t: v / total for t, v in share.items()}

    rev_big = revenue * share["大R"]
    rev_mid = revenue * share["中R"]
    rev_small = max(0.0, revenue - rev_big - rev_mid)   # 差额保证加总相等

    non_r = max(0, dau - pay_users)

    return [
        (d.isoformat(), "非R", non_r, 0.0),
        (d.isoformat(), "小R", small_r, round(rev_small, 2)),
        (d.isoformat(), "中R", mid_r, round(rev_mid, 2)),
        (d.isoformat(), "大R", big_r, round(rev_big, 2)),
    ]


# ================================================================
# 留存队列
# ================================================================

def gen_cohorts(cohort: date, cohort_new_users: int, retention_mult: dict,
                last_date: date, cfg: dict) -> list[tuple]:
    """为一个注册队列生成各档留存；未成熟的档位存 NULL。"""
    rng = rng_for(cfg["sim"]["seed"] + 7, cohort)
    noise = cfg["sim"]["noise"] * 0.5
    rows = []

    for day_n in RETENTION_DAYS:
        observe_on = cohort + timedelta(days=day_n)
        if observe_on > last_date:
            rows.append((cohort.isoformat(), day_n, None, None))   # 队列未成熟
            continue

        base_rate = cfg["retention_curve"][str(day_n)]
        mult = retention_mult.get(str(day_n), 1.0)
        rate = min(0.98, base_rate * mult * jitter(rng, noise))
        rows.append((cohort.isoformat(), day_n, int(round(cohort_new_users * rate)), round(rate, 6)))

    return rows


# ================================================================
# 主流程
# ================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="游戏运营数据生成器")
    ap.add_argument("--days", type=int, default=None, help="首次生成的总天数（默认取配置）")
    ap.add_argument("--end-date", type=str, default=None, help="结束日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--reset", action="store_true", help="清库重建")
    ap.add_argument("--config", type=str, default=str(CONFIG_PATH))
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today()

    if args.reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = connect(DB_PATH)
    fresh = not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_metrics'"
    ).fetchone()
    if fresh:
        build_schema(conn)

    # ---- 首次运行：规划剧本并固化日期 ----
    if fresh:
        total_days = args.days or cfg["sim"]["days"]
        plan_start = end_date - timedelta(days=total_days - 1)
        plan_end = end_date
        events = plan_events(cfg, plan_end)
        save_events(conn, events)
        cfg_set(conn, "plan_start", plan_start.isoformat(), "剧本起始日期")
        cfg_set(conn, "plan_end", plan_end.isoformat(), "剧本结束日期")
        cfg_set(conn, "config_snapshot", cfg, "生成时的完整配置留档")
        print(f"[初始化] 剧本区间 {plan_start} → {plan_end}（{total_days} 天）")
    else:
        events = load_events(conn)
        plan_start = date.fromisoformat(cfg_get(conn, "plan_start"))
        plan_end = date.fromisoformat(cfg_get(conn, "plan_end"))

    # ---- 计算本次要生成的日期 ----
    row = conn.execute("SELECT MAX(date) FROM daily_metrics").fetchone()
    last_in_db = date.fromisoformat(row[0]) if row and row[0] else None

    if last_in_db is None:
        todo = [plan_start + timedelta(days=i) for i in range((plan_end - plan_start).days + 1)]
    else:
        todo = [last_in_db + timedelta(days=i)
                for i in range(1, (end_date - last_in_db).days + 1)]

    if not todo:
        print(f"[跳过] 数据已是最新（最后一天 {last_in_db}），无需生成。")
        conn.close()
        return 0

    # ---- 恢复运行状态 ----
    state = {
        "dau": cfg["baseline"]["dau_start"],
        "retention_mult": {},
        "churn_mult": 1.0,
        "session_min_mult": 1.0,
        "pay_rate_mult": 1.0,
        "arppu_mult": 1.0,
        "head_share_boost": 0.0,
        "whale_lost": 0,
        "plan_start": plan_start.isoformat(),
        "plan_end": plan_end.isoformat(),
    }
    saved = cfg_get(conn, "runtime_state")
    if saved:
        state.update(saved)

    # 增量场景：先重放「上一次生成之后、本次开始之前」的事件，恢复累计系数
    if last_in_db is not None:
        for ev in events:
            ev_d = date.fromisoformat(ev["date"])
            if last_in_db < ev_d <= todo[0]:
                apply_persistent_impact(state, ev["impact"])

    events_by_date = {}
    for ev in events:
        events_by_date.setdefault(ev["date"], []).append(ev)

    # ---- 逐日生成 ----
    daily_rows, tier_rows, cohort_rows, event_log = [], [], [], []
    for d in todo:
        one_shot = {}

        for ev in events_by_date.get(d.isoformat(), []):
            applied = apply_persistent_impact(state, ev["impact"])
            for k in ("dau_shock", "revenue_shock"):
                if k in ev["impact"]:
                    one_shot[k] = ev["impact"][k]
            event_log.append((d, ev["name"], applied))

        daily, tiers = gen_day(d, state, cfg, one_shot)
        state["dau"] = daily["dau"]                      # 传递到下一天

        daily_rows.append((
            daily["date"], daily["new_users"], daily["dau"], daily["returning_users"],
            daily["pay_users"], daily["revenue"], daily["avg_session_min"],
            datetime.now().isoformat(timespec="seconds"),
        ))
        tier_rows.extend(tiers)

        # 队列留存：用「注册当天生效的留存系数」快照
        cohort_rows.extend(
            gen_cohorts(d, daily["new_users"], dict(state["retention_mult"]), end_date, cfg)
        )

    # ---- 落库 ----
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_metrics "
            "(date, new_users, dau, returning_users, pay_users, revenue, avg_session_min, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            daily_rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO revenue_tiers (date, tier, users, revenue) VALUES (?, ?, ?, ?)",
            tier_rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO retention_cohorts (cohort_date, day_n, retained, rate) "
            "VALUES (?, ?, ?, ?)",
            cohort_rows,
        )
        cfg_set(conn, "runtime_state", state, "运行状态快照（保证增量生成可续跑）")
        for key, value, note in (
            ("last_run", datetime.now().isoformat(timespec="seconds"), "上次生成时间"),
            ("total_days", (plan_end - plan_start).days + 1, "剧本总天数"),
        ):
            cfg_set(conn, key, value, note)

    # ---- 输出摘要 ----
    print(f"\n[生成] {cfg['game']['name']} · {todo[0]} → {todo[-1]}（{len(todo)} 天）")
    print(f"  daily_metrics      {len(daily_rows):>6} 行")
    print(f"  retention_cohorts  {len(cohort_rows):>6} 行")
    print(f"  revenue_tiers      {len(tier_rows):>6} 行")

    if event_log:
        print("\n[剧本事件]")
        for d, name, applied in event_log:
            detail = "、".join(f"{k} {v}" for k, v in applied.items()) if applied else "一次性冲击"
            print(f"  · {d}  {name}  →  {detail}")

    stat = conn.execute(
        "SELECT COUNT(*), MIN(date), MAX(date), ROUND(AVG(dau)), ROUND(AVG(revenue)) FROM daily_metrics"
    ).fetchone()
    print(f"\n[库概况] {stat[0]} 天（{stat[1]} → {stat[2]}）  平均 DAU {stat[3]:,}  平均日流水 ¥{stat[4]:,.0f}")

    # 自洽性校验
    bad = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT t.date,
                   SUM(t.users)            AS tier_users,
                   SUM(t.revenue)          AS tier_rev,
                   m.dau, m.revenue        AS day_rev
            FROM revenue_tiers t JOIN daily_metrics m ON m.date = t.date
            GROUP BY t.date
            HAVING tier_users <> m.dau OR ABS(tier_rev - day_rev) > 0.05
        )
    """).fetchone()[0]
    print(f"[自洽校验] 分层人数/流水与总量不一致的天数：{bad} 天" + ("  ✅ 全部通过" if bad == 0 else "  ❌ 需检查"))

    size_kb = DB_PATH.stat().st_size / 1024
    print(f"[完成] 数据库：{DB_PATH.relative_to(ROOT_DIR)}（{size_kb:,.0f} KB）")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
