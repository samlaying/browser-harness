# xhs-crawler 健壮性迭代设计

- **日期**: 2026-06-23
- **范围**: `.claude/skills/xhs-crawler/`
- **驱动力**: 可靠性/健壮性
- **目标**: 把散落在 SKILL.md 伪代码 + `xhs_crawl.py` 里的批量爬取逻辑收敛成一个自包含、可断点续爬、单篇可重试的脚本，让每次爬取不再手写编排循环。

## 背景与问题

当前 skill 有两个脚本：`xhs_crawl.py`（单篇提取，假设浮窗已打开）、`xhs_export.py`（导出 Excel）。SKILL.md 的 "Step 3: 一趟跑完" 只是一段伪代码，agent 每次爬取都要手写约 100 行编排逻辑（收卡片 → 点击验证 → 关浮窗 → 提取 → 存 JSON）。这带来三个问题：

1. **脆弱**：每次手写循环都可能漏掉一个 gotcha（点击前验证、关浮窗后验证 mask、不重新导航等）。
2. **无法续爬**：中途断了无法恢复，只能从头再来。
3. **逻辑分叉**：`xhs_crawl.py` 与 `xhs_export.py` 各算一遍 `thread_id`/`reply_to`，存在漂移风险。

### 关键技术约束：harness exec 模型

`browser-harness` 的 `run.py` 用 `exec(code, globals())` 执行管道传入的**单个脚本 blob**，helpers（`js`/`cdp`/`ensure_daemon`/`ensure_real_tab`）通过 `from .helpers import *` 注入到该 globals。

含义：**跨文件 `import` 不干净**——被导入模块有独立 globals 命名空间，里面没有 `js`/`cdp`，会 NameError。这也解释了为何当前 `xhs_crawl.py`（顶层即调用 `js()`）无法被 import 复用。

因此设计基线：**所有可运行脚本必须是自包含 blob**（函数定义在顶部，主调用在底部），helpers 在同一 blob 内自然解析到 harness globals。

## 方案选择

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 单个自包含 `xhs_batch.py`** | 一个 blob 脚本完成全流程，承载全部健壮性能力 | ✅ 采用 |
| B. 拆 importable 模块 + 薄批量脚本 | 抽公共 helpers 到模块、让 xhs_crawl.py 可 import | ❌ 对抗 exec 模型，需 globals shim，脆弱且过度工程 |
| C. shell 循环里每篇重新 pipe `xhs_crawl.py` | 每篇一个新 browser-harness 会话 | ❌ 违反 gotcha #16（重新导航导致卡片不渲染），且每次会话启动开销 ~10s |

## 架构

### 文件结构（变更后）

```
scripts/
├── xhs_batch.py    # 新增：自包含批量编排（全流程），取代手写循环
└── xhs_export.py   # 改：图片并行下载 + 删除重复线程逻辑
```

`xhs_crawl.py` **删除**。其提取逻辑完整并入 `xhs_batch.py` 的 `extract_note()`。单一规范提取路径，消除逻辑分叉。

### `xhs_batch.py` 模块布局

自包含 blob，函数定义在顶部，主流程在底部由环境变量驱动。

| 函数 | 职责 | 来源 |
|------|------|------|
| `safe_js(s)` / `safe_cdp(method,**kw)` | 异常时 `ensure_daemon(); ensure_real_tab()` 后重试一次 | 沿用 `xhs_crawl.py` |
| `jitter(lo,hi)` | `random.uniform` 限速 | 沿用 |
| `verify_click_target(cx,cy)` | `elementFromPoint` 验证：向上找 `.note-item`、检测坏元素、返回 chain | 沿用 |
| `click_card_with_verify(cx,cy)` | hover(mouseMoved) + press + release + 验证 | 沿用 |
| `wait_mask_gone(timeout)` | 关浮窗后轮询 `mask.display==='none'` | 沿用 |
| `collect_cards()` | 收集 `.note-item`→去重→瀑布流排序（y 差<100px 同排，排内 x 升序） | 新封装，逻辑来自 `waterfall-layout.md` |
| `get_card_rect(note_id)` | 按 ID 找 `a[href*="/explore/{id}"]` 祖先 `.note-item` 坐标，**不 scrollIntoView** | 新封装，来自 gotcha #2/#12 |
| `close_overlay()` | hover-click (50,400) 区域 → `wait_mask_gone()` | 新封装 |
| `wait_for_comments()` | `.note-scroller` 滚到底 + 展开 `.show-more`/`.expand-btn`，stall≥5 判底 | 沿用 `xhs_crawl.py` 主流程 |
| `extract_note()` | 提取 meta（title/desc/bar/hasVideo/noteImgs active 顺序）+ 评论（层级/问一问/回复关系），返回 `(ok, data)` | 移植自 `xhs_crawl.py` |
| `health_check()` | 每 N 篇 `js('return document.title')` 心跳；异常则 `ensure_daemon()+ensure_real_tab()`，记日志 | 新增 |
| `run_batch()` | 主循环：读 state → 遍历剩余卡片 → 重试 → 增量存 → 限速 → 健康检查 | 新增 |

**`extract_note()` 返回 `(ok, data)`**——**失败判定 = meta 为空（无标题）**，这是浮窗未打开/未提取的清晰信号。不把"0 条评论"判为失败（无法可靠区分"提取失败"与"真·无评论帖"，且小红书存在合法无评论笔记）。`ok=False` 时触发重试。

