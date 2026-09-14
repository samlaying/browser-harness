#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书批量爬虫 — browser-harness (CDP) 自包含编排脚本

管道用法（harness 自动注入 js/cdp/ensure_daemon 等 globals）：
    XHS_KEYWORD="咖啡" XHS_TARGET=20 browser-harness < scripts/xhs_batch.py

环境变量：
    XHS_KEYWORD    搜索词（必填）
    XHS_TARGET     目标篇数（默认 20）
    XHS_OUTDIR     输出目录（默认 xhs_data/{date}_{keyword}）
    XHS_MAX_RETRY  单篇重试次数（默认 2）

健壮性：断点续爬(state.json) + 增量落盘 + 单篇重试 + 每5篇健康检查。

设计约束：本脚本经 harness `exec(code, globals())` 执行，js/cdp 在同一 globals。
故：① 不能跨文件 import 需要 js/cdp 的逻辑；② 入口由 'js' in dir() 守卫，
   这样 pytest 可直接 import 纯函数做单测而不触发 run_batch。

纯函数（无 js/cdp 依赖，可单测）：encode_keyword / waterfall_sort / compute_threads
                            / load_state / save_state / default_state / seed_done_from_disk
"""

import os, sys, json, time, random, glob, datetime
import urllib.parse


# ── 纯函数（无 js/cdp 依赖，可单测） ─────────────────────

def encode_keyword(kw):
    """URL 编码搜索词。"""
    return urllib.parse.quote(kw, safe='')


def waterfall_sort(items):
    """items: [{id, x, y}]。按瀑布流阅读顺序排序：y 差 <100 视为同排，
    排内按 x 升序，逐排从左到右。返回 id 列表。算法见 references/waterfall-layout.md。"""
    if not items:
        return []
    ordered = sorted(items, key=lambda it: (it['y'], it['x']))
    rows, current, last_y = [], [], None
    for it in ordered:
        if current and last_y is not None and abs(it['y'] - last_y) > 100:
            rows.append(current)
            current = []
        current.append(it)
        last_y = it['y']
    if current:
        rows.append(current)
    for row in rows:
        row.sort(key=lambda it: it['x'])
    flat = []
    for row in rows:
        for it in row:
            flat.append(it['id'])
    return flat


def compute_threads(comments):
    """给评论列表打 thread_id / reply_to。
    1级(lvl==1)= 新线程；2级(lvl==2, 祖先含 reply-container)= 归属当前线程。
    reply_to = 向前找上一个不同昵称者（跨线程回溯，匹配既有行为）。返回新列表（不修改入参）。
    消除 xhs_crawl.py / xhs_export.py 里重复的逻辑。"""
    out = [dict(c) for c in comments]
    thread_id = 0
    current_thread = 0
    for c in out:
        if c.get('lvl') == 1:
            thread_id += 1
            current_thread = thread_id
            c['thread_id'] = thread_id
            c['reply_to'] = ''
        else:
            c['thread_id'] = current_thread
            c['reply_to'] = ''
    for i, c in enumerate(out):
        if c.get('lvl') == 2:
            for j in range(i - 1, -1, -1):
                if out[j].get('nick') != c.get('nick'):
                    c['reply_to'] = out[j].get('nick', '')
                    break
    return out


STATE_FILENAME = 'state.json'


def _state_path(outdir):
    return os.path.join(outdir, STATE_FILENAME)


def default_state(keyword, target):
    return {'keyword': keyword, 'target': target, 'done': [], 'failed': [], 'order': []}


def load_state(outdir):
    p = _state_path(outdir)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_state(outdir, state):
    os.makedirs(outdir, exist_ok=True)
    with open(_state_path(outdir), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def seed_done_from_disk(outdir):
    """扫描 outdir 下 {id}.json（排除 state.json 与非 hex id），返回已完成 id 集合。
    接受 8 位（旧）或 24 位（新）hex id，长度 >=8 即可。
    启动时与 state.done 取并集 → 即便进程在'存 JSON 后写 state 前'崩了，重跑也不重爬。"""
    done = set()
    if not os.path.isdir(outdir):
        return done
    hexset = set('0123456789abcdefABCDEF')
    for fp in glob.glob(os.path.join(outdir, '*.json')):
        name = os.path.basename(fp)
        if name == STATE_FILENAME:
            continue
        stem = os.path.splitext(name)[0]
        if len(stem) >= 8 and all(ch in hexset for ch in stem):
            done.add(stem)
    return done


# ── DOM 工具函数（harness 内运行，引用 js/cdp 全局） ──────

BAD_ELEMENTS = ['发布', '下载APP', '登录', '注册', '创作']

# scroll_to_card 在卡片被虚拟滚动移除时，用它记录的绝对文档位置重渲染。
CARD_Y_MAP = {}            # note_id → 收集时的绝对文档 y（viewport y + 当时 scrollY）


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


def delay_after_open():
    return jitter(2, 4)


def delay_scroll():
    return jitter(1, 2)


def delay_expand():
    return jitter(1.5, 3)


def verify_click_target(cx, cy):
    """elementFromPoint 验证坐标处元素。ok=True 可点；isCard=是否 .note-item 后代；
    bad=坏元素。见 gotcha #17。"""
    return safe_js(r'''
var el = document.elementFromPoint(%d, %d);
if (!el) return {ok:false, reason:'no_element'};
var tag = el.tagName;
var cls = el.className || '';
var text = (el.textContent || '').substring(0, 50).trim();
var chain = [];
var p = el;
for (var i = 0; i < 6 && p; i++) {
    var c = p.className || '';
    var t = (p.textContent || '').substring(0, 30).trim();
    chain.push(p.tagName + (c ? '.' + c.split(' ')[0] : '') + (t ? ' "' + t.substring(0,20) + '"' : ''));
    p = p.parentElement;
}
var isCard = false;
p = el;
for (var i = 0; i < 8 && p; i++) {
    if (p.classList && p.classList.contains('note-item')) { isCard = true; break; }
    p = p.parentElement;
}
var bad = false, badReason = '';
var badList = %s;
for (var i = 0; i < badList.length; i++) {
    if (text.indexOf(badList[i]) >= 0) { bad = true; badReason = badList[i]; break; }
    if (cls.indexOf('channel') >= 0 && text.indexOf('发布') >= 0) { bad = true; badReason = 'channel-发布'; break; }
}
return {ok: !bad && isCard, bad: bad, badReason: badReason, isCard: isCard, tag: tag, cls: cls.substring(0,80), text: text.substring(0,40), chain: chain};
''' % (cx, cy, json.dumps(BAD_ELEMENTS)))


