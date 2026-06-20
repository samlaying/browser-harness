#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X (Twitter) Home Feed AI 巡检 — browser-harness (CDP)

用法（pipe 给 browser-harness）：
    browser-harness < scripts/x_ai_scan.py

环境变量：
    XAI_MAX_ROUNDS  - 滚动轮数（默认 30）
    XAI_OUT         - 输出目录（默认 xai_data/<YYYYMMDD>_scan）
    XAI_TAB_HINT    - 定位 feed 标签的 URL 片段（默认 x.com/home）

行为：
    1) 找到/打开 home feed 标签并 attach
    2) 滚动 feed，提取每条推文（作者/handle/正文/链接/互动/时间），按推文 ID 去重
    3) 用双语启发式分类器判断是否 AI 相关，并归类为
       trend(趋势) / project(项目) / opinion(观点)
    4) 写出 all_tweets.json（全部）与 ai_hits.json（仅 AI 相关）

前提：浏览器已连接、X 已登录、home feed 可见。
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

# ── AI 分类器（双语启发式）────────────────────────────────

# 核心关键词：命中任一即视为"AI 相关"候选
AI_CORE = [
    # 通用概念
    r'\bAI\b', r'\bA\.I\.\b', r'\bAGI\b', r'\bASI\b', r'superintelligence',
    r'artificial intelligence',
    # 模型 / 公司
    r'ChatGPT', r'\bGPT[-\s]?\d*\b', r'\bClaude\b', r'\bGemini\b', r'\bLlama\b',
    r'\bGrok\b', r'OpenAI', r'Anthropic', r'\bxAI\b', r'DeepMind', r'Mistral',
    r'\bQwen\b', r'DeepSeek', r'\bSora\b', r'\bVeo\b', r'Midjourney',
    r'stable diffusion', r'\bDALL[\- ]?E\b', r'Perplexity', r'Cursor\b',
    # 技术术语
    r'\bLLM(s)?\b', r'large language model', r'machine learning', r'\bML\b',
    r'neural net', r'deep learning', r'\btransformer(s)?\b', r'diffusion model',
    r'generative AI', r'\bGenAI\b', r'foundation model', r'\bRAG\b', r'\bMCP\b',
    r'agentic', r'\bLLM agent', r'AI agent', r'copilot', r'inference',
    r'fine[- ]?tun(e|ing|ed)', r'\bRLHF\b', r'reasoning model', r'\bmultimodal\b',
    r'text.to.image', r'text.to.video', r'prompt engineer', r'\bembedding',
    r'vision model', r'\bvibe coding\b', r'chain.of.thought',
    # 中文
    '人工智能', '大模型', '大语言模型', '智能体', '机器学习', '深度学习',
    '神经网络', '生成式', '多模态', '通用人工智能', '提示词工程', '微调',
    '豆包', '文心', '通义', '智谱', 'Kimi', 'Deepseek', 'deepseek',
]
AI_CORE_RE = re.compile('|'.join(AI_CORE), re.IGNORECASE)

# 项目 / 产品信号
PROJECT = [
    'launch', 'launched', 'releas', 'shipping', 'shipped', 'introduc',
    'is out', 'just dropp', 'open source', 'open-source', 'github', 'repo',
    'demo', 'try it', 'try now', 'beta', 'now live', 'go live', 'we built',
    'new tool', 'new model', 'announc', 'unveil', 'roll out', 'rolled out',
    'available now', 'early access', 'waitlist', 'shipping today', 'out now',
    '发布', '上线', '开源', '推出', '新模型', '新工具', '内测', '公测',
    '可以试', '体验', '更新',
]
# 趋势 / 方向信号
TREND = [
    'trend', 'future of', 'will replace', 'replaced by', r'by 20\d\d', 'adoption',
    'market', 'billion', 'trillion', 'grew', 'growth', 'surge', 'exploding',
    'everyone is', 'going to be', 'inevitab', 'shift', 'era of', 'age of',
    'percent', '% of', 'revolution', 'wave', 'tipping point', 'mainstream',
    'just the beginning', 'take over', 'more powerful than',
    '趋势', '未来', '增长', '爆发', '将取代', '普及', '浪潮', '时代',
    '拐点', '淘汰', '颠覆',
]
# 观点 / 看法信号
OPINION = [
    "i think", "i believe", "imo", "in my opinion", "i feel", "we should",
    "honestly", "the thing is", "hot take", "my take", "i agree", "i disagree",
    "controversial", "unpopular opinion", "i'd argue", "i would argue",
    "my guess", "i predict", "i expect", "i worry", "i'm bullish", "i'm bearish",
    '我认为', '我觉得', '我的看法', '我的观点', '其实', '说实话', '应该',
    '建议', '我不认为', '个人觉得',
]

