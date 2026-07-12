---
id: xhs-crawler-ops
type: knowledge
title: xhs-crawler 运行手册 — 健康判断、跨天续爬、富化路径
status: active
created: 2026-07-11
updated: 2026-07-11
tags: [pensieve, knowledge, xhs-crawler, xiaohongshu, scraping]
---

# xhs-crawler 运行手册

## Summary

xhs-crawler skill（`.claude/skills/xhs-crawler/`，编排脚本 `scripts/xhs_batch.py`）的运行行为知识：怎么判断爬虫真挂了 vs 正常慢跑、跨天续爬必须传 `XHS_OUTDIR`、两条互不兼容的富化路径怎么选。

## Content

### 1. 健康判断：别被静默和零卡片骗了

**单篇重帖静默 2~3 分钟是正常的。** 嵌套回复多的重帖（如爆款"锐评"帖）会让 `wait_for_comments` 的展开循环（上限 80 次 × 每次 hover+click+sleep ~2.5s ≈ 200s）跑满，期间脚本**完全不打印日志**。
- 判断进度看 **JSON 完成数 + state.json 的 `done`**，**不要**看日志文件的新鲜度/大小。
- 真崩会 loud-fail（exit≠0 + traceback，如 `CDP no close frame`），崩溃后直接重跑（断点续爬自动跳过已完成）。
- 真挂起（完成数 5+ 分钟不涨且非重帖）才考虑干预。
- 实测：2026-06-28 爬 `vibe coding 工具对比`，第 1 篇重帖静默 3+ 分钟被误判成 CDP 挂起、提前 `TaskStop` 杀掉了正在正常慢跑的进程（done-count 其实在涨）。

**零卡片失败常是 SPA 冷启动，不是限流/登录态。** `xhs_batch.py` 报 `ERROR: 未收集到任何卡片（可能未登录 / 被限流 / SPA 未渲染）` 时，三选一里最常见的是 SPA 冷启动——卡片渲染轮询只有 40×0.5s=20s，紧接上一次爬取的浏览器/网络偶发会超过这个窗口。
- 先诊断（别盲查登录态）：
  ```bash
  browser-harness <<'PY'
  print(js('return {path: location.pathname, items: document.querySelectorAll(".note-item").length, title: document.title};'))
  PY
  ```
- `items > 0` 且 `path == /search_result` 且 title 正常 → 纯冷启动超时，**直接重跑**（浏览器已热、SPA 资源已缓存，第二次 20s 内必渲染完）。
- `items == 0` 持续不出现、或被跳转登录页 → 才是真限流/登录墙，需人工处理。
- 实测：`30岁给20岁人的建议` 首跑零卡片，诊断时已有 44 张卡，重跑秒过。

### 2. 跨天续爬：必须显式传 XHS_OUTDIR

`xhs_batch.py` 默认 `XHS_OUTDIR = xhs_data/{当日日期}_{keyword[:10]}`，日期取**启动当天**。断点续爬靠 state.json 的 `done` ∪ 磁盘 JSON，但只在**同一个 OUTDIR** 下生效。若跨天（或当天崩溃次日续爬），默认目录变新日期 → 找不到旧 state → **从 0 重爬**。

续爬时一定显式传 `XHS_OUTDIR` 指回**原始目录名**（含原始日期）：
```bash
XHS_KEYWORD='...' XHS_TARGET=20 XHS_OUTDIR='xhs_data/20260629_某关键词' \
  browser-harness < .claude/skills/xhs-crawler/scripts/xhs_batch.py
```
启动日志会打印 `已完成 N，待爬 M`，看到 N=0 说明 OUTDIR 指错了，立刻停。
- 实测：豆包收费那次爬到 14/20 触发 CDP 长连断连崩溃，次日续爬靠这条避免了重爬 14 篇。

### 3. 两条富化→飞书路径（互不兼容，按主题选）

1. **简历专用**：`xhs_enrich.py`（NEWAPI_TOKEN + Qwen3-VL，prompt 硬编码提取{求职方向/教育/经历/项目/技能/亮点}、分类为模板展示/求评改简历）→ `xhs_to_lark.py`（简历 schema，默认表名"AI产品经理简历"）。**只适合简历主题**，对其他主题产出垃圾字段。
2. **通用 OCR**：`xhs_ocr.py`（XSF_KEY + SiliconFlow Qwen3-VL-32B，主题无关，提图片全文，见 [[knowledge/vision-ocr-models/content]]）→ `xhs_ocr_to_lark.py`（通用 schema：标题/正文/图片OCR/评论精华/互动/图片/链接，表名取 state.keyword）。**适合任意主题**。

两条路径的 `notes_enriched.json` schema 不同（简历用嵌套 `enriched{ocr,fields,summary,...}`；通用用扁平 `{noteImg_ocr,comments_text,...}`），脚本不能交叉使用。
- 非简历主题（方法论/教程/测评/攻略等）一律走通用路径。
- 上传时默认 profile「猎聘」缺 base scope 会 missing_scope 报错，必须 `LARK_PROFILE=cli_aa823d7922f8dbc3`（SA 账号，有 base scope），见 [[knowledge/feishu-lark-cli-ops/content]]。

### 反爬节奏（个人经验）

每个平台每天不超过 2–3 次批量运行；脚本内置随机延迟/并发上限/指数退避，但替代不了常识。

## When to Use

- 跑 xhs_batch.py 判断爬虫是否真挂、要不要重跑时。
- 跨天/崩溃后续爬 xhs 时。
- 选择 xhs 富化→飞书路径时。
