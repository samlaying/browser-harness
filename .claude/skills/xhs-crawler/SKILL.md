---
name: xhs-crawler
description: |
  小红书（Xiaohongshu/RedNote）笔记搜索、评论爬取、图片下载、Excel导出。
  基于 browser-harness (CDP) 实现，处理反爬（xsec_token）、瀑布流布局排序、
  评论懒加载、回复展开、问一问AI摘要展开、帖子图片/视频检测。
  触发场景：用户提到爬取小红书、小红书评论、XHS搜索、小红书数据采集。
---

# 小红书爬虫 Skill

基于 browser-harness (CDP) 的小红书全链路数据采集：搜索 → 点击笔记 → 提取标题/正文/图片 → 滚动加载评论 → 展开回复+问一问 → 导出 Excel。

## 前提

1. browser-harness 已安装（`uv tool install -e ~/browser-harness`）
2. Chrome 已连接（`chrome://inspect` 勾选远程调试）
3. 小红书已登录

## 核心流程

### 1. 搜索

```
搜索URL: https://www.xiaohongshu.com/search_result?keyword={编码后关键词}&source=web_explore_feed
```

打开搜索页后，轮询等待卡片渲染（SPA 冷启动慢）：

```javascript
// 等待卡片出现
for (var i = 0; i < 40; i++) {
    wait_for_load();
    if (document.querySelectorAll('a[href*="/explore/"]').length > 0) break;
    sleep(0.6);
}
// 滚动加载更多卡片（瀑布流懒加载）
for (var i = 0; i < 6; i++) {
    window.scrollBy(0, 1200);
    sleep(0.8);
}
```

### 2. 瀑布流阅读顺序

搜索结果是 **5 列瀑布流**，按**肉眼从左到右、从上到下**逐排阅读：

```
排1: [x=196] [x=451] [x=706] [x=960] [x=1215]
排2: [x=196] [x=451] [x=706] [x=960] [x=1215]
...
```

**排序算法**：按 y 坐标分组（差距 < 100px 视为同一排），每排内按 x 升序。

```javascript
// 按 y→x 排序后，按 y 差距分组为"排"
items.sort((a, b) => a.y === b.y ? a.x - b.x : a.y - b.y);
var rows = [], currentRow = [], lastY = -999;
for (var i = 0; i < items.length; i++) {
    if (Math.abs(items[i].y - lastY) > 100 && currentRow.length > 0) {
        rows.push(currentRow); currentRow = [];
    }
    currentRow.push(items[i]); lastY = items[i].y;
}
if (currentRow.length > 0) rows.push(currentRow);
// 每排内按 x 排序
rows.forEach(row => row.sort((a, b) => a.x - b.x));
```

**注意**：`scrollIntoView` 会改变页面滚动位置导致坐标失效。**先取坐标，再点击，不动 scrollIntoView**。

### 3. 点击笔记卡片

**必须 click 卡片打开笔记**，不能直接 `goto /explore/{id}`（会 404，error_code=300031）。点击携带 `xsec_token` 才能通过反爬。

```javascript
// 1) 找到目标笔记卡片（通过 href 中的 ID）
var a = document.querySelector('a[href*="/explore/{NOTE_ID}"]');
var card = a;
for (var i = 0; i < 8; i++) {
    if (card.parentElement) card = card.parentElement;
    if (card.classList && card.classList.contains('note-item')) break;
}

// 2) 获取坐标（不 scrollIntoView！）
var rr = card.getBoundingClientRect();
var cx = Math.round(rr.x + rr.width / 2);
var cy = Math.round(rr.y + rr.height / 2);

// 3) 完整点击序列（hover-gated，必须 mouseMoved）
cdp("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy);
sleep(0.5);
cdp("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", clickCount=1);
cdp("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", clickCount=1);
sleep(3);
```

**关闭笔记浮窗**：点击浮窗外部空白区域（x=50, y=400）。

### 4. 帖子元信息提取

| 字段 | 选择器 | 说明 |
|------|--------|------|
| 标题 | `#detail-title` 或 `document.title` | — |
| 正文/描述 | `#detail-desc` 或 `.desc` | `innerText` 取全文 |
| 互动数据 | `.engage-bar` | barText 格式：`"说点什么... {赞} {收藏} {评论} 发送 取消"` |
| 帖子类型 | `video` 元素是否存在 | 有则为视频帖 |

```javascript
var title = (document.querySelector("#detail-title") || {}).textContent || document.title;
var descEl = document.querySelector("#detail-desc, .desc");
var desc = descEl ? descEl.innerText.replace(/\s+/g, " ").trim() : "";
var bar = document.querySelector('.engage-bar, [class*="engage"]');
var barText = bar ? bar.innerText.replace(/\s+/g, ' ').trim() : "";
// barText 中的数字顺序：赞、收藏、评论
var hasVideo = !!document.querySelector('video');
```

