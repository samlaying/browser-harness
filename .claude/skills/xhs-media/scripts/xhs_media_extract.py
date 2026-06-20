#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书媒体字段提取 — xhs-media skill 核心

从已打开的笔记浮窗里提取原视频/原图/头像地址。两条路径：

  PRIMARY  : 直接读浏览器里的 window.__INITIAL_STATE__.note.noteDetailMap
             （点击卡片后 SPA 已注入完整数据，含签名 masterUrl）
  FALLBACK : 若 PRIMARY 拿不到（字段空/无该 noteId），用 note 的 xsec_token +
             浏览器 cookies 做服务端 GET，正则解析 __INITIAL_STATE__

既可被 xhs_media_batch.py import（函数显式接收 _js/_cdp，避免 free-variable NameError），
也可独立 pipe：
    XHS_NOTE_ID=<id> browser-harness < scripts/xhs_media_extract.py
（piped 脚本由 harness exec(code, globals()) 执行，__name__ 不是 '__main__'，
 故 standalone 用 'ensure_daemon' in globals() 守卫。）
"""

import os
import re
import json

import requests

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'

# ── PRIMARY: 读 __INITIAL_STATE__ 的 JS 模板 ──────────────────────────────
# %s 处填 json.dumps(note_id)（None 时取 noteDetailMap 里 lastUpdateTime 最新的一条）。
# 只 return 扁平小对象——__INITIAL_STATE__ 很大，整包 return 会爆 returnByValue "chain too long"。
# 字段路径已对照真实抓包 _raw_data.json 校验（视频笔记实测可下载 masterUrl）。
PRIMARY_JS = r'''
return (function(){
  var st = window.__INITIAL_STATE__;
  if (!st || !st.note || !st.note.noteDetailMap) return {ok:false, reason:'no_state'};
  var map = st.note.noteDetailMap;
  var ids = Object.keys(map);
  if (!ids.length) return {ok:false, reason:'empty_map'};

  var want = __NOTEID__;
  var entry = null;
  if (want && map[want] && map[want].note) {
    entry = map[want].note;
  } else {
    var best = null, bestT = -1;
    for (var i = 0; i < ids.length; i++) {
      var n = map[ids[i]].note;
      if (!n) continue;
      var t = n.lastUpdateTime || n.time || 0;
      if (typeof t === 'string') t = parseInt(t, 10) || 0;
      if (t >= bestT) { bestT = t; best = n; }
    }
    entry = best;
  }
  if (!entry) return {ok:false, reason:'no_entry'};

  // ---- 视频：video.media.stream.h264[0].masterUrl（签名URL，会过期）----
  // ⚠️ 不要用 video.consumer.originVideoKey —— 实测不存在。
  // backupUrls 在同一 stream 节点内（unsigned CDN，masterUrl 过期时顶上）。
  var videoUrl = '', videoBackups = [];
  if (entry.type === 'video' && entry.video) {
    var h264 = (((entry.video.media || {}).stream || {}).h264) || [];
    if (h264.length) {
      videoUrl = h264[0].masterUrl || '';
      var bu = h264[0].backupUrls || [];
      for (var b = 0; b < bu.length && b < 2; b++) if (bu[b]) videoBackups.push(bu[b]);
    }
  }

  // ---- 图片：每张取最大分辨率 ----
  var imageUrls = [];
  var imgs = entry.imageList || [];
  for (var k = 0; k < imgs.length; k++) {
    var im = imgs[k];
    var bestUrl = im.urlDefault || im.url || '';
    var info = im.infoList || [];
    var bestArea = -1;
    for (var j = 0; j < info.length; j++) {
      var it = info[j];
      var area = (it.width || 0) * (it.height || 0);
      if (it.url && area > bestArea) { bestArea = area; bestUrl = it.url; }
    }
    if (bestUrl) imageUrls.push(bestUrl);
  }

  // ---- 头像：user.avatar（真实字段），imageb/images 仅 fallback ----
  var u = entry.user || {};
  var avatar = u.avatar || u.imageb || u.images || '';
  var ii = entry.interactInfo || {};
  var noteId = entry.noteId || '';
  var xsec = entry.xsecToken || '';

  return {
    ok: true,
    type: entry.type || 'normal',
    noteId: noteId,
    title: (entry.title || '').slice(0, 120),
    desc: (entry.desc || '').slice(0, 1000),
    ipLocation: entry.ipLocation || '',
    tags: (entry.tagList || []).map(function (t) { return t.name || ''; }).slice(0, 30),
    videoUrl: videoUrl,
    videoBackups: videoBackups,
    imageUrls: imageUrls,
    avatar: avatar,
    nickname: u.nickname || '',
    userId: u.userId || '',
    likedCount: ii.likedCount || '',
    collectedCount: ii.collectedCount || '',
    commentCount: ii.commentCount || '',
    shareCount: ii.shareCount || '',
    xsecToken: xsec,
    note_url: noteId ? ('https://www.xiaohongshu.com/explore/' + noteId + (xsec ? ('?xsec_token=' + xsec + '&xsec_source=pc_search') : '')) : ''
  };
})();
'''


# ── 纯函数：raw note dict → 媒体字段（FALLBACK 与 PRIMARY 共用映射）─────────

def normalize_note(note):
    """把 __INITIAL_STATE__ 的原始 note 对象规范成媒体字段 dict。
    PRIMARY 的 JS 已在浏览器内做了等价映射；这里给 FALLBACK 用。两者须保持一致。"""
    if not note:
        return {'ok': False, 'reason': 'empty_note'}

    video_url, video_backups = '', []
    if note.get('type') == 'video' and note.get('video'):
        h264 = (((note['video'].get('media') or {}).get('stream') or {}).get('h264')) or []
        if h264:
            video_url = h264[0].get('masterUrl', '') or ''
            for b in (h264[0].get('backupUrls') or [])[:2]:
                if b:
                    video_backups.append(b)

    image_urls = []
    for im in (note.get('imageList') or []):
        best = im.get('urlDefault') or im.get('url') or ''
        best_area = -1
        for it in (im.get('infoList') or []):
            area = (it.get('width') or 0) * (it.get('height') or 0)
            if it.get('url') and area > best_area:
                best_area = area
                best = it['url']
        if best:
            image_urls.append(best)

    u = note.get('user') or {}
    ii = note.get('interactInfo') or {}
    note_id = note.get('noteId', '')
    xsec = note.get('xsecToken', '')
    return {
        'ok': True,
        'type': note.get('type') or 'normal',
        'noteId': note_id,
        'title': (note.get('title') or '')[:120],
        'desc': (note.get('desc') or '')[:1000],
        'ipLocation': note.get('ipLocation') or '',
        'tags': [t.get('name', '') for t in (note.get('tagList') or [])][:30],
        'videoUrl': video_url,
        'videoBackups': video_backups,
        'imageUrls': image_urls,
        'avatar': u.get('avatar') or u.get('imageb') or u.get('images') or '',
        'nickname': u.get('nickname') or '',
        'userId': u.get('userId') or '',
        'likedCount': ii.get('likedCount') or '',
        'collectedCount': ii.get('collectedCount') or '',
        'commentCount': ii.get('commentCount') or '',
        'shareCount': ii.get('shareCount') or '',
        'xsecToken': xsec,
        'note_url': ('https://www.xiaohongshu.com/explore/' + note_id +
                     ('?xsec_token=' + xsec + '&xsec_source=pc_search' if xsec else '')) if note_id else '',
    }


def _has_media(media):
    """判断 media 是否真有可下载内容（决定是否走 FALLBACK）"""
    if not media or not media.get('ok'):
        return False
    if media.get('type') == 'video' and not media.get('videoUrl'):
        return False
    if media.get('type') != 'video' and not media.get('imageUrls'):
        return False
    return True


# ── FALLBACK: 服务端 GET + 浏览器 cookies ─────────────────────────────────

def parse_initial_state_from_html(html):
    """从页面 HTML 正则抠 window.__INITIAL_STATE__，返回 noteDetailMap 的 note（第一条）。"""
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", html, re.DOTALL)
    if not m:
        return None, None
    state_str = m.group(1).replace("undefined", '""')
    try:
        state = json.loads(state_str)
    except json.JSONDecodeError:
        return None, None
    ndm = (state.get('note') or {}).get('noteDetailMap') or {}
    if not ndm:
        return None, state
    note = list(ndm.values())[0].get('note') or {}
    return note, state


def get_cookie_dicts(_cdp):
    """通过 CDP 取浏览器 cookies，返回原始 list（线程安全可跨 worker 共享）。"""
    res = _cdp("Network.getAllCookies") or {}
    return [c for c in res.get("cookies", []) if 'xiaohongshu' in c.get('domain', '')]


def build_jar(cookie_dicts):
    """把 cookie list 建成 requests CookieJar（每个 worker 各建一份，避免共享 jar 的线程问题）。"""
    jar = requests.cookies.RequestsCookieJar()
    for c in cookie_dicts or []:
        jar.set(c['name'], c['value'], domain=c.get('domain', ''), path=c.get('path', '/'))
    return jar


def cookies_from_cdp(_cdp):
    """便捷封装：CDP 取 cookies 并直接建 jar（单线程场景用）。"""
    return build_jar(get_cookie_dicts(_cdp))


def fetch_via_http(note_id, xsec_token, cookie_jar):
    """FALLBACK：带浏览器 cookies GET 笔记页，解析 __INITIAL_STATE__，返回 media 或 None。"""
    if not note_id:
        return None
    url = ('https://www.xiaohongshu.com/explore/' + note_id +
           ('?xsec_token=' + xsec_token + '&xsec_source=pc_search' if xsec_token else ''))
    s = requests.Session()
    s.headers.update({
        'User-Agent': UA,
        'Referer': 'https://www.xiaohongshu.com/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })
    s.cookies = cookie_jar
    try:
        resp = s.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠ FALLBACK HTTP 失败: {e}", flush=True)
        return None
    note, _state = parse_initial_state_from_html(resp.text)
    if not note:
        return None
    media = normalize_note(note)
    media['source_detail'] = 'fallback_http'
    return media


# ── 编排：PRIMARY 先，不行走 FALLBACK ─────────────────────────────────────

def extract_media(note_id, _js, _cdp):
    """提取单篇媒体。返回 (media_dict, source_str)。

    note_id 可为 None（取 noteDetailMap 里最新一条）。
    _js/_cdp 是 harness 的 js()/cdp()，显式传入避免 free-variable NameError。
    """
    js_text = "var __NOTEID__=%s;\n" % json.dumps(note_id) + PRIMARY_JS
    media = None
    try:
        media = _js(js_text)
    except Exception as e:
        print(f"  ⚠ PRIMARY js 异常: {e}", flush=True)

    if _has_media(media):
        media = media or {}
        media.setdefault('source_detail', 'initial_state')
        return media, 'initial_state'

    # FALLBACK：需要 note_id + xsec_token（从 PRIMARY 的半成品或单独再读一次）
    nid = note_id or (media or {}).get('noteId') or ''
    xsec = (media or {}).get('xsecToken') or ''
    if not xsec and nid:
        try:
            xsec = _js(("var m=window.__INITIAL_STATE__.note.noteDetailMap;"
                        "var n=m[%r]&&m[%r].note;return n?n.xsecToken:'';") % (nid, nid)) or ''
        except Exception:
            xsec = ''
    if not nid:
        return (media or {'ok': False, 'reason': 'no_note_id'}), 'none'

    print(f"  ↻ PRIMARY 不足，走 FALLBACK (noteId={nid})", flush=True)
    try:
        jar = cookies_from_cdp(_cdp)
    except Exception as e:
        print(f"  ⚠ 取 cookies 失败: {e}", flush=True)
        jar = requests.cookies.RequestsCookieJar()
    fb = fetch_via_http(nid, xsec, jar)
    if _has_media(fb):
        return fb, 'fallback'
    return (fb or media or {'ok': False, 'reason': 'both_failed'}), 'none'


# ── standalone（piped）：读 XHS_NOTE_ID，打印 JSON ────────────────────────

def _standalone():
    ensure_daemon(); ensure_real_tab()  # noqa: F821
    note_id = os.environ.get('XHS_NOTE_ID') or None
    media, source = extract_media(note_id, js, cdp)  # noqa: F821
    out = {'media': media or {}, 'source': source,
           'note_url': (media or {}).get('note_url', '')}
    print(json.dumps(out, ensure_ascii=False, indent=2))


# harness exec(code, globals()) 时 'ensure_daemon' 在 globals 里；import 时不在。
if 'ensure_daemon' in globals():
    _standalone()
