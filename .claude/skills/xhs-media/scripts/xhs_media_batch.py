#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书媒体批量下载编排器 — xhs-media skill

单 browser-harness 会话内：搜索页滚动加载 → 收集卡片(瀑布流排序) →
逐篇：关闭上一篇浮窗 → 点击验证 → 读 __INITIAL_STATE__ 取媒体 → 当篇立即下载(签名URL不过夜)。

用法（pipe 给 browser-harness）：
    XHS_KEYWORD="关键词" XHS_LIMIT=10 \\
    XHS_RUN_DIR="xhs_media_data/20260618_关键词" \\
    browser-harness < scripts/xhs_media_batch.py

依赖：
  - xhs_media_extract.extract_media / xhs_media_download.download_note_media （同目录 import）
  - 点击/验证/关闭 helper 逐字复制自 xhs-crawler/scripts/xhs_crawl.py（import xhs_crawl 会触发其
    module-level 爬取，且 harness exec 时 __name__!='__main__'，故复制而非 import。下方标有 SYNC 标记）。
"""

import os
import sys
import json
import time
import datetime

# ── path bootstrap：定位同目录的 extract / download 模块 ───────────────────
# piped 脚本由 harness exec(code, globals()) 执行，无 __file__；用 env + 已知绝对路径。
_SCRIPTS = None
for _c in (
    os.environ.get('XHS_MEDIA_SCRIPTS', ''),
    '/Users/sam/03-Code/01-GitHub/browser-harness/.claude/skills/xhs-media/scripts',
    os.path.expanduser('~/03-Code/01-GitHub/browser-harness/.claude/skills/xhs-media/scripts'),
):
    if _c and os.path.isfile(os.path.join(_c, 'xhs_media_extract.py')):
        _SCRIPTS = _c
        break
if _SCRIPTS and _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import xhs_media_extract as E
import xhs_media_download as D


def safe_filename(name, max_length=40):
    import re
    if not name:
        return "未命名"
    name = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return (name[:max_length]).strip('. ') or "未命名"


# ══ SYNC: 以下 helper 逐字复制自 xhs-crawler/scripts/xhs_crawl.py ══════════
# 改动须同步回 xhs_crawl.py。引用 js/cdp/ensure_daemon/ensure_real_tab 作为 harness
# 全局（piped 时存在于 exec globals）。

def safe_js(s):
    try:
        return js(s)  # noqa: F821
    except Exception:
        ensure_daemon(); ensure_real_tab(); time.sleep(1.0)  # noqa: F821
        try:
            return js(s)  # noqa: F821
        except Exception:
            return None

def safe_cdp(method, **kw):
    try:
        return cdp(method, **kw)  # noqa: F821
    except Exception:
        ensure_daemon(); ensure_real_tab(); time.sleep(1.0)  # noqa: F821
        try:
            return cdp(method, **kw)  # noqa: F821
        except Exception:
            return None

def jitter(lo, hi):
    import random
    return random.uniform(lo, hi)

BAD_ELEMENTS = ['发布', '下载APP', '登录', '注册']

def verify_click_target(cx, cy):
    """检查坐标处的元素，返回 info dict（ok/bad/isCard/...）"""
    info = safe_js(r'''
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
    """点击卡片，带验证。返回 (clicked, info)"""
    info = verify_click_target(cx, cy)
    if not info:
        return False, {"error": "verify_failed"}
    if info.get('bad'):
        print(f"  ⚠ 跳过: 坐标({cx},{cy}) → {info.get('badReason')} | {info.get('text','')}", flush=True)
        return False, info
    if not info.get('isCard'):
        print(f"  ⚠ 非卡片: ({cx},{cy}) → {info.get('tag','')} {info.get('cls','')} \"{info.get('text','')}\"", flush=True)
        chain = info.get('chain', [])
        if chain:
            print(f"    chain: {' → '.join(chain[:4])}", flush=True)
        return False, info
    safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy)
    time.sleep(jitter(0.3, 0.5))
    safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", clickCount=1)
    safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", clickCount=1)
    print(f"  ✓ 点击: ({cx},{cy}) → {info.get('tag','')} {info.get('cls','')} \"{info.get('text','')}\"", flush=True)
    return True, info

def wait_mask_gone(timeout=5):
    for _ in range(int(timeout / 0.3)):
        d = safe_js('return document.querySelector(".note-detail-mask") ? getComputedStyle(document.querySelector(".note-detail-mask")).display : "none";')
        if d == 'none':
            return True
        time.sleep(0.3)
    return False
# ══ END SYNC ═══════════════════════════════════════════════════════════════


# ── 卡片收集 + 瀑布流排序（JS 来自 xhs-crawler/references/waterfall-layout.md）──

COLLECT_JS = r'''
var items = [];
document.querySelectorAll('.note-item').forEach(function(item) {
    var a = item.querySelector('a[href*="/explore/"]');
    if (!a) return;
    var m = /\/explore\/([a-z0-9]+)/i.exec(a.href);
    if (!m) return;
    var rr = item.getBoundingClientRect();
    items.push({id: m[1], x: Math.round(rr.x), y: Math.round(rr.y),
                title: (item.querySelector('.title span') || item.querySelector('.title') || {}).textContent || ''});
});
items.sort(function(a, b) { return a.y === b.y ? a.x - b.x : a.y - b.y; });
var rows = [], currentRow = [], lastY = -999;
for (var i = 0; i < items.length; i++) {
    if (Math.abs(items[i].y - lastY) > 100 && currentRow.length > 0) {
        rows.push(currentRow); currentRow = [];
    }
    currentRow.push(items[i]); lastY = items[i].y;
}
if (currentRow.length > 0) rows.push(currentRow);
rows.forEach(function(row) { row.sort(function(a, b) { return a.x - b.x; }); });
var ordered = [];
for (var r = 0; r < rows.length; r++) for (var c = 0; c < rows[r].length; c++) ordered.push(rows[r][c]);
return ordered;
'''

def collect_cards():
    return safe_js(COLLECT_JS) or []


# ── 浮窗/卡片定位 ──────────────────────────────────────────────────────────

def wait_overlay_open(timeout=5):
    for _ in range(int(timeout / 0.3)):
        d = safe_js('var m=document.querySelector(".note-detail-mask");return m?getComputedStyle(m).display:"none";')
        if d and d != 'none':
            return True
        time.sleep(0.3)
    return False

def wait_note_in_state(note_id, timeout=6):
    """等 noteId 进入 __INITIAL_STATE__.noteDetailMap（SPA 异步注入）"""
    for _ in range(int(timeout / 0.3)):
        ok = safe_js(("var s=window.__INITIAL_STATE__,m=s&&s.note&&s.note.noteDetailMap;"
                      "return !!(m&&m[%r]&&m[%r].note);") % (note_id, note_id))
        if ok:
            return True
        time.sleep(0.3)
    return False

def get_card_rect(note_id):
    """取卡片中心坐标。若不在视口则 window.scrollTo 后重取（不用 scrollIntoView，避免坐标漂移）。"""
    return safe_js(r'''
var a = document.querySelector('a[href*="/explore/%s"]');
if (!a) return null;
var card = a;
for (var i = 0; i < 8; i++) {
    if (card.parentElement) card = card.parentElement;
    if (card.classList && card.classList.contains('note-item')) break;
}
if (!card.classList || !card.classList.contains('note-item')) return null;
var rr = card.getBoundingClientRect();
if (rr.y < 80 || rr.y + rr.height > window.innerHeight) {
    window.scrollTo(0, window.scrollY + rr.y - 150);
    rr = card.getBoundingClientRect();
}
return {x: Math.round(rr.x + rr.width/2), y: Math.round(rr.y + rr.height/2)};
''' % note_id)

def close_overlay():
    """点关闭按钮（hover+press+release），失败按 ESC；然后等 mask 消失"""
    xy = safe_js(r'''
var btn = document.querySelector('.close-circle') || document.querySelector('[class*="close"]');
if (!btn) return null;
var rr = btn.getBoundingClientRect();
if (rr.width <= 0 || rr.height <= 0) return null;
return {x: Math.round(rr.x + rr.width/2), y: Math.round(rr.y + rr.height/2)};
''')
    if xy:
        safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=xy['x'], y=xy['y'])
        time.sleep(0.3)
        safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=xy['x'], y=xy['y'], button="left", clickCount=1)
        safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=xy['x'], y=xy['y'], button="left", clickCount=1)
    else:
        safe_cdp("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        safe_cdp("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    wait_mask_gone()
    time.sleep(jitter(0.5, 1.0))


# ── 下载 worker（带视频 URL 重取兜底）──────────────────────────────────────
# worker 只做 requests I/O，不碰 js/cdp（浏览器循环独占）。视频笔记若 masterUrl/backupUrls
# 都没下到，用入队时快照的 cookies 调 fetch_via_http 重取**新鲜签名 URL** 再试。

def download_worker(task, session):
    media = task['media']
    dl = D.download_note_media(media, task['run_dir'], task['index'], session)
    if media.get('type') == 'video' and not dl.get('video_path'):
        note_id = media.get('noteId', '')
        if note_id:
            try:
                jar = E.build_jar(task.get('cookie_dicts'))
                fresh = E.fetch_via_http(note_id, media.get('xsecToken', ''), jar)
                if fresh and fresh.get('videoUrl'):
                    m2 = dict(media)
                    m2['videoUrl'] = fresh['videoUrl']
                    m2['videoBackups'] = fresh.get('videoBackups') or []
                    v = D.download_video(m2, dl['note_dir'], session)
                    if v:
                        dl['video_path'] = v
                        dl['downloaded_files'].append(os.path.basename(v))
                        info = dict(m2); info['downloaded_files'] = dl['downloaded_files']; info['is_video'] = True
                        with open(os.path.join(dl['note_dir'], '笔记信息.json'), 'w', encoding='utf-8') as f:
                            json.dump(info, f, ensure_ascii=False, indent=2)
                        print(f"  🔄 [{task['index']:03d}] 重取新鲜 URL 补下视频成功", flush=True)
            except Exception as e:
                print(f"  ⚠ [{task['index']:03d}] 重取兜底失败: {e}", flush=True)
    return (media, dl)


# ── 主循环 ──────────────────────────────────────────────────────────────────

def main():
    ensure_daemon(); ensure_real_tab()  # noqa: F821

    keyword = os.environ.get('XHS_KEYWORD', '')
    limit = int(os.environ.get('XHS_LIMIT', '10'))
    run_dir = os.environ.get('XHS_RUN_DIR') or (
        'xhs_media_data/' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + safe_filename(keyword)[:20])
    os.makedirs(run_dir, exist_ok=True)
    print(f"📁 输出目录: {run_dir}  目标: {limit} 篇  关键词: {keyword}", flush=True)

    # Step 1-2: 滚动加载 + 收集排序
    for _ in range(6):
        safe_js('window.scrollBy(0,1200); return 1;')
        time.sleep(0.8)
    cards = collect_cards()
    # 去重，多取一些以备跳过
    seen = set(); ordered = []
    for c in cards:
        if c['id'] in seen:
            continue
        seen.add(c['id']); ordered.append(c)
    print(f"📋 收集到 {len(ordered)} 张卡片", flush=True)

    if not ordered:
        print("✗ 未收集到卡片。确认已在搜索结果页。", flush=True)
        return

    # cookies 快照一次（会话内稳定；视频重取兜底用）。get_cookie_dicts 取原始 list，线程安全共享。
    try:
        cookie_dicts = E.get_cookie_dicts(cdp)  # noqa: F821
    except Exception:
        cookie_dicts = []

    n_workers = int(os.environ.get('XHS_WORKERS', '3'))
    pool = D.DownloadPool(download_worker, n_workers=n_workers)
    print(f"🧵 {n_workers} 个下载 worker 就绪", flush=True)

    first = True
    saved = 0
    for i, card in enumerate(ordered):
        if saved >= limit:
            break
        nid = card['id']
        # 每 5 篇重连，防 CDP 长会话掉线（xhs-crawler gotcha #18）
        if i and i % 5 == 0:
            ensure_daemon(); ensure_real_tab(); time.sleep(0.5)  # noqa: F821

        if not first:
            close_overlay()
        first = False

        rect = get_card_rect(nid)
        if not rect:
            print(f"  ✗ [{nid}] 找不到卡片坐标", flush=True)
            continue
        clicked, info = click_card_with_verify(rect['x'], rect['y'])
        if not clicked:
            continue
        if not wait_overlay_open():
            print(f"  ✗ [{nid}] 浮窗未打开", flush=True)
            continue
        wait_note_in_state(nid)

        # 媒体优先：浮窗一开就读 __INITIAL_STATE__（masterUrl 签名 URL）
        media, source = E.extract_media(nid, js, cdp)  # noqa: F821
        if not media or not media.get('ok'):
            print(f"  ✗ [{nid}] 提取失败: {media.get('reason') if media else 'None'}", flush=True)
            continue
        media['source'] = source
        media['card_title'] = card.get('title', '')

        saved += 1
        idx = saved
        # ① 磁盘检查点：立即写 JSON（进程崩可用 xhs_media_download.py 续传）
        with open(os.path.join(run_dir, f'{nid}.json'), 'w', encoding='utf-8') as f:
            json.dump(media, f, ensure_ascii=False, indent=2)
        # ② 入队异步下载（非阻塞，浏览器循环继续下一篇，不等下载）
        pool.put({'media': media, 'run_dir': run_dir, 'index': idx, 'cookie_dicts': cookie_dicts})
        print(f"  ⏭️  [{idx:03d}] 入队下载 (pending={pool.pending})", flush=True)

        time.sleep(jitter(3, 8))

    # 等队列排空（worker 完成顺序不定，join 内部按 index 排序）
    if pool.pending:
        print(f"\n⏳ 等待 {pool.pending} 个下载任务完成…", flush=True)
    results = pool.join()

    # 汇总 Excel
    if results:
        out = os.path.join(run_dir, 'xhs_media_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.xlsx')
        D.build_excel(results, out, run_dir)
        videos = sum(1 for _, d in results if d.get('video_path'))
        print(f"\n✅ 提取 {saved}/{limit} 篇，下载完成 {len(results)} 篇 (视频 {videos}, 图文 {len(results)-videos}) → {out}", flush=True)
    else:
        print("\n✗ 未成功提取/下载任何笔记", flush=True)


# harness exec(code, globals()) 时 'ensure_daemon' 在 globals 里 → 跑 main；
# 被 import（测试/复用 download_worker）时不在 → 不跑。
if 'ensure_daemon' in globals():
    main()
