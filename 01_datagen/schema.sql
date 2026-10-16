-- ============================================================
-- 游戏运营数据闭环系统 · 数据库结构
-- 唯一数据源：data/game.db  （SQLite）
--
-- 结构对应字段清单：
--   模块A 大盘数据     → daily_metrics
--   模块B 付费分层数据  → revenue_tiers
--   模块C 留存数据      → retention_cohorts（长表存储）+ v_retention_wide（宽表视图，列按配置动态生成）
--   模块D 新增阈值      → new_user_thresholds（DAU 盈亏平衡线）
--
-- 扩展原则：所有档位、区间、边界全部来自 config.json，不写死在 SQL 里。
--          新增付费层级只需改配置，无需动表结构。
--          留存天数（D1~D30）同样不写死：宽表视图由 generator.py 按 config 的
--          cohort_days 动态创建，补充 D60 / D90 时本文件不需要改动。
-- ============================================================

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_consistency;
DROP VIEW  IF EXISTS v_threshold_daily;
DROP VIEW  IF EXISTS v_retention_wide;
DROP VIEW  IF EXISTS v_retention_pivot;
DROP VIEW  IF EXISTS v_tier_daily;
DROP VIEW  IF EXISTS v_daily_kpi;

DROP TRIGGER IF EXISTS trg_dau_consistency;

DROP TABLE IF EXISTS activity_effects;
DROP TABLE IF EXISTS activities;
DROP TABLE IF EXISTS revenue_tiers;
DROP TABLE IF EXISTS new_user_thresholds;
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
-- 模块D · 新增阈值（DAU 的盈亏平衡线）
--
--   字段1  date             日期
--   字段2  churned_users    每日流失用户数（昨日活跃中、今日未回流的人数）
--   字段3  threshold_users  每日新增用户数阈值（= 当日流失用户数）
--   字段4  new_users        当日新增用户数（放这里便于直接对照，值同模块A）
--   字段5  margin           安全边际 = 新增 − 阈值
--   字段6  status           涨跌状态 up / flat / down
--
--   口径与推导（全部依赖模块C 的留存数据）：
--     非新增活跃(t) 是由历史各日新增 × 留存率推导出来的，也就是
--     「昨天及更早活跃的用户中，今天仍回来的人」。
--     于是  当日流失用户数 = 昨日 DAU − 今日非新增活跃
--     由此得到恒等式
--         DAU(t) − DAU(t−1) = 新增(t) − 流失(t)
--     即：新增等于流失时 DAU 持平，高于流失时 DAU 上涨。
--     所以「每日新增阈值」在数值上就等于「当日流失用户数」——
--     这是定义推导出的结果，不是巧合。
--
--   prev_dau / stock_active 为辅助列，保留下来便于把阈值逐项复算回去。
--   起点首日不存在「昨日活跃」，阈值无定义，记 NULL 而不是 0
--   ——与留存队列「未成熟不写 0」保持同一套数据纪律。
-- ------------------------------------------------------------
CREATE TABLE new_user_thresholds (
    date             TEXT    PRIMARY KEY,   -- YYYY-MM-DD
    prev_dau         INTEGER,                -- 前一日 DAU（首日为 NULL）
    stock_active     INTEGER NOT NULL,       -- 当日非新增活跃（= 回流人数）
    churned_users    INTEGER,                -- 当日流失用户数（= 阈值）
    threshold_users  INTEGER,                -- 每日新增用户数阈值
    new_users        INTEGER NOT NULL,       -- 当日新增用户数
    margin           INTEGER,                -- 安全边际 = 新增 − 阈值
    status           TEXT                    -- up / flat / down
);


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


-- 新增阈值视图：直接可用的一行一天，带流失率与「连续同状态天数」
--   churn_rate = 阈值 ÷ 昨日 DAU，即当日活跃的流失比例
--                （判定留存好坏请看模块C 的队列留存率；此处的流失率会受
--                  「队列年龄结构」影响——起点阶段存量池全是新队列，流失率天然偏高）
--   dau_delta 是 DAU 的日环比增量，恒等于 margin（用于自检）
--   streak_days 是当前涨/跌状态已经连续了多少天（gaps & islands 写法）
CREATE VIEW v_threshold_daily AS
WITH base AS (
    SELECT
        t.date,
        t.prev_dau,
        t.stock_active,
        t.churned_users,
        t.threshold_users,
        t.new_users,
        t.margin,
        t.status,
        m.dau,
        m.dau - t.prev_dau AS dau_delta,
        CASE WHEN t.prev_dau IS NULL OR t.prev_dau = 0 THEN NULL
             ELSE ROUND(t.threshold_users * 1.0 / t.prev_dau, 6) END AS churn_rate
    FROM new_user_thresholds t
    JOIN daily_metrics m ON m.date = t.date
),
island AS (
    SELECT *,
        ROW_NUMBER() OVER (ORDER BY date)
      - ROW_NUMBER() OVER (PARTITION BY status ORDER BY date) AS grp
    FROM base
)
SELECT
    date,
    prev_dau,
    stock_active,
    churned_users,
    threshold_users,
    new_users,
    margin,
    status,
    dau,
    dau_delta,
    churn_rate,
    COUNT(*) OVER (PARTITION BY status, grp) AS streak_days
FROM island;


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
HAVING ABS(SUM(t.revenue) - m.revenue) > 0.05

UNION ALL

-- 模块D 恒等式自检：安全边际必须恒等于 DAU 的日环比增量
SELECT m.date, '安全边际 ≠ DAU 日环比增量',
       t.margin, m.dau - t.prev_dau
FROM new_user_thresholds t JOIN daily_metrics m ON m.date = t.date
WHERE t.prev_dau IS NOT NULL
  AND t.margin <> m.dau - t.prev_dau

UNION ALL

-- 模块D 口径自检：阈值必须等于当日流失用户数
SELECT t.date, '阈值 ≠ 当日流失用户数',
       t.threshold_users, t.churned_users
FROM new_user_thresholds t
WHERE t.churned_users IS NOT NULL
  AND t.threshold_users <> t.churned_users;
