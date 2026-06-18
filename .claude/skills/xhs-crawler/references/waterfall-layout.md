# 小红书瀑布流布局详解

## 布局结构

搜索结果页是 **5 列瀑布流**（Masonry Layout），每列宽度约 223px，列间距约 30px。

列的 x 坐标大约为：`196, 451, 706, 960, 1215`

```
     列1(x=196)  列2(x=451)  列3(x=706)  列4(x=960)  列5(x=1215)
排1: [卡片1]     [卡片2]     [卡片3]     [卡片4]     [卡片5]
排2: [卡片6]     [卡片7]     [卡片8]     [卡片9]     [卡片10]
排3: [卡片11]    [卡片12]    [卡片13]    [卡片14]    [卡片15]
...
```

## 阅读顺序

用户肉眼阅读顺序是**逐排从左到右**：

```
排1: 卡片1 → 卡片2 → 卡片3 → 卡片4 → 卡片5
排2: 卡片6 → 卡片7 → 卡片8 → 卡片9 → 卡片10
排3: 卡片11 → ...
```

## 排序算法

由于瀑布流各列高度不一致（图片比例不同），同一"排"的卡片 y 坐标会有差异。

### 分组规则

- y 坐标差距 **< 100px** → 视为同一排
- y 坐标差距 **>= 100px** → 新的一排

### 排序步骤

1. 收集所有 `.note-item` 的 `{id, title, x, y}`
2. 按 y 升序、x 升序排序
3. 按 y 差距分组为"排"
4. 每排内按 x 升序排列
5. 逐排从左到右编号

```javascript
// 1) 收集
var items = [];
document.querySelectorAll('.note-item').forEach(function(item) {
    var a = item.querySelector('a[href*="/explore/"]');
    if (!a) return;
    var m = /\/explore\/([a-z0-9]+)/i.exec(a.href);
    if (!m) return;
    var rr = item.getBoundingClientRect();
    items.push({
        id: m[1],
        x: Math.round(rr.x),
        y: Math.round(rr.y),
        title: (item.querySelector('.title span') || item.querySelector('.title') || {}).textContent || ''
    });
});

// 2) 初排序
items.sort((a, b) => a.y === b.y ? a.x - b.x : a.y - b.y);

// 3) 按 y 差距分组
var rows = [], currentRow = [], lastY = -999;
for (var i = 0; i < items.length; i++) {
    if (Math.abs(items[i].y - lastY) > 100 && currentRow.length > 0) {
        rows.push(currentRow);
        currentRow = [];
    }
    currentRow.push(items[i]);
    lastY = items[i].y;
}
if (currentRow.length > 0) rows.push(currentRow);

// 4) 每排内按 x 排序
rows.forEach(row => row.sort((a, b) => a.x - b.x));

// 5) 扁平化为阅读顺序
var ordered = rows.flat();
```

## 已爬笔记定位

已爬过的笔记需要跳过。用 Set 记录已爬 ID：

```javascript
var crawledIds = new Set(['6a0aed23', '6975fd05', ...]);
var nextNote = ordered.find(item => !crawledIds.has(item.id));
```

## "搜一搜"元素

搜索结果中可能混入"搜一搜"推广卡片，不是笔记。跳过条件：
- 没有 `a[href*="/explore/"]` 链接
- 或 href 中不包含有效的笔记 ID

## 滚动加载

瀑布流使用滚动懒加载，需要 `window.scrollBy(0, 1200)` 多次才能加载完所有卡片。

```javascript
for (var i = 0; i < 6; i++) {
    window.scrollBy(0, 1200);
    sleep(0.8);
}
```