def _count(text, words):
    c = 0
    low = text.lower()
    for w in words:
        c += low.count(w.lower())
    return c

def classify(text):
    """返回 {is_ai, categories[list], primary, terms[matched AI keywords], score}"""
    text = text or ""
    m = [mt.group(0) for mt in AI_CORE_RE.finditer(text)]
    if not m:
        return {"is_ai": False, "categories": [], "primary": None, "terms": [], "score": 0}
    terms = sorted(set(t.lower() for t in m))
    scores = {
        "project": _count(text, PROJECT),
        "trend": _count(text, TREND),
        "opinion": _count(text, OPINION),
    }
    cats = [k for k, v in scores.items() if v > 0]
    # primary：project > trend > opinion（产品类最有记录价值），并列取分高
    if cats:
        order = {"project": 0, "trend": 1, "opinion": 2}
        primary = sorted(cats, key=lambda k: (-scores[k], order[k]))[0]
    else:
        primary = "general"  # AI 相关但无明显类别信号 —— 归为 general
        cats = ["general"]
    score = sum(scores.values()) + len(terms)
    return {"is_ai": True, "categories": cats, "primary": primary,
            "terms": terms, "score": score}

# ── 互动数解析 ─────────────────────────────────────────────

def parse_eng(label):
    """'102947 Likes. Like' / '1.2K' / '2.3M' → int"""
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

def attach_home():
    """找到 x.com/home 标签并 attach；没有就新开。返回当前 url。"""
    hint = os.environ.get("XAI_TAB_HINT", "x.com/home")
    tabs = []
    try:
        tabs = list_tabs(include_chrome=False)
    except Exception:
        tabs = []
    for t in tabs:
        url = ""
        try:
            url = t.get("url", "") if isinstance(t, dict) else ""
        except Exception:
            pass
        if hint in url:
            switch_tab(t["targetId"] if isinstance(t, dict) else t)
            time.sleep(0.6)
            return page_info().get("url", url)
    # 没找到 → 新开
    new_tab("https://x.com/home")
    wait_for_load()
    time.sleep(2.5)
    return page_info().get("url", "")

def refresh_feed():
    """X 网页版不会主动推流，必须每个 session 主动 reload 一次才拉得到新帖。
    登录用户刷新自己首页是正常行为，不是封号风险；之前只 scrollTo 顶部
    导致一直读同一批旧推（连续 0 新增的根因）。"""
    goto_url("https://x.com/home")
    try:
        wait_for_load()
    except Exception:
        pass
    # 等 feed 渲染出 article（冷启动可能要几秒）
    for _ in range(12):
        n = safe_js('return document.querySelectorAll("article[data-testid=\\"tweet\\"]").length;') or 0
        if n:
            break
        time.sleep(0.5)
    time.sleep(jitter(1.0, 1.8))

# ── 提取 ───────────────────────────────────────────────────

EXTRACT_JS = r'''
var arts = document.querySelectorAll('article[data-testid="tweet"]');
var out = [];
arts.forEach(function(a){
    try {
        var txtEl = a.querySelector('[data-testid="tweetText"]');
        var txt = txtEl ? (txtEl.innerText||"").replace(/\s+/g," ").trim() : "";
        var timeEl = a.querySelector("time");
        var dt = timeEl ? timeEl.getAttribute("datetime") : "";
        var href = timeEl ? (timeEl.closest("a")?.getAttribute("href")||"") : "";
        var handle=""; var tid="";
        var m = href.match(/^\/([^\/]+)\/status\/(\d+)/);
        if (m){handle=m[1]; tid=m[2];}
        var nameEl = a.querySelector('[data-testid="User-Name"]');
        var name = nameEl ? (nameEl.textContent||"").replace(/\s+/g," ").trim().slice(0,60) : "";
        var promoted = /\bPromoted\b|Sponsored/i.test(a.textContent||"");
        var isRT = / reposted\b|@\S+\s+Reposted/i.test((nameEl?nameEl.textContent:""));
        function grp(t){var e=a.querySelector('[data-testid="'+t+'"]'); if(!e) return ""; return e.getAttribute('aria-label')||"";}
        out.push({tid:tid, handle:handle, name:name, text:txt, dt:dt, href:href,
                  promoted:promoted, isRT:isRT,
                  reply:grp("reply"), rt:grp("retweet"), like:grp("like"),
                  view:grp("analytics")});
    } catch(e){}
});
return JSON.stringify(out);
'''

