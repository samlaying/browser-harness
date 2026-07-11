#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X 推文 → 飞书多维表格（原子脚本 ③）

读 tweets_enriched.json →（可选）新建多维表格含 schema → 批量写入记录。
通过 lark-cli（须已登录）。

用法：
    # 新建表并写入（默认）
    python3 x_to_lark.py [tweets_enriched.json]
    # 写入已有多维表格（须已有匹配字段）
    X_TO_LARK_BASE=<base_token> python3 x_to_lark.py [tweets_enriched.json]

环境变量：
    X_TO_LARK_BASE   已有多维表格 token；不设则新建一个
    X_TO_LARK_NAME   新表名（默认 "X 推文巡检 <YYYYMMDD>"）
    X_TO_LARK_TABLE  数据表名（默认 "推文"）
    XENRICH_DIR      默认输入目录（默认 x_data/<今天>_fetch）
"""

import os, sys, json, time, subprocess

# 多维表格字段 schema（与 x_enrich 输出对齐）
FIELDS = [
    {"name": "序号", "type": "number"},
    {"name": "作者", "type": "text"},
    {"name": "时间", "type": "text"},
    {"name": "原文", "type": "text"},
    {"name": "中文翻译", "type": "text"},
    {"name": "分类", "type": "select",
     "options": [{"name": n} for n in ["项目", "趋势", "观点", "通用", "其他"]]},
    {"name": "标签", "type": "text"},
    {"name": "点赞", "type": "number"},
    {"name": "图片", "type": "text"},
    {"name": "视频", "type": "text"},
    {"name": "OCR", "type": "text"},
    {"name": "链接", "type": "text"},
]
COLS = [f["name"] for f in FIELDS]

# 可选：指定 lark-cli profile（如多账号时用 SA 账号而非默认）
PROFILE = os.environ.get("LARK_PROFILE", "")


def run_lark(args):
    cmd = ["lark-cli", "base"]
    if PROFILE:
        cmd += ["--profile", PROFILE]
    cmd += args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"✗ lark-cli 失败: {' '.join(args[:2])}" + (f" (profile={PROFILE})" if PROFILE else ""))
        print(r.stderr[-500:] or r.stdout[-500:])
        sys.exit(1)
    return r.stdout


def find_key(o, key):
    """递归找第一个匹配的 key 值（lark-cli 返回结构嵌套较深）。"""
    if isinstance(o, dict):
        if key in o:
            return o[key]
        for v in o.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def create_base(name, table):
    out = run_lark(["+base-create", "--as", "user", "--name", name,
                    "--table-name", table, "--fields", json.dumps(FIELDS, ensure_ascii=False)])
    d = json.loads(out)
    bt = find_key(d, "app_token") or find_key(d, "base_token")
    url = find_key(d, "url")
    if not bt:
        print("✗ 建表未返回 token，原始输出：\n", out[:500]); sys.exit(1)
    print(f"✓ 新建多维表格：{name}\n  base_token = {bt}\n  {url}")
    return bt


def build_rows(tweets):
    rows = []
    for i, t in enumerate(tweets, 1):
        e = t.get("enriched") or {}
        rows.append([
            i,
            f"@{t.get('handle', '')}",
            f"{t.get('time_text', '')} | {t.get('dt', '')}",
            t.get("text", "") or "",
            (e.get("zh") or ""),
            (e.get("category") or "通用"),
            ", ".join(e.get("tags") or []),
            int(t.get("likes", 0) or 0),
            "\n".join(t.get("imgs") or []) or "",
            t.get("url", "") if t.get("has_video") else "",
            (e.get("img") or ""),       # 图片理解+OCR（VL 模型输出）
            t.get("url", "") or "",
        ])
    return rows


def main():
    default_dir = os.environ.get("XENRICH_DIR", f"x_data/{time.strftime('%Y%m%d')}_fetch")
    in_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(default_dir, "tweets_enriched.json")
    tweets = json.load(open(in_path, encoding="utf-8"))
    print(f"加载 {len(tweets)} 条 ← {in_path}")

    table = os.environ.get("X_TO_LARK_TABLE", "推文")
    bt = os.environ.get("X_TO_LARK_BASE")
    if not bt:
        name = os.environ.get("X_TO_LARK_NAME", f"X 推文巡检 {time.strftime('%Y%m%d')}")
        bt = create_base(name, table)
    else:
        print(f"✓ 使用已有多维表格：{bt}（须已有匹配字段 schema）")

    rows = build_rows(tweets)
    payload = json.dumps({"fields": COLS, "rows": rows}, ensure_ascii=False)
    print(f"写入 {len(rows)} 行（payload {len(payload) // 1024} KB）…")
    run_lark(["+record-batch-create", "--as", "user",
              "--base-token", bt, "--table-id", table, "--json", payload])
    print(f"✓ 写入完成 → https://pcnlp18cy9bm.feishu.cn/base/{bt}")


if __name__ == "__main__":
    main()