def click_card_with_verify(cx, cy):
    """验证 + hover + 点击。返回 (clicked, info)。见 gotcha #3/#17。"""
    info = verify_click_target(cx, cy)
    if not info:
        return False, {"error": "verify_failed"}
    if info.get('bad'):
        print("  ⚠ 跳过: 坐标(%d,%d) → %s | %s" % (cx, cy, info.get('badReason'), info.get('text', '')), flush=True)
        return False, info
    if not info.get('isCard'):
        print("  ⚠ 非卡片: (%d,%d) → %s %s \"%s\"" % (cx, cy, info.get('tag', ''), info.get('cls', ''), info.get('text', '')), flush=True)
        chain = info.get('chain', [])
        if chain:
            print("    chain: " + ' → '.join(chain[:4]), flush=True)
        return False, info
    safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy)
    time.sleep(jitter(0.3, 0.5))
    safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", clickCount=1)
    safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", clickCount=1)
    print("  ✓ 点击: (%d,%d) → %s %s \"%s\"" % (cx, cy, info.get('tag', ''), info.get('cls', ''), info.get('text', '')), flush=True)
    return True, info


def wait_mask_gone(timeout=5):
    """关闭浮窗后轮询 mask 消失。见 gotcha #11。"""
    for _ in range(int(timeout / 0.3)):
        d = safe_js('return document.querySelector(".note-detail-mask") ? getComputedStyle(document.querySelector(".note-detail-mask")).display : "none";')
        if d == 'none':
            return True
        time.sleep(0.3)
    return False


