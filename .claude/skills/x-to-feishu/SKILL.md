---
name: x-to-feishu
description: |
  X (Twitter) 推文端到端处理流水线：抓取 home feed（滚动加载 + "show more" 展开长文 + 提取全文/时间/点赞/图片URL/视频标记）→ 经 new-api 网关用 Kimi 做翻译(英→中)+分类(项目/趋势/观点/通用/其他)+打标 → 写入飞书多维表格（lark-cli）。顺带可导嵌图 Excel。
  四个阶段都是独立可跑的原子脚本，用户可只跑其中一步（只抓取 / 只翻译分类 / 只导 Excel / 只入飞书），也可串成完整 pipeline。
  触发词：抓 X、抓推特、Twitter、刷推、爬推文、翻译推文、X 内容存飞书/多维表格、推特备份、tweet translation、把 X 数据导入飞书 等——即使用户没明说"用 skill"，只要意图匹配就激活。
compatibility: browser-harness, lark-cli, openpyxl
---

# X → Feishu

抓 X (Twitter) 推文 → 翻译 + 分类 + 打标 → 写入飞书多维表格（可顺带导 Excel）。四个阶段各自原子、独立可跑，也能串成一条 pipeline。

## 设计哲学：原子化

每个阶段是一个**独立可跑的脚本**，只依赖上一步的 JSON 产物（不依赖在内存里传递）：

```
x_fetch.py  →  tweets.json
x_enrich.py →  tweets_enriched.json   （在 tweets.json 上加 zh/category/tags）
x_to_lark.py →  飞书多维表格（读 tweets_enriched.json）
x_export_excel.py →  .xlsx 嵌图（读 tweets_enriched.json 或 tweets.json）
```

任意一步都能单独跑、单独重跑（都有断点续存/幂等）。用户说"只翻译"就只跑 `x_enrich.py`；说"全套"就按 pipeline 串起来。

## 前提

1. **browser-harness** 已安装、Chrome 已连接（CDP 远程调试）、**X 已登录**，且有停在 `x.com/home` 的标签页。
2. **NEWAPI_TOKEN** 环境变量：new-api 网关令牌（用于翻译+分类）。获取见 [references/gateway.md](references/gateway.md)。
3. **lark-cli** 已登录（写入飞书用）。`lark-cli base --help` 能跑即 OK。
4. **openpyxl**（导 Excel 用）：`pip install openpyxl`。

## 完整 Pipeline（端到端）

```bash
export NEWAPI_TOKEN=<new-api 网关令牌>     # 见 references/gateway.md
DIR="x_data/$(date +%Y%m%d)_fetch"

# ① 抓取（在 X home 页滚动、展开长文、提取）
XFETCH_OUTDIR="$DIR" browser-harness < scripts/x_fetch.py

# ② 翻译 + 分类 + 打标（网关 Kimi；并发、断点续存）
XENRICH_DIR="$DIR" python3 scripts/x_enrich.py

# ③ 写入飞书多维表格（新建表 + 批量写记录）
python3 scripts/x_to_lark.py "$DIR/tweets_enriched.json"

# ④（可选）导出嵌图 Excel
python3 scripts/x_export_excel.py "$DIR" "$DIR/x_tweets.xlsx" && open "$DIR/x_tweets.xlsx"
```

## 原子脚本逐个

### ① `x_fetch.py` — 抓取 X 推文

**做什么**：attach `x.com/home` 标签 → 每轮滚约一屏（逼近底部触发 lazy-load）→ 点掉所有 "show more" 展开长文 → 提取每条 `tid/handle/全文/dt/点赞/回复/转发/图片URL(orig)/视频标记+poster` → 按 tid 去重、断点续爬。

**用法**：
```bash
XFETCH_OUTDIR="x_data/20260703_fetch" XFETCH_MAX_TWEETS=30 \
  browser-harness < scripts/x_fetch.py
```
**环境变量**：`XFETCH_MAX_TWEETS`(30) · `XFETCH_OUTDIR`(x_data/<今天>_fetch) · `XFETCH_MAX_ROUNDS`(60) · `XFETCH_TAB_HINT`(x.com/home)

**产物**：`tweets.json`（全部字段）、`video_tweets.json`（视频帖索引，供阶段 mp4 用）。

> 滚动机制非平凡——见 [references/x-gotchas.md](references/x-gotchas.md) 的「滚动 lazy-load」坑。

### ② `x_enrich.py` — 翻译 + 分类 + 打标（网关 Kimi）

