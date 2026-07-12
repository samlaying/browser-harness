---
id: vision-ocr-models
type: knowledge
title: 图片 OCR / 视觉理解走硅基流动 VL 直连（不经 new-api 网关）
status: active
created: 2026-07-11
updated: 2026-07-11
tags: [pensieve, knowledge, ocr, vl, siliconflow, vision]
---

# 图片 OCR / 视觉理解模型

## Summary

小红书等社交帖子的真实内容多在图里，正文往往很薄，必须 OCR 图才能判真假干货。**VL 模型（Qwen3-VL-32B-Instruct / -8B / Thinking 等）在 siliconflow 平台可用，但未接入 new-api 网关渠道——必须用平台原始 key 直连 `https://api.siliconflow.cn/v1`，不能走 new-api。** ⚠️ 旧文档里"网关上跑 Qwen3-VL-8B"的说法已过时。

## Content

### 调用方式

- OpenAI SDK 兼容，image 走 `data:image/jpeg;base64,...`，temperature 0.1。
- 单图 ~1200 token，ThreadPoolExecutor 8 并发，105 图约 1-2 分钟、0 失败。
- key 在 `/Users/sam/lark/account/servers/RackNerd/new-api/providers/siliconflow/siliconflow.md`（真实密钥，**别提交进库**）。

### 封装脚本

`.claude/skills/xhs-crawler/scripts/xhs_ocr.py`：`XSF_KEY` / `XHS_OUTDIR` 走环境变量（key 不入库），产出 `ocr_cache.json` + `notes_enriched.json`，支持断点续跑。

### 图片→笔记映射

要严格复刻 `xhs_export.build_excel` 的扁平去重顺序（`dict.fromkeys` 全局 noteImgs + 评论图[:2]），否则 `img_N.jpg` 对不上笔记。

## When to Use

- 小红书/社交帖子需要 OCR 图片文字或做视觉理解时。
- 配合 xhs-crawler 的通用 OCR 富化路径（见 [[knowledge/xhs-crawler-ops/content]]）。