def collect_cards():
    """收集搜索页 .note-item 卡片 → [{id, x, y}]（中心坐标）。去重，仅 .note-item 内。
    见 gotcha #12（搜索页元素误判）。"""
    raw = safe_js(r'''
var out = [];
document.querySelectorAll('.note-item').forEach(function(item) {
    var a = item.querySelector('a[href*="/explore/"]');
    if (!a) return;
    var m = /\/explore\/([a-z0-9]+)/i.exec(a.href);
    if (!m) return;
    var rr = item.getBoundingClientRect();
    if (rr.width <= 0 || rr.height <= 0) return;
    out.push({id: m[1], x: Math.round(rr.x + rr.width/2), y: Math.round(rr.y + rr.height/2)});
});
return out;
''') or []
    seen = set(); uniq = []
    for c in raw:
        if c['id'] in seen:
            continue
        seen.add(c['id']); uniq.append(c)
    return uniq


def on_search_page():
    """当前活动页是否仍是搜索页。浮窗打开时 URL 不变（仍在 /search_result）；
    若某卡片点击触发了整页跳转，URL 会变为 /explore/{id} → 返回 False = 已漂移。"""
    p = safe_js('return location.pathname;')
    return bool(p) and '/search_result' in p


def reanchor_search(url):
    """导航漂移恢复：new_tab 重开一个全新搜索页并重建 CARD_Y_MAP。

    根因：偶尔某张卡片的点击会让整个标签页跳转到 /explore/{id} 详情页（而非弹浮窗）。
    一旦离开搜索页，document.querySelectorAll('.note-item') 返回空 → 后续所有卡片
    都判 card_not_found，白白跑完整张重试表（gotcha：导航漂移）。

    恢复：重开全新搜索标签页。新页面会正常渲染卡片（这正是「不能在原 tab 重新导航」
    的 gotcha #16 的破解点——重新导航不渲染，但全新 new_tab 会渲染）。然后重新收集
    所有已渲染卡片的位置写回 CARD_Y_MAP，使 scroll_to_card 能在新鲜页面上恢复虚拟滚动。
    order 不变（同一搜索词结果一致）；旧详情页 tab 留在后台不碍事。"""
    new_tab(url)
    wait_for_load()
    for _ in range(40):
        if safe_js('return document.querySelectorAll(".note-item").length;'):
            break
        time.sleep(0.5)
    global CARD_Y_MAP
    CARD_Y_MAP = {}
    safe_js('window.scrollTo(0,0);')
    # 逐屏向下收集，刷新所有已渲染卡片的位置（绝对文档 y = viewport y + scrollY）
    for _ in range(8):
        sy = safe_js('return window.scrollY;') or 0
        for c in collect_cards():
            CARD_Y_MAP[c['id']] = c['y'] + sy
        safe_js('window.scrollBy(0, 1000);')
        time.sleep(0.8)
    sy = safe_js('return window.scrollY;') or 0
    for c in collect_cards():
        CARD_Y_MAP[c['id']] = c['y'] + sy
    safe_js('window.scrollTo(0,0);')


def scroll_to_card(note_id):
    """把指定卡片滚入视口中心，使 getBoundingClientRect / elementFromPoint 有效。
    若卡片不在 DOM（虚拟滚动），先滚动到收集时的近似文档位置触发渲染，再找一次。"""
    # 先尝试直接找
    found = safe_js(r'''
var a = document.querySelector('a[href*="/explore/%s"]');
if (!a) return false;
var card = a;
for (var i = 0; i < 8 && card; i++) {
    if (card.classList && card.classList.contains('note-item')) break;
    card = card.parentElement;
}
if (!card) return false;
var vpH = window.innerHeight || document.documentElement.clientHeight;
var top = card.getBoundingClientRect().top + window.scrollY - vpH / 2;
window.scrollTo(0, Math.max(0, top));
return true;
''' % note_id)
    if found:
        return
    # 卡片不在 DOM → 滚动到收集时的绝对文档位置触发虚拟滚动重渲染
    est_doc_y = CARD_Y_MAP.get(note_id)     # 已是绝对文档 y（见 run_batch 的 _merge_batch）
    if est_doc_y is not None:
        safe_js('window.scrollTo(0, Math.max(0, %d));' % int(est_doc_y - 600))
        time.sleep(1.0)
        # 再试一次
        safe_js(r'''
var a = document.querySelector('a[href*="/explore/%s"]');
if (!a) return false;
var card = a;
for (var i = 0; i < 8 && card; i++) {
    if (card.classList && card.classList.contains('note-item')) break;
    card = card.parentElement;
}
if (!card) return false;
var vpH = window.innerHeight || document.documentElement.clientHeight;
var top = card.getBoundingClientRect().top + window.scrollY - vpH / 2;
window.scrollTo(0, Math.max(0, top));
return true;
''' % note_id)


