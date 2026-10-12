-- ============================================================
-- 游戏运营数据闭环系统 · 数据库结构
-- 唯一数据源：data/game.db  （SQLite）
--
-- 设计原则
--   1. 分层建模：日粒度指标 / 留存队列 / 付费分层 三张事实表 + 活动两张表
--   2. 可追溯：剧本事件单独落库，看板能标注曲线上的拐点
--   3. 派生指标用视图算，不冗余存储，避免口径不一致
-- ============================================================

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_daily_kpi;
DROP VIEW  IF EXISTS v_tier_daily;
DROP VIEW  IF EXISTS v_retention_pivot;

DROP TABLE IF EXISTS activity_effects;
DROP TABLE IF EXISTS activities;
DROP TABLE IF EXISTS revenue_tiers;
DROP TABLE IF EXISTS retention_cohorts;
DROP TABLE IF EXISTS daily_metrics;
DROP TABLE IF EXISTS story_events;
DROP TABLE IF EXISTS sim_config;


-- ------------------------------------------------------------
-- 1. 日粒度指标表 · 对应运营日报主表
-- ------------------------------------------------------------
CREATE TABLE daily_metrics (
    date              TEXT    PRIMARY KEY,          -- 日期 YYYY-MM-DD
    new_users         INTEGER NOT NULL,             -- 新增用户数
    dau               INTEGER NOT NULL,             -- 活跃用户数 DAU
    returning_users   INTEGER NOT NULL,             -- 回流用户数
    pay_users         INTEGER NOT NULL,             -- 当日付费用户数
    revenue           REAL    NOT NULL,             -- 当日充值总金额(元)
    avg_session_min   REAL    NOT NULL,             -- 人均在线时长(分钟)
    created_at        TEXT    NOT NULL              -- 入库时间
);


-- ------------------------------------------------------------
-- 2. 留存队列表 · 对应日报里 "44(17.33%)" 这种列
--    retained / rate 为 NULL 表示「队列尚未成熟」，不是 0
-- ------------------------------------------------------------
CREATE TABLE retention_cohorts (
    cohort_date   TEXT    NOT NULL,                 -- 注册日期(队列)
    day_n         INTEGER NOT NULL,                 -- 第 N 日留存
    retained      INTEGER,                          -- 留存人数(NULL=未成熟)
    rate          REAL,                             -- 留存率  (NULL=未成熟)
    PRIMARY KEY (cohort_date, day_n)
);

CREATE INDEX idx_cohort_day ON retention_cohorts (day_n, cohort_date);


-- ------------------------------------------------------------
-- 3. 付费分层表 · 变现盘结构诊断
--    约束：同一 date 下各层 users 之和 = 日付费用户数(含非R则 = DAU)
--          同一 date 下各层 revenue 之和 = 日充值总额
-- ------------------------------------------------------------
CREATE TABLE revenue_tiers (
    date       TEXT    NOT NULL,
    tier       TEXT    NOT NULL,                    -- 非R / 小R / 中R / 大R
    users      INTEGER NOT NULL,                    -- 该层人数
    revenue    REAL    NOT NULL,                    -- 该层流水(元)
    PRIMARY KEY (date, tier)
);


-- ------------------------------------------------------------
-- 4. 活动表 · 模块③ 活动 Agent 的产出
-- ------------------------------------------------------------
CREATE TABLE activities (
    activity_id     TEXT PRIMARY KEY,               -- 活动编号
    name            TEXT NOT NULL,                  -- 活动名称
    category        TEXT NOT NULL,                  -- 商城/礼包/权益/抽奖/任务/排行榜/特殊
    form            TEXT NOT NULL,                  -- 具体形式
    start_date      TEXT NOT NULL,
    end_date        TEXT,
    target_tier     TEXT,                           -- 主投人群
    target_metric   TEXT,                           -- 目标指标
    expected_lift   REAL,                           -- 预期提升幅度(0.15 = +15%)
    status          TEXT NOT NULL,                  -- planned / running / finished
    rationale       TEXT                            -- 缺口归因(为什么要上这个)
);

CREATE INDEX idx_act_date ON activities (start_date, end_date);


-- ------------------------------------------------------------
-- 5. 活动效果回流表 · 活动是否真的起作用，用数据说话
-- ------------------------------------------------------------
CREATE TABLE activity_effects (
    activity_id  TEXT NOT NULL,
    date         TEXT NOT NULL,
    metric       TEXT NOT NULL,                     -- 指标名
    baseline     REAL,                              -- 无活动时的基线
    actual       REAL,                              -- 实际观测值
    lift         REAL,                              -- 提升幅度
    PRIMARY KEY (activity_id, date, metric)
);


-- ------------------------------------------------------------
-- 6. 剧本事件表 · 生成器的「剧情」，让每根曲线都有解释
-- ------------------------------------------------------------
CREATE TABLE story_events (
    event_id     TEXT PRIMARY KEY,
    event_date   TEXT NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT,
    impact       TEXT                               -- JSON: 影响的参数与幅度
);

CREATE INDEX idx_event_date ON story_events (event_date);


-- ------------------------------------------------------------
-- 7. 模拟参数表 · 落库留档，保证数据可解释、可复现
-- ------------------------------------------------------------
CREATE TABLE sim_config (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL,
    note   TEXT
);


-- ============================================================
-- 视图：派生指标统一在这里算
-- ============================================================

CREATE VIEW v_daily_kpi AS
SELECT
    date,
    new_users,
    dau,
    returning_users,
    pay_users,
    revenue,
    avg_session_min,
    ROUND(pay_users * 1.0 / dau, 6)  AS pay_rate,   -- 付费率
    ROUND(revenue / pay_users, 2)    AS arppu,      -- 每付费用户收入
    ROUND(revenue / dau, 2)          AS arpu        -- 每活跃用户收入
FROM daily_metrics;


CREATE VIEW v_tier_daily AS
SELECT
    t.date,
    t.tier,
    t.users,
    t.revenue,
    ROUND(t.users * 1.0 / SUM(t.users) OVER (PARTITION BY t.date), 6)   AS user_share,
    ROUND(t.revenue / SUM(t.revenue) OVER (PARTITION BY t.date), 6)     AS revenue_share,
    CASE WHEN t.users > 0 THEN ROUND(t.revenue / t.users, 2) END        AS arpu_tier
FROM revenue_tiers t
WHERE t.tier <> '非R';   -- 非R不参与付费结构判定


CREATE VIEW v_retention_pivot AS
SELECT
    cohort_date,
    new_users,
    MAX(CASE WHEN day_n = 1  THEN rate END) AS d1,
    MAX(CASE WHEN day_n = 3  THEN rate END) AS d3,
    MAX(CASE WHEN day_n = 7  THEN rate END) AS d7,
    MAX(CASE WHEN day_n = 14 THEN rate END) AS d14,
    MAX(CASE WHEN day_n = 30 THEN rate END) AS d30,
    MAX(CASE WHEN day_n = 60 THEN rate END) AS d60,
    MAX(CASE WHEN day_n = 90 THEN rate END) AS d90
FROM (
    SELECT c.cohort_date, c.day_n, c.rate, m.new_users
    FROM retention_cohorts c
    LEFT JOIN daily_metrics m ON m.date = c.cohort_date
) x
GROUP BY cohort_date, new_users;
