# -*- coding: utf-8 -*-
"""模块⑥ 舆情监控 · 虚拟语料生成器

不做真实采集（不联网、不接 QQ 机器人）。这里按「事件脚本」造一批论坛帖与
QQ 群发言，供看板区块 06 展示监控口径与分析能力。

真实感来自三件事，不是句子写得多漂亮：
  1. 渠道形态不同 —— 群消息是碎片（+1 / 连发 / @管理 / [图片]），论坛是长帖
  2. 时间戳有形状 —— 事件围绕峰值时刻聚集，群聊集中在晚间
  3. 事件有起承转合 —— 零星抱怨 → 附和 → 集中爆发 → 官方回应 → 回落

生成结果落 sentiment.json，字段里 is_virtual 全部标 1，页面明示为模拟语料。

用法：
    python 06_sentiment/gen_sentiment.py          # 生成
    python 06_sentiment/gen_sentiment.py --stat   # 只看统计，不写文件
"""
import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "sentiment.json"
SEED = 20261017

TOPICS = {
    "server": "服务器", "bug": "BUG", "pay": "充值", "cheat": "外挂",
    "play": "玩法", "event": "活动", "cs": "客服", "social": "社交",
    "perf": "性能", "misc": "其它",
}


def T(s):
    return datetime.fromisoformat("2026-" + s)