def get_card_rect(note_id):
    """按 id 找卡片中心坐标。返回 {x,y} 或 None。调用前须先 scroll_to_card。"""
    return safe_js(r'''
var a = document.querySelector('a[href*="/explore/%s"]');
if (!a) return null;
var card = a;
for (var i = 0; i < 8 && card; i++) {
    if (card.classList && card.classList.contains('note-item')) break;
    card = card.parentElement;
}
if (!card || !card.classList || !card.classList.contains('note-item')) return null;
var rr = card.getBoundingClientRect();
if (rr.width <= 0 || rr.height <= 0) return null;
return {x: Math.round(rr.x + rr.width/2), y: Math.round(rr.y + rr.height/2)};
''' % note_id)


def close_overlay():
    """关浮窗：Escape 关闭 preview-modal + note-detail-mask。
    见 gotcha #11。仅在浮窗确实存在时才操作，避免误点页面上的其他链接。"""
    for _ in range(5):
        has_preview = safe_js('return !!document.querySelector(".preview-modal");')
        has_mask = safe_js('var m=document.querySelector(".note-detail-mask"); return m && getComputedStyle(m).display !== "none";')
        if not has_preview and not has_mask:
            break
        safe_cdp("Input.dispatchKeyEvent", type="rawKeyDown", windowsVirtualKeyCode=27, key="Escape")
        safe_cdp("Input.dispatchKeyEvent", type="keyUp", windowsVirtualKeyCode=27, key="Escape")
        time.sleep(jitter(0.5, 0.8))
    time.sleep(jitter(0.3, 0.5))


def wait_for_comments():
    """滚动加载评论（stall≥5 判底）+ 展开 .show-more/.expand-btn（hover-gated）。见 gotcha #3/#10。"""
    # 硬超时预算：评论/展开两段循环共用。导航漂移到 /explore 详情页时，.show-more 点击会
    # 持续触发评论懒加载 → 评论数一直涨 → stall 与 no_progress 都无法累积判停，循环跑满
    # 上限（60+80 次）单篇卡 5~7min（2026-08-02 命中）。75s 对正常笔记足够（120 评论约 30~60s）。
    deadline = time.time() + 75
    last = 0; stall = 0
    for _ in range(60):
        if time.time() > deadline:
            break
        safe_js('var s=document.querySelector(".note-scroller");if(s){s.scrollTop=s.scrollHeight;}return 1;')
        time.sleep(delay_scroll())
        c = safe_js('return document.querySelectorAll(".comment-item").length;') or 0
        if c == last:
            stall += 1
        else:
            stall = 0; last = c
        if stall >= 5:
            break
    last_comments = 0
    no_progress = 0
    for _ in range(80):
        if time.time() > deadline:
            break
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
        if not btn:
            break
        safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=btn['x'], y=btn['y'])
        time.sleep(jitter(0.3, 0.5))
        safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=btn['x'], y=btn['y'], button="left", clickCount=1)
        safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=btn['x'], y=btn['y'], button="left", clickCount=1)
        time.sleep(delay_expand())
        # 无进展保护：连续点击后评论数不增长即退出。导航漂移到 /explore 详情页时
        # .show-more 点击无效却始终存在，会空转到 80 次上限 → 单篇卡数分钟（2026-08-02
        # 「后脑勺脂溢性皮炎」第5篇命中，COMMENTS 稳定 20、SHOW_MORE 稳定 10 空转 9min）。
        _now_c = safe_js('return document.querySelectorAll(".comment-item").length;') or 0
        no_progress = 0 if _now_c > last_comments else no_progress + 1
        last_comments = _now_c
        if no_progress >= 4:
            break


