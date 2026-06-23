---
name: xhs-crawler
description: |
  小红书（Xiaohongshu/RedNote）笔记搜索、评论爬取、图片下载、Excel 导出。
  基于 browser-harness (CDP) 实现。处理反爬（xsec_token 必须 click 卡片）、
  5列瀑布流排序、评论懒加载、回复展开、问一问 AI 摘要展开、帖子图片下载。
  触发：用户提到爬取小红书、小红书评论、XHS 搜索、小红书数据采集、批量爬取小红书。
compatibility: browser-harness, openpyxl
---

# 小红书爬虫 Skill

搜索 → 点击笔记 → 一趟提取全部（标题/正文/图片/评论） → 下载图片 → 导出 Excel。

## 前提

1. browser-harness 已安装（`uv tool install -e ~/browser-harness`）
2. Chrome 已连接（`chrome://inspect` 勾选远程调试）
3. 小红书已登录
4. openpyxl 已安装（`pip install openpyxl`）

## 批量爬取流程

### Step 1: 打开搜索页

```
URL: https://www.xiaohongshu.com/search_result?keyword={编码关键词}&source=web_explore_feed
```

轮询等待卡片渲染（SPA 冷启动慢），然后 `window.scrollBy(0, 1200)` 滚动 6 次加载更多卡片。

### Step 2: 收集卡片（去重 + 排序）

收集所有 `.note-item` 内的 `a[href*="/explore/"]`，按 ID 去重。不足目标数量则继续滚动加载。

**排序**：5 列瀑布流，按 y 分组（差距 <100px = 同排），每排内按 x 升序。详见 [waterfall-layout.md](references/waterfall-layout.md)。

### Step 2.5: 创建本次爬取目录

每次爬取用独立子目录，防止旧数据混入：

```bash
mkdir -p xhs_data/$(date +%Y%m%d)_{关键词简写}
```

所有 JSON 保存到这个子目录。导出 Excel 时也指定这个目录。

### Step 3: 一趟跑完（关键！）

**直接运行自包含编排脚本 `scripts/xhs_batch.py`，不再手写循环。**

```bash
XHS_KEYWORD="咖啡" XHS_TARGET=20 \
  browser-harness < .claude/skills/xhs-crawler/scripts/xhs_batch.py
```

环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `XHS_KEYWORD` | 必填 | 搜索词 |
| `XHS_TARGET` | 20 | 目标篇数 |
| `XHS_OUTDIR` | `xhs_data/{date}_{keyword}` | 输出子目录 |
| `XHS_MAX_RETRY` | 2 | 单篇重试次数 |

**为什么必须在一个 browser-harness 会话里跑**：小红书是 SPA，重新导航到搜索页会导致卡片不渲染（gotcha #16）。脚本在会话首次 `new_tab` 到搜索页后，全程留在该页操作（关浮窗 → 点下一篇），中途不重新导航。

**脚本内置健壮性**（详见 scripts/xhs_batch.py 函数注释）：
- **断点续爬**：每篇成功即写 `{id}.json` + 更新 `state.json`。重跑自动跳过已完成（state.json 的 done ∪ 磁盘已存 JSON 双保险）。
- **单篇重试**：提取失败（无标题）→ 关浮窗重点同卡，最多 `XHS_MAX_RETRY` 次，仍失败记入 `state.json.failed`。
- **增量落盘**：先写笔记 JSON 再写 state，崩溃不丢已爬。
- **连接健康检查**：每 5 篇心跳，掉线由 `safe_js`/`safe_cdp` 自动重连。

实现细节（函数级）见 `scripts/xhs_batch.py`；坑点见 `references/gotchas.md`。

### Step 4: 导出 Excel

执行 `scripts/xhs_export.py`，读取所有 JSON → 合并 → 下载图片 → 生成 Excel。

## 点击验证（重要！）

点击卡片前必须用 `elementFromPoint(x, y)` 检查目标元素：

| 检查项 | 说明 |
|--------|------|
| `isCard` | 向上找 `.note-item` 祖先，必须存在 |
| `bad` | 文本包含"发布"、"下载APP"、"登录"、"注册" |
| `chain` | 打印元素链，方便调试点击偏移问题 |

如果验证失败：
- 打印 `⚠ 跳过: 坐标(x,y) → 原因`
- 不执行点击
- 继续下一篇

Retina 屏（devicePixelRatio=2）可能导致坐标偏移。优先用 `elementFromPoint` 验证而非盲目点击。

## 反爬要点

| 规则 | 说明 |
|------|------|
| **必须 click 卡片** | 直接 goto `/explore/{id}` 会 404（xsec_token） |
| **不 scrollIntoView 取坐标** | 会改变位置导致点错 |
| **hover + click** | 展开按钮 hover-gated，必须 mouseMoved |
| **关闭后验证** | mask != 'none' 时不能点下一篇 |
| **速度随机** | 笔记间 3~8s + 15% 概率长停顿 |
| **不重新导航** | SPA 不会重新渲染卡片，必须留在搜索页操作 |

## 速度控制（防封）

| 控制点 | 延迟 | 说明 |
|--------|------|------|
| 笔记间 | 3~8s + 15%概率额外 5~10s | 模拟浏览列表 |
| 开帖后 | 2~4s | 等渲染 |
| 评论滚动 | 1~2s | 模拟滚轮 |
| 展开点击 | 1.5~3s | 模拟阅读 |
| 关闭浮窗 | 0.5~1s | 等动画 |

## 选择器速查

| 元素 | 选择器 |
|------|--------|
| 卡片容器 | `.note-item` |
| 笔记链接 | `a[href*="/explore/{id}"]` |
| 浮窗遮罩 | `.note-detail-mask` |
| 标题 | `#detail-title` |
| 正文 | `#detail-desc` / `.desc` |
| 互动栏 | `.engage-bar` |
| 评论条目 | `.comment-item` |
| 评论内容 | `.note-text` |
| 问一问 AI | `.ai-comment-text-container` / `.text-content` |
| 层级 | 祖先 `.reply-container` = 回复 |
| 展开(回复) | `.show-more` |
| 展开(AI) | `.expand-btn` |
| 轮播图 | `.swiper-slide img` |
| active 图 | `.swiper-slide-active img` |

完整选择器列表：[selectors.md](references/selectors.md)

## 已知限制

- **视频**：blob URL，无法下载 mp4
- **评论图片**：表情包（`note-content-emoji`）忽略，只提取内容图
- **问一问**：AI 摘要，长度有限（~140字）
- **CDP 长时间运行**：10+ 分钟可能断连，每 5 篇检查一次连接

## 参考

- 选择器详细列表：[selectors.md](references/selectors.md)
- 瀑布流排序算法：[waterfall-layout.md](references/waterfall-layout.md)
- 已知坑点：[gotchas.md](references/gotchas.md)
