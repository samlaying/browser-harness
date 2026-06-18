#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书单篇笔记提取 — browser-harness (CDP)

用法（pipe 给 browser-harness）：
    browser-harness < scripts/xhs_crawl.py

环境变量：
    XHS_NOTE_ID    - 笔记 ID（8位hex）

前提：浏览器已在搜索页，且笔记浮窗已打开。
本脚本只做提取，不负责导航和点击。

输出：JSON 到 stdout
"""

import os, json, time, random

# ── 工具函数 ──────────────────────────────────────────────

def safe_js(s):
    try:
        return js(s)
    except Exception:
        ensure_daemon(); ensure_real_tab(); time.sleep(1.0)
        try:
            return js(s)
        except Exception:
            return None

def safe_cdp(method, **kw):
    try:
        return cdp(method, **kw)
    except Exception:
        ensure_daemon(); ensure_real_tab(); time.sleep(1.0)
        try:
            return cdp(method, **kw)
        except Exception:
            return None

def jitter(lo, hi):
    return random.uniform(lo, hi)

# ── 点击验证 ──────────────────────────────────────────────

# 这些元素不应该被点击
BAD_ELEMENTS = ['发布', '下载APP', '登录', '注册']

def verify_click_target(cx, cy):
    """检查坐标处的元素，返回 (ok, info)
    ok=True 表示可以点击，ok=False 表示应该跳过"""
    info = safe_js(r'''
var el = document.elementFromPoint(%d, %d);
if (!el) return {ok:false, reason:'no_element'};
var tag = el.tagName;
var cls = el.className || '';
var text = (el.textContent || '').substring(0, 50).trim();
// 向上找最近的有意义的祖先
var chain = [];
var p = el;
for (var i = 0; i < 6 && p; i++) {
    var c = p.className || '';
    var t = (p.textContent || '').substring(0, 30).trim();
    chain.push(p.tagName + (c ? '.' + c.split(' ')[0] : '') + (t ? ' "' + t.substring(0,20) + '"' : ''));
    p = p.parentElement;
}
// 检查是否是卡片
var isCard = false;
p = el;
for (var i = 0; i < 8 && p; i++) {
    if (p.classList && p.classList.contains('note-item')) { isCard = true; break; }
    p = p.parentElement;
}
// 检查是否是坏元素
var bad = false;
var badReason = '';
var badList = %s;
for (var i = 0; i < badList.length; i++) {
    if (text.indexOf(badList[i]) >= 0) { bad = true; badReason = badList[i]; break; }
    if (cls.indexOf('channel') >= 0 && text.indexOf('发布') >= 0) { bad = true; badReason = 'channel-发布'; break; }
}
return {ok: !bad && isCard, bad: bad, badReason: badReason, isCard: isCard, tag: tag, cls: cls.substring(0,80), text: text.substring(0,40), chain: chain};
''' % (cx, cy, json.dumps(BAD_ELEMENTS)))
    return info

def click_card_with_verify(cx, cy):
    """点击卡片，带验证。返回 (clicked, element_info)"""
    info = verify_click_target(cx, cy)
    if not info:
        return False, {"error": "verify_failed"}

    if info.get('bad'):
        print(f"  ⚠ 跳过: 坐标({cx},{cy}) → {info.get('badReason')} | {info.get('text','')}", flush=True)
        return False, info

    if not info.get('isCard'):
        print(f"  ⚠ 非卡片: ({cx},{cy}) → {info.get('tag','')} {info.get('cls','')} \"{info.get('text','')}\"", flush=True)
        # 打印 chain 方便调试
        chain = info.get('chain', [])
        if chain:
            print(f"    chain: {' → '.join(chain[:4])}", flush=True)
        return False, info

    # 验证通过，执行点击
    safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy)
    time.sleep(jitter(0.3, 0.5))
    safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", clickCount=1)
    safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", clickCount=1)

    print(f"  ✓ 点击: ({cx},{cy}) → {info.get('tag','')} {info.get('cls','')} \"{info.get('text','')}\"", flush=True)
    return True, info

def wait_mask_gone(timeout=5):
    """关闭浮窗后轮询验证 mask 消失"""
    for _ in range(int(timeout / 0.3)):
        d = safe_js('return document.querySelector(".note-detail-mask") ? getComputedStyle(document.querySelector(".note-detail-mask")).display : "none";')
        if d == 'none':
            return True
        time.sleep(0.3)
    return False

# ── 速度控制 ──────────────────────────────────────────────

def delay_after_open():
    return jitter(2, 4)

def delay_scroll():
    return jitter(1, 2)

def delay_expand():
    return jitter(1.5, 3)

# ── 主流程 ────────────────────────────────────────────────

ensure_daemon()
ensure_real_tab()

# 一趟提取：元信息 + 帖子图片
meta = safe_js(r'''
var title = (document.querySelector("#detail-title")||{}).textContent || document.title || "";
var descEl = document.querySelector("#detail-desc,.desc");
var desc = descEl ? (descEl.innerText||"").replace(/\\s+/g," ").trim() : "";
var bar = document.querySelector('.engage-bar, [class*="engage"]');
var barText = bar ? bar.innerText.replace(/\\s+/g,' ').trim() : "";
var hasVideo = !!document.querySelector('video');
// 帖子图片（按 active 顺序）
var slides = document.querySelectorAll('.swiper-slide');
var noteImgs = []; var seen = {};
slides.forEach(function(s) {
    var img = s.querySelector('img');
    if (!img) return; var src = img.src || '';
    if (!src || seen[src]) return; seen[src] = true;
    noteImgs.push(src);
});
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

# 滚动加载评论
last = 0; stall = 0
for rnd in range(60):
    safe_js('var s=document.querySelector(".note-scroller");if(s){s.scrollTop=s.scrollHeight;}return 1;')
    time.sleep(delay_scroll())
    c = safe_js('return document.querySelectorAll(".comment-item").length;') or 0
    if c == last: stall += 1
    else: stall = 0; last = c
    if stall >= 5: break

# 展开引擎（.show-more + .expand-btn）
for i in range(80):
    btn = safe_js(r'''
var best = null, bestY = Infinity;
var all1 = document.querySelectorAll('.show-more');
for (var i = 0; i < all1.length; i++) {
    var el = all1[i]; var t = el.textContent.trim();
    if (!/展开/.test(t) && !/查看/.test(t)) continue;
    el.scrollIntoView({block:"center"});
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (r.y < bestY) { bestY = r.y; best = {t:t, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}; }
}
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
    if not btn: break
    # 展开按钮也需要 hover
    safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=btn['x'], y=btn['y'])
    time.sleep(jitter(0.3, 0.5))
    safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=btn['x'], y=btn['y'], button="left", clickCount=1)
    safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=btn['x'], y=btn['y'], button="left", clickCount=1)
    time.sleep(delay_expand())

total = safe_js('return document.querySelectorAll(".comment-item").length;') or 0

# 提取评论（含问一问）
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

# 构建线程关系
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

# 输出
result = {
    'meta': meta,
    'comments': data,
    'total_comments': total,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
