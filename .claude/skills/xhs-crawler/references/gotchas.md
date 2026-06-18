# 小红书爬虫已知坑点

## 1. 反爬：必须点击卡片打开笔记

**问题**：直接 `goto_url("https://www.xiaohongshu.com/explore/{id}")` 会返回 404（error_code=300031，"当前笔记暂时无法浏览"）。

**原因**：笔记 URL 需要 `xsec_token` 参数，这个 token 只有从搜索结果页点击卡片时才会携带。

**解决**：永远从搜索结果页点击卡片打开笔记，不直接跳转。

## 2. scrollIntoView 导致坐标偏移

**问题**：使用 `scrollIntoView({block:"center"})` 后再取 `getBoundingClientRect()`，坐标会因为页面滚动而变化，导致点错位置。

**表现**：点击笔记卡片时可能点到用户头像、跳转到创作者页面 (`creator.xiaohongshu.com`) 等。

**解决**：先取坐标，再点击。不要在取坐标前调用 `scrollIntoView`。如果需要滚动到可见区域，用 `window.scrollTo` 代替。

```javascript
// ❌ 错误：scrollIntoView 改变了位置
card.scrollIntoView({block:"center"});
var rr = card.getBoundingClientRect();  // 坐标已变
click(rr.x, rr.y);

// ✅ 正确：直接取坐标
var rr = card.getBoundingClientRect();
click(rr.x, rr.y);
```

## 3. 展开按钮需要 hover

**问题**：`click_at_xy` 不发 `mouseMoved` 事件，小红书的展开按钮（`.show-more`，311×32）是 hover-gated，不 hover 就点空。

**解决**：用完整的 trusted event 序列：

```javascript
cdp("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy);
sleep(0.35);
cdp("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", clickCount=1);
cdp("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", clickCount=1);
```

同样的问题也适用于：抖音按钮、小红书关注按钮等 React 站点。

## 4. 评论层级判断

**问题**：用 `.comment-item` 祖先判断层级会把所有评论都判为 1 级。

**原因**：小红书的回复在 `.reply-container` 里，是 `.comment-item` 的**兄弟节点**，不是子节点。

**正确判断**：检查祖先中是否有 `.reply-container`。

```javascript
var p = it.parentElement, lvl = 1;
while (p) {
    if (p.classList && p.classList.contains("reply-container")) {
        lvl = 2;
        break;
    }
    p = p.parentElement;
}
```

## 5. 问一问 AI 摘要内容选择器

**问题**：问一问（AI 生成的帖子摘要）的内容不在 `.note-text` 里，提取为空。

**原因**：问一问使用独立的 DOM 结构。

**解决**：用多个选择器并列备选：

```javascript
var contentEl = it.querySelector(".note-text")
    || it.querySelector(".ai-comment-text-container")
    || it.querySelector(".text-content")
    || it.querySelector(".desc");
```

问一问的展开按钮是 `.expand-btn`（不是 `.show-more`），需要单独处理。

## 6. 图片顺序：active slide 才是第一张

**问题**：轮播图的 DOM 顺序不等于用户看到的顺序。循环轮播（loop mode）会复制 slide，DOM 第一张可能不是用户看到的第一张。

**解决**：从 `.swiper-slide-active` 开始，按 slide 索引循环提取，去重。

```javascript
var activeSrc = document.querySelector('.swiper-slide-active img').src;
// 找 active 在去重列表中的位置，从那里开始循环
```

## 7. 图片下载需要 Referer 头

**问题**：直接请求图片 URL 会被拒绝（403）。

**解决**：下载时带 Referer 头：

```python
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://www.xiaohongshu.com/'
})
```

## 8. Excel 图片必须用 OneCellAnchor

**问题**：`ws.add_image(img, 'G5')` 用绝对定位，图片不随单元格移动。

**解决**：用 `OneCellAnchor` + `AnchorMarker` + `XDRPositiveSize2D`：

```python
img.anchor = OneCellAnchor(
    _from=AnchorMarker(col=6, colOff=0, row=row-1, rowOff=0),
    ext=XDRPositiveSize2D(pixels_to_EMU(80), pixels_to_EMU(80)),
)
```

## 9. 视频帖无法下载视频

**问题**：视频源是 `blob:` URL（MSE 流媒体），没有直接的 mp4 链接。

**现状**：只能提取标题、描述、评论，无法下载视频文件。

## 10. THE END 标记常驻 DOM

**问题**：`.end-container`（内容 `"- THE END -"`）始终存在于 DOM 中，不能靠"在 DOM 中？"判断到底。

**解决**：靠**连续 5 轮评论数不变**（stall）判定到底。效果等价。

## 11. 浮窗未关闭就点下一篇 → 重复爬取

**问题**：关闭浮窗后没验证 mask 消失就点击下一篇，实际浮窗还在，点到了同一篇笔记。

**解决**：关闭浮窗后轮询验证 `mask.display === 'none'`：

```python
def wait_mask_gone(timeout=5):
    for _ in range(int(timeout / 0.3)):
        d = js('return document.querySelector(".note-detail-mask") ? getComputedStyle(document.querySelector(".note-detail-mask")).display : "none";')
        if d == 'none': return True
        sleep(0.3)
    return False
```

## 12. 搜索页被当成笔记卡片

**问题**：搜索页的某些元素也包含 `/explore/` 链接，被误识别为笔记卡片，导致点开的是搜索页本身。

**解决**：卡片必须是 `.note-item` 的子元素：

```javascript
var card = a;
for (var i = 0; i < 8; i++) {
    if (card.parentElement) card = card.parentElement;
    if (card.classList && card.classList.contains('note-item')) break;
}
// 必须验证最终找到的是 .note-item
if (!card.classList || !card.classList.contains('note-item')) return null;
```

## 13. 两趟跑效率低且容易出错

**问题**：先提取 20 篇的标题/描述，再逐篇回去取评论。两次打开同一篇笔记，浪费时间且丢失状态。

**解决**：一趟跑完。点击打开笔记后一次性提取：标题 + 描述 + 互动数据 + 帖子图片 + 评论滚动 + 展开 + 评论提取。

## 14. 卡片滚出视口点不到

**问题**：滚动加载更多卡片后，前面的卡片 y 坐标为负数（在视口上方），点击失败。

**解决**：点击前 `window.scrollTo(0, 0)` 回到顶部，确保卡片在视口内，然后重新 `getBoundingClientRect` 取坐标。

## 15. 批量爬取速度过快被封

**问题**：连续快速点击笔记，触发反爬检测。

**解决**：5 个控制点随机延迟（详见 SKILL.md 速度控制表）。笔记间 3~8s + 15% 概率额外等待 5~10s。

## 16. browser-harness 长会话掉线

**问题**：单次 browser-harness 调用超过 ~2 分钟可能 CDP 断连。

**解决**：每篇笔记一次独立调用，用 `safe_js`/`safe_cdp` 包装，异常时 `ensure_daemon(); ensure_real_tab()` 重连。

```python
def safe_js(s):
    try:
        return js(s)
    except Exception:
        ensure_daemon()
        ensure_real_tab()
        time.sleep(1.0)
        try:
            return js(s)
        except Exception:
            return None
```
