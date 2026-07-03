#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X (Twitter) 页面提取器 — browser-harness (CDP)

聚焦提取（不做 AI 分类）。在当前 x.com/home（或指定 feed 标签）上：
  1) 滚动加载更多推文
  2) 每条若被截断 → 点 "show more" 展开取全文
  3) 提取每条：发帖时间 / 全文 / 点赞数 / 图片原图 URL / 视频标记(poster+status URL)

用法（pipe 给 browser-harness）：
    browser-harness < scripts/x_fetch.py

环境变量：
    XFETCH_MAX_TWEETS  - 目标条数（默认 30，达到即停）
    XFETCH_MAX_ROUNDS  - 滚动轮数上限（默认 40，兜底）
    XFETCH_OUT         - 输出目录（默认 x_data/<YYYYMMDD>_fetch）
    XFETCH_TAB_HINT    - 定位 feed 标签的 URL 片段（默认 x.com/home）
    XFETCH_PAUSE       - 滚动停顿区间 'lo,hi'（默认 1.5,3.0）

视频说明：DOM 里 <video src> 是 blob，拿不到直链。本脚本只记录
has_video + poster(缩略图) + status URL；要可下载 mp4 走阶段 2 的
Network/TweetResultByRestId 流程（见 memory: x-video-download-recipe），
对 video_tweets.json 里的条目按需单独抓。