### 环境变量（管道传入时设）

| 变量 | 默认 | 说明 |
|------|------|------|
| `XHS_KEYWORD` | 必填 | 搜索词（URL 编码由脚本负责） |
| `XHS_TARGET` | `20` | 目标篇数 |
| `XHS_OUTDIR` | `xhs_data/{date}_{keyword}` | 输出子目录 |
| `XHS_MAX_RETRY` | `2` | 单篇重试次数 |

## 健壮性设计（四项能力）

### 1. 断点续爬 / 幂等

状态文件 `state.json` 存于 `XHS_OUTDIR`，与笔记 JSON 并列：

```json
{
  "keyword": "...",
  "target": 20,
  "done": ["id1", "id2"],
  "failed": [{"id": "..", "reason": "..", "attempts": 2}],
  "order": ["id1", "id2", ...]
}
```

- `order` = 瀑布流排序后的完整 ID 列表，持久化以免重跑时重新收/排序。
- **续爬流程**（每次都是新 browser-harness 会话）：`new_tab` 到搜索页 → 滚动加载（scrollBy 6 次）→ `collect_cards()` 排序 → 读 `done[]` 过滤 → 遍历剩余。状态文件跨会话存活，DOM 状态无需保留（fresh 导航到搜索页天然可用，不触发 gotcha #16，因为是会话首次导航而非中途重新导航）。

### 2. 增量落盘（真正幂等）

- 每篇提取成功后：**立即**写 `{id}.json`，再追加 `done[]` 并重写 `state.json`。
- **启动时双保险**：除读 `state.json`，还扫描 `XHS_OUTDIR` 下已存在的 `{id}.json` 文件名并入 `done[]`。即便进程在"存 JSON 后、写 state 前"崩溃，重跑也不重爬。

### 3. 单篇重试 + 失败日志

- `extract_note()` 返回 `(ok=False, ...)` → `close_overlay()` → `click_card_with_verify()` 重点同一卡片 → 重提，最多 `XHS_MAX_RETRY`（默认 2）。
- 仍失败：记入 `state.json.failed[]`（`{id, reason, attempts}`），打印后继续下一篇。

### 4. 连接健康检查

- 每 5 篇：心跳 `js('return document.title')`。
- 异常 → `ensure_daemon(); ensure_real_tab()` + 记日志。**真正的单调用恢复由 `safe_js`/`safe_cdp` 兜底**（每次异常自动重连）。健康检查主要负责检测+记日志，不引入额外恢复复杂度（遵循 SKILL.md "不加 manager 层" 约束）。

## Export 改动（`xhs_export.py`）

健壮性相邻、一起做，不加新数据字段（YAGNI）。

1. **图片并行下载**：`ThreadPoolExecutor(max_workers=8)`，先批量下载所有笔记的唯一图片 URL 到本地（沿用现有 Referer 头），再构建 Excel 嵌入本地路径。下载与排版解耦，避免逐张串行阻塞。
2. **删除重复线程逻辑**：信任 batch 脚本写入的 JSON（已含 `thread_id`/`reply_to`），export 直接读，不再重算（当前 `xhs_crawl.py` 输出的 JSON 已含这俩字段，export 重算是冗余）。

## SKILL.md 更新

- "Step 3: 一趟跑完" 从伪代码改为指向 `xhs_batch.py` 的真实用法（管道 + 环境变量）。
- 更新"前提"和文件清单。
- 新增一节"断点续爬"说明 state.json 用法。
- references 保持（gotchas / waterfall-layout / selectors 仍是事实库，`xhs_batch.py` 的函数注释里交叉引用它们）。

## 错误处理

| 场景 | 处理 |
|------|------|
| 搜索页卡片收不满 target | 按实际收集数爬取，打印 `实际 N 篇` |
| 点击验证失败（坏元素/非卡片） | 打印 `⚠ 跳过`，记 failed，下一篇 |
| 提取为空（无标题） | 重试 `MAX_RETRY` 次，仍空记 failed |
| CDP 断连 | `safe_js`/`safe_cdp` 自动重连；健康检查每 5 篇检测 |
| 关浮窗后 mask 未消 | `wait_mask_gone` 轮询，超时不点下一篇 |
| 图片下载失败 | 打印，Excel 该格留空（沿用现有） |

## 测试 / 验证

无单元测试框架（CDP skill，依赖真实浏览器+登录态）。验证方式：

1. **语法/导入自检**：`python3 -c "import ast; ast.parse(open('scripts/xhs_batch.py').read())"` 通过。
2. **干跑结构**：不连浏览器时 `run_batch` 的非 DOM 部分（状态文件读写、done 扫描、order 持久化）可单独验证逻辑。
3. **实跑**（用户侧）：在已登录 Chrome 上，对一个小 keyword 跑 `XHS_TARGET=3`，确认：3 篇 JSON 落盘、state.json 正确、中断重跑跳过已完成、Excel 生成且图片嵌入。
4. **回归**：export 改动后，用现有 JSON 目录导出，确认线程关系与改前一致（thread_id/reply_to 来自 JSON）。

## 不做（YAGNI / 超范围）

- 新增数据字段（作者、收藏数、用户主页）——属"新增能力"，非本次健壮性目标。
- 视频帖 mp4 下载——blob URL 限制，已知不解决。
- 分 Sheet 导出——当前单 Sheet 够用。
- 模块化重构（方案 B）——对抗 exec 模型。
