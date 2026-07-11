#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书笔记 → 飞书多维表格（xhs-crawler 阶段 ③）

读 notes_enriched.json（xhs_enrich.py 产物）→ 新建多维表格（简历主题 schema）
→ lark-cli 批量写记录。只入 enriched 非空的笔记（有图且 VL 富化成功）。

架构对齐 x-to-feishu 的 x_to_lark.py：原子脚本、SA 账号、≤200/批。
★ 必须 SA 账号：LARK_PROFILE=cli_aa823d7922f8dbc3（默认 profile 无 base scope）。

用法：
    export LARK_PROFILE=cli_aa823d7922f8dbc3
    # 新建表并写入（默认）
    python3 xhs_to_lark.py [notes_enriched.json]
    # 写入已有多维表格（须已有匹配字段）
    XHS_TO_LARK_BASE=<base_token> python3 xhs_to_lark.py [notes_enriched.json]

环境变量：
    LARK_PROFILE       ★ SA 账号 cli_aa823d7922f8dbc3
    XHS_TO_LARK_BASE   已有多维表格 token；不设则新建
    XHS_TO_LARK_NAME   新表名（默认 "AI产品经理简历 <YYYYMMDD>"）
    XHS_TO_LARK_TABLE  数据表名（默认 "笔记"）
