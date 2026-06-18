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

## 批量爬取流程（10 步）

执行入口：`scripts/xhs_crawl.py`（单篇）+ `scripts/xhs_export.py`（导出）。

### Step 1: 打开搜索页

```
URL: https://www.xiaohongshu.com/search_result?keyword={编码关键词}&source=web_explore_feed
```

轮询等待卡片渲染（SPA 冷启动慢），然后 `window.scrollBy(0, 1200)` 滚动 6 次加载更多卡片。

### Step 2: 收集卡片（去重 + 排序）

收集所有 `.note-item` 内的 `a[href*="/explore/"]`，按 ID 去重。不足目标数量则继续滚动加载。

**排序**：5 列瀑布流，按 y 分组（差距 <100px = 同排），每排内按 x 升序。详见 [waterfall-layout.md](references/waterfall-layout.md)。

### Step 3: 逐篇爬取（一趟跑完）

每篇笔记一次独立的 `browser-harness` 调用。流程：

```
关闭浮窗 → 验证 mask=none → 确保卡片在视口 → hover+click → 等评论出现
→ 提取元信息（标题/描述/互动/类型）+ 提取帖子图片
→ 滚动加载评论（stall 判定） → 展开引擎（.show-more + .expand-btn）
→ 提取全部评论 → 下载图片 → 保存 JSON
```

**一趟跑完**：打开笔记后一次性提取所有数据，不分开两趟。

### Step 4: 导出 Excel

执行 `scripts/xhs_export.py`，读取所有 JSON → 合并 → 下载图片 → 生成 Excel。

**Excel 结构**：单 Sheet，帖子标题行（彩色底色 + 帖子图片）→ 评论行缩进，同帖同色。

## 反爬要点

| 规则 | 说明 |
|------|------|
| **必须 click 卡片** | 直接 goto `/explore/{id}` 会 404（xsec_token） |
| **不 scrollIntoView 取坐标** | 会改变位置导致点错 |
| **hover + click** | 展开按钮 hover-gated，必须 mouseMoved |
| **关闭后验证** | mask != 'none' 时不能点下一篇 |
| **速度随机** | 笔记间 3~8s + 15% 概率长停顿 |

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

## 参考

- 选择器详细列表：[selectors.md](references/selectors.md)
- 瀑布流排序算法：[waterfall-layout.md](references/waterfall-layout.md)
- 已知坑点：[gotchas.md](references/gotchas.md)
