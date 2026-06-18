#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书单篇笔记爬取脚本 — browser-harness (CDP) 版

用法（通过 browser-harness pipe 执行）：
    browser-harness < scripts/xhs_crawl.py

环境变量：
    XHS_NOTE_ID    - 笔记 ID（8位hex）
    XHS_SEARCH_URL - 搜索页 URL

输出：JSON 到 stdout，格式：
    { "meta": {...}, "comments": [...], "img_map": {...} }
"""

import os, sys, json, time, random

# ── 工具函数 ──────────────────────────────────────────────

def safe_js(s):
    try:
        return js(s)
    except Exception:
        ensure_daemon()
        ensure_real_tab()
        time.sleep(1.0)
        try:
            return js(s)
        except Exception:
            return None

def safe_cdp(method, **kw):
    try:
        return cdp(method, **kw)
    except Exception:
        ensure_daemon()
        ensure_real_tab()
        time.sleep(1.0)
        try:
            return cdp(method, **kw)
        except Exception:
            return None

def jitter(a, b):
    return random.uniform(a, b)

def hover_click(cx, cy):
    """完整 hover+click 序列（hover-gated 按钮必需）"""
    safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy)
    time.sleep(0.35)
    safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy,
             button="left", clickCount=1)
    safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy,
             button="left", clickCount=1)

def click_outside():
    """点击浮窗外部关闭笔记"""
    hover_click(50, 400)
    time.sleep(1.5)

# ── 主流程 ────────────────────────────────────────────────

ensure_daemon()
ensure_real_tab()

NOTE_ID = os.environ.get("XHS_NOTE_ID", "")
SEARCH_URL = os.environ.get("XHS_SEARCH_URL", "")

# 1) 回到搜索页
if SEARCH_URL:
    safe_js('window.location.href=%s;return 1;' % json.dumps(SEARCH_URL))
    for _ in range(20):
        try:
            wait_for_load()
        except Exception:
            pass
        c = safe_js('return document.querySelectorAll("a[href*=\\"/explore/\\"]").length;')
        if (c or 0) > 0:
            break
        time.sleep(0.6)
    time.sleep(1)

    # 关闭可能打开的浮窗
    mask = safe_js('return document.querySelector(".note-detail-mask") ? getComputedStyle(document.querySelector(".note-detail-mask")).display : "none";')
    if mask and mask != 'none':
        click_outside()

    # 点击目标笔记卡片（不 scrollIntoView！）
    rect = safe_js(r'''
var a = document.querySelector('a[href*="/explore/''' + NOTE_ID + r'''"]');
if (!a) return null;
var card = a;
for (var i = 0; i < 8; i++) {
    if (card.parentElement) card = card.parentElement;
    if (card.classList && card.classList.contains('note-item')) break;
}
var rr = card.getBoundingClientRect();
return {x: Math.round(rr.x + rr.width/2), y: Math.round(rr.y + rr.height/2)};
''')
    if rect:
        hover_click(rect['x'], rect['y'])
        time.sleep(3)

    # 等评论出现
    for _ in range(15):
        c = safe_js('return document.querySelectorAll(".comment-item").length;')
        if (c or 0) > 0:
            break
        time.sleep(0.7)

# 2) 获取帖子元信息
meta = safe_js(r'''
var title = (document.querySelector("#detail-title")||{}).textContent || document.title || "";
var descEl = document.querySelector("#detail-desc,.desc");
var desc = descEl ? (descEl.innerText||"").replace(/\\s+/g," ").trim() : "";
var bar = document.querySelector('.engage-bar, [class*="engage"]');
var barText = bar ? bar.innerText.replace(/\\s+/g,' ').trim() : "";
var hasVideo = !!document.querySelector('video');
var slides = document.querySelectorAll('.swiper-slide');
var noteImgs = []; var seen = {};
slides.forEach(function(s) {
    var img = s.querySelector('img');
    if (!img) return; var src = img.src || '';
    if (!src || seen[src]) return; seen[src] = true;
    noteImgs.push(src);
});
// 按 active slide 顺序重排
var active = document.querySelector('.swiper-slide-active img');
var activeSrc = active ? active.src : '';
var startIdx = noteImgs.indexOf(activeSrc);
if (startIdx > 0) {
    var ordered = [];
    for (var i = 0; i < noteImgs.length; i++) {
        ordered.push(noteImgs[(startIdx + i) % noteImgs.length]);
    }
    noteImgs = ordered;
}
return {title:title, desc:desc, barText:barText, hasVideo:hasVideo, noteImgs:noteImgs};
''') or {}

# 3) 滚动加载一级评论
last = 0; stall = 0
for rnd in range(60):
    safe_js('var s=document.querySelector(".note-scroller");if(s){s.scrollTop=s.scrollHeight;}return 1;')
    time.sleep(jitter(0.8, 1.2))
    c = safe_js('return document.querySelectorAll(".comment-item").length;') or 0
    if c == last:
        stall += 1
    else:
        stall = 0
        last = c
    if stall >= 5:
        break

# 4) 展开引擎：.show-more + .expand-btn
for i in range(80):
    btn = safe_js(r'''
var best = null, bestY = Infinity;
// 普通回复展开
var all1 = document.querySelectorAll('.show-more');
for (var i = 0; i < all1.length; i++) {
    var el = all1[i]; var t = el.textContent.trim();
    if (!/展开/.test(t) && !/查看/.test(t)) continue;
    el.scrollIntoView({block:"center"});
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (r.y < bestY) { bestY = r.y; best = {t:t, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}; }
}
// 问一问 AI 展开
var all2 = document.querySelectorAll('.expand-btn');
for (var i = 0; i < all2.length; i++) {
    var el = all2[i]; var t = el.textContent.trim();
    if (t.indexOf('展开') < 0) continue;
    el.scrollIntoView({block:"center"});
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (r.y < bestY) { bestY = r.y; best = {t:t, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}; }
}
return best;
''')
    if not btn:
        break
    hover_click(btn['x'], btn['y'])
    time.sleep(jitter(1.0, 1.5))

total = safe_js('return document.querySelectorAll(".comment-item").length;') or 0

# 5) 提取评论（含问一问）
data = safe_js(r'''
var out = [];
document.querySelectorAll(".comment-item").forEach(function(it) {
    try {
        var p = it.parentElement, lvl = 1;
        while (p) { if (p.classList && p.classList.contains("reply-container")) { lvl=2; break; } p=p.parentElement; }
        var nick = (it.querySelector(".name")||{}).textContent||"";
        nick = nick.replace(/\\s+/g," ").trim();
        var contentEl = it.querySelector(".note-text")
            || it.querySelector(".ai-comment-text-container")
            || it.querySelector(".text-content")
            || it.querySelector(".desc");
        var content = contentEl ? (contentEl.innerText||"").replace(/\\s+/g," ").trim() : "";
        var locEl = it.querySelector(".location");
        var ip = locEl ? (locEl.textContent||"").replace(/\\s+/g," ").trim() : "";
        var dateEl = it.querySelector(".date");
        var dateText = "";
        if (dateEl) { var d=(dateEl.textContent||"").replace(/\\s+/g," ").trim(); dateText=ip?d.replace(ip,"").trim():d; }
        function cnt(s){var e=it.querySelector(s);if(!e)return"0";var t=(e.textContent||"").replace(/\\s+/g,"").trim();return /^\\d+$/.test(t)?t:"0";}
        var likes=cnt(".interactions .like .count")||cnt(".like .count");
        var replies=cnt(".interactions .reply .count")||cnt(".reply .count");
        var imgs=[];
        it.querySelectorAll("img").forEach(function(img){
            var src=img.src||""; var cls=img.className||"";
            if(src&&src.indexOf("avatar")<0&&cls.indexOf("emoji")<0) imgs.push(src);
        });
        if(nick||content) out.push({lvl:lvl,nick:nick,content:content,date:dateText,ip:ip,likes:likes,replies:replies,imgs:imgs});
    } catch(e) {}
});
return out;
''') or []

# 6) 构建线程关系
thread_id = 0; current_thread = 0
for item in data:
    if item['lvl'] == 1:
        thread_id += 1; current_thread = thread_id
        item['thread_id'] = thread_id; item['reply_to'] = ''
    else:
        item['thread_id'] = current_thread; item['reply_to'] = ''
for i, item in enumerate(data):
    if item['lvl'] == 2:
        for j in range(i-1, -1, -1):
            if data[j]['nick'] != item['nick']:
                item['reply_to'] = data[j]['nick']
                break

# 7) 输出
result = {
    'meta': meta,
    'comments': data,
    'total_comments': total,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
