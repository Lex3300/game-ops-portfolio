-- ============================================================
-- 游戏运营数据闭环系统 · 数据库结构
-- 唯一数据源：data/game.db  （SQLite）
--
-- 结构对应字段清单：
--   模块A 大盘数据     → daily_metrics
--   模块B 付费分层数据  → revenue_tiers
--   DAU 的推导依据      → retention_cohorts
--
-- 扩展原则：所有档位、区间、边界全部来自 config.json，不写死在 SQL 里。
--          新增层级只需改配置，无需动表结构。
-- ============================================================

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_consistency;
DROP VIEW  IF EXISTS v_retention_pivot;
DROP VIEW  IF EXISTS v_tier_daily;
DROP VIEW  IF EXISTS v_daily_kpi;

DROP TRIGGER IF EXISTS trg_dau_consistency;

DROP TABLE IF EXISTS activity_effects;
DROP TABLE IF EXISTS activities;
DROP TABLE IF EXISTS revenue_tiers;
DROP TABLE IF EXISTS retention_cohorts;
DROP TABLE IF EXISTS daily_metrics;
DROP TABLE IF EXISTS story_events;
DROP TABLE IF EXISTS sim_config;


-- ------------------------------------------------------------
-- 模块A · 大盘数据
--   date          字段1  日期
--   new_users     字段2  每日新增用户数
--   stock_active  字段3  每日非新增活跃用户数（由历史新增 + 留存推导）
--   dau           字段3  每日活跃用户数 = stock_active + new_users
--   pay_rate      字段4  每日付费率
--   pay_users     字段5  付费用户数 = dau × pay_rate（模块B字段2）
--   revenue       字段5  每日流水（由付费分层汇总得出）
-- ------------------------------------------------------------
CREATE TABLE daily_metrics (
    date          TEXT    PRIMARY KEY,        -- YYYY-MM-DD
    new_users     INTEGER NOT NULL,
    stock_active  INTEGER NOT NULL,
    dau           INTEGER NOT NULL,
    pay_rate      REAL    NOT NULL,
    pay_users     INTEGER NOT NULL,
    revenue       REAL    NOT NULL,
    created_at    TEXT    NOT NULL
);

-- 硬约束：DAU 必须严格等于 非新增活跃 + 新增
CREATE TRIGGER trg_dau_consistency
BEFORE INSERT ON daily_metrics
FOR EACH ROW
WHEN NEW.dau <> NEW.stock_active + NEW.new_users
BEGIN
    SELECT RAISE(ABORT, 'DAU 必须等于 非新增活跃 + 新增用户数');
END;


-- ------------------------------------------------------------
-- 模块B · 付费分层数据（长表结构，档位数量不限）
--   字段3~12 = N 个档位 × (付费用户数, ARPPU)
--   约束：同一 date 下 SUM(users)                  = daily_metrics.pay_users
--        同一 date 下 SUM(users × arppu)          = daily_metrics.revenue
-- ------------------------------------------------------------
CREATE TABLE revenue_tiers (
    date       TEXT    NOT NULL,
    tier_code  TEXT    NOT NULL,              -- 档位代号，如 L1
    tier_name  TEXT    NOT NULL,              -- 档位名称，如 "0-10元"
    tier_min   REAL,                          -- 区间下界
    tier_max   REAL,                          -- 区间上界（NULL = 无上限）
    sort_order INTEGER NOT NULL,              -- 展示排序
    users      INTEGER NOT NULL,              -- 该档付费用户数
    arppu      REAL    NOT NULL,              -- 该档 ARPPU
    revenue    REAL    NOT NULL,              -- 该档流水 = users × arppu
    PRIMARY KEY (date, tier_code)
);

CREATE INDEX idx_tier_date ON revenue_tiers (date, sort_order);


-- ------------------------------------------------------------
-- 留存队列 · DAU 的推导依据，同时供诊断使用
--   retained / rate 为 NULL 表示「队列尚未成熟」，不是 0
-- ------------------------------------------------------------
CREATE TABLE retention_cohorts (
    cohort_date   TEXT    NOT NULL,
    day_n         INTEGER NOT NULL,
    retained      INTEGER,
    rate          REAL,
    PRIMARY KEY (cohort_date, day_n)
);

