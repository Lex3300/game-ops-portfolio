#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
客服知识库构建（模块⑤）：把《Q&A-RAG.md》（客服答疑手册）切成可检索的知识块。

为什么要有这个脚本
------------------
客服 AI 的答案必须可追溯——每条回复都要能说出「来自手册第几条」。
所以不能把整篇文档丢给模型，而是先切成一条条独立的 QA 知识块：

    ## 分类（一、游戏基本信息 … 十二、玩法与其他）
      └── ###### Q：xxx / A：yyy  →  一个知识块（KB-001）

游戏简介、背景故事这类叙述性内容按段落切成 intro / lore 块，
避免和问答混在一起降低检索精度。

产物
----
    05_cs_rag/kb.json     看板与检索共用的知识库（chunks + 统计 + 分类）
    （同时被 02_dashboard/build_data.py 读入 data.js 的 kb 段）

用法
----
    python 05_cs_rag/build_kb.py            解析手册并写出 kb.json
    python 05_cs_rag/build_kb.py --check    只打印统计，不写文件
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 手册源文件（2026-10-17 由旧文件名统一改名为 Q&A-RAG.md）
SRC = ROOT / "Q&A-RAG.md"
OUT = Path(__file__).resolve().parent / "kb.json"

# 手册所在的二级标题里，哪些是问答、哪些是叙述
FAQ_SECTION = "常见问题答疑"


def parse_manual(text):
    """逐行扫描：识别 ## 分区、### 分类、###### Q/A 问答、普通段落。"""
    chunks = []
    section = ""          # 二级标题：# 常见问题答疑 / 游戏简介 / 背景故事
    cat = ""              # 三级标题分类
    cur = None            # 正在收集的问答
    para = []             # 叙述性段落缓冲

    def flush_para():
        nonlocal para
        if not para:
            return
        body = "\n".join(para).strip()
        if body:
            chunks.append({
                "kind": "narrative",
                "section": section,
                "cat": section,
                "q": section or "概述",
                "a": body,
            })
        para = []

    def flush_qa():
        nonlocal cur
        if not cur:
            return
        ans = "\n".join(cur["a"]).strip()
        if cur["q"] and ans:
            chunks.append({
                "kind": "faq",
                "section": cur["section"],
                "cat": cur["cat"],
                "q": cur["q"],
                "a": ans,
            })
        cur = None

    for raw in text.splitlines():
        line = raw.rstrip()

        # 跳过 front-matter 与分隔线
        if line.strip() in ("---", ""):
            if cur is None and para:
                # 空行是段落边界，但仍可能在连续叙述中，先留着
                para.append("")
            continue
        if line.startswith("AIGC:") or re.match(r"^\s{4}\w+:", line):
            continue

        m1 = re.match(r"^#\s+(.+)$", line)
        if m1:
            flush_qa()
            flush_para()          # 文档大标题不入库
            continue

        m2 = re.match(r"^##\s+(.+)$", line)
        if m2:
            flush_qa()
            flush_para()
            section = m2.group(1).strip()
            cat = section
            continue

        m3 = re.match(r"^###\s+(.+)$", line)
        if m3:
            flush_qa()
            flush_para()
            cat = m3.group(1).strip()
            continue

        mq = re.match(r"^#{4,6}\s*Q[：:]\s*(.+)$", line)
        if mq:
            flush_qa()
            flush_para()
            cur = {"section": section, "cat": cat, "q": mq.group(1).strip(), "a": []}
            continue

        ma = re.match(r"^A[：:]\s*(.*)$", line)
        if ma and cur is not None:
            cur["a"].append(ma.group(1).strip())
            continue

        # 叙述正文
        if cur is not None:
            cur["a"].append(line.strip())
        elif line.strip().startswith(">"):
            continue                      # 文末声明
        else:
            para.append(line.strip())

    flush_qa()
    flush_para()

    # 清理叙述段里的空行残留
    for c in chunks:
        c["a"] = re.sub(r"\n{3,}", "\n\n", c["a"]).strip()
    return [c for c in chunks if c["a"]]


def build(src=SRC):
    text = src.read_text(encoding="utf-8")
    chunks = parse_manual(text)

    # 编号与检索文本（q + a 一起进索引，问句权重更高）
    for i, c in enumerate(chunks, 1):
        c["id"] = "KB-%03d" % i
        c["text"] = (c["q"] + " " + c["a"]) if c["kind"] == "faq" else c["a"]

    cats = {}
    for c in chunks:
        if c["kind"] == "faq":
            cats.setdefault(c["cat"], 0)
            cats[c["cat"]] += 1

    return {
        "_comment": "由 05_cs_rag/build_kb.py 从《Q&A-RAG.md》自动生成，勿手改。",
        "source": src.name,
        "version": "V1.0",
        "built_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "chunks": len(chunks),
            "faq": sum(1 for c in chunks if c["kind"] == "faq"),
            "narrative": sum(1 for c in chunks if c["kind"] != "faq"),
            "categories": len(cats),
            "chars": sum(len(c["text"]) for c in chunks),
        },
        "categories": [{"name": k, "count": v} for k, v in cats.items()],
        "chunks": [{"id": c["id"], "kind": c["kind"], "cat": c["cat"],
                    "q": c["q"], "a": c["a"]} for c in chunks],
    }


def main():
    ap = argparse.ArgumentParser(description="构建客服知识库")
    ap.add_argument("--check", action="store_true", help="只打印统计")
    args = ap.parse_args()

    if not SRC.exists():
        raise SystemExit(f"[ERROR] 找不到手册：{SRC}")
    kb = build()
    st = kb["stats"]
    print("客服知识库构建")
    print(f"  来源   {SRC.name}")
    print(f"  知识块 {st['chunks']} 条（问答 {st['faq']} · 叙述 {st['narrative']}）")
    print(f"  分类   {st['categories']} 类 · 正文 {st['chars']} 字")
    for c in kb["categories"]:
        print(f"         {c['name']}（{c['count']}）")

    if args.check:
        print("\n（--check 模式，未写入文件）")
        return 0

    OUT.write_text(json.dumps(kb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n  [OUT ] {OUT.relative_to(ROOT)}  {OUT.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