# ------------------------------------------------------------
# 事件脚本：20 个事件，对齐 10-13 开服 ~ 10-17 的排期与缺口
#   sent  = 情绪均值（-1 全负 / 0 中性 / 1 全正）
#   forum = 主题帖条数（回复另外按帖生成）
#   qq    = 群消息条数
# ------------------------------------------------------------
EVENTS = [
    {
        "id": "EV-01", "topic": "server", "level": "P0", "sent": -0.78,
        "start": "10-13T10:00", "peak": "10-13T10:35", "end": "10-13T13:30",
        "forum": 7, "qq": 52,
        "name": "开服排队与登录失败",
        "rules": ["命中「进不去/排队/连接失败」", "30 分钟内 30+ 条同类", "开服首小时，权重 ×1.5"],
        "action": "技术侧确认扩容进度 → 全服公告给补偿（元宝×200）→ 群内每 30 分钟同步一次",
        "titles": [
            "【求助】开服就炸了？现在连不上服务器",
            "10 点开服，卡在登录界面半小时了",
            "排队 8000+，这是开服还是抢票",
            "官方能给个说法吗，开服第一天就这体验",
            "服务器是不是压根没扩容",
            "一直提示连接失败，重装也没用",
            "现在能进了吗？我这边还是排队 5000+",
        ],
        "bodies": [
            "十点准时进的，选完服就卡住了，重进提示连接失败。群里一大半人都这样，应该不是我的网络问题。",
            "排队排到 8000 多，等了二十分钟掉回 5000，白等。官方先扩容再谈别的吧。",
            "我这边能进，但一进主城就卡成 PPT，走两步退三步，打个怪延迟 300 多。",
            "建议先别重装，是服务端的问题，重装没用的。我已经试过清缓存、换网络了。",
            "十二点半之后好多了，能正常进，排队还有两千左右，估计在陆续放人。",
            "首日这样其实能理解，但至少给个公告说明下进度，一直没声音才让人烦。",
            "补偿什么时候发？群里说送 200 元宝，我这边邮件里啥都没有。",
        ],
        "voices": [
            "进不去啊", "卡在登录界面", "排队 8000+", "炸了吧这是", "我也进不去",
            "重进三次了", "官方在干嘛", "@管理 能看看吗", "我朋友进去了我没进",
            "12 点半好点了", "能进了能进了", "卡成 PPT", "延迟 300 多打不了架",
            "补偿呢", "说好的 200 元宝呢", "我收到了", "慢慢等吧",
        ],
    },
    {
        "id": "EV-02", "topic": "bug", "level": "P1", "sent": -0.42,
        "start": "10-13T11:10", "peak": "10-13T15:00", "end": "10-13T19:00",
        "forum": 5, "qq": 24,
        "name": "新手引导卡在第 4 步",
        "rules": ["命中「新手任务/引导 + 卡住」", "可复现步骤明确", "影响新注册用户"],
        "action": "确认触发条件（背包满时领奖）→ 次日热更加保护 → 受影响账号补发引导奖励",
        "titles": [
            "新手任务第 4 步点不动，有人遇到过吗",
            "引导卡住了，重登也没用",
            "新号建了两个，都卡在同一个地方",
            "新手引导 bug 怎么跳过？",
            "卡引导的看这里，找到个临时办法",
        ],
        "bodies": [
            "到「打开背包领取装备」那一步，点任务追踪没反应，手动开背包也不推进。重登、换角色都试过。",
            "应该是背包满了才会卡，我先清了两格再点就成了。可以试试，不确定是不是巧合。",
            "客服说已经记录，让我等热更。新号第一天就卡主线，体验挺差的。",
            "临时办法：把背包里没用的白装分解掉，留空位，再点一次任务追踪就能过。",
            "已经修了吗？我朋友下午建的号还是卡住。",
        ],
        "voices": [
            "新手任务卡住了", "第 4 步点不动", "我也卡了", "背包满了会卡", "清两格就好了",
            "真的假的", "我试试", "成了，谢谢", "客服说等热更", "这 bug 有点离谱",
        ],
    },
    {
        "id": "EV-03", "topic": "pay", "level": "P0", "sent": -0.82,
        "start": "10-13T19:20", "peak": "10-13T20:25", "end": "10-13T23:40",
        "forum": 8, "qq": 40,
        "name": "首充到账异常 / 双倍未生效",
        "rules": ["命中「充值/支付 + 未到账」", "涉及实际付费，置 P0", "20 分钟内 8 条同类"],
        "action": "按订单号核对支付回调 → 2 小时内补发并额外补偿 → 群内公示处理进度 → 单独回帖",
        "titles": [
            "【急】首充 6 元付了，元宝没到账",
            "首充双倍没生效，只给了一份",
            "充值页面转圈，扣款成功但没到账",
            "付了 328，订单显示成功，游戏里啥也没有",
            "充值问题汇总贴，有同样情况的进",
            "已经到账了，官方处理得挺快",
        ],
        "bodies": [
            "20:10 付的 6 元，微信显示扣款成功，游戏里元宝还是 0。客服排队 40 多位，先来论坛问下。",
            "同上，我付的 328，订单号 SF20261013201533，背包和邮件都没有。已经截图了。",
            "客服说要提供订单号，我把截图发过去了，十分钟后补到账了，还多给了 100 元宝。速度还行。",
            "双倍那个是第二天才生效？我首充只拿到一份，公告里写的是首充双倍，这点得说清楚。",
            "刚收到邮件补发了，问题不大，但当时确实慌，毕竟真金白银。",
            "建议官方把充值回调状态做出来，别让我们瞎猜。",
        ],
        "voices": [
            "首充没到账", "我 328 也没到", "扣钱了", "客服排队 40 多", "有订单号就能补",
            "我补到了", "多久补的", "十分钟", "双倍呢", "双倍好像第二天", "坑啊",
            "@管理 充值没到账怎么处理", "已经处理了，谢谢",
        ],
    },
    {
        "id": "EV-04", "topic": "pay", "level": "P1", "sent": -0.28,
        "start": "10-14T09:10", "peak": "10-14T11:30", "end": "10-14T15:00",
        "forum": 4, "qq": 18,
        "name": "首充双倍规则理解分歧",
        "rules": ["命中「首充/双倍 + 规则」", "争议型，非资金异常", "官方口径已存在但未触达"],
        "action": "在充值页加一行规则说明 → 置顶答疑帖 → 客服话术统一",
        "titles": [
            "首充双倍到底是当天双倍还是永久双倍",
            "关于首充规则，官方能不能写清楚点",
            "首充只给了一份，客服说是正常的？",
            "首充规则答疑（已问客服，结论在这）",
        ],
        "bodies": [
            "我理解的是首充给双倍元宝，结果只给了一份。客服说双倍指的是额外赠送那一档，不是全部翻倍。",
            "规则藏在充值页最下面那行小字里，谁看得见。建议直接写「首充额外赠送 100%」，别用双倍这个词。",
            "问过客服了：6 元档给 60 元宝 + 赠送 60，一共 120，确实是双倍。没到账的看邮件，可能延迟。",
            "总之不是 bug，是文案的锅。但第一天因为这个来论坛的人不少。",
        ],
        "voices": [
            "首充双倍是啥意思", "给了一份还是一倍", "客服说额外赠送", "就是翻倍啊",
            "我看只到了一份", "看邮件", "明白了", "文案太绕了",
        ],
    },
    {
        "id": "EV-05", "topic": "pay", "level": "P2", "sent": 0.18,
        "start": "10-14T12:20", "peak": "10-14T20:00", "end": "10-14T23:00",
        "forum": 5, "qq": 20,
        "name": "月卡周卡性价比讨论",
        "rules": ["讨论型内容", "情绪中性偏正", "无资金异常"],
        "action": "无需干预；可提炼为攻略素材进社区运营",
        "titles": [
            "月卡和周卡怎么选？算了一笔账",
            "30 块月卡值不值，说点实际的",
            "零氪玩家的资源规划（含月卡对比）",
            "周卡比月卡划算？我可能算错了",
        ],
        "bodies": [
            "周卡 12 元给 7 天双倍经验，月卡 30 元给 30 天 + 每日 100 元宝。按元宝折算月卡明显划算，但周卡更适合周末集中玩的人。",
            "算下来月卡性价比大概高 20%，前提是你每天都上线。断签的话不如买周卡。",
            "零氪建议先攒着，等累充活动出来一起买，能顺手拿累充档位。",
            "我买了月卡，感觉经验加成挺明显的，第二天就追上了大部队。",
        ],
        "voices": [
            "月卡值吗", "30 块还行", "周卡更灵活", "我买月卡了", "经验加成挺多",
            "等累充再买", "累充什么时候出", "听说 24 号",
        ],
    },
    {
        "id": "EV-06", "topic": "cheat", "level": "P0", "sent": -0.7,
        "start": "10-14T20:40", "peak": "10-14T23:10", "end": "10-15T01:20",
        "forum": 5, "qq": 30,
        "name": "野外自动打怪脚本举报",
        "rules": ["命中「脚本/外挂/自动打怪」", "附截图与坐标，可核查", "涉及公平性，置 P0"],
        "action": "收集角色 ID + 坐标 + 时间 → 提交反外挂核查 → 24 小时内公示封禁名单",
        "titles": [
            "【举报】野外一群脚本号自动打怪，坐标附图",
            "凌晨挂机刷怪的能不能管管",
            "举报外挂，角色名和坐标都在",
            "自动打怪脚本已经泛滥到主城门口了",
            "官方封号名单什么时候出",
        ],
        "bodies": [
            "坐标（214, 388）附近有十几个号，动作完全同步，打怪路径一模一样，明显是脚本。截图我传了三张。",
            "凌晨两点去看，还在刷。举报按钮点了没反馈，只能来论坛发。",
            "这种号不封，手动玩的人就很亏。经验、材料全被他们刷走了。",
            "官方回帖说已收到，正在核查。希望别只是回个帖子。",
        ],
        "voices": [
            "野外一堆脚本", "坐标 214 388", "我也看到了", "同步走位", "举报了没反应",
            "官方说在查", "这种号早该封", "封了名单会公示吗", "凌晨更多",
        ],
    },
    {
        "id": "EV-07", "topic": "play", "level": "P1", "sent": -0.36,
        "start": "10-15T10:20", "peak": "10-15T14:00", "end": "10-15T20:30",
        "forum": 8, "qq": 32,
        "name": "职业平衡争议（战士偏弱）",
        "rules": ["命中「职业/战士 + 太弱/加强」", "同类帖 6 条以上", "无付费指向"],
        "action": "收集各职业 PVP 胜率数据 → 下一版本调整数值 → 论坛回复给出调整方向与时间",
        "titles": [
            "战士是不是太弱了？打架完全打不过法师",
            "三天体验下来，战士的定位很尴尬",
            "关于职业平衡，说几句不好听的",
            "法师现在是不是版本答案",
            "战士玩家集中反馈贴，希望官方看一下",
            "道士打野效率是真的高",
            "别急着喊弱，战士装备起来很强",
        ],
        "bodies": [
            "同装备下战士打法师，被风筝到死，突进技能 CD 太长，追不上也跑不掉。",
            "我战士 38 级，竞技场前十只有一个战士。数据摆在这，不用我说。",
            "前期确实弱，但 40 级穿上套装之后抗性起来会好很多。我就是战士，别劝退了。",
            "不是战士弱，是装备没跟上。你们拿白装去打紫装法师，当然打不过。",
            "建议把冲锋 CD 从 12 秒降到 9 秒，其他不用动，战士就能玩了。",
            "道士打野效率是真高，宝宝抗伤还能回血，战士单刷累得要死。",
        ],
        "voices": [
            "战士太弱了", "被法师风筝死", "冲锋 CD 太长", "我 40 了还行", "装备起来能打",
            "道士打野快", "求加强战士", "官方看得到吗", "下周更新会不会调",
        ],
    },
    {
        "id": "EV-08", "topic": "event", "level": "P1", "sent": -0.46,
        "start": "10-15T18:10", "peak": "10-15T21:00", "end": "10-15T23:50",
        "forum": 4, "qq": 24,
        "name": "开服竞技排行榜太卷",
        "rules": ["命中「排行榜/冲榜 + 奖励」", "活动期内集中反馈", "涉及活动规则"],
        "action": "公示榜单结算口径 → 下期增加分段奖励（前 10% 均有奖）→ 公告说明",
        "titles": [
            "竞技排行榜前 100 有奖，我们这些 200 名的算啥",
            "榜单是不是被工作室包了",
            "冲榜三天，最后什么也没拿到",
            "建议排行榜改成百分比奖励",
        ],
        "bodies": [
            "打到 180 名，奖励线卡在 100 名，白忙三天。分段奖励不好吗，前 10% 都给点东西。",
            "前 20 名有几个号明显是同一个人，名字格式都一样，这不查一下？",
            "冲榜期间每天要打 40 多场，纯耗时间。给个参与奖也行。",
            "榜单结算规则写的是「活动结束后 24 小时内发放」，现在还没到时间，别急。",
        ],
        "voices": [
            "榜前 100 才有奖", "我 180 名", "白打了", "工作室包榜了吧", "建议百分比",
            "奖励什么时候发", "24 小时内", "太卷了",
        ],
    },
    {
        "id": "EV-09", "topic": "event", "level": "P2", "sent": -0.3,
        "start": "10-16T09:20", "peak": "10-16T12:00", "end": "10-16T16:40",
        "forum": 4, "qq": 16,
        "name": "回归礼包不如新号福利",
        "rules": ["命中「回归/老玩家 + 礼包」", "情绪偏负但无资金异常", "可转需求池"],
        "action": "记录为需求：回归礼包按战力缺口动态配置 → 排入下版本活动评审",
        "titles": [
            "老玩家回归礼包，比新号差远了",
            "回归号福利能不能看一眼",
            "AFK 一个月回来，感觉被抛弃了",
            "回归礼包和新手礼包对比（有图）",
        ],
        "bodies": [
            "回归给了 50 元宝 + 几件蓝装，新手号直接送紫装和三天月卡体验。老玩家反而更亏。",
            "理解要拉新，但留存也得给点东西吧。回来第一天就想再 AFK。",
            "其实回归礼包分档的，战力越高给得越多。我 6 万战力拿了 300 元宝，还行。",
            "建议按离线天数给补偿，别一刀切。",
        ],
        "voices": [
            "回归礼包好差", "不如新手", "我拿了 300 元宝", "看战力", "老玩家没人权",
            "凑合吧", "至少给点",
        ],
    },
    {
        "id": "EV-10", "topic": "bug", "level": "P1", "sent": -0.5,
        "start": "10-16T11:00", "peak": "10-16T13:00", "end": "10-16T17:20",
        "forum": 3, "qq": 14,
        "name": "老带新邀请链接失效",
        "rules": ["命中「邀请/拉新 + 链接失效」", "影响拉新转化，可量化", "1 小时内 6 条"],
        "action": "排查短链服务与活动配置 → 补发失效期间的邀请奖励 → 公告说明",
        "titles": [
            "邀请链接打不开，提示参数错误",
            "老带新活动是不是挂了",
            "拉了三个人，奖励一个没到",
        ],
        "bodies": [
            "我的邀请链接发给朋友，点开是「参数错误」。换了三个浏览器都一样。",
            "奖励规则写的是被邀请人到 20 级才算，我朋友才 12 级，可能还没到。",
            "已经能打开了，官方说是短链服务的问题，下午三点修好的。",
        ],
        "voices": [
            "邀请链接打不开", "参数错误", "我也是", "奖励没到", "要到 20 级", "修好了",
        ],
    },
    {
        "id": "EV-11", "topic": "play", "level": "P2", "sent": -0.24,
        "start": "10-16T15:00", "peak": "10-16T19:30", "end": "10-16T22:40",
        "forum": 3, "qq": 12,
        "name": "拍卖行手续费偏高",
        "rules": ["讨论型内容", "情绪偏负", "无资金异常"],
        "action": "记录为需求：手续费分级（低价物品降费）→ 下版本评估",
        "titles": [
            "拍卖行 10% 手续费是不是有点狠",
            "卖个材料手续费比赚的还多",
            "建议拍卖行手续费改成阶梯",
        ],
        "bodies": [
            "一件材料卖 50 金，扣 5 金手续费，来回挂几次就不赚了。低价值物品建议免手续费。",
            "10% 在同类游戏里算正常，但人家有拍卖行会员减免。",
            "主要是流拍也扣费，这点比较难受。",
        ],
        "voices": [
            "拍卖行手续费 10%", "太高了", "流拍也扣", "建议阶梯", "材料都不好卖",
        ],
    },
    {
        "id": "EV-12", "topic": "cs", "level": "P2", "sent": -0.44,
        "start": "10-16T19:10", "peak": "10-16T21:00", "end": "10-16T23:30",
        "forum": 2, "qq": 15,
        "name": "客服排队久 / 回复慢",
        "rules": ["命中「客服 + 排队/不回」", "服务体验类", "无资金异常"],
        "action": "高峰期增加在线客服并发 → 常见问题前置到自助问答 → 公告回复时效承诺",
        "titles": [
            "客服排队 60 位，等了四十分钟",
            "提了工单三天没回复",
        ],
        "bodies": [
            "晚上八点问充值问题，前面排 60 多位，等到十点才有人。建议高峰期多开几个人。",
            "工单提交三天了还是「处理中」，也不知道在处理什么。",
        ],
        "voices": [
            "客服排队 60", "等了四十分钟", "工单三天没回", "晚上人多", "白天快一点",
            "自助问答也行",
        ],
    },
    {
        "id": "EV-13", "topic": "event", "level": "P0", "sent": -0.72,
        "start": "10-17T12:00", "peak": "10-17T12:45", "end": "10-17T17:30",
        "forum": 8, "qq": 46,
        "name": "定向抽奖概率质疑",
        "rules": ["命中「抽奖/概率 + 假/坑」", "活动上线 1 小时内 20+ 条", "涉及付费预期，置 P0"],
        "action": "公示奖池概率与保底次数 → 抽取后台数据证明分布正常 → 论坛置顶回应 → 群内同步",
        "titles": [
            "星舰池抽了 80 次，一个金都没出，概率是真的吗",
            "定向抽奖的概率公示在哪？找不到",
            "抽奖概率是不是暗改了",
            "80 抽保底到底怎么算的，客服说的和公告不一致",
            "理性讨论：这个池子的期望成本",
            "抽了 30 次出了两个紫，感觉还行",
            "官方能公示下真实概率吗",
        ],
        "bodies": [
            "公告写金 1.2%，80 抽保底。我 80 抽只出了 2 个紫，金一个没有。按 1.2% 算 80 抽不出金的概率是 38%，但连着三个人都这样就不对劲了。",
            "概率公示藏在活动页最下面的「查看详情」里，还是图片，糊得看不清。",
            "保底是 80 抽必出，不是 80 抽必出金，客服说是「必出最高品质」，但池子里最高是金还是红？定义不清。",
            "算了下期望：金 1.2% 就是平均 83 抽一个，单抽 18 元，一个金大概 1500。这个价格在同类里算贵。",
            "我 30 抽两个紫，感觉正常。可能运气问题，但官方最好把概率说清楚。",
            "刚看了下，活动页更新了概率公示，写得比之前清楚。",
        ],
        "voices": [
            "80 抽没金", "概率假的吧", "我 60 抽一个紫", "公示在哪", "保底怎么算的",
            "18 一抽太贵", "期望 1500 一个金", "官方说话", "@管理 概率公示",
            "我出了", "运气问题吧", "反正我不抽了",
        ],
    },
    {
        "id": "EV-14", "topic": "event", "level": "P1", "sent": -0.5,
        "start": "10-17T13:10", "peak": "10-17T15:00", "end": "10-17T18:20",
        "forum": 4, "qq": 22,
        "name": "抽奖券获取太少 / 保底太贵",
        "rules": ["命中「抽奖券/保底 + 不够/太贵」", "付费意愿受阻，关联流水", "同类 8 条"],
        "action": "评估免费券投放（每日任务 +2 张）→ 下期活动前调整 → 公告预告",
        "titles": [
            "免费抽奖券一天就给 1 张，80 抽保底要攒三个月",
            "活跃抽奖券能不能多给点",
            "保底次数对比同类游戏偏高",
            "建议每日任务加抽奖券产出",
        ],
        "bodies": [
            "每日任务给 1 张，活跃宝箱 3 天给 2 张，按这个速度 80 抽要攒三个多月。保底基本等于没有。",
            "同类游戏一般 60 抽保底，而且每周能白嫖 10 抽左右。这个差距有点大。",
            "理解要赚钱，但免费玩家也得有点参与感，不然活动跟我们没关系。",
            "已经把券留着了，等累充出来一起抽，能顺便拿累充档位。",
        ],
        "voices": [
            "一天一张券", "80 抽攒三个月", "保底太远", "同类 60 抽", "建议多给点",
            "留着等累充", "免费玩家没参与感", "确实",
        ],
    },
    {
        "id": "EV-15", "topic": "event", "level": "P1", "sent": -0.56,
        "start": "10-17T12:10", "peak": "10-17T14:00", "end": "10-17T16:30",
        "forum": 3, "qq": 20,
        "name": "周末限时收益 UP 未生效",
        "rules": ["命中「收益 UP/双倍 + 没生效」", "活动规则未兑现", "12 条同类"],
        "action": "核对活动开关与生效范围（是否仅限特定副本）→ 补发差额 → 公告澄清适用范围",
        "titles": [
            "周末收益 UP 是不是没开？经验没变",
            "限时收益 UP 只在特定副本生效？公告没说",
            "刷了两小时，收益跟平时一样",
        ],
        "bodies": [
            "公告说周末全服经验 +50%，我刷了两小时野外，经验条涨得跟昨天一样。截图对比过了。",
            "客服说是「副本内生效」，但公告写的是「全服收益提升」，这差别很大。",
            "副本里确实有加成，野外没有。建议公告把适用范围写清楚。",
        ],
        "voices": [
            "收益 UP 没生效", "经验没变", "只在副本吧", "公告没写", "客服说副本内",
            "那野外呢", "坑",
        ],
    },
    {
        "id": "EV-16", "topic": "pay", "level": "P1", "sent": -0.48,
        "start": "10-17T14:00", "peak": "10-17T16:00", "end": "10-17T18:40",
        "forum": 4, "qq": 18,
        "name": "终身限量礼包定价争议",
        "rules": ["命中「礼包 + 648/太贵/限量」", "涉及付费预期，关联大 R 转化", "预告期舆情"],
        "action": "补充礼包内容拆解说明 → 公布限量份数与抢购规则 → 避免开售当日集中投诉",
        "titles": [
            "终身限量礼包 648，内容值这个价吗",
            "第 2 期还是 648？能不能出个低档",
            "限量 2000 份，抢不到怎么办",
            "算了下终身礼包，比月卡划算但门槛太高",
        ],
        "bodies": [
            "648 一次性给的东西确实多，但门槛太高了。出个 128 或 328 的档位，买的人会多不少。",
            "第 1 期没抢到，第 2 期说 20 号上，限量 2000 份，估计又是秒没。",
            "拆开算了下，按元宝折算大概是 1:1.6，比直充划算，但得一次性掏 648。",
            "希望公布下具体几点开售，别又是突然上架。",
        ],
        "voices": [
            "648 太贵", "出个 328 档", "限量 2000 抢不到", "20 号上", "几点开售",
            "内容挺多", "一次性掏不起", "大R专供吧",
        ],
    },
    {
        "id": "EV-17", "topic": "perf", "level": "P1", "sent": -0.44,
        "start": "10-14T20:00", "peak": "10-16T21:30", "end": "10-17T18:00",
        "forum": 4, "qq": 22,
        "name": "晚间高峰卡顿掉线",
        "rules": ["命中「卡顿/掉线/延迟」", "集中在 20-23 点", "跨天复现"],
        "action": "定位高峰时段节点负载 → 扩容与线路优化 → 公告维护窗口",
        "titles": [
            "晚上八点以后必卡，是不是服务器扛不住",
            "打副本掉线三次，队友骂死我了",
            "延迟稳定 200+，只有晚上这样",
            "换成手机热点好多了，可能是线路问题",
        ],
        "bodies": [
            "白天很顺，晚上八点一过延迟就上 200，技能按出去半秒才出。",
            "副本里掉线直接算逃跑，扣了信誉分，这个能申诉吗。",
            "换热点之后正常了，估计是宽带线路到机房的问题。",
            "官方说在做线路优化，希望快点。",
        ],
        "voices": [
            "晚上卡死", "延迟 200+", "副本掉线", "扣信誉分", "换热点好点", "线路问题吧",
            "官方在优化", "快点吧",
        ],
    },
    {
        "id": "EV-18", "topic": "play", "level": "P2", "sent": 0.62,
        "start": "10-15T09:00", "peak": "10-16T20:00", "end": "10-17T17:00",
        "forum": 5, "qq": 10,
        "name": "副本攻略与职业推荐",
        "rules": ["攻略型内容", "情绪正面", "可作为社区运营素材"],
        "action": "无需干预；择优加精并推送到社区首页",
        "titles": [
            "血月副本通关思路，附站位图",
            "新手职业选择建议（开服三天版）",
            "强化 +7 稳上的小技巧",
            "装备词条优先级整理，别再乱洗了",
            "分享一套 40 级前最快的升级路线",
        ],
        "bodies": [
            "血月老二会放三次范围，第二次之后有 5 秒空隙，这时候集火。站位图我放在二楼了。",
            "新手建议先玩法或道士，战士前期确实吃力。等 40 级再考虑转。",
            "强化 +7 以下失败不掉级，可以放心冲。+8 开始要用保护符。",
            "词条优先级：攻击 > 暴击 > 破甲，防御类词条前期收益很低。",
            "按这个路线走，8 小时能到 35 级，比瞎逛快一倍。",
        ],
        "voices": [
            "血月怎么打", "老二有技巧", "谢谢大佬", "战士前期难", "强化 +7 稳",
            "词条怎么洗", "看攻略", "有用",
        ],
    },
    {
        "id": "EV-19", "topic": "social", "level": "P2", "sent": 0.34,
        "start": "10-13T18:00", "peak": "10-16T19:00", "end": "10-17T16:00",
        "forum": 3, "qq": 14,
        "name": "组队与公会招募",
        "rules": ["社交型内容", "情绪中性偏正", "无风险"],
        "action": "无需干预；可引导至公会频道",
        "titles": [
            "【招募】晚上八点固定队，缺一个奶",
            "新公会收人，不卷，休闲为主",
            "有没有一起刷血月的，缺两输出",
        ],
        "bodies": [
            "固定队每晚八点刷血月，缺一个道士，要求能上语音，不鸽。",
            "公会「夜航船」收人，休闲为主，不要求活跃度，主要是有人一起玩。",
            "缺两个输出，今晚九点开，能来的回帖。",
        ],
        "voices": [
            "缺奶吗", "我道士", "晚上八点?", "公会还收人吗", "拉我", "休闲公会好啊",
        ],
    },
    {
        "id": "EV-20", "topic": "misc", "level": "P2", "sent": -0.3,
        "start": "10-16T10:00", "peak": "10-17T11:00", "end": "10-17T17:30",
        "forum": 2, "qq": 12,
        "name": "群内广告与刷屏小号",
        "rules": ["命中「代充/收号/加群」", "非游戏内容", "污染群环境"],
        "action": "群管理开启入群验证 → 关键词自动撤回 → 清理近期广告号",
        "titles": [
            "群里全是代充广告，管不管",
            "建议开个入群验证",
        ],
        "bodies": [
            "一晚上进来七八个发代充的，还 @全体成员，烦得很。",
            "建议把入群问题设成游戏常识，能挡掉一大半。",
        ],
        "voices": [
            "代充加V", "收号收号", "又是广告", "@管理 踢了", "开验证吧", "已踢",
        ],
    },
]

