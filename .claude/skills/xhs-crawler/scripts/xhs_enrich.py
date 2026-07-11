#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书笔记 VL 富化 — 经 new-api 网关用 Qwen3-VL 做简历截图 OCR + 结构化提取

只处理 noteImgs 非空的笔记（有简历截图）。每篇一次 VL 调用，同时产出：
  - ocr       简历截图 OCR 全文（逐字提取，多图用 --- 分隔）
  - fields    结构化要点 {求职方向, 教育, 经历, 项目, 技能, 亮点}
  - summary   一句话内容摘要
  - category  分类：模板展示 / 经验方法 / 求评改简历 / 岗位分析 / 其他
  - tags      1~3 个标签

架构对齐 x-to-feishu 的 x_enrich.py：原子脚本、断点续存、并发、重试退避。
图片走小红书 CDN（带 Referer 绕防盗链），原图 base64 直传（简历 OCR 需清晰度，不降采样）。

用法：
    XHS_ENRICH_DIR="xhs_data/20260704_xxx" python3 xhs_enrich.py
    python3 xhs_enrich.py path/to/dir_or_file
环境变量：
    NEWAPI_TOKEN          必填：new-api 网关令牌（见 x-to-feishu/references/gateway.md）
    NEWAPI_BASE_URL       网关地址（默认 http://<YOUR_SERVER_IP>:3000/v1/chat/completions）
    NEWAPI_MODEL          Qwen/Qwen3-VL-8B-Instruct
    XHS_ENRICH_DIR        输入输出目录
    XHS_ENRICH_WORKERS    并发（默认 4）
    XHS_ENRICH_MAX_IMAGES 每篇最多喂几张图（默认 6，控体积）

断点续存：已富化的 note_id 写入 notes_enriched.json，重跑自动跳过。
"""

import os, sys, json, re, time, base64, glob, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

TOK = os.environ.get("NEWAPI_TOKEN", "")
URL = os.environ.get("NEWAPI_BASE_URL", "http://<YOUR_SERVER_IP>:3000/v1/chat/completions")
MODEL = os.environ.get("NEWAPI_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
MAX_IMAGES = int(os.environ.get("XHS_ENRICH_MAX_IMAGES", "6"))
VALID_CAT = {"模板展示", "经验方法", "求评改简历", "岗位分析", "其他"}

PROMPT = """你是简历分析助手。用户给你一篇小红书笔记的【标题/正文】和【配图】（简历截图，可能多张）。结合图文完成：
1) 简历OCR：逐字提取所有配图里的文字（简历原文，尽量完整准确，多张图之间用 --- 分隔）。
2) 结构化要点（从图文提取，没有的项留空）：
   - 求职方向：如 AI产品经理 / 校招 / 实习 / 转行
   - 教育：学历 / 学校 / 专业
   - 经历：工作或实习经历要点
   - 项目：项目经历（尤其 AI / Agent / RAG / VibeCoding 相关，重点摘录）
   - 技能：硬技能 / 工具
   - 亮点：这份简历最值得借鉴的 1~3 个点
3) 内容摘要：一句话概括这篇笔记在讲什么。
4) 归类到以下之一：
   - 模板展示：贴出完整简历模板/范例
   - 经验方法：讲简历怎么写（方法论/技巧）
   - 求评改简历：作者贴自己简历求锐评/指点/拷打
   - 岗位分析：讲某个岗位简历看重什么
   - 其他
5) 标签：1~3 个中文标签（如 "VibeCoding"、"校招"、"Agent项目"、"RAG"）。

只输出一行 JSON，不要 markdown 代码块、不要解释：
{"ocr":"<简历OCR全文>","fields":{"求职方向":"...","教育":"...","经历":"...","项目":"...","技能":"...","亮点":"..."},"summary":"<一句话摘要>","category":"<模板展示|经验方法|求评改简历|岗位分析|其他>","tags":["..."]}
"""


def fetch_image_b64(url, timeout=20, retries=3):
    """下载小红书图（带 Referer 绕防盗链），返回 data:image/jpeg;base64,... 或 None。
    简历 OCR 需清晰度，保留原图不降采样（与 xhs_export.py 同一下载策略）。
    带重试：并发批量下载时小红书 CDN 会偶发限流/超时，重试可救回大部分。"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                'Referer': 'https://www.xiaohongshu.com/'})
            raw = urllib.request.urlopen(req, timeout=timeout).read()
            return "data:image/jpeg;base64," + base64.b64encode(raw).decode()
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 + attempt * 2)   # 2s, 4s 退避
    return None


def call_model(note, timeout=180):
    """视觉感知富化：标题/正文 + 简历截图(base64) 喂 VL。返回 {ocr, fields, summary, category, tags}。"""
    meta = note.get("meta", {}) or {}
    title = (meta.get("title") or "").strip()
    desc = (meta.get("desc") or "").strip()
    imgs = (meta.get("noteImgs") or [])[:MAX_IMAGES]
    text = (f"标题: {title}\n正文: {desc}") if (title or desc) else "(无正文，纯图帖，请只看图分析)"
    content = [{"type": "text", "text": PROMPT + "\n笔记图文:\n" + text}]
    n_ok = 0
    for u in imgs:
        b64 = fetch_image_b64(u)
        if b64:
            content.append({"type": "image_url", "image_url": {"url": b64}})
            n_ok += 1
    if n_ok == 0:
        return {"ocr": "", "fields": {}, "summary": "", "category": "其他",
                "tags": [], "_err": "no_image_fetched"}
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return parse_response(d["choices"][0]["message"]["content"].strip())


