#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书评论 Excel 导出脚本（含帖子图片 + 评论图片嵌入）

用法：
    python3 xhs_export.py <json_file> [output_dir]

输入：xhs_crawl.py 输出的 JSON 文件
输出：Excel 文件（两个 Sheet：帖子信息 + 评论），图片嵌入单元格

依赖：pip install openpyxl
"""

import json, os, sys, datetime, urllib.request
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XlImage
from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.styles import Alignment, Font, PatternFill


def download_image(url, fpath):
    """下载图片，带 Referer 头"""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Referer': 'https://www.xiaohongshu.com/',
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(fpath, 'wb') as f:
                f.write(resp.read())
        return True
    except Exception as e:
        print(f"  下载失败: {e}")
        return False


def build_excel(data, output_path):
    """生成 Excel 文件"""
    meta = data.get('meta', {})
    comments = data.get('comments', [])

    wb = Workbook()

    # ── Sheet 1: 帖子信息 ──
    ws1 = wb.active
    ws1.title = "帖子信息"
    ws1.append(['字段', '内容'])
    ws1.append(['标题', meta.get('title', '')])
    ws1.append(['描述', meta.get('desc', '')])
    ws1.append(['互动栏', meta.get('barText', '')])
    ws1.append(['类型', '视频帖' if meta.get('hasVideo') else '图文帖'])
    ws1.append(['帖子图片数', len(meta.get('noteImgs', []))])
    ws1.column_dimensions['A'].width = 12
    ws1.column_dimensions['B'].width = 80

    # 帖子图片：每张独占一行
    IMG_POST_H = 267
    img_dir = os.path.join(os.path.dirname(output_path), 'xhs_images')
    os.makedirs(img_dir, exist_ok=True)

    dl_map = {}  # url -> local path
    for idx, img_url in enumerate(meta.get('noteImgs', [])):
        fpath = os.path.join(img_dir, f'post_{idx}.jpg')
        if not os.path.exists(fpath):
            download_image(img_url, fpath)
        dl_map[img_url] = fpath

        row = 5 + idx
        ws1.row_dimensions[row].height = IMG_POST_H * 0.75
        if os.path.exists(fpath):
            img = XlImage(fpath)
            img.width = 200
            img.height = IMG_POST_H
            img.anchor = OneCellAnchor(
                _from=AnchorMarker(col=1, colOff=0, row=row-1, rowOff=0),
                ext=XDRPositiveSize2D(pixels_to_EMU(200), pixels_to_EMU(IMG_POST_H)),
            )
            ws1.add_image(img)

    # ── Sheet 2: 评论 ──
    ws2 = wb.create_sheet("评论")
    headers = ['序号', '线程ID', '层级', '回复对象', '昵称', '评论内容',
               '评论图片', '时间', 'IP属地', '点赞', '回复数']
    ws2.append(headers)
    for cell in ws2[1]:
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal='center')

    # 下载评论图片
    cmt_img_idx = 0
    for c in comments:
        for img_url in c.get('imgs', []):
            if img_url in dl_map:
                continue
            fpath = os.path.join(img_dir, f'cmt_{cmt_img_idx}.jpg')
            download_image(img_url, fpath)
            dl_map[img_url] = fpath
            cmt_img_idx += 1

    # 写入评论行
    IMG_CMT_SIZE = 80
    emu_size = pixels_to_EMU(IMG_CMT_SIZE)

    for i, c in enumerate(comments, 1):
        row = i + 1
        ws2.append([
            i,
            c.get('thread_id', ''),
            '评论' if c['lvl'] == 1 else '回复',
            c.get('reply_to', ''),
            c['nick'],
            c['content'],
            '',  # 图片列占位
            c['date'],
            c['ip'],
            c.get('likes', '0'),
            c.get('replies', '0'),
        ])

        # 嵌入评论图片
        imgs = c.get('imgs', [])
        if imgs:
            ws2.row_dimensions[row].height = IMG_CMT_SIZE * 0.75
            for img_url in imgs[:3]:  # 最多 3 张
                fpath = dl_map.get(img_url)
                if fpath and os.path.exists(fpath):
                    try:
                        img = XlImage(fpath)
                        img.width = IMG_CMT_SIZE
                        img.height = IMG_CMT_SIZE
                        img.anchor = OneCellAnchor(
                            _from=AnchorMarker(col=6, colOff=0, row=row-1, rowOff=0),
                            ext=XDRPositiveSize2D(emu_size, emu_size),
                        )
                        ws2.add_image(img)
                    except Exception:
                        pass

    # 列宽
    for col, w in [('A',5),('B',8),('C',6),('D',12),('E',18),('F',50),
                    ('G',15),('H',12),('I',8),('J',6),('K',6)]:
        ws2.column_dimensions[col].width = w

    wb.save(output_path)
    return output_path


def main():
    if len(sys.argv) < 2:
        print("用法: python3 xhs_export.py <json_file> [output_dir]")
        sys.exit(1)

    json_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(json_file) or '.'

    with open(json_file, encoding='utf-8') as f:
        data = json.load(f)

    title = data.get('meta', {}).get('title', 'unknown')[:20]
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = ''.join(c if c.isalnum() or '一' <= c <= '鿿' else '_' for c in title)
    out = os.path.join(output_dir, f'xhs_{safe_title}_{ts}.xlsx')

    build_excel(data, out)
    print(f"✅ {len(data.get('comments',[]))} 条评论 → {out}")


if __name__ == '__main__':
    main()
