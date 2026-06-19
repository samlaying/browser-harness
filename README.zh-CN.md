<img src="https://raw.githubusercontent.com/browser-use/media/main/browser-harness/banner-ink.svg" alt="Browser Harness" width="100%" />

# Browser Harness ♞

> 🌐 English: [README.md](README.md)

用一套薄而可编辑的 CDP 线束，把 LLM 直接接到你自己的浏览器。适合需要**完全自由**的浏览器任务。

一条 WebSocket 连到 Chrome，中间没有任何东西。缺的 helper，agent 在执行时自己写。线束每跑一次都在自我改进。

```
  ● agent：想上传一个文件
  │
  ● agent-workspace/agent_helpers.py → 缺这个 helper
  │
  ● agent 自己写上                            agent_helpers.py
  │                                                          + 新 helper
  ✓ 文件已上传
```

**你将再也不需要自己开浏览器了。**

## 安装提示词

粘贴进 Claude Code 或 Codex：

```text
帮我配置 https://github.com/browser-use/browser-harness。

阅读 `install.md`，按步骤安装 browser-harness 并连到我的浏览器。
```

Agent 会打开 `chrome://inspect/#remote-debugging`，勾选复选框让它能连上你的浏览器：

<img src="docs/setup-remote-debugging.png" alt="Remote debugging setup" width="520" style="border-radius: 12px;" />

每次连接弹窗时点 Allow（Chrome 144+）：

<img src="docs/allow-remote-debugging.png" alt="Allow remote debugging popup" width="520" style="border-radius: 12px;" />

示例任务见 [agent-workspace/domain-skills/](agent-workspace/domain-skills/)。

## 免费的 Browser Use 云浏览器

隐身、子 agent、或无头部署。<br>
**Browser Use Cloud 免费档：3 个并发浏览器、代理、验证码自动解决等。无需绑卡。**