### 5. 帖子图片提取（轮播图）

**图片顺序**：按 active slide 顺序提取（用户看到的第一张是 active slide，不是 DOM 第一张）。

```javascript
var slides = document.querySelectorAll('.swiper-slide');
var active = document.querySelector('.swiper-slide-active img');
var activeSrc = active ? active.src : '';

// 去重并按 active 顺序排列
var all = [], seen = {};
slides.forEach(function(s) {
    var img = s.querySelector('img');
    if (!img) return;
    var src = img.src || '';
    if (!src || seen[src]) return;
    seen[src] = true;
    all.push(src);
});
var startIdx = all.indexOf(activeSrc);
if (startIdx < 0) startIdx = 0;
var ordered = [];
for (var i = 0; i < all.length; i++) {
    ordered.push(all[(startIdx + i) % all.length]);
}
// ordered 就是用户看到的图片顺序
```

**视频帖**：视频源是 `blob:` URL（MSE 流媒体），无法直接下载 mp4。标记为视频帖即可。

### 6. 评论滚动加载

评论容器 `.note-scroller` 使用 `IntersectionObserver` 懒加载，**直接设 `scrollTop` 就能触发**（和抖音不同，抖音只认真实按键）。

```javascript
var last = 0, stall = 0;
for (var round = 0; round < 60; round++) {
    var s = document.querySelector(".note-scroller");
    if (s) s.scrollTop = s.scrollHeight;
    sleep(random(0.8, 1.2));
    var c = document.querySelectorAll(".comment-item").length;
    if (c === last) stall++;
    else { stall = 0; last = c; }
    if (stall >= 5) break;  // 连续5轮无增长 = 到底
}
```

**停止条件**：连续 5 轮评论数不变。底部有 `- THE END -`（`.end-container`），但它常驻 DOM，靠 stall 判定更可靠。

### 7. 展开回复引擎

展开按钮需要 **hover 才响应**（`click_at_xy` 不发 hover 会点空），必须用完整序列 mouseMoved + press + release。

```javascript
// 同时处理两种展开按钮
function findExpandBtn() {
    var best = null, bestY = Infinity;

    // 1) 普通回复展开：.show-more
    var showMores = document.querySelectorAll('.show-more');
    for (var i = 0; i < showMores.length; i++) {
        var el = showMores[i];
        var t = el.textContent.trim();
        if (!/展开/.test(t) && !/查看/.test(t)) continue;
        var r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        if (r.y < bestY) {
            bestY = r.y;
            best = { t: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2) };
        }
    }

    // 2) 问一问 AI 摘要展开：.expand-btn
    var expandBtns = document.querySelectorAll('.expand-btn');
    for (var i = 0; i < expandBtns.length; i++) {
        var el = expandBtns[i];
        var t = el.textContent.trim();
        if (t.indexOf('展开') < 0) continue;
        var r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        if (r.y < bestY) {
            bestY = r.y;
            best = { t: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2) };
        }
    }

    return best;
}

// 循环展开直到没有按钮
while (true) {
    var btn = findExpandBtn();
    if (!btn) break;
    // hover + click
    cdp("Input.dispatchMouseEvent", type="mouseMoved", x: btn.x, y: btn.y);
    sleep(0.35);
    cdp("Input.dispatchMouseEvent", type: "mousePressed", x: btn.x, y: btn.y, button: "left", clickCount: 1);
    cdp("Input.dispatchMouseEvent", type: "mouseReleased", x: btn.x, y: btn.y, button: "left", clickCount: 1);
    sleep(1.5);
}
```

### 8. 评论提取

#### 选择器一览

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 评论容器 | `.comment-item` | 每条评论/回复 |
| 层级检测 | 祖先有无 `.reply-container` | 有=回复(2级)，无=评论(1级) |
| 昵称 | `.name` | — |
| 普通评论内容 | `.note-text` | `innerText` |
| **问一问 AI 内容** | `.ai-comment-text-container` 或 `.text-content` 或 `.desc` | 和 `.note-text` 并列备选 |
| 时间 | `.date` | 包含时间+IP，需剥离 IP |
| IP 属地 | `.location` | 从 `.date` 文本中减去 |
| 点赞数 | `.interactions .like .count` | 占位符"赞"=0 |
| 回复数 | `.interactions .reply .count` | 占位符"回复"=0 |
| 用户链接 | `a[href*="/user/"]` | — |

#### 提取代码