# ------------------------------------------------------------
# 昵称池与通用噪声
# ------------------------------------------------------------
NICKS = [
    "夜风不归", "老张打宝", "清风徐来", "铁匠铺学徒", "沙城守夜人", "七号玩家",
    "不吃香菜", "南山有雪", "刀口舔血", "小鱼干", "阿蒙", "半城烟雨",
    "打不过就跑", "落雨听风", "西瓜太郎", "白给少年", "元素使", "影子",
    "沉默的羊", "二营长", "老李头", "孤舟", "云中鹤", "三炮",
]

GENERIC_QQ = ["+1", "同上", "我也一样", "同问", "顶", "确实", "哈哈哈哈",
              "[图片]", "[表情]", "笑死", "真的假的", "???", "哎"]

# 只保留中性的补充句：「已解决」这类尾注挂在吐槽贴上会自相矛盾
FORUM_TAIL = ["", "", "", "", "", "", "补充：截图在二楼。"]


def _rng():
    return random.Random(SEED)


def pick(rnd, seq):
    return seq[rnd.randrange(len(seq))]


def sample_time(rnd, ev):
    """68% 聚在峰值附近，其余均匀铺满区间；两端夹住。"""
    s, p, e = T(ev["start"]), T(ev["peak"]), T(ev["end"])
    span = (e - s).total_seconds()
    if rnd.random() < 0.68:
        sigma = max(span / 6.0, 300)
        t = p + timedelta(seconds=rnd.gauss(0, sigma))
    else:
        t = s + timedelta(seconds=rnd.random() * span)
    return min(max(t, s), e)


