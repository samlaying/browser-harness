---
name: xhs-media
description: |
  小红书全方位媒体下载：原视频 mp4（无水印签名源）+ 全分辨率原图 + 头像。
  基于 browser-harness (CDP)，点击卡片打开笔记后读取 window.__INITIAL_STATE__.note.noteDetailMap
  拿到 DOM 里没有的 masterUrl（视频）和原图地址，当篇立即下载到独立文件夹，并生成媒体汇总 Excel。
  与 xhs-crawler 互补：xhs-crawler 管文本/评论，xhs-media 管原视频/原图/头像。
  触发：下载小红书视频、小红书原图、小红书头像、小红书全方位采集、批量下载小红书笔记媒体。
compatibility: browser-harness, requests, openpyxl
---

# 小红书媒体下载 Skill（xhs-media）

搜索 → 点击笔记 → 读 `__INITIAL_STATE__` 拿原视频/原图/头像 → 当篇立即下载 → 汇总 Excel。

**和 xhs-crawler 的分工**：xhs-crawler 抓**文本+评论**（DOM）；xhs-media 抓**原视频+原图+头像**（`__INITIAL_STATE__`）。要同时拿评论和媒体，两个 skill 配合用——xhs-media 下媒体，xhs-crawler 下评论，最后合并。

## 为什么需要这个 skill

xhs-crawler 只能从 DOM 抓**压缩缩略图**，且**下不了视频**（`<video>` 是 blob/MSE）。`__INITIAL_STATE__` 里有服务端注入的**签名 mp4 直链**和**全分辨率原图**——这个 skill 专门读它。

## 前提

1. browser-harness 已安装（`uv tool install -e ~/browser-harness`），Chrome 已连接且**已登录**小红书
2. `requests`、`openpyxl` 已装（`pip install requests openpyxl`）
3. 可选后处理：`GROQ_API_KEY`（视频转写）、`OCR_SPACE_API_KEY`（图片 OCR）

## 数据来源（两条路径）

| 路径 | 触发 | 做法 |
|------|------|------|
| **PRIMARY** | 默认 | 浮窗打开后，浏览器里 `window.__INITIAL_STATE__.note.noteDetailMap` 已含当前笔记全数据（含 masterUrl）。`js()` 在浏览器内只抠媒体字段、return 小对象。详见 [references/initial-state.md](references/initial-state.md) |
| **FALLBACK** | PRIMARY 字段空时 | 用 `xsecToken` + 浏览器 cookies（`cdp("Network.getAllCookies")`）服务端 GET 笔记页 HTML，正则解析 `__INITIAL_STATE__`。两条路径共用 `normalize_note()` 映射 |

## 批量流程

### Step 1：打开搜索页（同 xhs-crawler）

```
https://www.xiaohongshu.com/search_result?keyword={编码关键词}&source=web_explore_feed
```

脚本自动 `window.scrollBy(0,1200)` ×6 加载更多卡片。

### Step 2：收集卡片（5列瀑布流排序，复用 xhs-crawler）

收集 `.note-item` 内 `a[href*="/explore/"]`，去重，按 y 分组（差距<100px 同排）、排内按 x 升序——肉眼阅读顺序。算法见 xhs-crawler 的 [waterfall-layout.md](../xhs-crawler/references/waterfall-layout.md)。

### Step 2.5：建本次目录

```bash
mkdir -p xhs_media_data/$(date +%Y%m%d)_{关键词简写}
```

所有下载落这个目录。每篇一个子文件夹。

### Step 3：单会话循环（关键！爬取与下载解耦）

```bash
XHS_KEYWORD="关键词" XHS_LIMIT=10 XHS_WORKERS=3 \
XHS_RUN_DIR="xhs_media_data/20260618_关键词" \
browser-harness < scripts/xhs_media_batch.py
```

**必须单个 browser-harness 会话**完成（SPA 不重新导航，继承 xhs-crawler #16）。

**异步架构（生产者-消费者）**：浏览器循环只做提取，下载丢给后台线程池——下载不再阻塞爬取。

```
浏览器循环(生产者，单CDP会话，串行)        下载线程池(N=XHS_WORKERS 个worker)
  关闭上一篇浮窗                            while task=queue.get():
  点击前验证 elementFromPoint                 video→masterUrl,失败换backupUrls
  等浮窗开 + noteId 进 __INITIAL_STATE__       →还失败用cookies重取新鲜URL(fetch_via_http)
  extract_media 读 __INITIAL_STATE__         images/avatar 并发下
  ① 写 {noteId}.json 到盘(崩溃检查点) ──┐    写文件夹+笔记信息.json
  ② 入队 DownloadTask(含cookies快照) ───┴─→ 结果按index排序入results
  立即下一篇(不等下载)                      
循环结束 → pool.join() 等队列排空 → build_excel(results)
```

每篇浏览器侧步骤：

1. 关闭上一篇浮窗（`.close-circle` hover+click → `wait_mask_gone`）
2. 点击前验证 `elementFromPoint`（防误触"发布"，Retina 偏移，继承 #17）
3. 等浮窗打开 + `noteId` 进入 `__INITIAL_STATE__`
4. **媒体优先**：`extract_media` 读 `__INITIAL_STATE__` 拿 masterUrl/原图/头像
5. ① **写 `{noteId}.json` 到盘**（崩溃检查点，进程挂了也能续传）
6. ② **入队下载**（非阻塞，立即下一篇）——worker 只做 requests I/O，不碰 js/cdp，无 CDP 争用
7. 笔记间 3~8s 随机停顿；每 5 篇 `ensure_daemon`+`ensure_real_tab` 重连（#9）

