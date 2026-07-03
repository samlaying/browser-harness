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

import os, sys, json, re, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

TOK = os.environ.get("NEWAPI_TOKEN", "")           # 必填：new-api 网关令牌（见 references/gateway.md）
URL = os.environ.get("NEWAPI_BASE_URL", "http://192.227.138.214:3000/v1/chat/completions")
MODEL = os.environ.get("NEWAPI_MODEL", "@cf/moonshotai/kimi-k2.7-code")

PROMPT = """你是推文分类助手。对下面这条英文推文完成 3 件事：
1) 翻译成中文（保留人名/产品名/技术术语原文，只输出译文，不要解释）。
2) 归类到以下之一：
   - 项目：发布/上线/开源/新产品/新模型/工具
   - 趋势：未来/将取代/增长/浪潮/普及/拐点
   - 观点：我认为/我觉得/hot take/预测/建议
   - 通用：AI 相关但无明显上述信号
   - 其他：与 AI 无关
3) 给 1~3 个中文标签（短语，如 "Claude Code"、"智能体"、"开源工具"）。

只输出一行 JSON，不要 markdown 代码块、不要解释：
{"zh":"<中文译文>","category":"<项目|趋势|观点|通用|其他>","tags":["<标签1>",...]}

推文：
"""

VALID_CAT = {"项目", "趋势", "观点", "通用", "其他"}

def call_kimi(text, timeout=120):
    """返回 (zh, category, tags) 或失败抛异常。"""
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT + (text or "")}],
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    content = d["choices"][0]["message"]["content"].strip()
    return parse_response(content)

def parse_response(content):
    """从 Kimi 输出里抠 JSON（兼容 ```json``` 包裹 / 多余文字）。"""
    # 先尝试直接找第一个 {...}
    m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.S)
    raw = m.group(0) if m else content
    try:
        obj = json.loads(raw)
    except Exception:
        # 兜底：整段当译文
        return {"zh": content[:500], "category": "通用", "tags": []}
    zh = (obj.get("zh") or obj.get("translation") or "").strip()
    cat = (obj.get("category") or obj.get("cat") or "通用").strip()
    if cat not in VALID_CAT:
        cat = "通用"
    tags = obj.get("tags") or obj.get("tag") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tags = [str(t).strip() for t in tags if str(t).strip()][:3]
    return {"zh": zh, "category": cat, "tags": tags}

def enrich_one(tweet):
    """带重试 + 401 退避（网关令牌限流时返回 401）。返回 (tid, enrich_dict_or_None)。"""
    tid = tweet.get("tid")
    text = tweet.get("text") or ""
    if not text.strip():
        return tid, {"zh": "", "category": "其他", "tags": []}   # 纯图/视频帖
    last = None
    for attempt in range(4):
        try:
            return tid, call_kimi(text)
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 401:
                time.sleep(20)            # 限流窗口：长退避
            elif e.code in (429, 502, 503):
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