CREATE INDEX idx_cohort_day ON retention_cohorts (day_n, cohort_date);


-- ------------------------------------------------------------
-- 活动表 · 模块③ 活动 Agent 的产出
-- ------------------------------------------------------------
CREATE TABLE activities (
    activity_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    form            TEXT NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT,
    target_tier     TEXT,
    target_metric   TEXT,
    expected_lift   REAL,
    status          TEXT NOT NULL,
    rationale       TEXT
);

CREATE INDEX idx_act_date ON activities (start_date, end_date);


-- ------------------------------------------------------------
-- 活动效果回流表 · 活动到底有没有用，用数据说话
-- ------------------------------------------------------------
CREATE TABLE activity_effects (
    activity_id  TEXT NOT NULL,
    date         TEXT NOT NULL,
    metric       TEXT NOT NULL,
    baseline     REAL,
    actual       REAL,
    lift         REAL,
    PRIMARY KEY (activity_id, date, metric)
);


-- ------------------------------------------------------------
-- 剧本事件 · 生成器的「剧情」，让每根曲线都有解释
-- ------------------------------------------------------------
CREATE TABLE story_events (
    event_id     TEXT PRIMARY KEY,
    event_date   TEXT NOT NULL,
    day_index    INTEGER NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT,
    impact       TEXT
);

CREATE INDEX idx_event_date ON story_events (event_date);


-- ------------------------------------------------------------
-- 模拟参数 · 落库留档，保证数据可解释、可复现
-- ------------------------------------------------------------
CREATE TABLE sim_config (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL,
    note   TEXT
);


-- ============================================================
-- 视图
-- ============================================================

CREATE VIEW v_daily_kpi AS
SELECT
    date,
    new_users,
    stock_active,
    dau,
    pay_users,
    pay_rate,
    ROUND(revenue, 2)             AS revenue,
    ROUND(revenue / dau, 2)       AS arpu,
    ROUND(revenue / pay_users, 2) AS arppu
FROM daily_metrics;


CREATE VIEW v_tier_daily AS
SELECT
    date,
    tier_code,
    tier_name,
    sort_order,
    users,
    ROUND(users * 1.0 / SUM(users) OVER (PARTITION BY date), 6)     AS user_share,
    arppu,
    ROUND(revenue, 2)                                               AS revenue,
    ROUND(revenue / SUM(revenue) OVER (PARTITION BY date), 6)       AS revenue_share
FROM revenue_tiers;


CREATE VIEW v_retention_pivot AS
SELECT
    c.cohort_date,
    m.new_users,
    MAX(CASE WHEN c.day_n = 1  THEN c.rate END) AS d1,
    MAX(CASE WHEN c.day_n = 3  THEN c.rate END) AS d3,
    MAX(CASE WHEN c.day_n = 7  THEN c.rate END) AS d7,
    MAX(CASE WHEN c.day_n = 14 THEN c.rate END) AS d14,
    MAX(CASE WHEN c.day_n = 30 THEN c.rate END) AS d30,
    MAX(CASE WHEN c.day_n = 60 THEN c.rate END) AS d60,
    MAX(CASE WHEN c.day_n = 90 THEN c.rate END) AS d90
FROM retention_cohorts c
LEFT JOIN daily_metrics m ON m.date = c.cohort_date
GROUP BY c.cohort_date, m.new_users;


-- 一致性巡检视图：查出任何一行都说明数据有问题
CREATE VIEW v_consistency AS
SELECT m.date, '分层人数之和 ≠ 付费用户数' AS issue,
       SUM(t.users) AS tier_value, m.pay_users AS ref_value
FROM revenue_tiers t JOIN daily_metrics m ON m.date = t.date
GROUP BY m.date
HAVING SUM(t.users) <> m.pay_users

UNION ALL

SELECT m.date, '分层流水之和 ≠ 日流水',
       ROUND(SUM(t.revenue), 2), ROUND(m.revenue, 2)
FROM revenue_tiers t JOIN daily_metrics m ON m.date = t.date
GROUP BY m.date
HAVING ABS(SUM(t.revenue) - m.revenue) > 0.05;