def score(rnd, ev, neutral_p=0.26):
    """个体情绪 = 事件基调 + 噪声。约四分之一是中性附和/提问，不做情绪放大。"""
    if rnd.random() < neutral_p:
        return round(min(0.18, max(-0.18, rnd.gauss(0, 0.08))), 3)
    return round(min(1.0, max(-1.0, ev["sent"] + rnd.gauss(0, 0.3))), 3)


def label(v):
    return "负" if v <= -0.2 else ("正" if v >= 0.2 else "中")


def build():
    rnd = _rng()
    posts, events = [], []
    fp = fm = 0

    for ev in EVENTS:
        start_t = T(ev["start"])
        n_forum, n_qq = ev["forum"], ev["qq"]
        times = sorted(sample_time(rnd, ev) for _ in range(n_forum + n_qq))
        f_times = sorted(sample_time(rnd, ev) for _ in range(n_forum))
        q_times = sorted(sample_time(rnd, ev) for _ in range(n_qq))

        # ---------- 论坛：主题帖 + 回复 ----------
        for i, t in enumerate(f_times):
            fp += 1
            pid = "FP-%04d" % fp
            # 标题与正文按序配对：随机抽会导致"标题炸服、正文讲补偿"这种错位
            if i < len(ev["titles"]) and i < len(ev["bodies"]):
                title, body = ev["titles"][i], ev["bodies"][i]
            else:
                idx = i % min(len(ev["titles"]), len(ev["bodies"]))
                title, body = ev["titles"][idx], ev["bodies"][idx]
            body += pick(rnd, FORUM_TAIL)
            v = score(rnd, ev)
            thread = {
                "post_id": pid, "ch": "forum",
                "sub": "充值反馈区" if ev["topic"] == "pay" else "综合讨论区",
                "title": title, "text": body, "author": pick(rnd, NICKS),
                "at": t.strftime("%Y-%m-%d %H:%M"), "replies": 0,
                "sentiment": v, "topic": ev["topic"],
                "level": ev["level"], "event_id": ev["id"],
                "parent_id": None, "cross": 0,
            }
            posts.append(thread)
            # 回复 1~4 条，紧跟在主题帖之后
            n_rep = rnd.choice([1, 2, 2, 3, 3, 4])
            last = None
            for r in range(n_rep):
                rt = min(t + timedelta(minutes=rnd.randint(3, 90)),
                         T(ev["end"]) + timedelta(hours=2))
                fm += 1
                generic = rnd.random() >= 0.55
                txt = pick(rnd, GENERIC_QQ) if generic else pick(rnd, ev["voices"])
                rv = v if generic else score(rnd, ev)
                prefix = "@%s " % last if (last and rnd.random() < 0.35) else ""
                posts.append({
                    "post_id": "FR-%04d" % fm, "ch": "forum", "sub": "回复",
                    "title": "", "text": prefix + txt, "author": pick(rnd, NICKS),
                    "at": rt.strftime("%Y-%m-%d %H:%M"), "replies": 0,
                    "sentiment": round(rv, 3), "topic": ev["topic"],
                    "level": ev["level"], "event_id": ev["id"],
                    "parent_id": pid, "cross": 0,
                })
                last = posts[-1]["author"]
            thread["replies"] = n_rep

        # ---------- QQ 群：碎片、连发、@管理 ----------
        qq_seq = 0
        prev_author = None
        recent = []
        for t in q_times:
            qq_seq += 1
            pool = ev["voices"]
            generic = rnd.random() < 0.22
            if generic:
                txt = pick(rnd, GENERIC_QQ)
                v = score(rnd, ev) * 0.6
            else:
                txt = pool[qq_seq % len(pool)] if qq_seq < len(pool) else pick(rnd, pool)
                v = score(rnd, ev)
            # 只有内容像求助/投诉时才 @管理，否则「@管理 哈哈哈哈」很假；
            # 语句自带 @管理 的不重复加
            if not generic and "@管理" not in txt and rnd.random() < 0.1:
                txt = "@管理 " + txt
            # 同一句话短期内反复出现会暴露是程序生成，避开最近 10 条
            for _ in range(5):
                if txt not in recent:
                    break
                txt = pick(rnd, pool) if not generic else pick(rnd, GENERIC_QQ)
            recent.append(txt)
            if len(recent) > 10:
                recent.pop(0)
            if prev_author and rnd.random() < 0.18:
                author = prev_author
            else:
                author = "群友 %d***%d" % (rnd.randint(1, 9), rnd.randint(0, 9))
            prev_author = author
            posts.append({
                "post_id": "QM-%05d" % qq_seq, "ch": "qq", "sub": "官方 3 群",
                "title": "", "text": txt, "author": author,
                "at": t.strftime("%Y-%m-%d %H:%M"), "replies": 0,
                "sentiment": round(v, 3), "topic": ev["topic"],
                "level": ev["level"], "event_id": ev["id"],
                "parent_id": None, "cross": 0,
            })

        events.append({
            "event_id": ev["id"], "name": ev["name"], "topic": ev["topic"],
            "topic_name": TOPICS[ev["topic"]], "level": ev["level"],
            "start": ev["start"], "end": ev["end"], "peak": ev["peak"],
            "count": n_forum + n_qq, "forum": n_forum, "qq": n_qq,
            "action": ev["action"], "rules": ev["rules"],
        })

    posts.sort(key=lambda p: p["at"])

    # 跨渠道共振：同一事件论坛和群都有 ≥3 条，且级别 P0/P1
    cross = {}
    for e in events:
        if e["level"] in ("P0", "P1") and e["forum"] >= 3 and e["qq"] >= 10:
            cross[e["event_id"]] = True
    for p in posts:
        p["cross"] = 1 if cross.get(p["event_id"]) else 0

    return posts, events