- 到 [cloud.browser-use.com/new-api-key](https://cloud.browser-use.com/new-api-key) 领一个 key
- 或让 agent 自己通过 [docs.browser-use.com/llms.txt](https://docs.browser-use.com/llms.txt) 注册（含注册流程 + 挑战上下文）。

## 架构（4 个核心文件，约 1k 行）

- `install.md` — 首次安装与浏览器引导
- `SKILL.md` — 日常使用
- `src/browser_harness/` — 受保护的核心包
- `agent-workspace/agent_helpers.py` — agent 编辑的 helper 代码
- `agent-workspace/domain-skills/` — agent 编辑的可复用站点技能

## 贡献

欢迎 PR 与改进。最好的贡献方式：**提交一个新的 domain skill** 到 [agent-workspace/domain-skills/](agent-workspace/domain-skills/)，针对你常用的站点或任务（LinkedIn 外联、Amazon 下单、报销填报等）。每个技能教会 agent 那些 selector、流程和坑点，省得它每次重新摸索。

- **技能由线束自己写，不是你手写。** 你只管用 agent 跑任务——当它摸索出非显而易见的规律时，它会自己归档成技能（见 [SKILL.md](SKILL.md)）。请不要手工编写技能文件；agent 生成的才反映浏览器里真正能用的东西。
- 把生成的 `agent-workspace/domain-skills/<site>/` 目录提个 PR——小而聚焦就很好。
- 同样欢迎 bug 修复、文档微调和 helper 改进。
- 浏览现有技能（`github/`、`linkedin/`、`amazon/`…）看看长什么样。

不确定从哪开始就开个 issue，我们给你指个方向。

## Domain skills

设 `BH_DOMAIN_SKILLS=1` 启用 [agent-workspace/domain-skills/](agent-workspace/domain-skills/) —— 社区贡献的、按域名由 `goto_url` 自动浮现的站点手册。欢迎提 PR。

## 小红书爬虫 Skill（xhs-crawler）

一个 Claude Code skill，批量爬取小红书笔记——搜索、提取正文+评论、下载图片、导出 Excel。

**这是 [Claude Code](https://claude.ai/code) skill**，不是独立工具。它在 Claude Code 里通过 browser-harness 的 CDP 运行。

### 它做什么

1. **搜索** —— 按任意关键词搜小红书，按瀑布流视觉顺序（左→右、上→下）读结果
2. **爬取** —— 点开每张笔记卡，提取标题、正文、帖子图片和所有评论（含嵌套回复、AI 问答摘要）
3. **下载** —— 把帖子图片和评论图片存到本地
4. **导出** —— 生成 Excel：
   - 每篇帖子一行独特色块（彩色底）
   - 评论缩进展示（↳ 回复用浅色字）
   - 图片直接嵌进单元格
   - 一个 sheet，数据全在一起

### 快速开始

```bash
# 搜索并爬 5 篇
bh <<'PY'
search_xhs("ai产品经理焦虑", limit=5)
PY

# 导出 Excel
bh <<'PY'
export_to_excel("xhs_ai_pm.xlsx")
PY
```

### 输出结构

```
Excel 单 Sheet 结构：
┌──────────┬──────────┬────────┬──────────┬──────────┐
│ 标题      │ 正文      │ 点赞数  │ 帖子图片   │ 作者      │
│ AI产品经理…│ AI产品…  │ 1234   │ [嵌入图]  │ 用户A    │ ← 帖子行（蓝底）
│  ↳ 回复    │ 好文！   │ 56     │          │ 用户B    │ ← 评论行（同蓝底）
│  ↳ 回复    │ 同感     │ 12     │ [嵌入图]  │ 用户C    │ ← 带图评论
├──────────┼──────────┼────────┼──────────┼──────────┤
│ 下一篇帖子…│ ...      │ ...    │ [嵌入图]  │ 用户D    │ ← 绿底
│ ...       │ ...      │ ...    │          │          │
└──────────┴──────────┴────────┴──────────┴──────────┘
```

### 关键特性

- **瀑布流排序** —— 5 列砌墙网格，按视觉顺序读卡
- **评论展开** —— 自动展开「展开 N 条回复」和 AI 问答摘要
- **图片嵌入** —— 帖子图和评论图直接嵌进 Excel 单元格
- **反爬限速** —— 动作间随机延迟，避免封号
- **停滞检测** —— 没有新评论加载时停止滚动（THE END）

### 文件

| 文件 | 用途 |
|------|------|
| `SKILL.md` | skill 入口 —— Claude Code 的指令 |
| `scripts/xhs_crawl.py` | 单篇爬取（pipe 给 browser-harness） |
| `scripts/xhs_export.py` | 带图片嵌入的 Excel 导出 |
| `references/selectors.md` | 所有 XHS 元素的 DOM selector 参考 |
| `references/waterfall-layout.md` | 5 列砌墙排序算法 |
| `references/gotchas.md` | 已知坑点与解法 |

### 依赖

- Claude Code
- browser-harness 已安装并连到你的浏览器
- 小红书已登录（cookies 必须有效）
- Python 3 + `openpyxl`（`pip install openpyxl`）

## 小红书媒体 Skill（xhs-media）

爬虫 skill 的搭档。爬虫从 DOM 抓**正文 + 评论**，媒体 skill 则读 `window.__INITIAL_STATE__`（服务端注入、带签名 URL）抓**原视频 + 全分辨率原图 + 头像**——并在签名 URL 还没过期时立即下载。DOM 里只有压缩缩略图，而且 `<video>` 是 blob/MSE 流，没法直接抓。

### ⚠️ 先在 Chrome 登录你自己的账号

这个 skill 通过 browser-harness 驱动**你真实、已登录的 Chrome 会话**。它从当前页面读 `__INITIAL_STATE__`，并用浏览器的 cookies 做兜底请求，所以：

- 把 browser-harness 连到你日常用的 **Google Chrome**——不是无头/一次性浏览器。
- 在那个 Chrome 里用**你自己的账号**登录小红书，并保持该会话 cookies 有效。
- 跑到一半撞到登录墙就自己登录后重试——绝不从截图里读密码输入。

### 它做什么

1. **搜索** —— 打开关键词搜索页，滚动加载瀑布流
2. **收集** —— 按（瀑布流）视觉顺序读 `.note-item` 卡片
3. **逐篇** —— 关上一篇浮窗 → 点击验证 → 读 `__INITIAL_STATE__` 拿签名 `masterUrl`、全分辨率图、头像
4. **立即下载** —— 提取到就立刻下（签名视频 URL 会过期）；视频兜底链 `masterUrl → backupUrls → 用 HTTP 重取新鲜签名`
5. **导出** —— 生成 Excel 汇总（标题、作者、类型、视频链接、图片数、头像、点赞/收藏/评论、IP、缩略图）

### 速率限制（内置，反封号）

- **笔记间随机 3–8 秒停顿**
- **下载线程池有上限** —— `XHS_WORKERS` 个并发下载（默认 3），浏览器循环与下载解耦（无 CDP 争用）
- **下载失败指数退避** —— `2^attempt` 秒
- **每 5 篇重连一次 CDP** —— 抗长会话掉线

### 快速开始

```bash
XHS_KEYWORD="北京约会" XHS_LIMIT=20 XHS_WORKERS=4 \
XHS_RUN_DIR="xhs_media_data/$(date +%Y%m%d)_北京约会" \
browser-harness < .claude/skills/xhs-media/scripts/xhs_media_batch.py
```

崩溃后续传——每篇的 JSON 都写盘做了检查点，重跑下载器只会补缺失的：

```bash
XHS_WORKERS=4 python3 .claude/skills/xhs-media/scripts/xhs_media_download.py xhs_media_data/20260619_北京约会/
```

### 文件

| 文件 | 用途 |
|------|------|
| `.claude/skills/xhs-media/SKILL.md` | skill 入口 —— Claude Code 的指令 |
| `scripts/xhs_media_extract.py` | 读 `__INITIAL_STATE__` 取媒体（PRIMARY）+ HTTP 兜底 |
| `scripts/xhs_media_batch.py` | 单会话批量驱动 + 异步下载队列 |
| `scripts/xhs_media_download.py` | 下载器（视频/原图/头像）+ 线程池 + Excel |
| `scripts/video_transcriber.py` | 可选：Groq Whisper，mp4 → txt |
| `scripts/ocr_processor.py` | 可选：OCR.space，jpg → txt |
| `references/initial-state.md` | `__INITIAL_STATE__` 字段地图 |
| `references/gotchas.md` | 11 个已知坑点 |

### 依赖

- Claude Code
- browser-harness 已安装并连到**已登录的** Chrome
- 小红书用**你自己的账号**登录（cookies 有效）
- `requests` + `openpyxl`，装进 browser-harness 自己的 Python 环境（线束跑在它自己的 uv 托管环境里，直接 `pip install` 它看不到）：
  ```bash
  uv pip install --python ~/.local/share/uv/tools/browser-harness/bin/python requests openpyxl
  ```

### 爬虫 vs. 媒体

| Skill | 数据源 | 抓什么 |
|-------|--------|--------|
| `xhs-crawler` | DOM | 正文 + 评论 |
| `xhs-media` | `__INITIAL_STATE__` | 原视频 + 全分辨率原图 + 头像 |

配合用：媒体抓文件，爬虫抓评论，最后合并。

---

[The Bitter Lesson of Agent Harnesses](https://browser-use.com/posts/bitter-lesson-agent-harnesses) · [Web Agents That Actually Learn](https://browser-use.com/posts/web-agents-that-actually-learn)