**做什么**：每条推文一次 Kimi 调用，同时出 `{zh: 中文译文, category: 项目|趋势|观点|通用|其他, tags: [..]}`；并发、失败重试、断点续存（已富化的 tid 跳过）。

**用法**：
```bash
export NEWAPI_TOKEN=<令牌>
XENRICH_DIR="x_data/20260703_fetch" python3 scripts/x_enrich.py
# 或指定输入文件：
python3 scripts/x_enrich.py path/to/tweets.json
```
**环境变量**：`NEWAPI_TOKEN`(必填) · `NEWAPI_BASE_URL` · `NEWAPI_MODEL`(@cf/moonshotai/kimi-k2.7-code) · `XENRICH_WORKERS`(5) · `XENRICH_DIR`

**产物**：`tweets_enriched.json`（原字段 + `enriched: {zh, category, tags}`）。

> 网关模型选择、限流/额度教训见 [references/gateway.md](references/gateway.md)。

### ③ `x_to_lark.py` — 写入飞书多维表格

**做什么**：读 `tweets_enriched.json` →（默认）新建多维表格（含 12 字段 schema：序号/作者/时间/原文/中文翻译/分类(单选)/标签/点赞/图片/视频/OCR/链接）→ `lark-cli` 批量写记录（≤200/批）。

**用法**：
```bash
# 新建表并写入
python3 scripts/x_to_lark.py "x_data/20260703_fetch/tweets_enriched.json"
# 写入已有多维表格（须已有匹配字段）
X_TO_LARK_BASE=<base_token> python3 scripts/x_to_lark.py "path/tweets_enriched.json"
```
**环境变量**：`X_TO_LARK_BASE`(不设则新建) · `X_TO_LARK_NAME`(X 推文巡检 <date>) · `X_TO_LARK_TABLE`(推文)

**产物**：飞书多维表格（打印 base_token + url）。schema 细节见 [references/feishu-schema.md](references/feishu-schema.md)。

### ④ `x_export_excel.py` — 导出嵌图 Excel（可选）

**做什么**：读 JSON → 下载图片（带 `Referer: x.com`）→ openpyxl 按原始比例嵌入每行；视频帖无图时用 poster 兜底，视频列带原推超链接。

**用法**：
```bash
python3 scripts/x_export_excel.py "x_data/20260703_fetch" "x_data/20260703_fetch/x_tweets.xlsx"
```

## Guidelines（关键注意点）

- **滚动别用小步**：X 的 lazy-load 要靠"滚到接近底部"触发，每轮滚约一屏（`0.9 × innerHeight`）。小步 `scrollBy(900)` 永远到不了底部 → 卡在已加载窗口里出不来。详见 x-gotchas.md。
- **stall 判定**：深度往下扫时，"已收过的推文(overlap)"是正常的、不算到底；只有"**既无新推文、页面高度也不增长**"才是真的到底。别用"0 新增"当停止信号。
- **show-more 用 JS `.click()`**：实测 X 的 `[data-testid="tweet-text-show-more-link"]` 用 JS click 即可展开（无需 hover 坐标点）。
- **图片原图**：`pbs.twimg.com/media/...?name=medium` 改 `name=orig`；**必须过滤 `/media/` 路径**，否则会把头像 `profile_images` 误收。
- **视频没直链**：DOM 里 `<video src>` 是 `blob:`（MSE 流），拿不到 mp4。本 skill 只记 `has_video + poster + status URL`；要可下载 mp4 走 `references/x-gotchas.md` 的 Network/TweetResultByRestId 流程。
- **OCR 当前不可用**：网关的 `ocr-space` 渠道常超时（502）。`OCR` 列暂留空，等渠道恢复后单独跑一轮回填。
- **令牌别进 git**：`x_enrich.py` 的网关令牌读 `NEWAPI_TOKEN` 环境变量，**绝不硬编码**到脚本里。

## Extended Capabilities

- 网关用法（令牌/模型/Kimi/ocr-space/限流额度）→ [references/gateway.md](references/gateway.md)
- X 站点坑（滚动 lazy-load / show-more / 视频 blob / 图片过滤）→ [references/x-gotchas.md](references/x-gotchas.md)
- 多维表格 schema + lark-cli 写记录细节 → [references/feishu-schema.md](references/feishu-schema.md)

## 与 x-ai-scanner 的关系

`.claude/skills/x-ai-scanner/` 是"AI 分身替你刷 X 首页筛 AI 趋势"的 skill（带本地启发式分类器）。本 skill 聚焦"抓取→翻译→入飞书"，分类交给服务器 AI（Kimi）。两者互补：x-ai-scanner 重"筛选发现"，本 skill 重"采集交付到飞书"。