def aggregate(posts, events):
    """6 小时分桶 + 话题榜 + 预警清单 + 顶部数字。"""
    times = [datetime.strptime(p["at"], "%Y-%m-%d %H:%M") for p in posts]
    lo = min(times)
    lo = lo.replace(hour=(lo.hour // 6) * 6, minute=0)
    hi = max(times)
    buckets = []
    cur = lo
    while cur <= hi:
        nxt = cur + timedelta(hours=6)
        seg = [p for p in posts
               if cur <= datetime.strptime(p["at"], "%Y-%m-%d %H:%M") < nxt]
        pos = sum(1 for p in seg if label(p["sentiment"]) == "正")
        neu = sum(1 for p in seg if label(p["sentiment"]) == "中")
        neg = sum(1 for p in seg if label(p["sentiment"]) == "负")
        buckets.append({
            "t0": cur.strftime("%m-%d %H:%M"),
            "t1": nxt.strftime("%H:%M"),
            "key": cur.strftime("%Y-%m-%dT%H"),
            "pos": pos, "neu": neu, "neg": neg, "total": len(seg),
            "score": round(sum(p["sentiment"] for p in seg) / len(seg), 3) if seg else 0,
        })
        cur = nxt

    topics = []
    for code, name in TOPICS.items():
        seg = [p for p in posts if p["topic"] == code]
        if not seg:
            continue
        neg = sum(1 for p in seg if label(p["sentiment"]) == "负")
        topics.append({
            "code": code, "name": name, "total": len(seg), "neg": neg,
            "neg_rate": round(neg / len(seg), 3),
            "sent": round(sum(p["sentiment"] for p in seg) / len(seg), 3),
        })
    topics.sort(key=lambda x: -x["total"])

    alerts = []
    for e in sorted(events, key=lambda x: (x["level"], x["start"])):
        if e["level"] not in ("P0", "P1"):
            continue
        sample = next((p for p in posts if p["event_id"] == e["event_id"]
                       and p["ch"] == "forum" and p["parent_id"] is None), None)
        alerts.append({
            "alert_id": "AL-" + e["event_id"].split("-")[1],
            "event_id": e["event_id"], "level": e["level"],
            "topic": e["topic"], "topic_name": e["topic_name"],
            "title": e["name"], "at": e["peak"].replace("T", " "),
            "count": e["count"], "action": e["action"], "rules": e["rules"],
            "sample_id": sample["post_id"] if sample else None,
            "cross": 1 if cross_flag(e["event_id"]) else 0,
        })

    # 顶部数字：最近 24 小时
    now = max(times)
    day = [p for p in posts
           if now - timedelta(hours=24) <= datetime.strptime(p["at"], "%Y-%m-%d %H:%M") <= now]
    neg = sum(1 for p in day if label(p["sentiment"]) == "负")
    strip = {
        "total_24h": len(day),
        "neg_24h": neg,
        "neg_rate_24h": round(neg / len(day), 3) if day else 0,
        "pending_p0": sum(1 for a in alerts if a["level"] == "P0"),
        "pending_p1": sum(1 for a in alerts if a["level"] == "P1"),
        "net_24h": round(sum(p["sentiment"] for p in day) / len(day), 3) if day else 0,
        "forum_total": sum(1 for p in posts if p["ch"] == "forum"),
        "qq_total": sum(1 for p in posts if p["ch"] == "qq"),
        "events": len(events),
    }
    return buckets, topics, alerts, strip


def cross_flag(event_id):
    return event_id in CROSS_SET


CROSS_SET = set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat", action="store_true", help="只打印统计，不写文件")
    args = ap.parse_args()

    posts, events = build()
    buckets, topics, alerts, strip = aggregate(posts, events)

    data = {
        "meta": {
            "is_virtual": True,
            "note": "语料为程序按事件脚本生成的模拟数据，不来自真实玩家；仅用于展示监控口径与分析能力。",
            "seed": SEED, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "window": {"start": posts[0]["at"], "end": posts[-1]["at"]},
            "counts": {"total": len(posts), "forum": strip["forum_total"], "qq": strip["qq_total"]},
        },
        "strip": strip, "buckets": buckets, "topics": topics,
        "alerts": alerts, "events": events, "posts": posts,
    }

    # cross 标记需要在 events 聚合后才知道，这里回填
    for e in events:
        if e["level"] in ("P0", "P1") and e["forum"] >= 3 and e["qq"] >= 10:
            CROSS_SET.add(e["event_id"])
    for p in data["posts"]:
        p["cross"] = 1 if p["event_id"] in CROSS_SET else 0
    for a in data["alerts"]:
        a["cross"] = 1 if a["event_id"] in CROSS_SET else 0

    if args.stat:
        print("帖子 %d（论坛 %d / 群 %d）" % (len(posts), strip["forum_total"], strip["qq_total"]))
        print("事件 %d　预警 %d（P0 %d / P1 %d）" % (len(events), len(alerts),
                                              strip["pending_p0"], strip["pending_p1"]))
        print("24h 新增 %d，负面占比 %.0f%%，净情感 %.2f"
              % (strip["total_24h"], strip["neg_rate_24h"] * 100, strip["net_24h"]))
        print("话题 TOP5：", "、".join("%s(%d)" % (t["name"], t["total"]) for t in topics[:5]))
        return

    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("已生成 %s" % OUT.name)
    print("  帖子 %d（论坛 %d / QQ 群 %d）"
          % (len(posts), strip["forum_total"], strip["qq_total"]))
    print("  事件 %d　P0 %d / P1 %d"
          % (len(events), strip["pending_p0"], strip["pending_p1"]))
    print("  24h 新增 %d，负面 %.0f%%，净情感 %+.2f"
          % (strip["total_24h"], strip["neg_rate_24h"] * 100, strip["net_24h"]))
    print("  体积 %.0f KB" % (OUT.stat().st_size / 1024))


if __name__ == "__main__":
    main()
