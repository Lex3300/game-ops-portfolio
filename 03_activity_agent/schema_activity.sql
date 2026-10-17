-- ============================================================
-- 模块③ 活动 Agent · 活动库与排期表结构
-- ============================================================
-- 说明
--   01_datagen/schema.sql 里的 activities / activity_effects 是早期
--   预留的执行记录表，当前未使用；活动库、配置、排期都以下列表为准。
--
-- 建模要点
--   1. activity_master   活动库总表：主数据，activity_id 主键，一行一个活动形式；
--                        config_table 记录该活动专属配置表的名字
--   2. cfg_act_xxx       活动配置表：**一个活动一张表**。表名 = 'cfg_' +
--                        activity_id 小写、'-' 换成 '_'，如
--                        ACT-GIFT-001 → cfg_act_gift_001。
--                        每张表只放一个活动的配置、表内只有一行，activity_id 是固定值；
--                        表结构按活动类型决定（同类型字段一致，便于横向对比）。
--                        27 张表的建表语句由 activity_engine.py 生成并落在
--                        03_activity_agent/config_tables.sql，可直接查阅/维护。
--   3. activity_schedule 排期表：activity_id 是外键，一个活动可排多期，
--                        因此用 schedule_id（排期实例）做主键
--   4. activity_change_log 变更流水：每次生成记录 add / update / keep，
--                        配合 frozen 字段自证「已定档未被动过」
--
-- 为什么一活动一表
--   7 大类型的参数集差异很大：抽奖要保底次数、排行榜要排行指标、限时收益要倍率。
--   挤在一张宽表里会有一半列长期为空，读一个活动的配置得横向扫过无关字段，
--   改配置也容易误伤别的活动。一活动一表后，打开表就是该活动的全部参数。
--
-- 全部 IF NOT EXISTS，脚本可反复执行。
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 0. 清理旧版本遗留对象
--    早期把配置放在一张 activity_config 宽表里，现已拆成 27 张独立表；
--    数据全部由 arsenal_seed.json 重新灌入，不存在不可再生的内容。
-- ------------------------------------------------------------
DROP VIEW IF EXISTS v_activity_full;
DROP TABLE IF EXISTS activity_config;

-- ------------------------------------------------------------
-- 1. 活动库总表（主数据）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_master (
    activity_id   TEXT PRIMARY KEY,          -- 活动 ID，主键，如 ACT-GIFT-001
    name          TEXT NOT NULL,             -- 活动名称
    type          TEXT NOT NULL,             -- 礼包/权益/抽奖/任务/排行榜/特殊/商城
    target        TEXT NOT NULL,             -- 全量/新用户/中小R/中大R/大R/流失召回
    duration_days INTEGER,                   -- 默认持续天数；NULL = 长期常驻
    cadence       TEXT,                      -- 常驻/周度/月度/周末/节点
    difficulty    TEXT,                      -- 简单/中等/较难/核心设计
    risk          TEXT NOT NULL DEFAULT 'low', -- low / mid / high（口碑风险）
    purpose       TEXT,                      -- 活动目的（拉新/留存/付费率/ARPPU…）
    lever         TEXT,                      -- 作用杠杆：付费率/ARPPU/DAU/留存/回流/消耗
    config_table  TEXT,                      -- 该活动专属配置表名，如 cfg_act_gift_001
    enabled       INTEGER NOT NULL DEFAULT 1,-- 1 启用 / 0 停用
    note          TEXT                       -- 备注
);

-- 老库兼容：早期版本没有 config_table 列（引擎里另有 ALTER 兜底）
-- ALTER TABLE activity_master ADD COLUMN config_table TEXT;

-- ------------------------------------------------------------
-- 2. 各活动专属配置表（27 张，见 config_tables.sql）
--    命名规则：cfg_ + activity_id 小写，'-' → '_'
--    结构：activity_id（固定值）+ 该类型的参数列 + updated_at
-- ------------------------------------------------------------

-- ------------------------------------------------------------
-- 3. 排期表（活动实例；一个活动可排多期）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_schedule (
    schedule_id TEXT PRIMARY KEY,            -- 排期 ID，如 SCH-202610-001
    activity_id TEXT NOT NULL
                REFERENCES activity_master(activity_id),
    instance_name TEXT,                      -- 排期实例名（含「第 N 期」等后缀），空则用活动库名
    month       TEXT NOT NULL,               -- 归属月份，如 2026-10
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    rule_code   TEXT,                        -- 触发规则编号，如 R-STRUCT-01
    rule_note   TEXT,                        -- 触发规则说明（排期依据）
    frozen      INTEGER NOT NULL DEFAULT 0,  -- 1 = 已定档，引擎不再改动
    frozen_at   TEXT,                        -- 定档日期（= 上线日）
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sched_month ON activity_schedule (month, start_date);

-- ------------------------------------------------------------
-- 4. 变更流水
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_change_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at    TEXT NOT NULL,
    action    TEXT NOT NULL,                 -- add / update / keep
    schedule_id TEXT,
    activity_id TEXT,
    detail    TEXT
);

-- ------------------------------------------------------------
-- 5. 配置变更流水（看板区块04「一键发布」写入）
--    与排期变更分开记：一个是活动实例，一个是配置值
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config_change_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at TEXT NOT NULL,                -- 发布时间
    activity_id TEXT NOT NULL,
    field      TEXT NOT NULL,                -- 配置字段名
    old_value  TEXT,
    new_value  TEXT,
    source     TEXT,                         -- suggestion（建议带入）/ manual（人工改表）
    rule_code  TEXT,                         -- source=suggestion 时的规则编号
    batch      TEXT                          -- 同一次发布的批次号
);

CREATE INDEX IF NOT EXISTS idx_cfglog_time ON config_change_log (changed_at);

-- ------------------------------------------------------------
-- 视图：排期 + 活动信息（看板与报表都读这个）
--   实例名优先（「第 N 期」这类后缀不会丢），没有才回落到活动库名
-- ------------------------------------------------------------
DROP VIEW IF EXISTS v_activity_schedule;
CREATE VIEW v_activity_schedule AS
SELECT s.schedule_id, s.activity_id,
       COALESCE(NULLIF(s.instance_name, ''), m.name) AS name,
       m.type, m.target, m.risk,
       s.month, s.start_date, s.end_date,
       CAST(julianday(s.end_date) - julianday(s.start_date) AS INTEGER) + 1 AS days,
       s.rule_code, s.rule_note, s.frozen, s.frozen_at, s.created_at, s.updated_at
FROM activity_schedule s
JOIN activity_master m ON m.activity_id = s.activity_id;
