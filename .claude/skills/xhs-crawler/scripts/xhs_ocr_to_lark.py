#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书笔记(通用 OCR 版)→ 飞书多维表格

读 xhs_ocr.py 产出的 notes_enriched.json（通用 OCR：noteImg_ocr / comments_text，
主题无关）+ 关联原始 *.json（拿图片 URL）→ 新建多维表格（通用 schema）→ lark-cli 写记录。

与 xhs_to_lark.py 的区别：后者是「简历专用」schema（求职方向/教育/经历…），
只配 xhs_enrich.py 的简历富化输出；本脚本面向任意主题的 OCR 结果，
适合「用户访谈追问技巧」这类非简历内容。

用法：
    python3 xhs_ocr_to_lark.py <outdir>
    python3 xhs_ocr_to_lark.py <outdir> <notes_enriched.json>

环境变量：
    LARK_PROFILE        ★ 有 base scope 的 SA profile（默认 profile「猎聘」缺 base:app:create
                        等 scope，会 missing_scope 报错）。用 cli_aa823d7922f8dbc3（与 xhs_to_lark.py 一致）。
    XHS_TO_LARK_BASE    已有多维表格 token；不设则新建
    XHS_TO_LARK_NAME    新表名（默认取 state.json 的 keyword + 日期）
    XHS_TO_LARK_TABLE   数据表名（默认 "笔记"）

全程 --as user（bot 建的表用户打不开）。
"""

import os, sys, json, re, glob, subprocess

# 通用 schema（9 列，主题无关）
FIELDS = [
    {"name": "序号", "type": "number"},
    {"name": "标题", "type": "text"},
    {"name": "正文", "type": "text"},
    {"name": "图片OCR", "type": "text"},            # noteImg_ocr（核心内容，图里的方法论/话术）
    {"name": "评论精华", "type": "text"},            # comments_text（已格式化，含回复层级）
    {"name": "互动", "type": "text"},               # barText 解析的 赞/藏/评
    {"name": "评论数", "type": "number"},           # total_comments
    {"name": "图片", "type": "text"},               # noteImgs URL 换行
    {"name": "链接", "type": "text", "style": {"type": "url"}},  # explore URL
]
COLS = [f["name"] for f in FIELDS]


PROFILE = os.environ.get("LARK_PROFILE", "")


def run_lark(args):
    """调 lark-cli base，user 身份。LARK_PROFILE 可指定有 base scope 的 SA profile。
    失败即退出并打印 stderr。"""
    cmd = ["lark-cli", "base"]
    if PROFILE:
        cmd += ["--profile", PROFILE]
    cmd += args + ["--as", "user"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("✗ lark-cli 失败: " + " ".join(args[:2]))
        print((r.stderr or r.stdout)[-1000:])
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
    out = run_lark(["+base-create", "--name", name, "--table-name", table,
                    "--fields", json.dumps(FIELDS, ensure_ascii=False)])
    d = json.loads(out)
    bt = find_key(d, "app_token") or find_key(d, "base_token")
    url = find_key(d, "url")
    if not bt:
        print("✗ 建表未返回 token，原始输出：\n" + out[:500])
        sys.exit(1)
    print("✓ 新建多维表格：%s\n  base_token = %s\n  %s" % (name, bt, url))
    return bt


def parse_engage(bar_text):
    """从 barText 提取数字 → '赞181/藏258/评45'。去年份/大数噪音。"""
    nums = re.findall(r'\d+', bar_text or "")
    nums = [n for n in nums if int(n) < 100000]
    if not nums:
        return ""
    labels = ["赞", "藏", "评"]
    return " ".join("%s%s" % (labels[i], nums[i]) for i in range(min(len(nums), 3)))


def load_original_img_map(outdir):
    """读原始 *.json，建 {note_id: [图片URL]}，用于补 xhs_ocr.py 丢掉的 noteImgs。"""
    m = {}
    for fp in sorted(glob.glob(os.path.join(outdir, "*.json"))):
        if os.path.basename(fp) in ("state.json", "notes_enriched.json", "notes_order.json"):
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        nid = d.get("note_id")
        if nid:
            m[nid] = (d.get("meta", {}) or {}).get("noteImgs", []) or []
    return m


def build_rows(notes, img_map):
    rows = []
    for seq, n in enumerate(notes, 1):
        nid = n.get("note_id", "")
        imgs = img_map.get(nid, [])
        rows.append([
            seq,
            (n.get("title") or "")[:200],
            (n.get("desc") or "")[:2000],
            (n.get("noteImg_ocr") or "")[:8000] or None,
            (n.get("comments_text") or "")[:6000] or None,
            parse_engage(n.get("barText")) or None,
            n.get("total_comments", 0) or 0,
            "\n".join(imgs) if imgs else None,
            ("https://www.xiaohongshu.com/explore/%s" % nid) if nid else None,
        ])
    return rows


def main():
    if len(sys.argv) < 2:
        print("用法: python3 xhs_ocr_to_lark.py <outdir> [notes_enriched.json]")
        sys.exit(1)
    outdir = sys.argv[1]
    enriched_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(outdir, "notes_enriched.json")
    if not os.path.exists(enriched_path):
        print("✗ 找不到 %s（先跑 xhs_ocr.py）" % enriched_path)
        sys.exit(1)

    notes = json.load(open(enriched_path, encoding="utf-8"))
    img_map = load_original_img_map(outdir)
    print("加载 %d 篇 ← %s" % (len(notes), enriched_path))

    # 表名：优先 state.json 的 keyword
    table = os.environ.get("XHS_TO_LARK_TABLE", "笔记")
    name = os.environ.get("XHS_TO_LARK_NAME")
    if not name:
        try:
            st = json.load(open(os.path.join(outdir, "state.json"), encoding="utf-8"))
            kw = st.get("keyword", "小红书笔记")
        except Exception:
            kw = "小红书笔记"
        name = "%s %s" % (kw, __import__("datetime").datetime.now().strftime("%Y%m%d"))

    bt = os.environ.get("XHS_TO_LARK_BASE")
    if not bt:
        bt = create_base(name, table)
    else:
        print("✓ 使用已有多维表格：%s（须已有匹配字段 schema）" % bt)

    rows = build_rows(notes, img_map)
    print("写入 %d 行…" % len(rows))
    BATCH = 200
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        payload = json.dumps({"fields": COLS, "rows": batch}, ensure_ascii=False)
        run_lark(["+record-batch-create", "--base-token", bt, "--table-id", table,
                  "--json", payload])
    print("✓ 写入完成 → https://feishu.cn/base/%s" % bt)


if __name__ == "__main__":
    main()
