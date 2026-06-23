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
    reply_to = 向前找本线程内上一个不同昵称者。返回新列表（不修改入参）。
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

BAD_ELEMENTS = ['发布', '下载APP', '登录', '注册']


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


def get_card_rect(note_id):
    """按 id 找卡片中心坐标。不 scrollIntoView（gotcha #2）。返回 {x,y} 或 None。"""
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
    """关浮窗：mask 区点击 → 等 mask 消失；失败兜底 Escape。见 gotcha #11。
    (50,400) 是视口左上 mask 空白带（笔记浮窗居中、左侧为半透明遮罩）；
    分辨率/布局变更需重校，点击本身无 mask 命中验证，靠 wait_mask_gone 兜底。"""
    safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=50, y=400)
    time.sleep(jitter(0.2, 0.4))
    safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=50, y=400, button="left", clickCount=1)
    safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=50, y=400, button="left", clickCount=1)
    if not wait_mask_gone(timeout=3):
        safe_cdp("Input.dispatchKeyEvent", type="rawKeyDown", windowsVirtualKeyCode=27, key="Escape")
        safe_cdp("Input.dispatchKeyEvent", type="keyUp", windowsVirtualKeyCode=27, key="Escape")
        wait_mask_gone(timeout=2)
    time.sleep(jitter(0.5, 1.0))


def run_batch():
    """主编排：导航搜索页 → 收卡片排序 → 断点续爬 → 逐篇重试增量落盘 → 健康检查。
    见 Task 9。"""
    print("[xhs_batch] run_batch() 尚未实现（骨架）", flush=True)


# ── 入口 ─────────────────────────────────────────────────
# harness exec 时 js/cdp 在 dir()；pytest import 时不在 → 不触发 run_batch。
if 'js' in dir() and 'cdp' in dir():
    run_batch()
