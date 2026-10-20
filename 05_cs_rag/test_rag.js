/* ==========================================================================
 * 客服 RAG 检索回归测试
 * --------------------------------------------------------------------------
 * 用真实知识库跑一批问题，检查两件事：
 *   1) 手册里有的问题能命中正确条目（召回）
 *   2) 手册里没有的问题必须判定为「无法回答」（精确，走兜底话术）
 *
 * 运行：node 05_cs_rag/test_rag.js
 *      node 05_cs_rag/test_rag.js -v     打印每题的打分明细
 * ========================================================================== */
'use strict';

const fs = require('fs');
const path = require('path');
const RAG = require(path.join(__dirname, '..', '02_dashboard', 'rag.js'));

const kb = JSON.parse(fs.readFileSync(path.join(__dirname, 'kb.json'), 'utf8'));
const index = RAG.buildIndex(kb.chunks);
const VERBOSE = process.argv.indexOf('-v') >= 0;

// expect: hit = 必须命中；miss = 必须兜底；hint = 期望命中的关键词（用于判断命对没）
const CASES = [
  { q: '这个游戏什么时候上线', expect: 'hit', hint: '上线' },
  { q: '游戏包体多大', expect: 'hit', hint: '包体' },
  { q: '支持哪些平台', expect: 'hit', hint: '平台' },
  { q: '哪个职业最强', expect: 'hit', hint: '职业最强' },
  { q: '可以转职吗', expect: 'hit', hint: '转职' },
  { q: '角色最高多少级', expect: 'hit', hint: '等级上限' },
  { q: '装备强化最高多少级', expect: 'hit', hint: '强化上限' },
  { q: '红名是什么', expect: 'hit', hint: '红名' },
  { q: '沙巴克攻城战怎么参加', expect: 'hit', hint: '攻城战怎么参加' },
  { q: 'VIP会过期吗', expect: 'hit', hint: 'VIP 会过期' },
  { q: '月卡多少钱', expect: 'hit', hint: '月卡' },
  { q: '首充有什么奖励', expect: 'hit', hint: '首充' },
  { q: '交易有手续费吗', expect: 'hit', hint: '手续费' },
  { q: '每日签到有什么奖励', expect: 'hit', hint: '签到' },
  { q: '游戏卡顿怎么办', expect: 'hit', hint: '卡顿' },
  { q: '忘记密码怎么办', expect: 'hit', hint: '忘记密码' },
  { q: '账号被盗了怎么办', expect: 'hit', hint: '账号被盗' },
  { q: '怎么联系客服', expect: 'hit', hint: '联系客服' },
  { q: '怎么加入行会', expect: 'hit', hint: '加入行会' },
  { q: '怎么结婚', expect: 'hit', hint: '结婚' },
  { q: '翅膀多少级解锁', expect: 'hit', hint: '翅膀' },
  { q: '背包不够用怎么办', expect: 'hit', hint: '背包' },
  { q: 'BOSS什么时候刷新', expect: 'hit', hint: '刷新时间' },
  { q: '副本每天能打几次', expect: 'hit', hint: '副本' },
  { q: '氪金有哪几个档位', expect: 'hit', hint: '充值档位' },
  { q: '我充钱了没到账', expect: 'hit', hint: '未到账' },
  { q: '用外挂会被封号吗', expect: 'hit', hint: '封号' },
  { q: '怎么切换账号', expect: 'hit', hint: '切换账号' },

  // 扩充后新增内容的对位校验（2026-10-19）
  { q: '公测会删档吗', expect: 'hit', hint: '删档' },
  { q: '苹果和安卓能一起玩吗', expect: 'hit', hint: '互通' },
  { q: '转生后等级会清零吗', expect: 'hit', hint: '重置到 1 级' },
  { q: '强化失败装备会碎吗', expect: 'hit', hint: '不会碎' },
  { q: '红装从哪里掉', expect: 'hit', hint: '深渊挑战' },
  { q: '未成年一天能玩多久', expect: 'hit', hint: '未成年' },
  { q: '微信代充安全吗', expect: 'hit', hint: '代充' },
  { q: '小孩误充值能退吗', expect: 'hit', hint: '监护人' },
  { q: '线下交易会被封号吗', expect: 'hit', hint: '线下交易' },
  { q: '新手第一天做什么', expect: 'hit', hint: '主线' },
  { q: '官方会要我密码吗', expect: 'hit', hint: '绝对不会' },
  { q: '怎么识别钓鱼网站', expect: 'hit', hint: '域名' },
  { q: '时装加属性吗', expect: 'hit', hint: '属性时装' },
  { q: '战力压制是什么', expect: 'hit', hint: '战力差' },
  { q: '账号怎么注销', expect: 'hit', hint: '冷静期' },
  { q: '月卡和终身卡买哪个划算', expect: 'hit', hint: '终身卡' },
  { q: '装备先强化哪个部位', expect: 'hit', hint: '武器' },
  { q: '攻城战赢了有什么奖励', expect: 'hit', hint: '城主' },

  { q: '能退款吗', expect: 'hit', hint: '退款' },

  // 价格意图：同一个问题的七种问法，全部要落到「游戏是免费的吗」
  // （改造前只有「免费」这一种问法可用，其余五种兜底、一种误命中）
  { q: '游戏收费吗', expect: 'hit', hint: '免费' },
  { q: '游戏要钱吗', expect: 'hit', hint: '免费' },
  { q: '下载要钱吗', expect: 'hit', hint: '免费' },
  { q: '玩这个游戏花钱吗', expect: 'hit', hint: '免费' },
  { q: '需要付费吗', expect: 'hit', hint: '免费' },
  { q: '游戏收不收费', expect: 'hit', hint: '免费' },
  { q: '白嫖能玩吗', expect: 'hit', hint: '免费' },

  // 排序与归一改造的回归位（覆盖率降为闸门、词频截断、剥离后长词归一）
  { q: '月卡多少钱', expect: 'hit', hint: '售价' },
  { q: '要买月卡吗', expect: 'hit', hint: '月卡' },
  { q: '装备怎么升级', expect: 'hit', hint: '强化' },
  { q: '游戏官网是多少', expect: 'miss' },
  { q: '你们公司在哪里', expect: 'miss' },
  { q: '今天天气怎么样', expect: 'miss' },
  { q: '游戏什么时候关服', expect: 'miss' },
  { q: '能送我一个VIP吗', expect: 'miss' }
];