def extract_batch():
    raw = safe_js(EXTRACT_JS)
    try:
        return json.loads(raw or "[]")
    except Exception:
        return []

# ── 持续运转：限速 / 去重存储 / 边界检测 / 会话日志 ─────────

# 全局去重存储：跨所有 session、跨日期目录都认这一份
SEEN_PATH = "xai_data/seen.json"
LOG_PATH  = "xai_data/sessions.log"   # jsonl，每次运行追加一行

# 限速 / 防封配置（都可被环境变量覆盖）
def _pair(name, default):
    """解析 'lo,hi' 形式的环境变量为 (float,float)。"""
    v = os.environ.get(name)
    if v and "," in v:
        try:
            a, b = v.split(","); return (float(a.strip()), float(b.strip()))
        except Exception:
            pass
    return default

PAUSE_SHORT = _pair("XAI_PAUSE_SHORT", (2.0, 4.5))   # 普通滚一屏的停顿区间
PAUSE_LONG  = _pair("XAI_PAUSE_LONG",  (8.0, 16.0))  # 偶尔"认真读一条"的长停顿
P_LONG      = float(os.environ.get("XAI_P_LONG", "0.15"))  # 触发长停顿的概率
MAX_SESSION_SECS = float(os.environ.get("XAI_MAX_SECS", "300"))  # 单次会话时长上限（防封+防断连）
MAX_SESSION_NEW  = int(os.environ.get("XAI_MAX_NEW", "120"))    # 单次最多抓多少条新推文
OVERLAP_RATIO    = float(os.environ.get("XAI_OVERLAP", "0.7"))  # 一页≥此比例为"旧"→视为触边界
OVERLAP_STREAK   = int(os.environ.get("XAI_OVERLAP_STREAK", "2"))  # 连续 N 页触边界→收手

