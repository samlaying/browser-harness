# CDP → 浏览器插件 (MV3) 迁移设计

把 `archive/xhs_batch.py` + `archive/xhs_export.py`（browser-harness / CDP 版）迁移成 Chrome MV3 扩展。

**目标场景**：用户在小红书搜索页 (`search_result?keyword=...`) 搜好关键词 → 点扩展按钮 → 输入篇数 N → 扩展自动点开每篇笔记、提取标题/正文/图片/评论 → 下载图片 → 导出 Excel（嵌图）。

> 「前提是已经搜索了」直接对应 content script 的 match 规则：`*://www.xiaohongshu.com/search_result*`。扩展**不负责**打开/导航搜索页。

---

## 1. 核心判断：现有逻辑分四层

`xhs_batch.py` 的代码不是一整块 Python，按「迁移成本」分四层：

| 层 | 内容 | 迁移成本 | 出处 |
|---|---|---|---|
| **A. 页面 JS 片段** | `collect_cards` / `verify_click_target` / `get_card_rect` / `scroll_to_card` / `wait_mask_gone` / `wait_for_comments`(滚动部分) / `extract_note` | **≈0**：本来就是页面 JS，直接搬进 content script | `xhs_batch.py` 的 `safe_js(r'''...''')` 字串 |
| **B. 纯逻辑函数** | `waterfall_sort` / `compute_threads` / `encode_keyword` / `load_state` / `save_state` / `seed_done_from_disk` | **低**：改写 JS（`waterfall-layout.md` 已附 JS 版） | `xhs_batch.py` 顶部纯函数 |
| **C. 编排壳** | `run_batch` 的循环/重试/限速、`safe_js`/`safe_cdp` 重连、`ensure_daemon` | **中**：换成 `async/await` + `chrome.*` API；重连逻辑**删除** | `xhs_batch.py` `run_batch` |
| **D. Excel 导出** | `xhs_export.py` 全部 | **高**：openpyxl → 浏览器库 | `xhs_export.py` |

**A 层是主体**（爬取全靠它），而它几乎免费迁移——这就是把 CDP 版转插件的性价比所在。

### A 层逐个确认（直接可搬）

| Python 函数 | 内部用的 CDP 调用 | 迁移后 |
|---|---|---|
| `collect_cards` | 仅 `js()` 读 DOM | content script 直接读，零改动 |
| `verify_click_target` | 仅 `js()` 读 DOM | 零改动 |
| `get_card_rect` / `scroll_to_card` | 仅 `js()` | 零改动（`scroll_to_card` 的虚拟滚动兜底逻辑保留） |
| `wait_mask_gone` | 仅 `js()` 读样式 | 零改动 |
| `extract_note` | 仅 `js()` 读 DOM | 零改动（标题/正文/轮播图/评论全在这） |
| `wait_for_comments` 滚动 | `js()` 滚 `.note-scroller` | 零改动 |
| `wait_for_comments` 展开点击 | `cdp Input.dispatchMouseEvent` (hover+click) | **换 dispatchEvent**（见 §3） |
| `close_overlay` | `cdp Input.dispatchKeyEvent` Escape | **换 dispatchEvent(Escape) 或点 `.close-circle`** |
| `click_card_with_verify` | `cdp Input.dispatchMouseEvent` | **换 element.click() / dispatchEvent**（见 §3） |

---

## 2. CDP / harness → MV3 API 逐项映射

| 现有（CDP / browser-harness） | 扩展（MV3） | 说明 |
|---|---|---|
| `new_tab(url)` / `goto_url` | **不需要** | 前提条件：用户已在搜索页 |
| `js('return ...')` 执行页面脚本 | content script 直接执行 | 共享页面 DOM，无需注入 |
| `cdp Input.dispatchMouseEvent` (click) | `element.click()` | `HTMLElement.click()` 产生 **trusted** 事件，比 CDP 更干净 |
| `cdp Input.dispatchMouseEvent` (hover / mouseMoved) | `el.dispatchEvent(new MouseEvent('mousemove',{bubbles,clientX,clientY}))` | 合成事件 `isTrusted=false`，hover-gated 按钮需验证（见风险 R1） |
| `cdp Input.dispatchKeyEvent` (Escape) | `document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27}))` | 关浮窗 |
| `ensure_daemon` / `ensure_real_tab` / `safe_js` 重连 | **删除** | content script 常驻页面，无 CDP 长连接 |
| `time.sleep(jitter(3,8))` 限速 | `await sleep(ms)` | 逻辑不变 |
| `state.json` 断点续爬 | `chrome.storage.local` | `load_state/save_state` 改写为 async |
| 图片下载 `urllib` + `Referer` 头 | `declarativeNetRequest` 加 Referer + `chrome.downloads` | `fetch` 不能伪造 Referer（forbidden header），见 §5 |
| Excel `openpyxl` + `OneCellAnchor` 嵌图 | `exceljs` `worksheet.addImage` | SheetJS 社区版**不支持**嵌图，见 §6 |

