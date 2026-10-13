#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
游戏运营数据闭环系统 · 数据生成器（模块 ①）
=================================================

职责
----
按字段清单生成一套**自洽**的游戏运营数据，从固定起点逐日向后累积。

生成规则（全部来自 config.json，代码不写死任何业务数值）
--------------------------------------------------------
模块A 大盘
  字段1 日期          起点固定，每日 +1 天
  字段2 新增用户数     区间内随机（默认 300~1000）
  字段3 活跃用户数     不随机。DAU = 非新增活跃 + 新增
                      非新增活跃 = Σ(历史各日新增 × 该批用户在当日的留存率) + 初始存量
                      首日非新增活跃起点由配置指定（默认 1000）
  字段4 付费率         区间内随机（默认 7%~13%）
  字段5 日流水         不随机。= Σ(各档付费用户数 × 该档 ARPPU)

模块B 付费分层
  付费用户数 = DAU × 付费率
  各档付费用户数之和 = 付费用户数（用「最大余数法」取整，精确相等）
  各档 ARPPU 在档位区间内随机
  各档流水 = 付费用户数 × ARPPU，汇总即为日流水

模块C 留存
  字段1 日期 = 新增队列日（cohort_date）
  字段2~31 = D1~D30 留存率，基准曲线 D1≈45% → D30≈10%
  每日留存相对基准的波动不超过配置上限（默认 ±3%），由平滑正弦叠构造函数性保证
  与模块A 的 DAU 推导共用同一条留存曲线 —— 模块C 是模块A 的上游

三条硬约束
----------
1. DAU ≡ 非新增活跃 + 新增               （数据库触发器强制）
2. 各档付费用户数之和 ≡ 付费用户数        （生成后巡检 v_consistency）
3. 各档流水之和 ≡ 日流水                  （生成后巡检 v_consistency）

其他设计
--------
- 已生成的日期不会被改写。重复执行会自动跳过，只补缺失的天数。
- 留存队列按「今天观测到的留存」写入：day_n 的留存值在 cohort_date + day_n 那天才落库，
  未成熟的不写（而非写 0）。
- 剧本层（story）可选：只影响留存曲线与付费结构分布，不改动已声明的随机区间。

用法
----
    python generator.py                 # 首次：按配置天数生成；之后：增量补到最新
    python generator.py --days 90       # 指定从起点起累计生成 90 天
    python generator.py --reset         # 清库重建
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DB_PATH = ROOT_DIR / "data" / "game.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
CONFIG_PATH = BASE_DIR / "config.json"


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


def rng_for(seed: int, salt: str, d: date) -> random.Random:
    """按「种子 + 用途 + 日期」派生随机流：任意一天的数据任何时候重跑都一致。"""
    return random.Random(f"{seed}:{salt}:{d.isoformat()}")


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
# 留存模型（模块C）
# ================================================================

