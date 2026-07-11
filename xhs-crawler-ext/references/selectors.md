# 小红书 DOM 选择器完整参考

## 搜索结果页

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 笔记卡片容器 | `.note-item` | 每个搜索结果 |
| 笔记链接 | `a[href*="/explore/{id}"]` | `display:none`，用于定位卡片 |
| 笔记封面链接 | `a.cover.mask.ld` | 可见的封面链接 |
| 笔记标题 | `.title span` 或 `.title` | 卡片内的标题文本 |
| 笔记点赞数 | `.like-wrapper .count` | 卡片上显示的赞数 |

## 笔记详情浮层

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 浮层遮罩 | `.note-detail-mask` | `display:flex` 表示打开 |
| 笔记标题 | `#detail-title` | — |
| 笔记正文 | `#detail-desc` 或 `.desc` | `innerText` 取全文 |
| 互动栏 | `.engage-bar` 或 `[class*="engage"]` | barText: `"说点什么... {赞} {收藏} {评论} 发送 取消"` |
| 视频元素 | `video` | 存在则为视频帖 |
| 视频源 | `video source` 或 `video.src` | 通常是 `blob:` URL |
| 关闭按钮 | `.close-circle` 或 `[class*="close"]` | — |

## 轮播图（帖子图片）

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 轮播容器 | `.swiper-slide` | 每张图一个 slide |
| 当前展示图 | `.swiper-slide-active img` | 用户看到的第一张 |
| 图片元素 | `.swiper-slide img` | `src` 为图片 URL |

**顺序**：从 active slide 开始，按 slide 索引循环，去重。

## 评论区

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 评论滚动容器 | `.note-scroller` | 设 `scrollTop=scrollHeight` 触发懒加载 |
| 评论条目 | `.comment-item` | 每条评论/回复 |
| 评论总数 | `.comments-container .header` | 文本格式 `"共 N 条评论"` |
| 底部标记 | `.end-container` | 内容 `"- THE END -"`，常驻 DOM |
| 评论容器 | `.comments-container` | — |

## 评论内容

| 元素 | 选择器 | 说明 |
|------|--------|------|
| **普通评论内容** | `.note-text` | `innerText` |
| **问一问 AI 内容** | `.ai-comment-text-container` | 和 `.note-text` 并列备选 |
| **问一问 文本** | `.text-content` | 第三备选 |
| **描述性内容** | `.desc` | 第四备选 |
| 昵称 | `.name` | — |
| 时间 | `.date` | 包含时间+IP，需剥离 |
| IP 属地 | `.location` | — |
| 点赞数 | `.interactions .like .count` | 占位符"赞"=0 |
| 回复数 | `.interactions .reply .count` | 占位符"回复"=0 |
| 用户链接 | `a[href*="/user/"]` | — |

## 层级检测

| 层级 | 判断方式 |
|------|----------|
| 1级（评论） | 祖先中**没有** `.reply-container` |
| 2级（回复） | 祖先中**有** `.reply-container` |

**注意**：回复在 `.reply-container` 里，不是嵌在 `.comment-item` 里。用 `.comment-item` 祖先判断会把所有评论都判为 1 级。

## 展开按钮

| 类型 | 选择器 | 文本匹配 | 说明 |
|------|--------|----------|------|
| 普通回复展开 | `.show-more` | `/展开\d+条回复/` 或 `"展开更多回复"` | hover-gated |
| 问一问 AI 展开 | `.expand-btn` | 包含 `"展开"` | hover-gated |

**点击方式**：必须 mouseMoved + press + release（`click_at_xy` 不发 hover 会点空）。

## 用户信息

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 用户头像 | `.avatar img` 或 `img.avatar-item` | `src` 为头像 URL |
| 用户链接 | `a[href*="/user/"]` | — |
| 用户 ID | `a[data-user-id]` | — |
