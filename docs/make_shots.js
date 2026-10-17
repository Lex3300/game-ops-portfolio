#!/usr/bin/env node
/**
 * 生成 README 首屏截图：对单文件 index.html 的 6 个区块各截一张，
 * 存到 docs/screenshots/。仅本地维护文档时使用，作品集运行不依赖它。
 *
 * 原理：headless Chrome 开 DevTools 调试端口，CDP 控制滚动到目标区块
 * 后按视口截图（--screenshot 模式固定从页面顶部截，锚点不生效）。
 *
 * 用法（在本目录执行）：
 *   node make_shots.js
 */

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333;
const ROOT = path.resolve(__dirname, "..");
const PAGE = path.join(ROOT, "index.html");
const OUT = path.join(__dirname, "screenshots");

// [输出文件名, 区块选择器, 额外 hash]
const SHOTS = [
  ["01_kpi.png", "block-kpi", ""],
  ["02_tier.png", "block-tier", ""],
  ["03_schedule.png", "block-schedule", ""],
  ["04_console.png", "block-console", "#demo"],
  ["05_cs_rag.png", "block-cs", ""],
  ["06_sentiment.png", "block-senti", ""],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitDevtools() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (r.ok) return;
    } catch (e) { /* chrome 未就绪，继续等 */ }
    await sleep(500);
  }
  throw new Error("Chrome DevTools 端口 60 秒内未就绪");
}

async function main() {
  if (!fs.existsSync(PAGE)) throw new Error("缺少 index.html，先跑 02_dashboard/build_single.py");

  const profile = path.join(process.env.TEMP || __dirname, "wb_shot_profile");
  fs.rmSync(profile, { recursive: true, force: true });

  const chrome = spawn(CHROME, [
    "--headless=new", "--disable-gpu", "--hide-scrollbars",
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    "--window-size=1600,1150", "about:blank",
  ], { stdio: "ignore" });

  try {
    await waitDevtools();

    const fileUrl = pathToFileURL(PAGE).href;
    const r = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(fileUrl)}`, { method: "PUT" });
    const tab = await r.json();

    const ws = new WebSocket(tab.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

    let seq = 0;
    const pending = {};
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id && pending[m.id]) { pending[m.id](m.result); delete pending[m.id]; }
    };
    const send = (method, params) => new Promise((res) => {
      const i = ++seq;
      pending[i] = res;
      ws.send(JSON.stringify({ id: i, method, params: params || {} }));
    });

    await send("Page.enable");
    await sleep(3500); // 等数据渲染 + ECharts 动画结束

    fs.mkdirSync(OUT, { recursive: true });
    for (const [name, sel, hash] of SHOTS) {
      // 带 hash 的截图（区块04）先恢复无 hash，让演示面板保持展开态即可
      const expr = `(function(){
        var el=document.querySelector('#${sel}');
        if(!el) return -1;
        var top=Math.max(0, el.getBoundingClientRect().top + window.scrollY - 24);
        window.scrollTo(0, top);
        return top;
      })()`;
      const ev = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
      if (!ev || !ev.result || ev.result.value < 0) {
        console.log("跳过（找不到区块）", name);
        continue;
      }
      await sleep(800);
      const shot = await send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(OUT, name), Buffer.from(shot.data, "base64"));
      console.log("已截图", name);
    }
    ws.close();
    console.log("全部完成 ->", OUT);
  } finally {
    chrome.kill();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) { /* 清理失败不影响 */ }
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