class RetentionModel:
    """留存率模型：基准曲线 × 剧本系数 × 平滑波动，并对同一队列做单调性保护。

    模块C（留存表）与模块A（DAU 推导）共用**同一个** model 实例，
    所以「非新增活跃池」能从留存表逐日复算出来，两条链路不会各说各话。

    波动设计（对应「每日留存以误差不超过 3% 上下波动」）
    -------------------------------------------------
    取若干条不同周期的正弦按权重叠加：

        noise(t, n) = band × Σ wᵢ·sin(2π·t/pᵢ + φᵢ + dᵢ·n) / Σ|wᵢ|

    - **天然有界**：|Σ wᵢ·sin| ≤ Σ|wᵢ|，故 |noise| ≤ band。
      因为是构造性有界而非事后截断，所以不会在边界堆积、也不会破坏曲线形态。
    - **天然平滑**：t 为队列日期序号、n 为留存天数，相位随 n 缓慢漂移，
      相邻队列、相邻天数的扰动高度相关 —— 留存随天数递减的形态得以保持。
    """

    def __init__(self, cfg: dict, events: list[dict], first: date):
        curve = cfg["retention_curve"]
        self.anchors = sorted((int(k), float(v)) for k, v in curve["anchors"].items())
        self.tail = float(curve.get("tail_decay", 0.98))
        self.monotonic = bool(curve.get("monotonic", True))
        self.first = first
        # story.affects_retention=false 时，留存严格锁在基准曲线 + ±band 波动，
        # 剧本事件不再下移留存（它的其它影响，如档位权重，仍然生效）。
        self.events = events if cfg.get("story", {}).get("affects_retention", True) else []

        ns = curve.get("noise", {}) or {}
        self.band = float(ns.get("band", 0.0))
        self.mode = ns.get("mode", "relative")
        self.periods = [float(x) for x in ns.get("periods", [9.7, 23.3])]
        weights = ns.get("weights") or [1.0] * len(self.periods)
        drifts = ns.get("day_phase_drift") or [0.09] * len(self.periods)
        self.weights = [float(x) for x in weights][:len(self.periods)]
        self.drifts = [float(x) for x in drifts][:len(self.periods)]
        self.weights += [1.0] * (len(self.periods) - len(self.weights))
        self.drifts += [0.09] * (len(self.periods) - len(self.drifts))
        self.wsum = sum(abs(w) for w in self.weights) or 1.0

        # 相位由种子派生：同一份配置任何时候重跑，扰动序列完全一致
        rnd = random.Random(f"{cfg['sim']['seed']}:retention-phase")
        self.phases = [rnd.uniform(0.0, 2 * math.pi) for _ in self.periods]

        self._mult_cache: dict[date, object] = {}
        self._rate_cache: dict[date, list[float]] = {}

    # ---------- 基准曲线（锚点间对数插值，尾部几何衰减保证收敛） ----------
    def base(self, day_n: int) -> float:
        if day_n <= 0:
            return 1.0
        anchors, tail = self.anchors, self.tail
        if day_n <= anchors[0][0]:
            return anchors[0][1]
        if day_n >= anchors[-1][0]:
            k0, r0 = anchors[-1]
            return r0 * (tail ** (day_n - k0))
        for (k1, r1), (k2, r2) in zip(anchors, anchors[1:]):
            if k1 <= day_n <= k2:
                if r1 <= 0 or r2 <= 0:
                    return r1
                b = math.log(r2 / r1) / math.log(k2 / k1)
                return r1 * (day_n / k1) ** b
        return anchors[-1][1]

    # ---------- 剧本系数（按队列注册日推导，增量运行结果一致） ----------
    def mult_fn(self, cohort: date):
        if cohort not in self._mult_cache:
            self._mult_cache[cohort] = make_mult_fn(cohort_retention_mult(cohort, self.events))
        return self._mult_cache[cohort]

    # ---------- 波动（构造性有界，不需要截断） ----------
    def noise(self, cohort: date, day_n: int) -> float:
        if self.band <= 0:
            return 0.0
        t = (cohort - self.first).days
        s = 0.0
        for p, w, ph, dr in zip(self.periods, self.weights, self.phases, self.drifts):
            s += w * math.sin(2 * math.pi * t / p + ph + dr * day_n)
        return self.band * s / self.wsum

    def _raw(self, cohort: date, day_n: int) -> float:
        r = self.base(day_n) * self.mult_fn(cohort)(day_n)
        nz = self.noise(cohort, day_n)
        r = r * (1.0 + nz) if self.mode == "relative" else r + nz
        return max(0.0, min(0.99, r))

    # ---------- 取留存率 ----------
    def rates(self, cohort: date, upto: int) -> list[float]:
        """返回 [r(1) … r(upto)]，已做单调性保护（保证 r(n) ≥ r(n+1)）。"""
        cache = self._rate_cache.setdefault(cohort, [])
        for n in range(len(cache) + 1, max(upto, 0) + 1):
            v = self._raw(cohort, n)
            if self.monotonic and cache:
                v = min(v, cache[-1])
            cache.append(v)
        return cache[:upto]

    def rate(self, cohort: date, day_n: int) -> float:
        if day_n <= 0:
            return 1.0
        return self.rates(cohort, day_n)[-1]


def make_mult_fn(mult_dict: dict | None):
    """把「按日序号给出的系数表」变成可插值的函数。"""
    if not mult_dict:
        return lambda day_n: 1.0
    pts = sorted((int(k), float(v)) for k, v in mult_dict.items())

    def f(day_n: int) -> float:
        if day_n <= pts[0][0]:
            return pts[0][1]
        if day_n >= pts[-1][0]:
            return pts[-1][1]
        for (k1, v1), (k2, v2) in zip(pts, pts[1:]):
            if k1 <= day_n <= k2:
                w = (day_n - k1) / (k2 - k1)
                return v1 + (v2 - v1) * w
        return 1.0

    return f


