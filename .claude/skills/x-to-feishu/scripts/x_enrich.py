#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X 推文 AI 富化 — 经 new-api 网关用 Kimi 做翻译 + 分类 + 打标

每条推文一次 Kimi 调用，同时产出：
  - zh       中文翻译（保留人名/产品名/术语原文）
  - category 分类：项目 / 趋势 / 观点 / 通用 / 其他
  - tags     1~3 个中文标签

用法：
    python3 x_enrich.py [tweets.json]   # 默认 x_data/<dir>/tweets.json
环境变量：
    XENRICH_DIR   输入输出目录（默认 x_data/20260703_fetch）
    XENRICH_WORKERS 并发数（默认 5）

断点续存：已富化的 tid 写入 tweets_enriched.json，重跑自动跳过。
"""

import os, sys, json, re, time, base64, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

TOK = os.environ.get("NEWAPI_TOKEN", "")           # 必填：new-api 网关令牌（见 references/gateway.md）
URL = os.environ.get("NEWAPI_BASE_URL", "http://<YOUR_SERVER_IP>:3000/v1/chat/completions")
MODEL = os.environ.get("NEWAPI_MODEL", "Qwen/Qwen3-VL-8B-Instruct")  # 默认视觉模型（图文感知）

PROMPT = """你是推文分析助手。用户给你一条推文的【正文】和【配图】（可能多张，也可能无图）。结合图文完成：
1) 中文翻译：把正文译成中文（保留人名/产品名/技术术语原文，只输出译文）。
2) 图片理解：用中文简述配图内容，并提取图中文字（OCR）。无图则留空。
3) 归类到以下之一：
   - 项目：发布/上线/开源/新产品/新模型/工具
   - 趋势：未来/将取代/增长/浪潮/普及/拐点
   - 观点：我认为/我觉得/hot take/预测/建议
   - 通用：AI 相关但无明显上述信号
   - 其他：与 AI 无关
4) 给 1~3 个中文标签（结合图文，如 "Claude Code"、"智能体"、"教程"）。

只输出一行 JSON，不要 markdown 代码块、不要解释：
{"zh":"<正文中文译文>","img":"<图片理解+OCR，无图留空>","category":"<项目|趋势|观点|通用|其他>","tags":["<标签>",...]}
"""

VALID_CAT = {"项目", "趋势", "观点", "通用", "其他"}
MAX_IMAGES = int(os.environ.get("XENRICH_MAX_IMAGES", "2"))   # 每条最多喂几张图（控体积/成本）

def fetch_image_b64(url, timeout=15):
    """下载推文图（带 Referer 绕过 X 防盗链），返回 data:image/jpeg;base64,... 或 None。
    用 name=medium 而非 orig——VL 理解够用且 base64 体积小。"""
    url = re.sub(r'name=\w+', 'name=medium', url)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://x.com/'})
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    except Exception:
        return None

def call_model(tweet, timeout=150):
    """视觉感知富化：正文 + 配图(base64) 喂 VL 模型。返回 {zh, img, category, tags}。"""
    text = (tweet.get("text") or "").strip()
    content = [{"type": "text", "text":
        PROMPT + ("\n推文正文:\n" + text if text else "\n(无正文，纯图帖，请只看图分析)")}]
    for u in (tweet.get("imgs") or [])[:MAX_IMAGES]:
        b64 = fetch_image_b64(u)
        if b64:
            content.append({"type": "image_url", "image_url": {"url": b64}})
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return parse_response(d["choices"][0]["message"]["content"].strip())

def parse_response(content):
    """从模型输出里抠 JSON（兼容 ```json``` 包裹 / 多余文字）。"""
    m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.S)
    raw = m.group(0) if m else content
    try:
        obj = json.loads(raw)
    except Exception:
        # 兜底：整段当译文
        return {"zh": content[:500], "img": "", "category": "通用", "tags": []}
    zh = (obj.get("zh") or obj.get("translation") or "").strip()
    img = (obj.get("img") or obj.get("image") or obj.get("ocr") or "").strip()
    cat = (obj.get("category") or obj.get("cat") or "通用").strip()
    if cat not in VALID_CAT:
        cat = "通用"
    tags = obj.get("tags") or obj.get("tag") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tags = [str(t).strip() for t in tags if str(t).strip()][:3]
    return {"zh": zh, "img": img, "category": cat, "tags": tags}

def enrich_one(tweet):
    """带重试 + 401/429 退避。纯文本/纯图/图文都喂 VL 模型。返回 (tid, enrich_dict_or_None)。"""
    tid = tweet.get("tid")
    if not tid:
        return None, None
    text = (tweet.get("text") or "").strip()
    imgs = tweet.get("imgs") or []
    if not text and not imgs:                  # 既无文又无图：没东西可分析
        return tid, {"zh": "", "img": "", "category": "其他", "tags": []}
    last = None
    for attempt in range(4):
        try:
            return tid, call_model(tweet)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 429):
                time.sleep(15)            # 限流/额度：退避
            elif e.code in (502, 503):
                time.sleep(8)
            else:
                time.sleep(3)
        except Exception as e:
            last = e
            time.sleep(3)
    print(f"  ✗ @{tweet.get('handle')} 失败: {type(last).__name__} {str(last)[:80]}", flush=True)
    return tid, None

def main():
    if not TOK:
        print("✗ 未设置 NEWAPI_TOKEN（new-api 网关令牌，见 references/gateway.md）"); sys.exit(1)
    default_dir = os.environ.get("XENRICH_DIR", f"x_data/{time.strftime('%Y%m%d')}_fetch")
    in_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(default_dir, "tweets.json")
    base_dir = os.path.dirname(in_path) or default_dir
    out_path = os.path.join(base_dir, "tweets_enriched.json")
    workers = int(os.environ.get("XENRICH_WORKERS", "5"))

    tweets = json.load(open(in_path, encoding="utf-8"))
    print(f"加载 {len(tweets)} 条推文 ← {in_path}", flush=True)

    # 断点续存
    enriched = {}   # tid -> {zh, category, tags}
    if os.path.exists(out_path):
        try:
            for t in json.load(open(out_path, encoding="utf-8")):
                if t.get("tid") and t.get("enriched"):
                    enriched[t["tid"]] = t["enriched"]
            print(f"续存：已有 {len(enriched)} 条富化结果，跳过", flush=True)
        except Exception:
            pass

    todo = [t for t in tweets if t.get("tid") and t["tid"] not in enriched]
    print(f"待富化 {len(todo)} 条，并发 {workers} …", flush=True)

    ok = fail = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(enrich_one, t): t for t in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            tid, result = fut.result()
            if result is None:
                fail += 1
            else:
                enriched[tid] = result
                ok += 1
            # 进度 + 增量落盘（每 5 条存一次，防中途崩）
            if i % 5 == 0 or i == len(todo):
                _save(tweets, enriched, out_path)
                print(f"  [{i}/{len(todo)}] 成功 {ok} 失败 {fail} | 累计 {len(enriched)} "
                      f"| {time.time()-t0:.0f}s", flush=True)

    _save(tweets, enriched, out_path)
    print(f"\n完成：成功 {ok} / 失败 {fail} / 累计 {len(enriched)} → {out_path}")

def _save(tweets, enriched, out_path):
    """把富化结果合并回推文结构落盘。"""
    out = []
    for t in tweets:
        tid = t.get("tid")
        e = enriched.get(tid)
        item = dict(t)
        item["enriched"] = e or None
        out.append(item)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
