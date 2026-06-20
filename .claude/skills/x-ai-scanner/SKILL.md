---
name: x-ai-scanner
description: |
  X (Twitter) Home Feed AI 巡检分身：自动滚动"For you"信息流，提取每条推文，
  用双语启发式分类器筛出 AI 相关内容，并归为 趋势(trend) / 项目(project) / 观点(opinion)，
  导出 Markdown 摘要 + Excel。基于 browser-harness (CDP)。
  触发：用户提到刷 X / Twitter AI 趋势、AI 分身、AI 项目巡检、监控 X 上的 AI 内容、
  自动刷推特找 AI。
compatibility: browser-harness, openpyxl
---

# X AI 巡检 Skill（AI 分身）

让一个"AI 分身"替你刷 X 首页，挑出 **AI 趋势 / AI 项目 / AI 观点**，记录成报告。

## 前提

1. browser-harness 已安装（`uv tool install -e ~/browser-harness`）
2. Chrome 已连接（CDP 远程调试）
3. **X 已登录**，且有一个停在 `https://x.com/home`（"For you"信息流）的标签页
4. openpyxl 已安装（`pip install openpyxl`，否则跳过 Excel）

## 一键流程

```bash
# 1) 巡检采集（默认滚 30 轮，自动找/打开 home 标签）
XAI_MAX_ROUNDS=30 browser-harness < scripts/x_ai_scan.py

# 2) 导出报告（Markdown + Excel）
python3 scripts/x_ai_export.py
```

输出目录：`xai_data/<YYYYMMDD>_scan/`

| 文件 | 说明 |
|------|------|
| `all_tweets.json` | 扫到的全部推文（含非 AI），跨次累计去重 |
| `ai_hits.json` | 仅 AI 相关命中（已排序） |
| `ai_digest.md` | 人类可读摘要，按 4 类分组 |
| `ai_scan.xlsx` | Excel 表格，按分类配色 |

## 工作原理

### 采集
- `attach_home()`：用 `list_tabs()` 找 `x.com/home` 标签并 `switch_tab` attach；没有就 `new_tab`。
  - **坑**：用户若另开 Grok 等标签，`ensure_real_tab()` 会误 attach 到它，所以必须显式按 URL 找 home 标签。
- 每轮 `window.scrollBy(0,1400)` → `js(EXTRACT_JS)` 提取页面上的 `article[data-testid="tweet"]`。
- 按推文 ID（取自 `time > a[href]` 的 `/handle/status/<id>`）去重；连续 6 轮无新推文则停。

### X 推文选择器速查

| 元素 | 选择器 |
|------|--------|
| 推文容器 | `article[data-testid="tweet"]` |
| 正文 | `[data-testid="tweetText"]` |
| 作者区 | `[data-testid="User-Name"]` |
| 时间+链接 | `time`（`datetime` 属性 + 父 `a[href]`） |
| 回复/转/赞 | `[data-testid="reply"/"retweet"/"like"]`（数值在 `aria-label`） |
| 广告 | 文本含 `Promoted` / `Sponsored`（跳过） |

### AI 分类器（`classify`，双语）

1. **核心词命中**才进 AI 候选（AI/AGI/LLM/GPT/Claude/Gemini/Grok/OpenAI/Anthropic/
   DeepSeek/Qwen/豆包/大模型/智能体/机器学习/… 全集见脚本 `AI_CORE`）。
2. 再按 **信号词** 归类（一条可多类，取最高分作 `primary`）：
   - `project`：launch / open source / github / new model / 发布 / 上线 / 开源 …
   - `trend`：future of / will replace / adoption / billion / 趋势 / 未来 / 增长 …
   - `opinion`：i think / imo / hot take / 我认为 / 应该 …
   - `general`：AI 相关但无明显类别信号。

> 启发式偏快偏稳，追求更高精度可在 `ai_hits.json` 之上再过一道 LLM。分类逻辑集中在
> `classify()`，调词表即可改判定。

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `XAI_MAX_ROUNDS` | `30` | 滚动轮数（每轮约 2~3 条新推文） |
| `XAI_OUT` | `xai_data/<date>_scan` | 输出目录 |
| `XAI_TAB_HINT` | `x.com/home` | 定位 feed 标签的 URL 片段 |

## 已知限制

- **纯图/视频推文**：无正文 → 命中不了 AI 关键词，自然被滤掉（符合预期）。
- **"For you"算法流**：信息流是个性化推荐，覆盖面取决于账号；想更广可换 Explore / 搜索特定关键词。
- **CDP 长跑**：30 轮约 1.5 分钟内安全；超长会话参考 xhs-crawler 的断连注意点。
- **去重跨次有效**：重跑会把新推文并入同一个 `all_tweets.json`，不重复计。

## 参考
- 采集/分类脚本：[scripts/x_ai_scan.py](scripts/x_ai_scan.py)
- 导出脚本：[scripts/x_ai_export.py](scripts/x_ai_export.py)
- 同仓爬虫模板（小红书）：`.claude/skills/xhs-crawler/`