**视频下载兜底链**（worker 内）：`masterUrl` → 失败换 `backupUrls[]` → 还失败用入队时快照的 cookies 调 `fetch_via_http(noteId, xsecToken)` 重取**新鲜签名 URL** 再下（cookies 会话期内有效）。

### Step 4：汇总 Excel

循环结束自动生成 `xhs_media_*.xlsx`：一行一篇（标题/作者/类型/视频路径超链接/图片数/头像/点赞/收藏/评论/IP/首图缩略图）。也可单独跑：

```bash
python3 scripts/xhs_media_download.py xhs_media_data/20260618_关键词/
```

### 续传/恢复

进程崩了或中断？每篇 extract 后都写了 `{noteId}.json` 检查点，重跑下载器即可恢复——`download_url` 跳过已存在文件，只补缺失的：

```bash
XHS_WORKERS=4 python3 scripts/xhs_media_download.py xhs_media_data/20260618_关键词/
```

（视频签名 URL 若已过期，续传模式下没有浏览器 cookies 重取，会改用 `backupUrls`；实在下不到的需重跑 batch。）

## 输出结构

```
xhs_media_data/20260618_关键词/
├── 001_标题前缀_a1b2c3d4/
│   ├── 视频_a1b2c3d4.mp4          # 视频笔记
│   ├── 图片_01.jpg, 图片_02.jpg …  # 图文笔记的原图（全分辨率）
│   ├── 头像_昵称.jpg
│   └── 笔记信息.json               # 全部字段 + downloaded_files[]
├── 002_…/
├── {noteId}.json                   # 每篇原始媒体 JSON（供 Excel/合并用）
└── xhs_media_20260618_HHMMSS.xlsx  # 媒体汇总表
```

## 复用 xhs-crawler（不 import，逐字复制）

`xhs_media_batch.py` 顶部标 `SYNC` 的 helper（`safe_js`/`safe_cdp`/`jitter`/`verify_click_target`/`click_card_with_verify`/`wait_mask_gone`）**逐字复制**自 `xhs-crawler/scripts/xhs_crawl.py`。

为什么复制不 import：① import `xhs_crawl` 会触发它 module-level 的爬取（它无 `__main__` 守卫）；② harness exec 时 `__name__!='__main__'`，守卫语义不同。详见 [references/gotchas.md](references/gotchas.md) #10、#11。**改这些函数要同步回 `xhs_crawl.py`**。

## 关键坑点

完整列表见 [references/gotchas.md](references/gotchas.md)，最关键的：

- **签名 URL 过期**：`masterUrl` 含 `?sign=&t=`，当篇立即下，Referer=`https://www.xiaohongshu.com/`；失败换 `backupUrls`。
- **取 `video.media.stream.h264[0].masterUrl`**，不是 `consumer.originVideoKey`（实测不存在）。
- **`js()` 只 return 小对象**：`__INITIAL_STATE__` 整包很大，整包 return 爆 "chain too long"。
- **xsec_token 只能 click 卡片获得**，不能直接 goto `/explore/{id}`（404）。
- **blob 视频**只能从 `__INITIAL_STATE__` 拿，不能从 `<video>` 抓。

## 可选后处理（非强制依赖）

下载完成后，可对媒体做文字提取。脚本复制自 `redbook-download/`，主下载路径**不调用**它们：

### 视频转写（Groq Whisper）

```bash
export GROQ_API_KEY='...'
python3 scripts/video_transcriber.py xhs_media_data/20260618_关键词/001_*/
# → 生成 视频_{noteId}.txt（>25MB 自动用 ffmpeg 切 5 分钟）
```

### 图片 OCR（OCR.space）

```bash
export OCR_SPACE_API_KEY='...'   # 不设则用免费 demo key
python3 scripts/ocr_processor.py xhs_media_data/20260618_关键词/001_*/
# → 生成 图片_NN.txt（跳过头像）
```

## 文件

| 文件 | 用途 |
|------|------|
| `scripts/xhs_media_extract.py` | 读 `__INITIAL_STATE__` 取媒体字段（PRIMARY）+ HTTP fallback；cookies 拆分；可 pipe 单篇、可 import |
| `scripts/xhs_media_batch.py` | 单会话批量驱动（点击/验证/关闭复制自 xhs_crawl）+ 异步入队 + 重取兜底 worker |
| `scripts/xhs_media_download.py` | 下载器（视频/原图/头像）+ `DownloadPool` 线程池 + 汇总 Excel；纯 CLI，可续传 |
| `scripts/video_transcriber.py` | 可选：Groq Whisper，mp4→txt |
| `scripts/ocr_processor.py` | 可选：OCR.space，jpg→txt |
| `references/initial-state.md` | `__INITIAL_STATE__` 字段地图（实测校验） |
| `references/gotchas.md` | 11 个已知坑点 |

## 已知限制

- 视频是**有水印**的 `h264` 流源（`originVideoKey` 无水印源在实测里拿不到）；如需无水印需另寻接口。
- 评论区不在这个 skill 范围（用 xhs-crawler）。
- 视频转写受 Groq 25MB/5min 限制（仅转写阶段，下载不受限）。
- CDP 长 session 每 5 篇重连一次。

## 参考

- [`__INITIAL_STATE__` 字段地图](references/initial-state.md)
- [已知坑点](references/gotchas.md)
- xhs-crawler 的 [选择器](../xhs-crawler/references/selectors.md) / [瀑布流排序](../xhs-crawler/references/waterfall-layout.md)（点击/卡片部分复用）