def parse_response(content):
    """从模型输出里抠 JSON（兼容 ```json``` 包裹 / 多余文字）。"""
    m = re.search(r'\{.*\}', content, re.S)
    raw = m.group(0) if m else content
    try:
        obj = json.loads(raw)
    except Exception:
        # 兜底：整段当 OCR 文本
        return {"ocr": content[:1500], "fields": {}, "summary": "", "category": "其他", "tags": []}
    ocr = (obj.get("ocr") or "").strip()
    fields = obj.get("fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    summary = (obj.get("summary") or "").strip()
    cat = (obj.get("category") or "其他").strip()
    if cat not in VALID_CAT:
        cat = "其他"
    tags = obj.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tags = [str(t).strip() for t in tags if str(t).strip()][:3]
    return {"ocr": ocr, "fields": fields, "summary": summary, "category": cat, "tags": tags}


def enrich_one(note):
    """带重试 + 401/429/502 退避。只对有图笔记调 VL。返回 (note_id, enrich_dict_or_None)。"""
    nid = note.get("note_id")
    if not nid:
        return None, None
    imgs = (note.get("meta", {}) or {}).get("noteImgs") or []
    if not imgs:
        return nid, {"ocr": "", "fields": {}, "summary": "", "category": "其他",
                     "tags": [], "_skipped": "no_image"}
    last = None
    for attempt in range(4):
        try:
            return nid, call_model(note)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 429):
                time.sleep(15)
            elif e.code in (502, 503):
                time.sleep(8)
            else:
                time.sleep(3)
        except Exception as e:
            last = e
            time.sleep(3)
    print(f"  ✗ {nid} 失败: {type(last).__name__} {str(last)[:80]}", flush=True)
    return nid, None


def load_notes(path):
    """加载目录下所有笔记 JSON（按 note_id 识别，排除 state.json/notes_enriched.json）。返回 list。"""
    if os.path.isfile(path):
        return [json.load(open(path, encoding="utf-8"))]
    notes = []
    for fp in sorted(glob.glob(os.path.join(path, "*.json"))):
        if os.path.basename(fp) in ("state.json", "notes_enriched.json"):
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
            if isinstance(d, dict) and d.get("note_id"):
                notes.append(d)
        except Exception:
            pass
    return notes


def _save(notes, enriched, out_path):
    """把富化结果合并回笔记结构落盘（保留全部笔记，无图/失败的 enriched=None）。"""
    out = []
    for n in notes:
        nid = n.get("note_id")
        item = dict(n)
        item["enriched"] = enriched.get(nid)
        out.append(item)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def main():
    if not TOK:
        print("✗ 未设置 NEWAPI_TOKEN（new-api 网关令牌，见 x-to-feishu/references/gateway.md）")
        sys.exit(1)
    arg = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "XHS_ENRICH_DIR", f"xhs_data/{time.strftime('%Y%m%d')}")
    base_dir = arg if os.path.isdir(arg) else (os.path.dirname(arg) or ".")
    out_path = os.path.join(base_dir, "notes_enriched.json")
    workers = int(os.environ.get("XHS_ENRICH_WORKERS", "4"))

    notes = load_notes(arg)
    with_img = [n for n in notes if (n.get("meta", {}) or {}).get("noteImgs")]
    print(f"加载 {len(notes)} 篇笔记，其中 {len(with_img)} 篇有图 ← {arg}", flush=True)

    # 断点续存：只认真正成功的（ocr 非空）。_err（图下载失败）的不续存，重跑会重试。
    enriched = {}
    if os.path.exists(out_path):
        try:
            for n in json.load(open(out_path, encoding="utf-8")):
                e = n.get("enriched")
                if n.get("note_id") and e and e.get("ocr"):
                    enriched[n["note_id"]] = e
            print(f"续存：已有 {len(enriched)} 篇有效富化结果，跳过", flush=True)
        except Exception:
            pass

    todo = [n for n in with_img if n["note_id"] not in enriched]
    print(f"待富化 {len(todo)} 篇，并发 {workers} …", flush=True)

    ok = fail = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(enrich_one, n): n for n in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            nid, result = fut.result()
            if result is None:
                fail += 1
            else:
                enriched[nid] = result
                ok += 1
            # 进度 + 增量落盘（每 3 篇存一次，防中途崩）
            if i % 3 == 0 or i == len(todo):
                _save(notes, enriched, out_path)
                print(f"  [{i}/{len(todo)}] 成功 {ok} 失败 {fail} | 累计 {len(enriched)} "
                      f"| {time.time()-t0:.0f}s", flush=True)

    _save(notes, enriched, out_path)
    print(f"\n完成：成功 {ok} / 失败 {fail} / 累计 {len(enriched)} → {out_path}")


if __name__ == "__main__":
    main()