def extract_note(note_id):
    """提取当前已打开浮窗的笔记。返回 (ok, data)。
    失败判定 = meta 为空（无标题），见 spec。返回 data 含 note_id/meta/comments/total_comments。"""
    meta = safe_js(r'''
var title = (document.querySelector("#detail-title")||{}).textContent || document.title || "";
var descEl = document.querySelector("#detail-desc,.desc");
var desc = descEl ? (descEl.innerText||"").replace(/\s+/g," ").trim() : "";
var bar = document.querySelector('.engage-bar, [class*="engage"]');
var barText = bar ? bar.innerText.replace(/\s+/g,' ').trim() : "";
var hasVideo = !!document.querySelector('video');
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
    if not meta or not meta.get('title'):
        return False, {'note_id': note_id, 'reason': 'empty_meta'}

    wait_for_comments()
    total = safe_js('return document.querySelectorAll(".comment-item").length;') or 0
    comments = safe_js(r'''
var out = [];
document.querySelectorAll(".comment-item").forEach(function(it) {
    try {
        var p = it.parentElement, lvl = 1;
        while (p) { if (p.classList && p.classList.contains("reply-container")) { lvl=2; break; } p=p.parentElement; }
        var nick = (it.querySelector(".name")||{}).textContent||"";
        nick = nick.replace(/\s+/g," ").trim();
        var contentEl = it.querySelector(".note-text")
            || it.querySelector(".ai-comment-text-container")
            || it.querySelector(".text-content")
            || it.querySelector(".desc");
        var content = contentEl ? (contentEl.innerText||"").replace(/\s+/g," ").trim() : "";
        var locEl = it.querySelector(".location");
        var ip = locEl ? (locEl.textContent||"").replace(/\s+/g," ").trim() : "";
        var dateEl = it.querySelector(".date");
        var dateText = "";
        if (dateEl) { var d=(dateEl.textContent||"").replace(/\s+/g," ").trim(); dateText=ip?d.replace(ip,"").trim():d; }
        function cnt(s){var e=it.querySelector(s);if(!e)return"0";var t=(e.textContent||"").replace(/\s+/g,"").trim();return /^\d+$/.test(t)?t:"0";}
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
    comments = compute_threads(comments)
    return True, {'note_id': note_id, 'meta': meta, 'comments': comments, 'total_comments': total}


def health_check(note_count):
    """每 N 篇心跳：document.title 异常则重连。真正的单调用恢复由 safe_js 兜底。"""
    title = safe_js('return document.title;')
    if title is None:
        print("  [health] #%d 连接异常，重连..." % note_count, flush=True)
        try:
            ensure_daemon(); ensure_real_tab()
        except Exception as e:
            print("  [health] 重连失败: %s" % e, flush=True)


def run_batch():
    keyword = os.environ.get('XHS_KEYWORD', '').strip()
    if not keyword:
        print("ERROR: 必须设置 XHS_KEYWORD"); return
    target = int(os.environ.get('XHS_TARGET', '20'))
    max_retry = int(os.environ.get('XHS_MAX_RETRY', '2'))
    outdir = os.environ.get('XHS_OUTDIR') or os.path.join(
        'xhs_data', datetime.datetime.now().strftime('%Y%m%d') + '_' + keyword[:10])
    total_attempts = max_retry + 1

    ensure_daemon(); ensure_real_tab()

    # 1) 会话首次进入搜索页：开全新 tab（new_tab），不在原标签 goto_url。
    #    小红书搜索页现在默认进 AI 搜索视图（URL 被 &type=51 重写、<html> 加 ai-layout-active），
    #    此视图下原标签 goto_url（SPA 内部导航）不触发卡片瀑布流布局——容器 .feeds-container
    #    塌缩成 h:0，22 张卡片 position:absolute 全堆叠在 (24,144)，elementFromPoint 穿透命中
    #    <html> → 点击验证全失败（gotcha #19，2026-07-28「2周年礼物」命中）。
    #    new_tab 全新页加载即使 class 仍显 ai-layout-active，卡片也会正常瀑布流布局
    #    （实测 .feeds-container h:3204、3 列分散、elementFromPoint 命中 A.cover→.note-item）。
    #    这是 gotcha #16（SPA 重新导航不渲染卡片）的变体：解法同样是开全新 tab。
    #    关键词用原始中文：new_tab 对预编码 URL 会把 '%' 再编码成 %25 → 双重乱码；
    #    传原始中文由浏览器单次编码（已验证）。reanchor_search 复用同一 url。
    url = ('https://www.xiaohongshu.com/search_result?keyword='
           + keyword + '&source=web_explore_feed')
    new_tab(url)                                # 全新 tab 保证卡片瀑布流正常布局
    wait_for_load()
    # 2) 收集卡片：先在 scrollY=0 收（拿真正的顶部），不足目标再向下增量加载。
    #    小红书是虚拟滚动——往下滚会把顶部卡片从 DOM 移除，故不能「先滚再收」（会漏掉顶部）。
    for _ in range(40):                      # SPA 冷启动慢，轮询等顶部卡片渲染
        if safe_js('return document.querySelectorAll(".note-item").length;'):
            break
        time.sleep(0.5)
    # 等瀑布流布局落地：卡片 position:absolute 出现在 DOM 早于容器撑高——此刻 collect 拿到的
    # 中心坐标全相同（堆叠在左上角），elementFromPoint 穿透未布局卡片、点击验证全失败（gotcha #19）。
    # 实测「B端产品经理面试题」首张卡片出现瞬间 feeds-container h:0，约 2~3s 后才撑到 h:3711、
    # 坐标分散为 5 列。用容器高度 >0 作为「布局已落地」信号，最多再等 15s。
    for _ in range(30):
        fh = safe_js('var fc=document.querySelector(".feeds-container"); return fc?fc.getBoundingClientRect().height:0;') or 0
        if fh > 0:
            break
        time.sleep(0.5)
    global CARD_Y_MAP
    CARD_Y_MAP = {}                          # id → 收集时的绝对文档 y（供 scroll_to_card 重渲染）
    order = []                               # 去重保序；顶部批先入列 → 真正的顶部在前
    seen = set()

    def _merge_batch():
        sy = safe_js('return window.scrollY;') or 0
        batch = collect_cards()              # viewport-relative {id,x,y}
        for c in batch:
            CARD_Y_MAP[c['id']] = c['y'] + sy   # viewport y + 当前 scrollY = 绝对文档 y
        for cid in waterfall_sort(batch):       # 本批内按瀑布流（行→列）排序
            if cid not in seen:
                seen.add(cid); order.append(cid)

    safe_js('window.scrollTo(0,0);')
    _merge_batch()                           # 真正的顶部一批
    for _ in range(8):                       # 不足目标再向下增量加载；已收集的顶部被虚拟化移除也无妨，order 已记
        if len(order) >= target:
            break
        safe_js('window.scrollBy(0, 1000);')
        time.sleep(0.8)
        _merge_batch()

    if not order:
        state = load_state(outdir) or default_state(keyword, target)
        state['order'] = []
        save_state(outdir, state)
        print("ERROR: 未收集到任何卡片（可能未登录 / 被限流 / SPA 未渲染）。请检查浏览器与登录态后重试。", flush=True)
        return

    # 4) 状态：加载 + 双保险 seed（state.json 的 done ∪ 磁盘已存 JSON）
    state = load_state(outdir) or default_state(keyword, target)
    state['order'] = order
    done = set(state.get('done', [])) | seed_done_from_disk(outdir)
    state['done'] = sorted(done)
    save_state(outdir, state)

    pending = [i for i in order if i not in done]
    print("目标 %d 篇，实际收 %d 张卡片，已完成 %d，待爬 %d" % (
        target, len(order), len(done), len(pending)), flush=True)

    idx = 0
    for note_id in order:
        if note_id in done:
            continue
        if len(done) >= target:
            break
        idx += 1
        print("\n[%d/%d] %s" % (len(done) + 1, target, note_id), flush=True)

        success = False
        last_reason = 'unknown'
        reanchored = False
        for attempt in range(1, total_attempts + 1):
            if attempt > 1:
                close_overlay()
                time.sleep(jitter(0.5, 1.0))
            scroll_to_card(note_id)
            time.sleep(0.3)
            rect = get_card_rect(note_id)
            if not rect:
                # 漂移检测：上一篇点击若触发了整页跳转（非浮窗），此刻已不在搜索页 →
                # 重开搜索页续爬。每篇最多重锚一次（reanchored 标志），避免无限重锚。
                if not reanchored and not on_search_page():
                    print("  ⚠ 导航漂移（已离开搜索页），重新锚定搜索页续爬...", flush=True)
                    reanchor_search(url)
                    reanchored = True
                    time.sleep(1.0)
                    scroll_to_card(note_id)
                    time.sleep(0.3)
                    rect = get_card_rect(note_id)
                if not rect:
                    last_reason = 'card_not_found'
                    print("  ✗ 找不到卡片，重试 %d/%d" % (attempt, total_attempts), flush=True)
                    continue
            clicked, _ = click_card_with_verify(rect['x'], rect['y'])
            if not clicked:
                last_reason = 'click_verify_failed'
                print("  ✗ 点击未通过验证，重试 %d/%d" % (attempt, total_attempts), flush=True)
                time.sleep(jitter(0.5, 1.0))
                continue
            time.sleep(delay_after_open())
            ok, data = extract_note(note_id)
            if ok:
                # 增量落盘：先写笔记 JSON，再更新 state（崩溃安全）
                with open(os.path.join(outdir, note_id + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                done.add(note_id)
                state['done'] = sorted(done)
                save_state(outdir, state)
                print("  ✓ ok (%d 评论, %d 图)" % (
                    data['total_comments'], len(data['meta'].get('noteImgs', []))), flush=True)
                success = True
                break
            else:
                last_reason = data.get('reason', 'empty_meta')
                print("  ✗ 提取失败(%s)，重试 %d/%d" % (last_reason, attempt, total_attempts), flush=True)

        if not success:
            state['failed'] = [f for f in state['failed'] if f['id'] != note_id]
            state['failed'].append({'id': note_id, 'reason': last_reason, 'attempts': total_attempts})
            save_state(outdir, state)
            print("  ✗✗ 放弃 %s → failed(%s)" % (note_id, last_reason), flush=True)

        # 关闭当前笔记浮窗（成功/失败均关）。成功路径之前不关 → 下一篇首点落在残留遮罩上，
        # 白白浪费一次重试。close_overlay 仅在浮窗确实存在时才操作，无浮窗时安全空转。见 gotcha #11。
        close_overlay()

        # 每 5 篇健康检查
        if idx % 5 == 0:
            health_check(idx)

        # 笔记间限速 + 15% 长停顿（防封，见 SKILL.md 速度控制）
        time.sleep(jitter(3, 8))
        if random.random() < 0.15:
            time.sleep(jitter(5, 10))

    # 收尾
    state['done'] = sorted(done)
    save_state(outdir, state)
    failed = state.get('failed', [])
    print("\n==== 完成 ====", flush=True)
    print("已爬 %d 篇，失败 %d 篇 → %s" % (len(done), len(failed), outdir), flush=True)
    if failed:
        print("失败: " + ', '.join(f['id'] for f in failed), flush=True)


# ── 入口 ─────────────────────────────────────────────────
# harness exec 时 js/cdp 在 dir()；pytest import 时不在 → 不触发 run_batch。
if 'js' in dir() and 'cdp' in dir():
    run_batch()