def load_seen():
    if os.path.exists(SEEN_PATH):
        try:
            return set(json.load(open(SEEN_PATH, encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    json.dump(sorted(seen), open(SEEN_PATH, "w", encoding="utf-8"))

def append_log(entry):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def human_scroll():
    """小步多次滚、距离随机——像人手滑，不是脚本大跳。"""
    total = random.randint(480, 820)
    steps = random.choice([2, 3, 4])
    per = total // steps
    for _ in range(steps):
        js(f"window.scrollBy(0, {per})")
        time.sleep(jitter(0.12, 0.30))

def think_pause():
    """每屏之间停顿；偶发长停顿模拟"在认真看某条"。"""
    if random.random() < P_LONG:
        time.sleep(jitter(*PAUSE_LONG))
    else:
        time.sleep(jitter(*PAUSE_SHORT))

# ── 主流程 ─────────────────────────────────────────────────

ensure_daemon()
start_dt = datetime.now()
url = attach_home()
# ★ 刷新点：X 网页版不自动推流，必须 reload 才拉得到新帖
refresh_feed()
print(f"✓ 已刷新 feed: {url}", flush=True)

out_dir = os.environ.get("XAI_OUT") or f"xai_data/{start_dt.strftime('%Y%m%d')}_scan"
os.makedirs(out_dir, exist_ok=True)
max_rounds = int(os.environ.get("XAI_MAX_ROUNDS", "30"))

# ★ 去重点：全局 seen.json（跨 session 持久）+ 本目录 all_tweets.json（兜底）
all_path = os.path.join(out_dir, "all_tweets.json")
seen = load_seen()
all_tweets = []
if os.path.exists(all_path):
    try:
        all_tweets = json.load(open(all_path, encoding="utf-8"))
        seen |= {t.get("tid") for t in all_tweets if t.get("tid")}
    except Exception:
        all_tweets = []
print(f"✓ 已知推文 {len(seen)} 条（全局 seen.json）→ 本次只增量", flush=True)

session_new = 0      # 本次会话抓到的"新"推文数（喂给抓量上限）
stall = 0            # 连续"0 新增"轮数
overlap_run = 0      # 连续触边界轮数
reason = "max_rounds"

for rnd in range(max_rounds):
    batch = extract_batch()
    new = 0; old_on_page = 0; page_total = 0
    for t in batch:
        tid = t.get("tid")
        if not tid:
            continue
        page_total += 1
        if tid in seen:          # ← 去重就在这里：旧的一律跳过、不计入
            old_on_page += 1
            continue
        seen.add(tid)
        t["likes"]    = parse_eng(t.get("like"))
        t["reposts"]  = parse_eng(t.get("rt"))
        t["replies"]  = parse_eng(t.get("reply"))
        t["views"]    = parse_eng(t.get("view"))
        t["url"]      = f"https://x.com{t.get('href','')}" if t.get("href") else ""
        t["promoted"] = bool(t.get("promoted"))
        cls = classify(t.get("text", ""))
        t["ai"] = cls["is_ai"]; t["category"] = cls["primary"]
        t["categories"] = cls["categories"]; t["ai_terms"] = cls["terms"]
        t["scan_round"] = rnd
        all_tweets.append(t)
        new += 1; session_new += 1

    # ★ 旧内容标记：本页"已见过"的占比
    overlap_ratio = (old_on_page / page_total) if page_total else 0.0
    overlap_run = overlap_run + 1 if (page_total >= 4 and overlap_ratio >= OVERLAP_RATIO) else 0
    stall = stall + 1 if new == 0 else 0

    ai_so_far = sum(1 for t in all_tweets if t.get("ai"))
    tag = "🔁追上历史" if overlap_run else ("⏸无新增" if stall else "")
    print(f"round {rnd:02d}: 页面 {page_total} | 新 {new} | 旧 {old_on_page}"
          f"({overlap_ratio:.0%}) | 累计 {len(all_tweets)} | AI {ai_so_far} {tag}", flush=True)

    # ── 停止信号（优先级从高到低）──
    if overlap_run >= OVERLAP_STREAK:
        reason = "boundary_hit"; break      # ★ 刷到旧内容：本次到位
    if stall >= 6:
        reason = "stall"; break             # 连续多轮 0 新增
    if session_new >= MAX_SESSION_NEW:
        reason = "new_cap"; break           # 单次抓够量，主动收手（防封）
    if (datetime.now() - start_dt).total_seconds() >= MAX_SESSION_SECS:
        reason = "time_cap"; break          # 超时收手（防封 + 防 CDP 断连）

    human_scroll()
    think_pause()

# 落盘：每次都更新全局 seen + 本目录数据
save_seen(seen)
with open(all_path, "w", encoding="utf-8") as f:
    json.dump(all_tweets, f, ensure_ascii=False, indent=2)

ai_hits = [t for t in all_tweets if t.get("ai") and not t.get("promoted")]
ai_hits.sort(key=lambda t: ({"project":0,"trend":1,"opinion":2,"general":3}.get(t["category"],9),
                            -t.get("score",0)))
with open(os.path.join(out_dir, "ai_hits.json"), "w", encoding="utf-8") as f:
    json.dump(ai_hits, f, ensure_ascii=False, indent=2)

# ★ 会话日志（jsonl 追加）—— "这次有没有刷到旧东西"的标记就落在这里
end_dt = datetime.now()
session_ai_new = (sum(1 for t in all_tweets[-session_new:] if t.get("ai")) if session_new else 0)
append_log({
    "started_at": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    "ended_at":   end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    "duration_s": round((end_dt - start_dt).total_seconds(), 1),
    "rounds":     rnd + 1,
    "new_tweets": session_new,
    "ai_new":     session_ai_new,
    "total_seen": len(seen),
    "stopped_reason": reason,   # boundary_hit / stall / new_cap / time_cap / max_rounds
    "output_dir": out_dir,
})

# 摘要
from collections import Counter
cc = Counter(t["category"] for t in ai_hits)
REASON_ZH = {
    "boundary_hit": "🔁 刷到旧内容，已追上历史（本次到位）",
    "stall":        "⏸ 连续多轮无新增",
    "new_cap":      "📦 单次抓够量，主动收手",
    "time_cap":     "⏱ 到时收手",
    "max_rounds":   "🏁 跑满轮数",
}
print("\n" + "=" * 56)
print(f"扫描完成 → {out_dir}")
print(f"本次新增 {session_new} 条（AI {session_ai_new}）| 全局已知 {len(seen)} | 累计 AI {len(ai_hits)}")
print(f"停止原因：{REASON_ZH.get(reason, reason)}")
print("分类分布:", dict(cc) or "（无）")
if ai_hits:
    print("\nTop AI 命中（前 8）:")
    for t in ai_hits[:8]:
        txt = (t["text"] or "").replace("\n"," ")[:70]
        print(f"  [{t['category']}] @{t['handle']}: {txt}")
print("=" * 56)
