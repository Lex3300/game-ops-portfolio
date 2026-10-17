/* ==========================================================================
 * 客服知识库检索引擎（模块⑤）
 * --------------------------------------------------------------------------
 * 纯前端 RAG：不联网、不调模型、不需要后端。
 *   知识块（05_cs_rag/kb.json）→ 中文 bigram 分词 → BM25 打分
 *   → 覆盖率判定 → 命中则回原文，不命中返回 null（由界面回兜底话术）
 *
 * 为什么是 bigram 而不是分词：浏览器里没有中文分词器，也不该为了一个
 * 作品集引 1MB 的词典。bigram 对「充值没到账 / 充值未到账」这类近义表达
 * 天然兼容（共享 充值、到账 两个 gram），配合 IDF 加权已足够准。
 *
 * 为什么用「覆盖率」而不只看 BM25 分数：BM25 分数没有绝对量纲，
 * 换一个问题域就要重调阈值。覆盖率 = 问题里有多少实词在知识块中出现过，
 * 它才是判断「知识库里到底有没有这条」的稳定依据。
 * ========================================================================== */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.CS_RAG = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var K1 = 1.2;          // BM25 词频饱和参数
  var B = 0.75;          // BM25 长度归一参数
  var GENERIC_DF = 0.55; // 出现在超过这个比例知识块里的词，视为泛词（不参与覆盖率）
  var MIN_COVER = 0.42;  // 覆盖率门槛：低于它判定为「知识库没有」
  var MIN_SCORE = 0.8;   // 分数下限，防止只靠一个泛词命中
  var MIN_IDF_HIT = 2.0; // 至少命中一个「有区分度」的词（df 越小 idf 越大）

  /* 纯功能词：对判断意图没有贡献，分词后直接丢弃 */
  var STOP = {};
  ['什么', '怎么', '怎样', '如何', '哪些', '哪个', '可以', '是否', '能否',
   '请问', '告诉', '一下', '为什', '么办', '么样', '这个', '那个', '我们',
   '你们', '他们', '的话', '了吗', '呢', '吗', '吧', '啊', '呀'].forEach(function (w) {
    STOP[w] = 1;
  });

  /* 疑问短语：整段剥离。
     中文问句是「名词 + 疑问尾巴」结构，尾巴不剥掉就会切出
     "卡多""少钱"这类跨词边界的噪声 gram，把覆盖率算低（月卡多少钱 → 兜底，错）。
     长的放前面，避免「多少级」被「多少」先吃掉。 */
  var PHRASES = [
    '什么时候', '什么时间', '多少钱', '多少级', '多少元', '多少次', '多长',
    '怎么办', '怎么样', '怎么弄', '怎么', '如何', '是什么', '为什么', '什么',
    '哪几个', '哪些', '哪个', '哪里', '几次', '几个', '几点', '几星', '几级',
    '多大', '多长', '多少',
    '能不能', '可不可以', '可以吗', '有没有', '是不是', '会不会', '要不要', '是否',
    '请问', '想问', '一下', '帮我', '告诉我'
  ].sort(function (a, b) { return b.length - a.length; });

  /* 孤立虚字与语气词：剥离短语后再清一遍 */
  var FILLER = /[的我了是有没都就还也吧呀呢啊哦嗯吗嘛]/g;

  /* 玩家口语 → 手册用词。只做查询侧归一，不改知识块 */
  var SYN = {
    '氪金': '充值', '克金': '充值', '充钱': '充值', '冲钱': '充值', '付费': '充值',
    '花钱': '充值', '充值了': '充值', '付钱': '充值', '首冲': '首充',
    '充了钱': '充值', '充钱没': '充值未', '没到': '未到', '没给': '未到',
    '退款': '退款', '退钱': '退款', '返钱': '退款', '退费': '退款',
    '变强': '战力', '提升战力': '战力', '变厉害': '战力',
    '掉帧': '卡顿', '很卡': '卡顿', '卡死': '卡顿', '延迟': '卡顿', '卡顿': '卡顿',
    '崩溃': '闪退', '闪退': '闪退', '强退': '闪退', '打不开': '闪退',
    '换职业': '转职', '改职业': '转职', '转职业': '转职',
    '婚礼': '结婚', '情侣': '结婚', '老婆': '结婚', '老公': '结婚', '结拜': '结义',
    '攻城': '沙巴克', '攻沙': '沙巴克', '沙巴克': '沙巴克',
    '公会': '行会', '帮派': '行会', '帮会': '行会',
    '师父': '拜师', '师傅': '拜师', '收徒': '拜师', '徒弟': '拜师',
    '开挂': '外挂', '脚本': '外挂', '辅助': '外挂', '作弊': '外挂',
    '电脑': 'PC', 'pc': 'PC', '模拟器': '模拟器',
    '满级': '等级上限', '最高级': '等级上限', '顶级': '等级上限',
    '卖东西': '交易', '买东西': '交易', '买卖': '交易',
    '锻造': '强化', '精炼': '强化', '升星': '强化', '装备升级': '强化装备',
    '客服': '客服', '人工': '客服', '投诉': '举报', '举报': '举报',
    '电话': '联系', '热线': '联系', '邮箱': '联系',
    '掉线': '网络', '卡住': '卡顿', '打怪': '刷怪', '挂机': '挂机',
    '每天': '每日', '每日': '每日', '一键': '自动',
    '换手机': '更换绑定手机', '绑手机': '绑定手机',
    '掉东西': '掉装备', '爆装备': '掉装备', '改名字': '改名', '改个名': '改名',
    '密码': '密码', '被盗': '账号被盗', '封号': '封号'
  };

  function normalize(q) {
    var s = String(q || '').toLowerCase().trim();
    if (!s) return '';

    // 1) 口语 → 手册用词。跑两轮：第二轮用「去空格」文本匹配，
    //    这样「装备 怎么 升级」被剥成「装备 升级」后仍能命中「装备升级」这类长词。
    var keys = Object.keys(SYN).sort(function (a, b) { return b.length - a.length; });
    for (var round = 0; round < 2; round++) {
      var compact = s.replace(/\s+/g, '');
      keys.forEach(function (k) {
        if (k.length < 2 || SYN[k] === k) return;
        if (s.indexOf(k) >= 0) {
          s = s.split(k).join(' ' + SYN[k] + ' ');
        } else if (round === 1 && compact.indexOf(k) >= 0) {
          s = compact.split(k).join(' ' + SYN[k] + ' ');
        }
      });
    }

    // 2) 疑问短语整段剥离（长词优先，避免留碎片）
    PHRASES.forEach(function (p) { s = s.split(p).join(' '); });

    // 3) 虚字与语气词清理
    s = s.replace(FILLER, ' ').replace(/\s+/g, ' ').trim();

    // 全被剥光（例如只问了「怎么办」）时回退原文，交给分词与覆盖率判定
    return s || String(q || '').toLowerCase().trim();
  }

  function tokenize(text) {
    var out = [];
    var low = String(text || '').toLowerCase();
    var m;

    // 英文词 / 数字（等级、档位、时间等硬信息）
    var re = /[a-z]{2,}|[0-9]+(?:\.[0-9]+)?/g;
    while ((m = re.exec(low))) out.push(m[0]);

    // 中文：连续汉字段切 bigram，单字段保留单字
    var zh = low.match(/[\u4e00-\u9fa5]+/g) || [];
    zh.forEach(function (seg) {
      if (seg.length === 1) { out.push(seg); return; }
      for (var i = 0; i < seg.length - 1; i++) out.push(seg.slice(i, i + 2));
    });

    return out.filter(function (t) { return !STOP[t]; });
  }

  function uniq(arr) {
    var seen = {}, out = [];
    arr.forEach(function (t) { if (!seen[t]) { seen[t] = 1; out.push(t); } });
    return out;
  }

  /** 建索引：每条知识块一个 tf 向量 + 全局 df 表 */
  function buildIndex(chunks) {
    var docs = (chunks || []).map(function (c) {
      var tf = Object.create(null);
      var qTf = Object.create(null);
      var len = 0;
      // 索引侧与查询侧走同一套归一（口语→手册用词），否则「每天/每日」这类
      // 近义表述在 bigram 层面对不上，问句再准也匹配不到答案。
      var body = normalize((c.q || '') + ' ' + (c.q || '') + ' ' + (c.a || ''));
      tokenize(body).forEach(function (t) {
        tf[t] = (tf[t] || 0) + 1;      // 问句重复一次，让"问什么"权重高于"答什么"
        len++;
      });
      tokenize(normalize(c.q || '')).forEach(function (t) { qTf[t] = 1; });
      return { tf: tf, qTf: qTf, len: len };
    });

    var df = Object.create(null);
    docs.forEach(function (d) {
      for (var t in d.tf) df[t] = (df[t] || 0) + 1;
    });

    var total = docs.reduce(function (a, d) { return a + d.len; }, 0);
    return { docs: docs, df: df, N: docs.length, avgdl: docs.length ? total / docs.length : 0 };
  }

  /**
   * 检索。
   * @returns {{hit: object|null, reason: string, top: Array}}
   *          hit 为 null 时 reason 说明原因：empty / no-term / low-cover / low-score
   */
  function search(chunks, index, query, opt) {
    opt = opt || {};
    var minCover = opt.minCover === undefined ? MIN_COVER : opt.minCover;

    var qTokens = uniq(tokenize(normalize(query)));
    if (!qTokens.length) return { hit: null, reason: 'empty', top: [] };

    var N = index.N || 1;
    var scored = (chunks || []).map(function (c, i) {
      var d = index.docs[i];
      var score = 0, strongTotal = 0, strongHit = 0, anyHit = 0, maxHitIdf = 0, qHit = 0;

      qTokens.forEach(function (t) {
        var df = index.df[t] || 0;
        var idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
        var isStrong = (df / N) <= GENERIC_DF;   // 泛词不计入覆盖率
        if (isStrong) strongTotal++;
        var f = d.tf[t] || 0;
        if (!f) return;
        anyHit++;
        if (isStrong) strongHit++;
        if (d.qTf[t]) qHit++;                    // 命中在「问句」里，比命中在答案里更可信
        if (idf > maxHitIdf) maxHitIdf = idf;
        score += idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * d.len / (index.avgdl || 1)));
      });

      return {
        chunk: c, i: i, score: score,
        cover: strongTotal ? strongHit / strongTotal : 0,
        qCover: strongTotal ? qHit / strongTotal : 0,
        strongTotal: strongTotal, strongHit: strongHit, anyHit: anyHit,
        maxHitIdf: maxHitIdf
      };
    });

    scored.sort(function (a, b) {
      if (b.cover !== a.cover) return b.cover - a.cover;
      if (b.qCover !== a.qCover) return b.qCover - a.qCover;
      return b.score - a.score;
    });

    var best = scored[0];
    var top = scored.slice(0, 3).filter(function (x) { return x.anyHit > 0; });

    if (!best || !best.anyHit) return { hit: null, reason: 'no-term', top: top };
    if (!best.strongTotal) return { hit: null, reason: 'no-term', top: top };
    if (best.cover < minCover) return { hit: null, reason: 'low-cover', top: top };
    if (best.score < MIN_SCORE) return { hit: null, reason: 'low-score', top: top };
    // 只命中「游戏」「玩家」这类泛词 → 不算答得上（否则问"关服"会命中"游戏是免费的吗"）
    if (best.maxHitIdf < MIN_IDF_HIT) return { hit: null, reason: 'weak-term', top: top };

    return { hit: best.chunk, best: best, reason: 'ok', top: top };
  }

  return {
    tokenize: tokenize,
    normalize: normalize,
    buildIndex: buildIndex,
    search: search,
    STOP: STOP,
    SYN: SYN,
    MIN_COVER: MIN_COVER
  };
}));
