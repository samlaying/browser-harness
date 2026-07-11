#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书图片 OCR — 用硅基流动 SiliconFlow VL 模型识别笔记/评论图片文字。

为什么需要：小红书帖子的真实内容（评测方法、截图、数据、流程）大多在图片里，
正文往往只有一两句。要让 LLM 判断「真有实战 vs AI 口水话」，必须先把图片文字抠出来。

用法（key 走环境变量，不入库）:
    XSF_KEY=sk-... XHS_OUTDIR="xhs_data/20260706_skill评测迭代" python3 xhs_ocr.py

输入：OUTDIR/*.json（xhs_batch.py 产出）+ OUTDIR/xhs_images/*.jpg（xhs_export.py 下载）
输出：
  - OUTDIR/ocr_cache.json   {img_filename: ocr_text}  全量缓存，断点续跑
  - OUTDIR/notes_enriched.json  每篇笔记合并 OCR 文本 + 评论纯文本，供分类用

环境变量：
  XHS_OUTDIR      笔记目录（必填）
  XSF_KEY         siliconflow API key（必填；见 providers/siliconflow/siliconflow.md）
  XHS_VL_MODEL    VL 模型（默认 Qwen/Qwen3-VL-32B-Instruct）
  XHS_OCR_WORKERS 并发数（默认 8）
  XHS_OCR_LIMIT   只 OCR 前 N 张（调试用，默认全量）

文件名→笔记的映射依赖 xhs_export.build_excel 的扁平去重顺序，必须严格复刻，
否则 img_N.jpg 对不上笔记（export 用 dict.fromkeys 全局去重保序）。
"""
import os, sys, json, glob, base64, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

OUTDIR = os.environ.get('XHS_OUTDIR', '').strip()
KEY = os.environ.get('XSF_KEY', '').strip()
MODEL = os.environ.get('XHS_VL_MODEL', 'Qwen/Qwen3-VL-32B-Instruct')
WORKERS = int(os.environ.get('XHS_OCR_WORKERS', '8'))
LIMIT = int(os.environ.get('XHS_OCR_LIMIT', '0'))
IMGDIR = os.path.join(OUTDIR, 'xhs_images') if OUTDIR else ''
CACHE = os.path.join(OUTDIR, 'ocr_cache.json') if OUTDIR else ''
ENRICHED = os.path.join(OUTDIR, 'notes_enriched.json') if OUTDIR else ''

if not OUTDIR or not KEY:
    print("ERROR: 必须设置 XHS_OUTDIR 和 XSF_KEY"); sys.exit(1)

client = OpenAI(api_key=KEY, base_url="https://api.siliconflow.cn/v1")

PROMPT = ("OCR 这张图片，提取所有可见文字（标题、正文、标签、图表里的文字、代码、UI 文案等），"
          "保留原始结构与层级。如果图片是纯照片/无文字，回复「(无文字)」。只输出识别到的内容，不要解释。")


def load_notes():
    notes = []
    for fp in sorted(glob.glob(os.path.join(OUTDIR, '*.json'))):
        if os.path.basename(fp) in ('state.json', 'notes_order.json', 'notes_enriched.json'):
            continue
        try:
            d = json.load(open(fp))
        except Exception:
            continue
        if isinstance(d, dict) and d.get('note_id'):
            notes.append(d)
    return notes


def build_url2file(notes):
    """严格复刻 xhs_export.build_excel 的扁平去重顺序，得到 url→本地文件名映射。"""
    all_urls = []
    for n in notes:
        all_urls.extend(n.get('meta', {}).get('noteImgs', []))
        for c in n.get('comments', []):
            all_urls.extend(c.get('imgs', [])[:2])
    m = {}
    for idx, url in enumerate(dict.fromkeys(all_urls)):
        m[url] = 'img_%d.jpg' % idx
    return m


def ocr_one(fname):
    fp = os.path.join(IMGDIR, fname)
    if not os.path.exists(fp) or os.path.getsize(fp) == 0:
        return fname, '(文件缺失)'
    try:
        with open(fp, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': PROMPT},
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
            ]}],
            temperature=0.1, max_tokens=2000,
        )
        return fname, (r.choices[0].message.content or '').strip()
    except Exception as e:
        return fname, '(OCR失败: %s)' % str(e)[:120]


def main():
    notes = load_notes()
    url2file = build_url2file(notes)
    # 只 OCR 实际存在于磁盘的文件
    files = sorted(set(url2file.values()))
    files = [f for f in files if os.path.exists(os.path.join(IMGDIR, f))]
    if LIMIT:
        files = files[:LIMIT]

    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE))
        except Exception:
            cache = {}

    todo = [f for f in files if f not in cache or not cache[f] or cache[f].startswith('(OCR失败')]
    print(f"笔记 {len(notes)} 篇，图片 {len(files)} 张，已缓存 {len(cache)-len(todo) if False else len([f for f in files if f in cache and cache[f] and not cache[f].startswith('(OCR失败)')])}，待 OCR {len(todo)}", flush=True)

    done = 0
    failed = 0
    if todo:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(ocr_one, f): f for f in todo}
            for fut in as_completed(futs):
                fname, text = fut.result()
                cache[fname] = text
                done += 1
                if text.startswith('(OCR失败') or text == '(文件缺失)':
                    failed += 1
                if done % 10 == 0 or done == len(todo):
                    print("  OCR %d/%d (失败 %d)" % (done, len(todo), failed), flush=True)
                    # 增量落盘
                    with open(CACHE, 'w', encoding='utf-8') as f:
                        json.dump(cache, f, ensure_ascii=False, indent=2)
        with open(CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    # 组装 enriched：每篇合并 noteImgs 的 OCR + 评论纯文本
    enriched = []
    for n in notes:
        meta = n.get('meta', {})
        note_imgs_ocr = [cache.get(url2file.get(u, ''), '') for u in meta.get('noteImgs', [])]
        note_imgs_ocr = [t for t in note_imgs_ocr if t and not t.startswith('(')]
        cmt_imgs_ocr = []
        for c in n.get('comments', []):
            for u in c.get('imgs', [])[:2]:
                t = cache.get(url2file.get(u, ''), '')
                if t and not t.startswith('('):
                    cmt_imgs_ocr.append(t)
        comments_text = []
        for c in n.get('comments', []):
            nick = c.get('nick', '')
            content = c.get('content', '')
            likes = c.get('likes', '0')
            lvl = c.get('lvl', 1)
            prefix = '  ↳' if lvl == 2 else ''
            if content:
                comments_text.append('%s%s: %s%s' % (prefix, nick, content, (' [赞%s]' % likes if likes and likes != '0' else '')))
        enriched.append({
            'note_id': n.get('note_id'),
            'title': meta.get('title', ''),
            'desc': meta.get('desc', ''),
            'barText': meta.get('barText', ''),
            'hasVideo': meta.get('hasVideo', False),
            'noteImgs_count': len(meta.get('noteImgs', [])),
            'noteImg_ocr': '\n---\n'.join(note_imgs_ocr),
            'commentImg_ocr': '\n---\n'.join(cmt_imgs_ocr),
            'comments_text': '\n'.join(comments_text),
            'total_comments': n.get('total_comments', 0),
        })
    with open(ENRICHED, 'w', encoding='utf-8') as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print("\n==== OCR 完成 ====", flush=True)
    print("图片 %d 张，失败 %d 张 → %s" % (len(files), failed, CACHE), flush=True)
    print("enriched %d 篇 → %s" % (len(enriched), ENRICHED), flush=True)


if __name__ == '__main__':
    main()
