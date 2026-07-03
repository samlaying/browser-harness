#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X 推文 Excel 导出 — 含图片下载 + 嵌入对应位置

用法：
    python3 x_fetch_export.py <json_dir_or_tweets.json> [output.xlsx]

输入：x_fetch.py 输出的 tweets.json（或含它的目录）
输出：单 Sheet Excel，每行一条推文，图片按原始比例嵌入 I~L 列
依赖：pip install openpyxl
"""

import json, os, sys, datetime, glob, math, urllib.request, re
from concurrent.futures import ThreadPoolExecutor

# openpyxl 拒绝非法控制字符，写入前清洗
_ILLEGAL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
def _clean(v):
    return _ILLEGAL_CHARS_RE.sub('', v) if isinstance(v, str) else v

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XlImage
from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

# 交替行底色（浅色，便于阅读）
ROW_COLORS = ["FFFFFF", "F0F6FC"]
HEAD_FILL = PatternFill(start_color="1D9BF0", end_color="1D9BF0", fill_type="solid")  # X 蓝
THIN = Border(bottom=Side(style='thin', color='DDDDDD'))

IMG_W = 110          # 图片目标宽度（px），高度按原始比例
IMG_COL = 9          # 图片起始列（I），最多 4 张 → I,J,K,L

# ── 图片下载 ──────────────────────────────────────────────

def download_image(url, fpath):
    if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
        return True
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Referer': 'https://x.com/',
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(fpath, 'wb') as f:
                f.write(resp.read())
        return True
    except Exception as e:
        print(f"  下载失败 {url}: {e}")
        return False

def download_all(urls, img_dir, prefix):
    os.makedirs(img_dir, exist_ok=True)
    url_map = {}
    for idx, url in enumerate(dict.fromkeys(urls)):            # 去重保序
        url_map[url] = os.path.join(img_dir, '%s_%d.jpg' % (prefix, idx))
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda it: download_image(*it), url_map.items()))
    return url_map

# ── 加载 ──────────────────────────────────────────────────

def load_tweets(path):
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, list) else [d]
    cand = os.path.join(path, 'tweets.json')
    if os.path.exists(cand):
        with open(cand, encoding='utf-8') as f:
            return json.load(f)
    out = []
    for fp in sorted(glob.glob(os.path.join(path, '*.json'))):
        try:
            with open(fp, encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, list):
                out.extend(d)
        except Exception:
            pass
    return out

# ── 构建 Excel ────────────────────────────────────────────

def build_excel(tweets, output_path, img_dir):
    # 清洗文本字段
    for t in tweets:
        for k in ('text', 'name', 'handle'):
            if isinstance(t.get(k), str):
                t[k] = _clean(t[k])

    # 每条推文的图片清单：优先 imgs；视频帖无图则用 poster 当预览
    tweet_imgs = {}
    all_urls = []
    for t in tweets:
        imgs = list(t.get('imgs') or [])
        if not imgs and t.get('has_video') and t.get('video_poster'):
            imgs = [t['video_poster']]
        tweet_imgs[t.get('tid')] = imgs
        all_urls.extend(imgs)
    dl = download_all(all_urls, img_dir, 'tw')

    wb = Workbook()
    ws = wb.active
    ws.title = "X推文"

    # 列宽：A# B作者 C时间 D正文 E赞 F回复 G转 H视频 I-L 图片
    widths = {'A': 5, 'B': 18, 'C': 18, 'D': 80, 'E': 7, 'F': 7, 'G': 7,
              'H': 10, 'I': 15, 'J': 15, 'K': 15, 'L': 15}
    for c, w in widths.items():
        ws.column_dimensions[c].width = w

    headers = ['#', '作者 @handle', '时间', '正文', '❤赞', '💬回复', '🔁转', '视频', '图片1', '图片2', '图片3', '图片4']
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 24

    for i, t in enumerate(tweets):
        r = i + 2
        ws.cell(row=r, column=1, value=i + 1)
        ws.cell(row=r, column=2, value=f"@{t.get('handle', '')}\n{t.get('name', '')}")
        ws.cell(row=r, column=3, value=f"{t.get('time_text', '')}\n{t.get('dt', '')}")
        tc = ws.cell(row=r, column=4, value=t.get('text', ''))
        tc.alignment = Alignment(wrap_text=True, vertical='top')
        ws.cell(row=r, column=5, value=t.get('likes', 0))
        ws.cell(row=r, column=6, value=t.get('replies', 0))
        ws.cell(row=r, column=7, value=t.get('reposts', 0))
        vcell = ws.cell(row=r, column=8, value=('▶视频' if t.get('has_video') else '—'))
        if t.get('has_video') and t.get('url'):
            vcell.hyperlink = t.get('url')
            vcell.font = Font(color='1D9BF0', underline='single')

        fill = PatternFill(start_color=ROW_COLORS[i % 2], end_color=ROW_COLORS[i % 2], fill_type="solid")
        for col in range(1, 9):
            ws.cell(row=r, column=col).fill = fill
            ws.cell(row=r, column=col).border = THIN
        ws.cell(row=r, column=2).alignment = Alignment(vertical='top')
        ws.cell(row=r, column=3).alignment = Alignment(vertical='top')

        # 行高：按正文长度估算（D 列宽 80，混合文 ~70 字/行）
        text_len = len(t.get('text', '') or '')
        text_lines = max(1, math.ceil(text_len / 70))
        text_h_pt = text_lines * 15 + 8
        row_h_pt = max(30, min(text_h_pt, 420))

        # 嵌入图片（按原始比例缩放到宽 IMG_W）
        imgs = tweet_imgs.get(t.get('tid'), [])
        max_img_h_pt = 0
        for j, url in enumerate(imgs[:4]):
            fpath = dl.get(url)
            if not (fpath and os.path.exists(fpath) and os.path.getsize(fpath) > 0):
                continue
            try:
                img = XlImage(fpath)
                nw, nh = img.width, img.height or 1
                img.width = IMG_W
                img.height = max(1, int(IMG_W * nh / nw))
                img.anchor = OneCellAnchor(
                    _from=AnchorMarker(col=IMG_COL + j, colOff=0, row=r - 1, rowOff=0),
                    ext=XDRPositiveSize2D(pixels_to_EMU(img.width), pixels_to_EMU(img.height)),
                )
                ws.add_image(img)
                max_img_h_pt = max(max_img_h_pt, img.height * 0.75)
            except Exception as e:
                print(f"  嵌图失败: {e}")

        if max_img_h_pt:
            row_h_pt = max(row_h_pt, max_img_h_pt + 6)
        ws.row_dimensions[r].height = row_h_pt

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f"A1:L{len(tweets)+1}"
    wb.save(output_path)
    return output_path

# ── 入口 ──────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法: python3 x_fetch_export.py <json_dir_or_tweets.json> [output.xlsx]")
        sys.exit(1)
    path = sys.argv[1]
    base = os.path.dirname(path) if os.path.isfile(path) else path
    img_dir = os.path.join(base, 'x_images')
    os.makedirs(img_dir, exist_ok=True)

    tweets = load_tweets(path)
    seen = set(); uniq = []
    for t in tweets:
        tid = t.get('tid')
        if tid in seen:
            continue
        if tid:
            seen.add(tid)
        uniq.append(t)
    tweets = uniq
    print(f"加载 {len(tweets)} 条推文")

    if len(sys.argv) >= 3:
        out = sys.argv[2]
    else:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(base, f'x_tweets_{ts}.xlsx')

    build_excel(tweets, out, img_dir)
    with_img = sum(1 for t in tweets if (t.get('imgs') or (t.get('has_video') and t.get('video_poster'))))
    print(f"✅ {len(tweets)} 条推文（含图/视频 {with_img}）→ {out}")

if __name__ == '__main__':
    main()