前提：浏览器已连接、X 已登录、feed 标签可见。
"""

import os, re, json, time, random
from datetime import datetime

# ── 速度 / 重试 ────────────────────────────────────────────

def jitter(lo, hi):
    return random.uniform(lo, hi)

def safe_js(s):
    try:
        return js(s)
    except Exception:
        ensure_daemon(); time.sleep(1.0)
        try:
            return js(s)
        except Exception:
            return None

def _pair(name, default):
    v = os.environ.get(name)
    if v and "," in v:
        try:
            a, b = v.split(","); return (float(a.strip()), float(b.strip()))
        except Exception:
            pass
    return default

# ── 互动数解析 ─────────────────────────────────────────────

def parse_eng(label):
    """'60 Likes. Like' / '1.2K' / '2.3M' → int"""
    if not label:
        return 0
    m = re.search(r'([\d.,]+\s*[KMB]?)', label)
    if not m:
        return 0
    s = m.group(1).replace(',', '').strip().lower()
    mult = 1
    if s.endswith('k'): mult, s = 1_000, s[:-1]
    elif s.endswith('m'): mult, s = 1_000_000, s[:-1]
    elif s.endswith('b'): mult, s = 1_000_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0

# ── 标签管理 ───────────────────────────────────────────────

def attach_feed():
    """找到 x.com/home 标签并 attach（不 reload，保留"当前页面"状态）；没有就新开。"""
    hint = os.environ.get("XFETCH_TAB_HINT", "x.com/home")
    try:
        tabs = list_tabs(include_chrome=False)
    except Exception:
        tabs = []
    for t in tabs:
        url = t.get("url", "") if isinstance(t, dict) else ""
        if hint in url:
            switch_tab(t["targetId"] if isinstance(t, dict) else t)
            time.sleep(0.6)
            return page_info().get("url", url)
    new_tab("https://x.com/home")
    wait_for_load()
    time.sleep(2.5)
    return page_info().get("url", "")

def wait_for_articles(timeout=20):
    for _ in range(int(timeout / 0.5)):
        n = safe_js('return document.querySelectorAll(\'article[data-testid="tweet"]\').length;') or 0
        if n:
            return n
        time.sleep(0.5)
    return 0

# ── 展开 + 提取 ────────────────────────────────────────────

# 点掉当前 DOM 里所有 "show more"（JS .click() 已实测可展开，无需 hover）。
# 返回点击数。展开是 React 异步重渲染，调用方需 sleep 后再提取。
EXPAND_JS = r'''
return [...document.querySelectorAll('[data-testid="tweet-text-show-more-link"]')]
    .map(function(l){ try { l.click(); } catch(e){} return 1; }).length;
'''

EXTRACT_JS = r'''
var arts = document.querySelectorAll('article[data-testid="tweet"]');
var out = [];
arts.forEach(function(a){
    try {
        var txtEl = a.querySelector('[data-testid="tweetText"]');
        var txt = txtEl ? (txtEl.innerText||"").replace(/\s+/g," ").trim() : "";
        var timeEl = a.querySelector("time");
        var dt = timeEl ? timeEl.getAttribute("datetime") : "";
        var time_text = timeEl ? (timeEl.textContent||"").trim() : "";
        var href = timeEl ? ((timeEl.closest("a")&&timeEl.closest("a").getAttribute("href"))||"") : "";
        var handle=""; var tid="";
        var m = href.match(/^\/([^\/]+)\/status\/(\d+)/);
        if (m){handle=m[1]; tid=m[2];}
        var nameEl = a.querySelector('[data-testid="User-Name"]');
        var name = nameEl ? (nameEl.textContent||"").replace(/\s+/g," ").trim().slice(0,60) : "";
        var promoted = /\bPromoted\b|Sponsored/i.test(a.textContent||"");
        function grp(t){var e=a.querySelector('[data-testid="'+t+'"]'); return e? (e.getAttribute('aria-label')||"") : "";}
        // 图片：只要 /media/ 路径（排除头像 profile_images），升级 name=orig 拿原图，去重
        var seen={};
        var imgs = [...a.querySelectorAll('img')].filter(function(i){
            return /pbs\.twimg\.com\/media\//.test(i.src);
        }).map(function(i){
            return i.src.replace(/name=\w+/, 'name=orig');
        }).filter(function(u){ return seen[u] ? false : (seen[u]=true); });
        // 视频：DOM <video> 元素（src 是 blob，无用）；poster 是缩略图。视频卡可能用 videoPlayer testid
        var vid = a.querySelector('video');
        var vp = a.querySelector('[data-testid="videoPlayer"]');
        var has_video = !!(vid || vp);
        var poster = vid ? (vid.poster||"") : "";
        out.push({tid:tid, handle:handle, name:name, text:txt, dt:dt, time_text:time_text,
                  href:href, promoted:promoted,
                  reply:grp("reply"), rt:grp("retweet"), like:grp("like"), view:grp("analytics"),
                  imgs:imgs, has_video:has_video, video_poster:poster});
    } catch(e){}
});
return JSON.stringify(out);
'''

def expand_showmore():
    return safe_js(EXPAND_JS) or 0

def extract_batch():
    raw = safe_js(EXTRACT_JS)
    try:
        return json.loads(raw or "[]")
    except Exception:
        return []

# ── 滚动 / 边界 ────────────────────────────────────────────

def human_scroll():
    # 滚约一屏/轮（0.9 × 视口高），逐步逼近底部触发 X 的 lazy-load。
    # 之前每轮只滚 ~900px，永远到不了底部 → lazy-load 不触发，卡在已加载窗口里。
    vh = safe_js('return window.innerHeight;') or 800
    safe_js(f"window.scrollBy(0, {int(vh * 0.9)})")
    time.sleep(jitter(0.25, 0.5))   # 给 lazy-load 一点反应时间

# ── 主流程 ─────────────────────────────────────────────────

ensure_daemon()
start_dt = datetime.now()
url = attach_feed()
n = wait_for_articles()
print(f"✓ attach {url} | 当前 {n} 条 article", flush=True)

out_dir = os.environ.get("XFETCH_OUT") or f"x_data/{start_dt.strftime('%Y%m%d')}_fetch"
os.makedirs(out_dir, exist_ok=True)
max_tweets = int(os.environ.get("XFETCH_MAX_TWEETS", "30"))
max_rounds = int(os.environ.get("XFETCH_MAX_ROUNDS", "60"))
pause = _pair("XFETCH_PAUSE", (1.5, 3.0))

all_path = os.path.join(out_dir, "tweets.json")
seen = set()
collected = []
# 续扫：若已有 tweets.json，作为基线（去重 + 累加），本次只增量收新推文
if os.path.exists(all_path):
    try:
        prior = json.load(open(all_path, encoding="utf-8"))
        collected = list(prior)
        seen = {t.get("tid") for t in prior if t.get("tid")}
        print(f"✓ 续扫：已有 {len(seen)} 条作为基线，本次只增量", flush=True)
    except Exception:
        pass
stall = 0
prev_ph = 0
reason = "max_rounds"
start_new = len(collected)          # 基线条数，用于"本次新增"统计

for rnd in range(max_rounds):
    # 1) 展开当前页所有截断长帖
    clicked = expand_showmore()
    if clicked:
        time.sleep(0.7)  # 等 React 重渲染全文
    # 2) 提取
    batch = extract_batch()
    new = 0; old = 0; page_total = 0
    for t in batch:
        tid = t.get("tid")
        if not tid:
            continue
        page_total += 1
        if tid in seen:
            old += 1
            continue
        seen.add(tid)
        t["likes"]   = parse_eng(t.get("like"))
        t["reposts"] = parse_eng(t.get("rt"))
        t["replies"] = parse_eng(t.get("reply"))
        t["views"]   = parse_eng(t.get("view"))
        t["url"]     = f"https://x.com{t.get('href','')}" if t.get("href") else ""
        t["promoted"] = bool(t.get("promoted"))
        t["scan_round"] = rnd
        collected.append(t)
        new += 1

    overlap = (old / page_total) if page_total else 0.0
    ph = safe_js('return document.documentElement.scrollHeight;') or 0
    grew = (ph - prev_ph) > 50
    prev_ph = ph
    # ★ 关键修复：旧推文(overlap)不算 stall——深度往下扫时，中间段本就是已收过的；
    # 只有"既无新推文、页面高度也不增长"才视为真的到底（feed 真的没货了）。
    stuck = (new == 0) and (not grew)
    stall = stall + 1 if stuck else 0
    with_img = sum(1 for t in collected if t.get("imgs"))
    with_vid = sum(1 for t in collected if t.get("has_video"))
    print(f"round {rnd:02d}: 展开{clicked} | 页面{page_total} | 新{new} | 累计{len(collected)} "
          f"| 高度{ph}{'↑' if grew else '·'} stall{stall} | 图{with_img} 视{with_vid}", flush=True)

    if len(collected) >= max_tweets:
        reason = "target_reached"; break
    if stall >= 6:
        reason = "stall"; break
    if (datetime.now() - start_dt).total_seconds() >= 300:
        reason = "time_cap"; break

    human_scroll()
    time.sleep(jitter(*pause))

# ── 落盘 ──────────────────────────────────────────────────

all_path = os.path.join(out_dir, "tweets.json")
with open(all_path, "w", encoding="utf-8") as f:
    json.dump(collected, f, ensure_ascii=False, indent=2)

# 视频帖索引（供阶段 2 按需抓 mp4）
video_tweets = [
    {"tid": t["tid"], "handle": t["handle"], "url": t["url"],
     "poster": t.get("video_poster", ""), "text": (t.get("text") or "")[:80]}
    for t in collected if t.get("has_video")
]
with open(os.path.join(out_dir, "video_tweets.json"), "w", encoding="utf-8") as f:
    json.dump(video_tweets, f, ensure_ascii=False, indent=2)

REASON_ZH = {
    "target_reached": "📦 达到目标条数",
    "stall": "⏸ 连续多轮无新增",
    "time_cap": "⏱ 到时收手",
    "max_rounds": "🏁 跑满轮数",
}
print("\n" + "=" * 56)
print(f"提取完成 → {out_dir}")
new_cnt = len(collected) - start_new
print(f"共 {len(collected)} 条（本次新增 {new_cnt}）| 含图 {with_img} / 含视频 {with_vid} | 停止：{REASON_ZH.get(reason, reason)}")
print(f"  tweets.json        — 全部字段")
print(f"  video_tweets.json  — {len(video_tweets)} 条视频帖（mp4 按需单独抓）")
if collected:
    print("\n样本（前 3 条）:")
    for t in collected[:3]:
        txt = (t["text"] or "").replace("\n", " ")[:70]
        print(f"  @{t['handle']} [{t['time_text']}] ❤{t['likes']} 🖼{len(t['imgs'])} {'▶vid' if t['has_video'] else ''}: {txt}")
print("=" * 56)