# ================================================================
# 剧本事件
# ================================================================

def plan_events(cfg: dict, start: date) -> list[dict]:
    """把配置里「第 N 天」的事件固化成绝对日期。"""
    if not cfg.get("story", {}).get("enabled", False):
        return []
    out = []
    for ev in cfg["story"].get("events", []):
        d = start + timedelta(days=int(ev["day_index"]) - 1)
        out.append({
            "event_id": ev["id"],
            "date": d.isoformat(),
            "day_index": int(ev["day_index"]),
            "name": ev["name"],
            "description": ev.get("description", ""),
            "impact": ev.get("impact", {}),
        })
    out.sort(key=lambda e: e["date"])
    return out


def save_events(conn: sqlite3.Connection, events: list[dict]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO story_events "
        "(event_id, event_date, day_index, name, description, impact) VALUES (?, ?, ?, ?, ?, ?)",
        [(e["event_id"], e["date"], e["day_index"], e["name"],
          e["description"], json.dumps(e["impact"], ensure_ascii=False)) for e in events],
    )


def load_events(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT event_id, event_date, day_index, name, description, impact "
        "FROM story_events ORDER BY event_date"
    ).fetchall()
    return [{"event_id": r[0], "date": r[1], "day_index": r[2], "name": r[3],
             "description": r[4], "impact": json.loads(r[5])} for r in rows]


def cohort_retention_mult(cohort_date: date, events: list[dict]) -> dict:
    """某队列当日生效的留存系数 = 该队列注册之前发生的所有事件的乘积。

    用事件日期推导而非存快照——保证增量运行时结果与全量生成完全一致。
    """
    mult: dict[str, float] = {}
    for ev in events:
        if date.fromisoformat(ev["date"]) <= cohort_date:
            for k, v in ev["impact"].get("retention_mult", {}).items():
                mult[k] = mult.get(k, 1.0) * float(v)
    return mult


def apply_persistent_impact(state: dict, impact: dict) -> dict:
    """把事件里的持续型影响叠加到运行状态上（此后一直生效）。"""
    applied = {}
    # 留存系数不改运行状态，而是由 cohort_retention_mult() 按队列注册日推导，
    # 这里只做日志展示，让剧本执行过程可读。
    if "retention_mult" in impact:
        applied["留存系数"] = impact["retention_mult"]
    for key, label in (("tier_weight_mult", "档位权重"),):
        if key in impact:
            for code, mult in impact[key].items():
                state.setdefault(key, {})[code] = state[key].get(code, 1.0) * float(mult)
            applied[label] = impact[key]
    if "tier_user_delta" in impact:
        for code, delta in impact["tier_user_delta"].items():
            state.setdefault("tier_user_delta", {})[code] = (
                state["tier_user_delta"].get(code, 0) + int(delta)
            )
        applied["档位人数偏移"] = impact["tier_user_delta"]
    return applied


# ================================================================
# 生成核心
# ================================================================

