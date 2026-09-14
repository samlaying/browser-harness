---
id: xhs-crawler-ops
type: knowledge
title: xhs-crawler 运行手册 — 健康判断、跨天续爬、富化路径
status: active
created: 2026-07-11
updated: 2026-07-17
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
- **active tab 是 `about:blank`（非搜索页）、但 `Target.getTargets` 里有正常的 `/search_result` tab** → daemon tab 跟踪错乱（常见于**反复强制 `TaskStop` browser-harness 进程**之后），`new_tab(url)` 导航卡在 about:blank、没切到搜索页。**这不是限流/登录态/SPA**。修复：`browser-harness --reload`（fresh 重启 daemon），再用 `new_tab('https://example.com')` + 读 url 验证写操作恢复，然后重跑（断点续爬自动跳过已完成）。实测：2026-07-17 第 5 批「如何学ai」前 4 批正常，中途多次 TaskStop 后重跑即卡 about:blank、报"未收集到任何卡片"，reload 后从第 3 篇断点续爬秒过、20/20 完成。
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

#### 4. OUTDIR 必须传绝对路径（否则 daemon cwd 污染 → 嵌套）

`xhs_batch.py:511` 默认 `os.path.join('xhs_data', date+'_'+keyword[:10])` 是**相对路径**，基于执行进程的 cwd。browser-harness daemon 是长驻进程，cwd 持久——停在上次运行结束的位置。若 daemon cwd 已在某旧 OUTDIR（如 `xhs_data/20260712_一天拆解一个ai产品/`），这次相对路径会在它底下**再套一层** `xhs_data/{新关键词}/`，数据没丢但位置嵌套、难找。

- **修法（推荐）**：始终传**绝对路径** `XHS_OUTDIR`：
  ```bash
  XHS_KEYWORD='...' XHS_TARGET=20 \
    XHS_OUTDIR="$PWD/xhs_data/$(date +%Y%m%d)_关键词简写" \
    browser-harness < .claude/skills/xhs-crawler/scripts/xhs_batch.py
  ```
- 或爬取前在**项目根**跑 `browser-harness --reload` 重置 daemon cwd（治标，不绝对可靠）。
- **误判风险**：日志正常打 `[N/20] ✓ ok`、数据正常落盘，但 `xhs_data/{预期目录}` 找不到 → 别以为没爬到，先 `find . -name state.json -mmin -5` 定位真实路径。已嵌套的用 `mv` 扁平化即可（state.json 不存绝对路径，移动不影响续爬/导出）。
- 实测：2026-07-12 爬「面试问到遇到的最大困难」，daemon cwd 停在上一次「一天拆解」目录，新数据落在 `xhs_data/20260712_一天拆解一个ai产品/xhs_data/20260712_面试.../`，20/20 爬完后 `mv` 扁平化 + 导出正常。

> **另一条同症状的根因：Claude Bash 工具 cwd 持久化（不是 daemon）**。Bash 工具的工作目录**跨调用持久**。若在验证步骤里 `cd "xhs_data/某OUTDIR"`（如 `cd OUTDIR && ls` 验证 xlsx/json），后续所有 Bash 调用的 `$PWD` 就停在**那个 OUTDIR**：① 新 crawl 的 `mkdir -p "$PWD/xhs_data/新词"` 会在旧 OUTDIR 里再套一层；② `$PWD/.claude/skills/.../xhs_batch.py` 找不到脚本 → 启动报 `(eval): no such file or directory`、exit 1。
> - 这与上面的 **daemon cwd**（长驻进程的 cwd）是两码事，但**症状完全相同**：OUTDIR 嵌套。排查时先 `echo $PWD` 判断是外层 shell 的 cd 还是 daemon。
> - 规避：xhs 所有命令一律用**绝对路径**（OUTDIR、脚本路径都写全）；验证 JSON/图片/xlsx 时**不要 `cd` 进 OUTDIR**，改用 `python3`/`ls` 传绝对路径读。
> - 实测：2026-07-23 第二批「后台系统架构开发」连续 3 次启动失败（exit 1，`no such file or directory: .../20260723_电商后台设计/.claude/...`），根因是上一批验证时 `cd` 进了旧 OUTDIR 没退出。`cd` 回项目根 + 删掉空嵌套目录 + 全程绝对路径后正常。

## 反爬节奏（个人经验）

每个平台每天不超过 2–3 次批量运行；脚本内置随机延迟/并发上限/指数退避，但替代不了常识。

## When to Use

- 跑 xhs_batch.py 判断爬虫是否真挂、要不要重跑时。
- 跨天/崩溃后续爬 xhs 时。
- 选择 xhs 富化→飞书路径时。