"""

import os, sys, json, re, time, subprocess

# 简历主题 schema（11 列，与 xhs_enrich 输出对齐）
FIELDS = [
    {"name": "序号", "type": "number"},
    {"name": "标题", "type": "text"},
    {"name": "正文", "type": "text"},
    {"name": "简历OCR", "type": "text"},          # enriched.ocr（简历截图文字全文）
    {"name": "结构化要点", "type": "text"},        # enriched.fields 格式化（求职方向/教育/经历/项目/技能/亮点）
    {"name": "内容摘要", "type": "text"},          # enriched.summary
    {"name": "评论精华", "type": "text"},          # 高价值评论（问一问AI总结 + 实质长评，跳过水评）
    {"name": "分类", "type": "select",
     "options": [{"name": n} for n in ["模板展示", "经验方法", "求评改简历", "岗位分析", "其他"]]},
    {"name": "标签", "type": "text"},
    {"name": "互动", "type": "text"},              # barText 解析出的 赞/藏/评
    {"name": "图片", "type": "text"},              # noteImgs URL 换行
    {"name": "链接", "type": "text"},
]
COLS = [f["name"] for f in FIELDS]

PROFILE = os.environ.get("LARK_PROFILE", "")
FIELD_LABELS = ["求职方向", "教育", "经历", "项目", "技能", "亮点"]


def run_lark(args):
    cmd = ["lark-cli", "base"]
    if PROFILE:
        cmd += ["--profile", PROFILE]
    cmd += args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"✗ lark-cli 失败: {' '.join(args[:2])}" + (f" (profile={PROFILE})" if PROFILE else ""))
        print(r.stderr[-800:] or r.stdout[-800:])
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
        print("✗ 建表未返回 token，原始输出：\n", out[:500])
        sys.exit(1)
    print(f"✓ 新建多维表格：{name}\n  base_token = {bt}\n  {url}")
    return bt


def parse_engage(bar_text):
    """从 barText（如 '说点什么... 181 258 45 发送 取消'）提取数字 → '赞181/藏258/评45'。
    xhs engage-bar 顺序通常为 点赞/收藏/评论；无法保证时退化为 'a/b/c'。"""
    nums = re.findall(r'\d+', bar_text or "")
    nums = [n for n in nums if int(n) < 100000]  # 去掉年份/大数噪音
    if not nums:
        return ""
    labels = ["赞", "藏", "评"]
    parts = [f"{labels[i]}{nums[i]}" for i in range(min(len(nums), 3))]
    return " ".join(parts)


def fmt_fields(fields):
    """把结构化要点 dict 格式化成多行文本。"""
    if not fields:
        return ""
    lines = []
    for k in FIELD_LABELS:
        v = fields.get(k) or ""
        v = str(v).replace("\n", " ").strip()
        if v:
            lines.append(f"【{k}】{v}")
    return "\n".join(lines)


# 水评黑名单（求文档/单纯附和等无信息量评论），评论精华里跳过
WATER_COMMENTS = {
    "求文档", "求文档！", "求", "好的", "好", "安排", "可以的", "文档",
    "一键三连啦，求文档", "求文档！", "求锐评", "求批评", "求指点", "求拷打",
}


def fmt_comments(comments, max_n=15):
    """提取高价值评论 → 多行文本。
    保留：问一问 AI 总结（视频/笔记内容逐字稿，价值高）、实质性长评论（含具体建议/讨论）。
    跳过：水评（求文档/单纯附和）、过短无信息评论。问一问总结过长则截断。"""
    if not comments:
        return ""
    out = []
    for c in comments:
        nick = (c.get("nick") or "").strip()
        content = (c.get("content") or "").strip()
        if not content:
            continue
        is_ai = nick == "问一问"
        # 水评跳过
        if content in WATER_COMMENTS:
            continue
        if not is_ai and len(content) < 12:
            continue  # 短评论跳过（问一问不受此限）
        prefix = "@问一问 AI" if is_ai else (f"@{nick}" if nick else "")
        # 问一问总结可能很长（视频逐字稿），截断到 800 字；普通评论截到 300
        cap = 800 if is_ai else 300
        cshow = content[:cap] + ("…" if len(content) > cap else "")
        out.append(f"{prefix}: {cshow}")
        if len(out) >= max_n:
            break
    return "\n".join(out)


def build_rows(notes):
    rows = []
    seq = 0
    for n in notes:
        e = n.get("enriched") or {}
        if not e or (not e.get("ocr") and not e.get("summary")):
            continue  # 跳过未富化/失败的
        if e.get("_err"):
            continue
        seq += 1
        meta = n.get("meta", {}) or {}
        nid = n.get("note_id", "")
        rows.append([
            seq,
            (meta.get("title") or "")[:200],
            (meta.get("desc") or "")[:2000],
            (e.get("ocr") or "")[:8000],
            fmt_fields(e.get("fields"))[:4000],
            (e.get("summary") or "")[:500],
            fmt_comments(n.get("comments"))[:6000],
            (e.get("category") or "其他"),
            ", ".join(e.get("tags") or []),
            parse_engage(meta.get("barText")),
            "\n".join(meta.get("noteImgs") or []) or "",
            f"https://www.xiaohongshu.com/explore/{nid}" if nid else "",
        ])
    return rows


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get("XHS_ENRICH_DIR", f"xhs_data/{time.strftime('%Y%m%d')}"),
        "notes_enriched.json")
    notes = json.load(open(in_path, encoding="utf-8"))
    print(f"加载 {len(notes)} 篇 ← {in_path}")

    table = os.environ.get("XHS_TO_LARK_TABLE", "笔记")
    bt = os.environ.get("XHS_TO_LARK_BASE")
    if not bt:
        name = os.environ.get("XHS_TO_LARK_NAME", f"AI产品经理简历 {time.strftime('%Y%m%d')}")
        bt = create_base(name, table)
    else:
        print(f"✓ 使用已有多维表格：{bt}（须已有匹配字段 schema）")

    rows = build_rows(notes)
    if not rows:
        print("✗ 没有可写入的行（notes_enriched.json 里无有效富化结果）")
        sys.exit(1)

    payload = json.dumps({"fields": COLS, "rows": rows}, ensure_ascii=False)
    print(f"写入 {len(rows)} 行（payload {len(payload) // 1024} KB）…")
    # ≤200/批；这里 14 篇一批够，超 200 再分批
    BATCH = 200
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        p = json.dumps({"fields": COLS, "rows": batch}, ensure_ascii=False)
        run_lark(["+record-batch-create", "--as", "user",
                  "--base-token", bt, "--table-id", table, "--json", p])
    print(f"✓ 写入完成 → https://pcnlp18cy9bm.feishu.cn/base/{bt}")


if __name__ == "__main__":
    main()