let ok = 0, fail = [];
console.log('客服 RAG 检索测试　知识块 %d 条\n', kb.chunks.length);

CASES.forEach(function (c) {
  const r = RAG.search(kb.chunks, index, c.q);
  const b = r.best || {};
  const got = r.hit ? 'hit' : 'miss';
  let pass = got === c.expect;
  if (pass && c.expect === 'hit' && c.hint) {
    pass = (r.hit.q + r.hit.a).indexOf(c.hint) >= 0;
  }
  if (pass) ok++; else fail.push(c.q);

  const mark = pass ? '  ✓' : '  ✗';
  const detail = r.hit
    ? '命中「' + r.hit.q + '」'
    : '兜底（' + r.reason + '）';
  console.log('%s %s\n      %s  cover=%s score=%s', mark, c.q, detail,
    (b.cover === undefined ? '-' : b.cover.toFixed(2)),
    (b.score === undefined ? '-' : b.score.toFixed(2)));
  if (VERBOSE && r.top && r.top.length) {
    r.top.forEach(function (t) {
      console.log('        · %s  cover=%s score=%s', t.chunk.q,
        t.cover.toFixed(2), t.score.toFixed(2));
    });
  }
});

console.log('\n通过 %d / %d', ok, CASES.length);
if (fail.length) {
  console.log('未通过：');
  fail.forEach(function (q) { console.log('  -', q); });
  process.exitCode = 1;
}