def allocate_users(total: int, weights: list[float]) -> list[int]:
    """最大余数法：把 total 精确分配到各档，保证和严格等于 total。"""
    s = sum(weights)
    if s <= 0 or total <= 0:
        return [0] * len(weights)
    exact = [total * w / s for w in weights]
    floors = [int(x) for x in exact]
    remainder = total - sum(floors)
    order = sorted(range(len(exact)), key=lambda i: exact[i] - floors[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def sample_field(field_cfg: dict, prev, rng: random.Random, is_weekend: bool) -> float:
    """在 field_cfg['range'] 闭区间内取值，结果**永不越界**。

    - mean_revert > 0 时走「区间内均值回复游走」：数值仍落在区间内，但日间不会大幅跳变，
      更贴近真实运营指标的连续性。设为 0 即退化为每日独立均匀随机。
    - weekend_high_bias 把周末值推向区间上半段，而不是乘到区间外。
    """
    lo, hi = field_cfg["range"]
    span = float(hi) - float(lo)
    target = (float(lo) + float(hi)) / 2.0
    mr = float(field_cfg.get("mean_revert", 0.0))

    if prev is None or mr <= 0:
        val = lo + span * rng.uniform(0.0, 1.0)
    else:
        shock = rng.uniform(-1.0, 1.0) * span * float(field_cfg.get("shock_scale", 0.4))
        val = prev + (target - prev) * mr + shock

    if is_weekend and field_cfg.get("weekend_high_bias", False):
        val = val + (hi - val) * 0.35

    # 边界用「反射」而非硬截断，避免取值在区间端点堆积（否则会出现连续多天正好等于上限）
    for _ in range(3):
        if val > hi:
            val = hi - (val - hi)
        elif val < lo:
            val = lo + (lo - val)
        else:
            break

    return min(max(val, float(lo)), float(hi))


def gen_day(d: date, first: date, state: dict, cfg: dict, events: list[dict],
            history: list[tuple[date, int]], model: RetentionModel) -> tuple[dict, list[dict]]:
    """生成一天的模块A + 模块B 数据。"""
    ma, mb = cfg["module_a"], cfg["module_b"]
    seed, noise = cfg["sim"]["seed"], cfg["sim"]["noise"]
    is_weekend = d.weekday() >= 5

    # ---------- 字段2：新增用户数（区间内随机，严格不越界） ----------
    f2 = ma["field2_new_users"]
    prev = state.get("_prev", {})
    rng_nu = rng_for(seed, "new_users", d)
    new_users = max(1, int(round(sample_field(f2, prev.get("new_users"), rng_nu, is_weekend))))

    # ---------- 字段3：DAU = 非新增活跃 + 新增（不随机） ----------
    # 非新增活跃池 = 历史各日新增在该日的存活之和；留存率与模块C 共用同一条曲线
    stock = 0.0
    for c_date, c_new in history:
        day_n = (d - c_date).days
        if day_n <= 0:
            continue
        stock += c_new * model.rate(c_date, day_n)

    # 初始存量：等价于一个「虚拟队列」（注册于起点前一天），使其在首日贡献恰为 stock_active_start
    stock0 = ma["field3_dau"]["stock_active_start"]
    virtual = first - timedelta(days=1)
    stock += (stock0 / model.rate(virtual, 1)) * model.rate(virtual, (d - virtual).days)

    stock_active = int(round(stock))
    dau = stock_active + new_users

    # ---------- 字段4：付费率（区间内随机，严格不越界） ----------
    f4 = ma["field4_pay_rate"]
    rng_pr = rng_for(seed, "pay_rate", d)
    pay_rate = sample_field(f4, prev.get("pay_rate"), rng_pr, is_weekend)

    # ---------- 模块B：付费用户数 ----------
    pay_users = max(1, int(round(dau * pay_rate)))

    # ---------- 模块B：各档位分配 ----------
    tiers_cfg = mb["tiers"]
    rng_t = rng_for(seed, "tiers", d)
    weights, ranges, metas = [], [], []
    for t in tiers_cfg:
        w = float(t["user_weight"]) * state.get("tier_weight_mult", {}).get(t["code"], 1.0)
        weights.append(w * rng_t.uniform(1 - noise, 1 + noise))
        ranges.append(t["arppu_range"])
        metas.append(t)

    alloc = allocate_users(pay_users, weights)

    # 剧本的人数偏移（例如头部用户流失）——从对应档位扣减，差额补给相邻档，保持总数不变
    for code, delta in state.get("tier_user_delta", {}).items():
        idx = next((i for i, t in enumerate(tiers_cfg) if t["code"] == code), None)
        if idx is None or delta == 0:
            continue
        move = min(alloc[idx], -delta) if delta < 0 else 0
        if move:
            alloc[idx] -= move
            donor = idx - 1 if idx > 0 else min(idx + 1, len(alloc) - 1)
            alloc[donor] += move

    rows = []
    total_rev = 0.0
    a_noise = float(mb.get("arppu_noise", 1.0))
    # 一次性流水冲击按比例作用于各档 ARPPU —— 这样分层之和仍严格等于日流水
    shock = float(state.get("_one_shot", {}).get("revenue_shock", 0.0))
    for i, t in enumerate(metas):
        lo, hi = ranges[i]
        # ARPPU 基准取区间几何中位数，日波动幅度由 arppu_noise 控制，并截断在区间内。
        # 这样档位人均不会天天翻倍，符合真实付费行为的连续性。
        base = math.sqrt(max(lo, 1e-6) * hi) if hi > 0 else max(lo, 1.0)
        users = alloc[i]
        if users == 0:
            arppu = 0.0
        else:
            arppu = round(min(max(base * rng_t.uniform(1 - a_noise, 1 + a_noise), lo), hi) * (1 + shock), 2)
        revenue = round(users * arppu, 2)
        total_rev += revenue
        rows.append({
            "date": d.isoformat(), "tier_code": t["code"], "tier_name": t["name"],
            "tier_min": t.get("min"), "tier_max": t.get("max"), "sort_order": i + 1,
            "users": users, "arppu": arppu, "revenue": revenue,
        })

    # ---------- 字段5：日流水（由分层汇总，不随机） ----------
    daily = {
        "date": d.isoformat(), "new_users": new_users, "stock_active": stock_active,
        "dau": dau, "pay_rate": round(pay_rate, 6), "pay_users": pay_users,
        "revenue": round(total_rev, 2), "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    return daily, rows


def gen_cohort_observation(d: date, first: date, history: list[tuple[date, int]],
                           cohort_days: int, model: RetentionModel) -> list[tuple]:
    """写入「今天观测到的留存」：cohort_date + day_n == 今天 的那些档位。

    - 未成熟的档位不落库（而不是记 0）——队列成熟度是留存数据的固有特性。
    - 留存率取自与 DAU 推导**同一个** model，模块C 与模块A 可互相复算。
    """
    out = []
    new_by_date = dict(history)
    for day_n in range(1, cohort_days + 1):
        cohort = d - timedelta(days=day_n)
        if cohort < first:
            continue
        c_new = new_by_date.get(cohort)
        if c_new is None:
            continue
        rate = model.rate(cohort, day_n)
        retained = int(round(c_new * rate))
        out.append((cohort.isoformat(), day_n, retained, round(rate, 6)))
    return out


def build_retention_views(conn: sqlite3.Connection, cfg: dict) -> int:
    """按 config 的 cohort_days 动态创建留存视图，返回列数。

    字段清单后续可能补充（比如加 D60、D90），所以视图的列不写死在 SQL 里：
    改 cohort_days，表里的行和视图里的列会一起跟着变。
      · v_retention_wide  —— cohort_date + D1~Dn 全宽表（模块C 的交付形态）
      · v_retention_pivot —— 只保留常用里程碑（D1/D3/D7/D14/D30…），供诊断和看板用
    """
    days = int(cfg["retention_curve"].get("cohort_days", 30))
    cols = ",\n           ".join(
        f"MAX(CASE WHEN c.day_n = {n} THEN c.rate END) AS d{n}" for n in range(1, days + 1))
    milestones = [n for n in (1, 3, 7, 14, 30, 60, 90) if n <= days] or [1]
    key_cols = ", ".join(f"d{n}" for n in milestones)

    conn.executescript(f"""
DROP VIEW IF EXISTS v_retention_pivot;
DROP VIEW IF EXISTS v_retention_wide;

CREATE VIEW v_retention_wide AS
SELECT c.cohort_date,
       m.new_users,
       m.dau,
           {cols}
FROM retention_cohorts c
LEFT JOIN daily_metrics m ON m.date = c.cohort_date
GROUP BY c.cohort_date, m.new_users, m.dau;

CREATE VIEW v_retention_pivot AS
SELECT cohort_date, new_users, {key_cols} FROM v_retention_wide;
""")
    conn.commit()
    return days


# ================================================================
# 主流程
# ================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="游戏运营数据生成器")
    ap.add_argument("--days", type=int, default=None, help="从起点起累计生成的天数")
    ap.add_argument("--reset", action="store_true", help="清库重建")
    ap.add_argument("--config", type=str, default=str(CONFIG_PATH))
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    first = date.fromisoformat(cfg["sim"]["start_date"])
    today = date.today()
    cohort_days = int(cfg["retention_curve"].get("cohort_days", 30))

    if args.reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = connect(DB_PATH)
    fresh = not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_metrics'"
    ).fetchone()
    if fresh:
        build_schema(conn)

    # ---------- 剧本：首次固化为绝对日期，之后复用，保证剧情位置不漂移 ----------
    if fresh:
        events = plan_events(cfg, first)
        save_events(conn, events)
        cfg_set(conn, "config_snapshot", cfg, "生成时的完整配置留档")
        cfg_set(conn, "start_date", first.isoformat(), "数据起点（固定，不随运行日期变化）")
        print(f"[初始化] 起点 {first}　数据将由该日向后逐日累积")
        if events:
            print(f"[剧本] 已固化 {len(events)} 个事件")
    else:
        events = load_events(conn)
        first = date.fromisoformat(cfg_get(conn, "start_date", first.isoformat()))
        cfg_set(conn, "config_snapshot", cfg, "生成时的完整配置留档")

    # 留存视图的列数取决于 config，每次运行按当前配置重建（补字段不用改 SQL）
    build_retention_views(conn, cfg)

    # 留存模型：模块C 与模块A 共用，保证两条链路可互相复算
    model = RetentionModel(cfg, events, first)
    print(f"[留存] D1~D{cohort_days}　基准 D1 {model.base(1):.2%} → D7 {model.base(7):.2%} "
          f"→ D30 {model.base(min(30, cohort_days)):.2%}　"
          f"波动上限 ±{model.band:.1%}（{model.mode}）")

    # ---------- 决定本次生成哪些日期 ----------
    row = conn.execute("SELECT MAX(date) FROM daily_metrics").fetchone()
    last_in_db = date.fromisoformat(row[0]) if row and row[0] else None

    if last_in_db is None:
        total = args.days or cfg["sim"]["days"]
        todo = [first + timedelta(days=i) for i in range(total)]
    else:
        end_target = today if args.days is None else max(
            today, first + timedelta(days=args.days - 1)
        )
        todo = [last_in_db + timedelta(days=i)
                for i in range(1, (end_target - last_in_db).days + 1)]

    if not todo:
        print(f"[跳过] 数据已是最新（最后一天 {last_in_db}），无需生成。")
        conn.close()
        return 0

    # ---------- 载入历史新增（非新增活跃池的推导依据） ----------
    hist_rows = conn.execute("SELECT date, new_users FROM daily_metrics ORDER BY date").fetchall()
    history: list[tuple[date, int]] = [(date.fromisoformat(r[0]), r[1]) for r in hist_rows]

    state = {
        "tier_weight_mult": {},
        "tier_user_delta": {},
        "retention_mult": {},
    }
    saved = cfg_get(conn, "runtime_state")
    if saved:
        state.update(saved)

    # 增量场景：从库里取最后一天的取值，保证「均值回复」在跨次运行时连续
    prev_row = conn.execute(
        "SELECT new_users, pay_rate FROM daily_metrics ORDER BY date DESC LIMIT 1").fetchone()
    if prev_row:
        state["_prev"] = {"new_users": prev_row[0], "pay_rate": prev_row[1]}

    # 增量场景：补上「上次生成之后、本次开始之前」发生的事件影响
    if last_in_db is not None:
        for ev in events:
            ev_d = date.fromisoformat(ev["date"])
            if last_in_db < ev_d <= todo[0]:
                apply_persistent_impact(state, ev["impact"])

    events_by_date: dict[str, list[dict]] = {}
    for ev in events:
        events_by_date.setdefault(ev["date"], []).append(ev)

    # ---------- 逐日生成 ----------
    daily_rows, tier_rows, cohort_rows, event_log = [], [], [], []
    for d in todo:
        for ev in events_by_date.get(d.isoformat(), []):
            applied = apply_persistent_impact(state, ev["impact"])
            state["_one_shot"] = {"revenue_shock": ev["impact"]["revenue_shock"]} \
                if "revenue_shock" in ev["impact"] else {}
            event_log.append((d, ev["name"], applied))
        state.setdefault("_one_shot", {})

        daily, tiers = gen_day(d, first, state, cfg, events, history, model)
        daily_rows.append(tuple(daily[k] for k in (
            "date", "new_users", "stock_active", "dau",
            "pay_rate", "pay_users", "revenue", "created_at")))
        tier_rows.extend([
            (t["date"], t["tier_code"], t["tier_name"], t["tier_min"], t["tier_max"],
             t["sort_order"], t["users"], t["arppu"], t["revenue"]) for t in tiers
        ])
        cohort_rows.extend(
            gen_cohort_observation(d, first, history, cohort_days, model))
        history.append((d, daily["new_users"]))
        # 供下一天的均值回复取值使用
        state["_prev"] = {"new_users": daily["new_users"], "pay_rate": daily["pay_rate"]}
        state["_one_shot"] = {}

    # ---------- 落库 ----------
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_metrics "
            "(date, new_users, stock_active, dau, pay_rate, pay_users, revenue, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", daily_rows)
        conn.executemany(
            "INSERT OR REPLACE INTO revenue_tiers "
            "(date, tier_code, tier_name, tier_min, tier_max, sort_order, users, arppu, revenue) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", tier_rows)
        conn.executemany(
            "INSERT OR REPLACE INTO retention_cohorts (cohort_date, day_n, retained, rate) "
            "VALUES (?, ?, ?, ?)", cohort_rows)
        cfg_set(conn, "runtime_state", state, "运行状态快照（保证增量生成可续跑）")
        cfg_set(conn, "last_run", datetime.now().isoformat(timespec="seconds"), "上次生成时间")
        cfg_set(conn, "total_days_planned", (first + timedelta(days=(cfg["sim"]["days"] - 1))).isoformat(),
                "计划生成到的日期")

    # ---------- 摘要 ----------
    future = [d for d in todo if d > today]
    print(f"\n[生成] {cfg['game']['name']} · {todo[0]} → {todo[-1]}（{len(todo)} 天）")
    print(f"  daily_metrics      {len(daily_rows):>6} 行")
    print(f"  revenue_tiers      {len(tier_rows):>6} 行")
    print(f"  retention_cohorts  {len(cohort_rows):>6} 行")
    if future:
        print(f"  ⚠ 其中 {len(future)} 天日期晚于今天，属推演数据（{future[0]} → {future[-1]}）")

    if event_log:
        print("\n[剧本事件]")
        for d, name, applied in event_log:
            detail = "、".join(f"{k} {v}" for k, v in applied.items()) if applied else "一次性冲击"
            print(f"  · {d}  {name}  →  {detail}")

    stat = conn.execute(
        "SELECT COUNT(*), MIN(date), MAX(date), ROUND(AVG(dau)), ROUND(AVG(revenue)) "
        "FROM daily_metrics").fetchone()
    print(f"\n[库概况] {stat[0]} 天（{stat[1]} → {stat[2]}）　"
          f"平均 DAU {stat[3]:,.0f}　平均日流水 ¥{stat[4]:,.0f}")

    bad = conn.execute("SELECT COUNT(*) FROM v_consistency").fetchone()[0]
    print(f"[一致性巡检] 异常 {bad} 天" + ("　✅ 全部通过" if bad == 0 else "　❌ 请检查 v_consistency"))

    # ---------- 留存校验：实测波动幅度是否落在配置上限内 ----------
    worst_abs = worst_rel = 0.0
    checked = 0
    for c_s, n, rate in conn.execute(
            "SELECT cohort_date, day_n, rate FROM retention_cohorts WHERE rate IS NOT NULL"):
        base = model.base(n) * model.mult_fn(date.fromisoformat(c_s))(n)
        if base <= 0:
            continue
        checked += 1
        d_abs = abs(rate - base)
        worst_abs = max(worst_abs, d_abs)
        worst_rel = max(worst_rel, d_abs / base)
    if checked:
        avg = conn.execute(
            "SELECT ROUND(AVG(d1),4), ROUND(AVG(d7),4), ROUND(AVG(d30),4) "
            "FROM v_retention_wide WHERE d30 IS NOT NULL").fetchone()
        if avg and avg[0] is not None:
            print(f"[留存] 已成熟队列均值　D1 {avg[0]:.2%}　D7 {avg[1]:.2%}　D30 {avg[2]:.2%}")
        print(f"[留存波动] 观测 {checked} 条　相对基准最大偏离 {worst_rel:.2%}"
              f"（{worst_abs*100:.2f}pp）　上限 ±{model.band:.0%}"
              f"　{'✅ 未越界' if worst_rel <= model.band + 1e-9 else '⚠ 超出上限，请检查 monotonic 截断'}")

    size_kb = DB_PATH.stat().st_size / 1024
    print(f"[完成] 数据库：{DB_PATH.relative_to(ROOT_DIR)}（{size_kb:,.0f} KB）")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
