-- ==============================================================
-- 模块③ 活动 Agent · 27 张活动配置表（引擎自动生成）
-- ==============================================================
-- 一个活动一张表：cfg_ + activity_id 小写、'-' 换 '_'
--   ACT-GIFT-001 → cfg_act_gift_001
--
-- 本文件 = 表结构 + 当前生效配置值（配置即代码，可直接 diff / 回滚）。
--   表结构 ← activity_engine.py 的 CONFIG_TEMPLATES
--   配置值 ← arsenal_seed.json（由看板区块04「一键发布」从 Excel 回写）
-- 查某个活动的配置 → 看它那一段的 INSERT 语句，或打开库里对应的表。
--
-- 活动数：27　种子版本：2026-10-17　配置时间：2026-10-17T12:00:00
-- ==============================================================

-- ------------------------------------------------------------------
-- ACT-GIFT-001 · 首充礼包·双倍重置
--   礼包 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_gift_001 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-GIFT-001'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 价格/档位，多档用 / 分隔，如 6/30/98
    reward_desc    TEXT,     -- 奖励内容说明
    limit_per_user INTEGER,  -- 每人限购/限领次数
    stock          INTEGER,  -- 库存/限量份数；NULL = 不限量
    cycle          TEXT,     -- 刷新周期：日/周/月/赛季/一次性
    trigger_cond   TEXT,     -- 触发条件；NULL = 无门槛
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_gift_001 (activity_id, price_tiers, reward_desc, limit_per_user, cycle, updated_at)
  VALUES ('ACT-GIFT-001', '6/30/98', '首充双倍钻石', 1, '终身 1 次（可重置）', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-GIFT-002 · 每日礼包轮换
--   礼包 / 中小R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_gift_002 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-GIFT-002'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 价格/档位，多档用 / 分隔，如 6/30/98
    reward_desc    TEXT,     -- 奖励内容说明
    limit_per_user INTEGER,  -- 每人限购/限领次数
    stock          INTEGER,  -- 库存/限量份数；NULL = 不限量
    cycle          TEXT,     -- 刷新周期：日/周/月/赛季/一次性
    trigger_cond   TEXT,     -- 触发条件；NULL = 无门槛
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_gift_002 (activity_id, price_tiers, reward_desc, limit_per_user, cycle, updated_at)
  VALUES ('ACT-GIFT-002', '6/30/68', '每日轮换资源包', 1, '日', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-GIFT-003 · 回归玩家专属礼包
--   礼包 / 流失召回；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_gift_003 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-GIFT-003'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 价格/档位，多档用 / 分隔，如 6/30/98
    reward_desc    TEXT,     -- 奖励内容说明
    limit_per_user INTEGER,  -- 每人限购/限领次数
    stock          INTEGER,  -- 库存/限量份数；NULL = 不限量
    cycle          TEXT,     -- 刷新周期：日/周/月/赛季/一次性
    trigger_cond   TEXT,     -- 触发条件；NULL = 无门槛
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_gift_003 (activity_id, price_tiers, reward_desc, limit_per_user, cycle, trigger_cond, updated_at)
  VALUES ('ACT-GIFT-003', '1/6', '回归补给包', 1, '一次性', '连续 14 天未登录', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-GIFT-004 · 新手 7 日礼包链
--   礼包 / 新用户；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_gift_004 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-GIFT-004'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 价格/档位，多档用 / 分隔，如 6/30/98
    reward_desc    TEXT,     -- 奖励内容说明
    limit_per_user INTEGER,  -- 每人限购/限领次数
    stock          INTEGER,  -- 库存/限量份数；NULL = 不限量
    cycle          TEXT,     -- 刷新周期：日/周/月/赛季/一次性
    trigger_cond   TEXT,     -- 触发条件；NULL = 无门槛
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_gift_004 (activity_id, price_tiers, reward_desc, limit_per_user, cycle, updated_at)
  VALUES ('ACT-GIFT-004', '6/30', '7 日逐日资源 + 进阶档', 7, '日', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-GIFT-005 · 限时礼包·节点特惠
--   礼包 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_gift_005 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-GIFT-005'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 价格/档位，多档用 / 分隔，如 6/30/98
    reward_desc    TEXT,     -- 奖励内容说明
    limit_per_user INTEGER,  -- 每人限购/限领次数
    stock          INTEGER,  -- 库存/限量份数；NULL = 不限量
    cycle          TEXT,     -- 刷新周期：日/周/月/赛季/一次性
    trigger_cond   TEXT,     -- 触发条件；NULL = 无门槛
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_gift_005 (activity_id, price_tiers, reward_desc, limit_per_user, cycle, updated_at)
  VALUES ('ACT-GIFT-005', '30/128', '节点限定资源包', 2, '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-GIFT-006 · 终身限量礼包
--   礼包 / 中大R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_gift_006 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-GIFT-006'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 价格/档位，多档用 / 分隔，如 6/30/98
    reward_desc    TEXT,     -- 奖励内容说明
    limit_per_user INTEGER,  -- 每人限购/限领次数
    stock          INTEGER,  -- 库存/限量份数；NULL = 不限量
    cycle          TEXT,     -- 刷新周期：日/周/月/赛季/一次性
    trigger_cond   TEXT,     -- 触发条件；NULL = 无门槛
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_gift_006 (activity_id, price_tiers, reward_desc, limit_per_user, stock, cycle, updated_at)
  VALUES ('ACT-GIFT-006', '328/648', '终身限量资源包', 1, 2000, '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-GIFT-007 · 周/月礼包
--   礼包 / 中小R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_gift_007 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-GIFT-007'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 价格/档位，多档用 / 分隔，如 6/30/98
    reward_desc    TEXT,     -- 奖励内容说明
    limit_per_user INTEGER,  -- 每人限购/限领次数
    stock          INTEGER,  -- 库存/限量份数；NULL = 不限量
    cycle          TEXT,     -- 刷新周期：日/周/月/赛季/一次性
    trigger_cond   TEXT,     -- 触发条件；NULL = 无门槛
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_gift_007 (activity_id, price_tiers, reward_desc, limit_per_user, cycle, updated_at)
  VALUES ('ACT-GIFT-007', '30/98', '周档资源合集', 1, '周', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-BEN-001 · 周卡 / 月卡
--   权益 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_ben_001 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-BEN-001'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 购买价/档位，如 30/128
    reward_desc    TEXT,     -- 权益内容（每日领取 / 免费轨+付费轨 / 等级返还）
    limit_per_user INTEGER,  -- 每人可购份数
    cycle          TEXT,     -- 生效与刷新周期：日/月/赛季
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_ben_001 (activity_id, price_tiers, reward_desc, cycle, updated_at)
  VALUES ('ACT-BEN-001', '30/128', '每日登录领 1 份', '日', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-BEN-002 · 月度通行证
--   权益 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_ben_002 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-BEN-002'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 购买价/档位，如 30/128
    reward_desc    TEXT,     -- 权益内容（每日领取 / 免费轨+付费轨 / 等级返还）
    limit_per_user INTEGER,  -- 每人可购份数
    cycle          TEXT,     -- 生效与刷新周期：日/月/赛季
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_ben_002 (activity_id, price_tiers, reward_desc, cycle, updated_at)
  VALUES ('ACT-BEN-002', '68', '免费轨 + 付费轨', '月', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-BEN-003 · 等级基金
--   权益 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_ben_003 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-BEN-003'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 购买价/档位，如 30/128
    reward_desc    TEXT,     -- 权益内容（每日领取 / 免费轨+付费轨 / 等级返还）
    limit_per_user INTEGER,  -- 每人可购份数
    cycle          TEXT,     -- 生效与刷新周期：日/月/赛季
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_ben_003 (activity_id, price_tiers, reward_desc, cycle, updated_at)
  VALUES ('ACT-BEN-003', '98/198', '按等级返还资源', '赛季', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-BEN-004 · 赛季通行证
--   权益 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_ben_004 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-BEN-004'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 购买价/档位，如 30/128
    reward_desc    TEXT,     -- 权益内容（每日领取 / 免费轨+付费轨 / 等级返还）
    limit_per_user INTEGER,  -- 每人可购份数
    cycle          TEXT,     -- 生效与刷新周期：日/月/赛季
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_ben_004 (activity_id, price_tiers, reward_desc, cycle, updated_at)
  VALUES ('ACT-BEN-004', '68/128', '赛季任务积分兑换', '赛季', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-DRAW-001 · 定向抽奖
--   抽奖 / 大R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_draw_001 (
    activity_id TEXT PRIMARY KEY
                DEFAULT 'ACT-DRAW-001'
                REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers TEXT,     -- 单抽/十连价，如 6/68
    reward_desc TEXT,     -- 奖池与大奖说明
    pity_times  INTEGER,  -- 保底次数：累计 N 次必得大奖
    stock       INTEGER,  -- 奖池限量份数；NULL = 不限量
    cycle       TEXT,     -- 刷新周期：日/一次性
    updated_at  TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_draw_001 (activity_id, price_tiers, reward_desc, pity_times, cycle, updated_at)
  VALUES ('ACT-DRAW-001', '6/68', '自选大奖池 + 保底', 60, '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-DRAW-002 · 保底抽奖
--   抽奖 / 大R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_draw_002 (
    activity_id TEXT PRIMARY KEY
                DEFAULT 'ACT-DRAW-002'
                REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers TEXT,     -- 单抽/十连价，如 6/68
    reward_desc TEXT,     -- 奖池与大奖说明
    pity_times  INTEGER,  -- 保底次数：累计 N 次必得大奖
    stock       INTEGER,  -- 奖池限量份数；NULL = 不限量
    cycle       TEXT,     -- 刷新周期：日/一次性
    updated_at  TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_draw_002 (activity_id, price_tiers, reward_desc, pity_times, cycle, updated_at)
  VALUES ('ACT-DRAW-002', '6/30', '累计 N 次必得大奖（抽数进度可视化，保底跨期继承）', 45, '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-DRAW-003 · 免费抽奖券/活跃抽奖
--   抽奖 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_draw_003 (
    activity_id TEXT PRIMARY KEY
                DEFAULT 'ACT-DRAW-003'
                REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers TEXT,     -- 单抽/十连价，如 6/68
    reward_desc TEXT,     -- 奖池与大奖说明
    pity_times  INTEGER,  -- 保底次数：累计 N 次必得大奖
    stock       INTEGER,  -- 奖池限量份数；NULL = 不限量
    cycle       TEXT,     -- 刷新周期：日/一次性
    updated_at  TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_draw_003 (activity_id, reward_desc, cycle, updated_at)
  VALUES ('ACT-DRAW-003', '每日活跃送 1 抽', '日', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-DRAW-004 · 存量抽奖
--   抽奖 / 大R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_draw_004 (
    activity_id TEXT PRIMARY KEY
                DEFAULT 'ACT-DRAW-004'
                REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers TEXT,     -- 单抽/十连价，如 6/68
    reward_desc TEXT,     -- 奖池与大奖说明
    pity_times  INTEGER,  -- 保底次数：累计 N 次必得大奖
    stock       INTEGER,  -- 奖池限量份数；NULL = 不限量
    cycle       TEXT,     -- 刷新周期：日/一次性
    updated_at  TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_draw_004 (activity_id, price_tiers, reward_desc, stock, cycle, updated_at)
  VALUES ('ACT-DRAW-004', '68/328/648', '固定奖池，抽一少一', 3000, '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-TASK-001 · 累登签到
--   任务 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_task_001 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-TASK-001'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 累计充值档位（累充任务用），如 6/30/128
    reward_desc    TEXT,     -- 任务奖励说明
    limit_per_user INTEGER,  -- 可领取档数/次数
    cycle          TEXT,     -- 重置周期：日/周/一次性
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_task_001 (activity_id, reward_desc, cycle, updated_at)
  VALUES ('ACT-TASK-001', '7 日循环签到奖励', '日', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-TASK-002 · 累充任务
--   任务 / 大R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_task_002 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-TASK-002'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 累计充值档位（累充任务用），如 6/30/128
    reward_desc    TEXT,     -- 任务奖励说明
    limit_per_user INTEGER,  -- 可领取档数/次数
    cycle          TEXT,     -- 重置周期：日/周/一次性
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_task_002 (activity_id, price_tiers, reward_desc, limit_per_user, cycle, updated_at)
  VALUES ('ACT-TASK-002', '6/30/128/328/648/1288', '五档累计充值奖励', 6, '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-TASK-003 · 每日任务
--   任务 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_task_003 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-TASK-003'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 累计充值档位（累充任务用），如 6/30/128
    reward_desc    TEXT,     -- 任务奖励说明
    limit_per_user INTEGER,  -- 可领取档数/次数
    cycle          TEXT,     -- 重置周期：日/周/一次性
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_task_003 (activity_id, reward_desc, cycle, updated_at)
  VALUES ('ACT-TASK-003', '活跃度宝箱', '日', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-TASK-004 · 活跃宝箱
--   任务 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_task_004 (
    activity_id    TEXT PRIMARY KEY
                   DEFAULT 'ACT-TASK-004'
                   REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers    TEXT,     -- 累计充值档位（累充任务用），如 6/30/128
    reward_desc    TEXT,     -- 任务奖励说明
    limit_per_user INTEGER,  -- 可领取档数/次数
    cycle          TEXT,     -- 重置周期：日/周/一次性
    updated_at     TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_task_004 (activity_id, reward_desc, cycle, updated_at)
  VALUES ('ACT-TASK-004', '30/60/120 分钟三档宝箱', '日', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-RANK-001 · 开服竞技排行榜
--   排行榜 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_rank_001 (
    activity_id TEXT PRIMARY KEY
                DEFAULT 'ACT-RANK-001'
                REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    rank_metric TEXT,     -- 排行依据指标，如 战力排名 / 累计充值额
    reward_desc TEXT,     -- 名次奖励与非头部参与奖
    cycle       TEXT,     -- 赛季/一次性
    updated_at  TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_rank_001 (activity_id, rank_metric, reward_desc, cycle, updated_at)
  VALUES ('ACT-RANK-001', '战力排名', '稀有称号 + 资源', '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-RANK-002 · 消费排行榜
--   排行榜 / 大R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_rank_002 (
    activity_id TEXT PRIMARY KEY
                DEFAULT 'ACT-RANK-002'
                REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    rank_metric TEXT,     -- 排行依据指标，如 战力排名 / 累计充值额
    reward_desc TEXT,     -- 名次奖励与非头部参与奖
    cycle       TEXT,     -- 赛季/一次性
    updated_at  TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_rank_002 (activity_id, rank_metric, reward_desc, cycle, updated_at)
  VALUES ('ACT-RANK-002', '累计充值额', '榜单排名奖励', '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-SPEC-001 · 老带新邀请返利
--   特殊 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_spec_001 (
    activity_id  TEXT PRIMARY KEY
                 DEFAULT 'ACT-SPEC-001'
                 REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    reward_desc  TEXT,     -- 活动产出说明
    multiplier   REAL,     -- 产出倍率（限时收益 UP / 双倍掉落用）
    trigger_cond TEXT,     -- 触发/参与条件
    cycle        TEXT,     -- 刷新周期：周/一次性
    updated_at   TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_spec_001 (activity_id, reward_desc, trigger_cond, cycle, updated_at)
  VALUES ('ACT-SPEC-001', '邀请礼包 + 返利', '被邀请人达 10 级', '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-SPEC-002 · 周末限时收益 UP
--   特殊 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_spec_002 (
    activity_id  TEXT PRIMARY KEY
                 DEFAULT 'ACT-SPEC-002'
                 REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    reward_desc  TEXT,     -- 活动产出说明
    multiplier   REAL,     -- 产出倍率（限时收益 UP / 双倍掉落用）
    trigger_cond TEXT,     -- 触发/参与条件
    cycle        TEXT,     -- 刷新周期：周/一次性
    updated_at   TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_spec_002 (activity_id, reward_desc, multiplier, cycle, updated_at)
  VALUES ('ACT-SPEC-002', '双倍掉落 / 双倍经验', 2.0, '周', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-SPEC-003 · 限时双倍掉落
--   特殊 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_spec_003 (
    activity_id  TEXT PRIMARY KEY
                 DEFAULT 'ACT-SPEC-003'
                 REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    reward_desc  TEXT,     -- 活动产出说明
    multiplier   REAL,     -- 产出倍率（限时收益 UP / 双倍掉落用）
    trigger_cond TEXT,     -- 触发/参与条件
    cycle        TEXT,     -- 刷新周期：周/一次性
    updated_at   TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_spec_003 (activity_id, reward_desc, multiplier, cycle, updated_at)
  VALUES ('ACT-SPEC-003', '指定副本掉落翻倍', 2.0, '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-SPEC-004 · 节日/联动活动
--   特殊 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_spec_004 (
    activity_id  TEXT PRIMARY KEY
                 DEFAULT 'ACT-SPEC-004'
                 REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    reward_desc  TEXT,     -- 活动产出说明
    multiplier   REAL,     -- 产出倍率（限时收益 UP / 双倍掉落用）
    trigger_cond TEXT,     -- 触发/参与条件
    cycle        TEXT,     -- 刷新周期：周/一次性
    updated_at   TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_spec_004 (activity_id, reward_desc, cycle, updated_at)
  VALUES ('ACT-SPEC-004', '主题限定内容', '一次性', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-SHOP-001 · 常驻商品售卖
--   商城 / 全量；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_shop_001 (
    activity_id TEXT PRIMARY KEY
                DEFAULT 'ACT-SHOP-001'
                REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers TEXT,     -- 定价方式，如 按道具定价 / 积分价
    reward_desc TEXT,     -- 售卖/兑换内容
    cycle       TEXT,     -- 刷新周期：常驻/周
    updated_at  TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_shop_001 (activity_id, price_tiers, cycle, updated_at)
  VALUES ('ACT-SHOP-001', '按道具定价', '常驻', '2026-10-17T12:00:00');

-- ------------------------------------------------------------------
-- ACT-SHOP-002 · 积分兑换
--   商城 / 中大R；本表只放这一个活动的配置，改它不影响其他活动
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cfg_act_shop_002 (
    activity_id TEXT PRIMARY KEY
                DEFAULT 'ACT-SHOP-002'
                REFERENCES activity_master(activity_id) ON DELETE CASCADE,
    price_tiers TEXT,     -- 定价方式，如 按道具定价 / 积分价
    reward_desc TEXT,     -- 售卖/兑换内容
    cycle       TEXT,     -- 刷新周期：常驻/周
    updated_at  TEXT      -- 最近一次由引擎写入的时间
);
INSERT OR REPLACE INTO cfg_act_shop_002 (activity_id, reward_desc, cycle, updated_at)
  VALUES ('ACT-SHOP-002', '积分兑换道具池', '周', '2026-10-17T12:00:00');
