-- ============================================================
-- 游戏运营数据闭环系统 · 数据库结构
-- 唯一数据源：data/game.db  （SQLite）
--
-- 结构对应字段清单：
--   模块A 大盘数据     → daily_metrics
--   模块B 付费分层数据  → revenue_tiers
--   模块C 留存数据      → retention_cohorts（长表存储）+ v_retention_wide（宽表视图，列按配置动态生成）
--
-- 扩展原则：所有档位、区间、边界全部来自 config.json，不写死在 SQL 里。
--          新增付费层级只需改配置，无需动表结构。
--          留存天数（D1~D30）同样不写死：宽表视图由 generator.py 按 config 的
--          cohort_days 动态创建，补充 D60 / D90 时本文件不需要改动。
-- ============================================================

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_consistency;
DROP VIEW  IF EXISTS v_retention_wide;
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
-- 模块C · 留存数据（长表存储 / 宽表输出）
--   字段1 = cohort_date（日期 = 新增队列日）
--   字段2~31 = day_n 1~30，即 D1~D30 留存率
--
--   为什么用长表存、用视图出宽表：
--     长表结构下「留存天数」不是列，而是行，补 D60/D90 只是多几行数据，不用改表；
--     出报表时再由 v_retention_wide 转成 D1~D30 的宽表形态。
--
--   rate / retained 为 NULL 表示「队列尚未成熟」，不是 0
--   —— day_n 的观测值只在 cohort_date + day_n 那天才写入，未成熟不落库。
-- ------------------------------------------------------------
CREATE TABLE retention_cohorts (
    cohort_date   TEXT    NOT NULL,
    day_n         INTEGER NOT NULL,
    retained      INTEGER,                    -- 该队列在 day_n 仍活跃的人数
    rate          REAL,                       -- 留存率 = retained / cohort 当日新增
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


-- 留存宽表 v_retention_pivot / v_retention_wide 不在这里定义：
-- 其列数（D1~D30）取决于 config 的 cohort_days，由 generator.py 的
-- build_retention_views() 在每次运行时按配置动态创建，避免把字段清单写死。


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