---

## 3. 点击 / hover：CDP trusted event → content script

卡片本身点击用 `element.click()`（trusted，可靠）：

```js
// 替代 cdp Input.dispatchMouseEvent 点击卡片
function clickCard(cardEl) {
  verifyClickTarget(cardEl);          // A 层 verify_click_target 直接搬
  cardEl.scrollIntoView({block:'center'});  // 注：取坐标前不能 scrollIntoView（坑 #2），这里点元素不取坐标所以安全
  cardEl.querySelector('a.cover')?.click();  // 点封面链接打开浮窗
}
```

> 注意：原 CDP 版用坐标点击，是因为 CDP 只有 `dispatchMouseEvent(x,y)`。扩展里有 `element.click()`，**优先用元素引用而非坐标**，可绕过 Retina 坐标偏移（坑 #17 大幅缓解）。

展开按钮（`.show-more` / `.expand-btn`）是 hover-gated（坑 #3），必须先派发 mousemove：

```js
// 替代 wait_for_comments 里的 cdp hover+click
function hoverClick(el) {
  const r = el.getBoundingClientRect();
  const ev = (type) => new MouseEvent(type, {
    bubbles: true, clientX: r.x + r.width/2, clientY: r.y + r.height/2,
  });
  el.dispatchEvent(ev('mousemove'));
  el.dispatchEvent(ev('mousedown'));
  el.dispatchEvent(ev('mouseup'));
  el.dispatchEvent(ev('click'));
}
```

合成事件 `isTrusted=false`，XHS（React）是否接受需实测（见 R1）。备选：很多 hover-gated 按钮直接 `.click()` 也能展开。

---

## 4. 18 个 gotcha 在扩展里的状态

对照 `references/gotchas.md`：

| # | 坑 | 状态 | 扩展里怎么处理 |
|---|---|---|---|
| 1 | 必须 click 卡片（xsec_token） | **保留但更简单** | 从搜索页点卡片天然带 token，比 CDP 还省事 |
| 2 | scrollIntoView 取坐标偏移 | 保留 | 仍用 `scrollTo`，取坐标前不 scrollIntoView |
| 3 | 展开按钮需 hover | **换法** | `dispatchEvent(mousemove…)` 或 `.click()`（R1） |
| 4 | 评论层级 `.reply-container` | 保留 | 纯 DOM 判断不变 |
| 5 | 问一问 AI 选择器 | 保留 | 选择器链不变 |
| 6 | active slide 图片顺序 | 保留 | 循环去重逻辑不变 |
| 7 | 图片下载需 Referer | **换法** | `declarativeNetRequest`（§5） |
| 8 | Excel 嵌图用 OneCellAnchor | **换法** | `exceljs` `addImage`（§6） |
| 9 | 视频无法下载 | 保留 | blob URL 仍无解 |
| 10 | THE END 常驻 DOM | 保留 | stall≥5 判底不变 |
| 11 | 浮窗未关点下一篇 | 保留 | `wait_mask_gone` 不变 |
| 12 | 搜索页误判卡片 | 保留 | `.note-item` 祖先验证不变 |
| 13 | 两趟跑低效 | 保留 | 一趟跑完逻辑不变 |
| 14 | 卡片滚出视口 | 保留 | `scroll_to_card` 兜底不变 |
| 15 | 速度过快被封 | 保留 | jitter 限速表不变 |
| 16 | SPA 重新导航不渲染卡片 | **自动消失** | content script 本就在搜索页，全程不导航 |
| 17 | 点击前 elementFromPoint 验证 | **缓解** | 优先 `element.click()`，坐标点击减少 |
| 18 | CDP 长会话掉线 | **自动消失** | 无 CDP 长连接 |

**净效果**：18 坑里 2 个自动消失、3 个换法、其余逻辑原样保留——迁移风险集中在 R1（hover）和 §5（图片 Referer）两点。

---

## 5. 图片下载 + Referer（坑 #7 在扩展里）

现状（`xhs_export.py`）：

```python
urllib.request.Request(url, headers={'Referer': 'https://www.xiaohongshu.com/'})
```