```javascript
var out = [];
document.querySelectorAll(".comment-item").forEach(function(it) {
    try {
        // 层级
        var p = it.parentElement, lvl = 1;
        while (p) {
            if (p.classList && p.classList.contains("reply-container")) { lvl = 2; break; }
            p = p.parentElement;
        }

        // 昵称
        var nick = (it.querySelector(".name") || {}).textContent || "";
        nick = nick.replace(/\s+/g, " ").trim();

        // 内容（同时兼容普通评论和问一问AI）
        var contentEl = it.querySelector(".note-text")
            || it.querySelector(".ai-comment-text-container")
            || it.querySelector(".text-content")
            || it.querySelector(".desc");
        var content = contentEl ? (contentEl.innerText || "").replace(/\s+/g, " ").trim() : "";

        // 时间 & IP
        var locEl = it.querySelector(".location");
        var ip = locEl ? (locEl.textContent || "").replace(/\s+/g, " ").trim() : "";
        var dateEl = it.querySelector(".date");
        var dateText = "";
        if (dateEl) {
            var d = (dateEl.textContent || "").replace(/\s+/g, " ").trim();
            dateText = ip ? d.replace(ip, "").trim() : d;
        }

        // 互动数据
        function cnt(sel) {
            var e = it.querySelector(sel);
            if (!e) return "0";
            var t = (e.textContent || "").replace(/\s+/g, "").trim();
            return /^\d+$/.test(t) ? t : "0";
        }
        var likes = cnt(".interactions .like .count") || cnt(".like .count");
        var replies = cnt(".interactions .reply .count") || cnt(".reply .count");

        // 评论图片（排除头像和表情包）
        var imgs = [];
        it.querySelectorAll("img").forEach(function(img) {
            var src = img.src || "";
            var cls = img.className || "";
            if (src && src.indexOf("avatar") < 0 && cls.indexOf("emoji") < 0) imgs.push(src);
        });

        if (nick || content) out.push({
            lvl: lvl, nick: nick, content: content,
            date: dateText, ip: ip, likes: likes, replies: replies, imgs: imgs
        });
    } catch(e) {}
});
```

#### 线程关系构建

```javascript
// 建立 thread_id 和 reply_to
var thread_id = 0, current_thread = 0;
for (var item of data) {
    if (item.lvl === 1) {
        thread_id++;
        current_thread = thread_id;
        item.thread_id = thread_id;
        item.reply_to = '';
    } else {
        item.thread_id = current_thread;
        item.reply_to = '';
    }
}
// 识别回复对象：向上找最近的非自己昵称
for (var i = 0; i < data.length; i++) {
    if (data[i].lvl === 2) {
        for (var j = i - 1; j >= 0; j--) {
            if (data[j].nick !== data[i].nick) {
                data[i].reply_to = data[j].nick;
                break;
            }
        }
    }
}
```

### 9. 评论图片下载

```javascript
// 过滤条件：排除头像(avatar)和表情包(emoji class)
it.querySelectorAll("img").forEach(function(img) {
    var src = img.src || "";
    var cls = img.className || "";
    if (src && src.indexOf("avatar") < 0 && cls.indexOf("emoji") < 0) imgs.push(src);
});
```

下载时带 Referer 头：

```python
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://www.xiaohongshu.com/'
})
```

### 10. Excel 导出（含嵌入图片）

使用 `openpyxl`，图片用 `OneCellAnchor` 绑定单元格（随单元格移动）。

**关键**：帖子多图时，每张图独占一行，设行高避免重合。

```python
from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils.units import pixels_to_EMU

# 图片绑定单元格
img.anchor = OneCellAnchor(
    _from=AnchorMarker(col=6, colOff=0, row=row-1, rowOff=0),
    ext=XDRPositiveSize2D(pixels_to_EMU(80), pixels_to_EMU(80)),
)
ws.add_image(img)

# 帖子多图：每张独占一行
ws.row_dimensions[row].height = IMG_HEIGHT * 0.75  # points
```

### 11. 完整单篇爬取流程

```
1. 回到搜索页（不刷新，保持已加载的卡片）
2. 关闭浮窗（点击 x=50, y=400）
3. 定位目标卡片 → getBoundingClientRect → hover+click
4. 等待评论加载（轮询 .comment-item）
5. 获取元信息（标题、描述、互动数据、帖子类型）
6. 滚动加载一级评论（.note-scroller scrollTop，stall 判定）
7. 展开引擎（.show-more + .expand-btn，循环直到无按钮）
8. 提取评论（.note-text || .ai-comment-text-container）
9. 构建线程关系（thread_id, reply_to）
10. 下载图片（帖子图按 active 顺序，评论图过滤头像/表情包）
11. 导出 Excel（两个 Sheet：帖子信息 + 评论，图片 OneCellAnchor）
```

## 已知限制

- **视频下载**：blob URL (MSE)，无法直接获取 mp4
- **评论图片**：只提取内容图，表情包（`note-content-emoji` class）忽略
- **问一问内容**：AI 生成的帖子摘要，长度有限（~140字）
- **反爬**：笔记必须从搜索结果点击打开，直接 goto 会 404

## 参考

- 选择器详细列表：[selectors.md](references/selectors.md)
- 瀑布流布局详解：[waterfall-layout.md](references/waterfall-layout.md)
- 已知坑点：[gotchas.md](references/gotchas.md)