扩展里的限制：`fetch(url, {headers:{Referer:...}})` **无效**——`Referer` 是 [forbidden header](https://developer.mozilla.org/en-US/docs/Glossary/Forbidden_header_name)，浏览器不允许脚本伪造。

**主方案：`declarativeNetRequest` 给 XHS CDN 请求加 Referer**

`rules/referer.json`：
```json
[
  {
    "id": 1,
    "priority": 1,
    "action": {
      "type": "modifyHeaders",
      "requestHeaders": [{ "header": "Referer", "operation": "set", "value": "https://www.xiaohongshu.com/" }]
    },
    "condition": { "urlFilter": "||xhscdn.com", "resourceTypes": ["image", "xmlhttprequest"] }
  }
]
```

然后 `chrome.downloads.download({url, filename})` 即可（请求经 DNR 规则带上正确 Referer）。

> XHS 图片域名以 `sns-img-*.xhscdn.com` / `*xhscdn.com` 为主，上线前用 Network 面板确认实际域名，调整 `urlFilter`。

**备选**：background service worker `fetch` → blob → `URL.createObjectURL` → `<a download>`。SW 的 fetch 不受页面 CORS 读限制，但 Referer 仍需 DNR 规则加持。DNR 方案更通用，优先。

---

## 6. Excel 导出：openpyxl → 浏览器库

> ⚠ **重要权衡**：原脚本的核心体验是**图片嵌入单元格**（`OneCellAnchor`）。这决定了库的选择。

| 库 | 嵌图支持 | 体积 | 结论 |
|---|---|---|---|
| **SheetJS 社区版** (`xlsx`) | ❌ 不支持单元格嵌图 | 小 | 导出文字/评论 OK，但**丢掉嵌图体验** |
| SheetJS Pro | ✅ | 收费 | 不推荐 |
| **ExcelJS** (`exceljs`) | ✅ `worksheet.addImage({imageId, tl, br})` | 中 | **推荐**——对齐现有嵌图体验 |

虽然选型时倾向 SheetJS，但要在浏览器里复刻「图片嵌入单元格」，**ExcelJS 是社区版唯一可行选项**。`addImage` 用法：

```js
const wb = new ExcelJS.Workbook();
const ws = wb.addWorksheet('小红书数据');
const imgId = wb.addImage({ buffer: arrayBuffer, extension: 'jpg' });
ws.addImage(imgId, { tl: { col: 8, row: r-1 }, br: { col: 9.2, row: r } });  // 对应原 OneCellAnchor(col=8)
const buf = await wb.xlsx.writeBuffer();
// 下载
const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
// 走 §5 的下载链路（带 Referer 的是图片；Excel 本身直接 <a download>）
```

`xhs_export.py` 的列定义、配色 `POST_COLORS`、帖子行/评论行结构、线程缩进（`↳回复`）全部在 ExcelJS 里 1:1 复刻——`build_excel` 的结构是纯数据布局，迁语言不迁逻辑。

**降级方案**：若嵌图非必须，SheetJS 社区版 + 图片单独打 zip 下载更轻。

---

## 7. 推荐的 MV3 目录骨架（未来实现，先记录）

```
xhs-crawler-ext/extension/
├── manifest.json
├── content/
│   ├── crawl.js        # 编排：collect → waterfall_sort → 逐篇 click/extract（搬 run_batch）
│   ├── extract.js      # extract_note / wait_for_comments / wait_mask_gone（A 层）
│   ├── dom.js          # collect_cards / verify_click_target / scroll_to_card / get_card_rect / close_overlay（A 层）
│   ├── logic.js        # waterfall_sort / compute_threads（B 层，waterfall-layout.md 已给 JS）
│   ├── throttle.js     # sleep / jitter（限速，C 层）
│   └── storage.js      # chrome.storage.local 包装：state 读写（B 层 load/save_state）
├── background/
│   └── service.js      # chrome.downloads 图片下载；进度消息中转
├── popup/
│   ├── popup.html      # 输入篇数 N / 开始 / 暂停 / 进度 / 导出按钮
│   └── popup.js        # chrome.tabs.sendMessage → content/crawl.js；监听进度
├── rules/
│   └── referer.json    # declarativeNetRequest：给 xhscdn 加 Referer
└── lib/
    └── exceljs.min.js  # Excel 生成（含嵌图）
```

`manifest.json` 关键字段：

```json
{
  "manifest_version": 3,
  "name": "小红书爬虫",
  "version": "0.1.0",
  "permissions": ["storage", "downloads", "declarativeNetRequest"],
  "host_permissions": ["*://*.xiaohongshu.com/*", "*://*.xhscdn.com/*"],
  "action": { "default_popup": "popup/popup.html" },
  "background": { "service_worker": "background/service.js" },
  "content_scripts": [{
    "matches": ["*://www.xiaohongshu.com/search_result*"],
    "js": ["lib/exceljs.min.js", "content/logic.js", "content/dom.js",
           "content/extract.js", "content/throttle.js", "content/storage.js", "content/crawl.js"]
  }],
  "declarative_net_request": {
    "rule_resources": [{ "id": "referer_rules", "path": "rules/referer.json", "enabled": true }]
  }
}
```

**数据流**：

```
popup 输入 N
  └─chrome.tabs.sendMessage→ content/crawl.js
       ├─ collect_cards + waterfall_sort（得到有序 id 列表）
       ├─ storage.loadState（断点续爬，跳过 done）
       └─ for each pending id:
            ├─ scroll_to_card → click 封面 → wait 浮窗
            ├─ extract_note（标题/正文/图/评论，一趟）
            ├─ storage.saveNote + saveState（增量落盘）
            ├─ 限速 sleep（3~8s + 15% 长停顿）
            └─ chrome.runtime.sendMessage→ background：图片下载（带 Referer）
       └─ 全部完成 → 生成 ExcelJS → <a download>
```

---

## 8. 待验证风险点

| ID | 风险 | 验证方式 | 备选 |
|----|------|----------|------|
| **R1** | hover-gated 展开按钮（`.show-more`/`.expand-btn`）是否响应合成 `mousemove`（`isTrusted=false`） | 阶段 2 单篇实测：开一篇有多条回复的笔记，看能否展开 | 直接 `.click()`；若都不行，回退坐标点击（CDP 同款，扩展里用 `chrome.debugger` 或 `elementFromPoint`+dispatch） |
| **R2** | `declarativeNetRequest` 加 Referer 后，XHS CDN 是否返回 200（坑 #7） | 阶段 4 实测图片下载成功率 | background `fetch`→blob；或 content script 内 `<img>`+canvas 转 blob（绕过下载器） |
| **R3** | ExcelJS 在 popup/SW 里生成大 Excel（含数十张图）的内存/耗时 | 阶段 4 压测 20 篇 × 11 图 | 分批写；或导出 JSON + 离线转 Excel |
| R4 | content script isolated world 与 XHS Vue 应用的事件兼容（dispatchEvent 能否触发 Vue 监听） | 阶段 2 验证 `card.click()` 能开浮窗 | 注入 page-world `<script>`（MAIN world）跑逻辑 |

---

## 9. 迁移路线图

| 阶段 | 目标 | 产出 | 验证 |
|------|------|------|------|
| **0（已完成）** | 归档 CDP 版 + 本文档 | `archive/` + 本文件 | — |
| 1 | MV3 骨架打通：popup → content 注入 → `collect_cards` 打印 | `extension/` 可加载 | 控制台输出卡片数 |
| 2 | 单篇 `click → extract` 跑通（标题/正文/评论） | `extract.js` | 验证 R1/R4 |
| 3 | 批量编排 + `chrome.storage` 断点续爬 + 限速 | `crawl.js` | 20 篇 0 失败 |
| 4 | 图片下载（DNR Referer）+ Excel 导出（ExcelJS） | `service.js` + `rules/` | 验证 R2/R3 |
| 5 | UI 打磨：进度条、暂停/继续、错误提示、篇数校验 | `popup/*` | 真实用户流 |

---

## 附：可直接搬运的 JS 片段清单

以下 `xhs_batch.py` 内的 `safe_js(r'''...''')` 字串，去掉 Python 包装即为 content script 函数：

- `collect_cards()` — 收集 `.note-item` 卡片中心坐标
- `verify_click_target(cx,cy)` — elementFromPoint 验证 + 坏元素检测（坑 #17）
- `get_card_rect(note_id)` — 按 id 取卡片中心
- `scroll_to_card(note_id)` — 滚入视口 + 虚拟滚动兜底
- `wait_mask_gone()` — 浮窗关闭轮询（坑 #11）
- `extract_note` 的两个 JS 块 — meta 提取 + 评论提取（含轮播图 active 排序 坑 #6、层级判断 坑 #4、问一问选择器 坑 #5）

B 层纯逻辑 `waterfall_sort` 的 JS 版已在 `references/waterfall-layout.md` 给出；`compute_threads` 按 `xhs_batch.py` 的 Python 逐行翻译即可（逻辑简单：lvl==1 起新线程，lvl==2 回溯找 reply_to）。
