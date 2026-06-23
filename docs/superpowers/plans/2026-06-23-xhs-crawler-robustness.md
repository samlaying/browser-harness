# xhs-crawler 健壮性迭代 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把小红书批量爬取逻辑收敛成一个自包含 `xhs_batch.py`，支持断点续爬、单篇重试、增量落盘、连接健康检查；并清理 export 的串行下载与重复线程逻辑。

**Architecture:** 单个自包含 blob 脚本（贴合 harness `exec(code, globals())` 模型）。纯逻辑（状态 IO / 瀑布流排序 / 评论线程 / 关键词编码）提取为无 harness 依赖的函数，入口用 `'js' in dir()` 守卫——这样 pytest 可直接 import 这些纯函数做单测，而 harness 执行时自动跑 `run_batch()`。

**Tech Stack:** Python 3, browser-harness (CDP), openpyxl, pytest（仅测试用）。

**Spec:** `docs/superpowers/specs/2026-06-23-xhs-crawler-robustness-design.md`

**关键约束（已实测验证）：**
- harness 用 `exec(code, globals())` 执行管道脚本，`js`/`cdp`/`ensure_daemon`/`ensure_real_tab`/`new_tab`/`wait_for_load` 注入到该 globals。
- 执行时 `__name__ == 'browser_harness.run'`（**不是** `'__main__'`），但 `'js' in dir()` 为 `True`。故入口守卫用 `'js' in dir()`。
- 被跨文件 import 的模块有独立 globals（无 `js`/`cdp`），所以**不能**把需要 js/cdp 的逻辑放到被 import 的模块里。纯函数（无 js/cdp 调用）可安全放同一 blob 顶层并被 pytest import。

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `scripts/xhs_batch.py` | 新建 | 自包含批量编排 blob：纯函数 + DOM 函数 + run_batch + 入口守卫 |
| `scripts/xhs_crawl.py` | 删除 | 逻辑已并入 xhs_batch.py |
| `scripts/xhs_export.py` | 修改 | 图片并行下载（ThreadPoolExecutor）；删除重复的 compute_threads 逻辑 |
| `tests/test_xhs_batch_pure.py` | 新建 | pytest：纯函数单测 |
| `.claude/skills/xhs-crawler/SKILL.md` | 修改 | Step 3 指向 xhs_batch.py；新增"断点续爬"说明 |

纯函数（可单测，无 js/cdp）：`encode_keyword` / `waterfall_sort` / `compute_threads` / `load_state` / `save_state` / `default_state` / `seed_done_from_disk`
DOM/编排函数（harness 内运行，靠真实浏览器验证）：`safe_js` / `safe_cdp` / `jitter` / `verify_click_target` / `click_card_with_verify` / `wait_mask_gone` / `collect_cards` / `get_card_rect` / `close_overlay` / `delay_*` / `wait_for_comments` / `extract_note` / `health_check` / `run_batch`

---

## Task 1: 脚手架 — 创建 xhs_batch.py 骨架 + 入口守卫

**Files:**
- Create: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`

- [ ] **Step 1: 创建骨架文件**

Create `.claude/skills/xhs-crawler/scripts/xhs_batch.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书批量爬虫 — browser-harness (CDP) 自包含编排脚本

管道用法（harness 自动注入 js/cdp/ensure_daemon 等 globals）：
    XHS_KEYWORD="咖啡" XHS_TARGET=20 browser-harness < scripts/xhs_batch.py

环境变量：
    XHS_KEYWORD    搜索词（必填）
    XHS_TARGET     目标篇数（默认 20）
    XHS_OUTDIR     输出目录（默认 xhs_data/{date}_{keyword}）
    XHS_MAX_RETRY  单篇重试次数（默认 2）

健壮性：断点续爬(state.json) + 增量落盘 + 单篇重试 + 每5篇健康检查。

设计约束：本脚本经 harness `exec(code, globals())` 执行，js/cdp 在同一 globals。
故：① 不能跨文件 import 需要 js/cdp 的逻辑；② 入口由 'js' in dir() 守卫，
   这样 pytest 可直接 import 纯函数做单测而不触发 run_batch。

纯函数（无 js/cdp 依赖，可单测）：encode_keyword / waterfall_sort / compute_threads
                            / load_state / save_state / default_state / seed_done_from_disk
"""

import os, sys, json, time, random, glob, datetime
import urllib.parse


# ── 纯函数占位（后续 Task 填充） ─────────────────────────
# encode_keyword / waterfall_sort / compute_threads / 状态 IO — 见 Task 2-5


# ── DOM/编排函数占位（后续 Task 填充） ───────────────────
# safe_js / safe_cdp / jitter / verify_click_target / click_card_with_verify
# / wait_mask_gone / collect_cards / get_card_rect / close_overlay
# / delay_* / wait_for_comments / extract_note / health_check — 见 Task 6-9


def run_batch():
    """主编排：导航搜索页 → 收卡片排序 → 断点续爬 → 逐篇重试增量落盘 → 健康检查。
    见 Task 9。"""
    print("[xhs_batch] run_batch() 尚未实现（骨架）", flush=True)


# ── 入口 ─────────────────────────────────────────────────
# harness exec 时 js/cdp 在 dir()；pytest import 时不在 → 不触发 run_batch。
if 'js' in dir() and 'cdp' in dir():
    run_batch()
```

- [ ] **Step 2: 语法自检**

Run: `python3 -c "import ast; ast.parse(open('.claude/skills/xhs-crawler/scripts/xhs_batch.py').read())"`
Expected: 无输出（解析成功）。

- [ ] **Step 3: 验证入口守卫在普通 python 下不触发**

Run: `python3 .claude/skills/xhs-crawler/scripts/xhs_batch.py`
Expected: 无输出（`'js' in dir()` 为 False，`run_batch()` 不被调用）。这是 import 安全的关键保证。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py
git commit -m "feat(xhs): add xhs_batch.py scaffold with harness entry guard"
```

---

## Task 2: 纯函数 encode_keyword（TDD）

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`
- Test: `.claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py`

- [ ] **Step 1: 创建测试文件 + 写失败测试**

Create `.claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py`:

```python
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import xhs_batch as X


def test_encode_keyword():
    assert X.encode_keyword("咖啡") == "%E5%92%96%E5%95%A1"
    assert X.encode_keyword("a b") == "a%20b"
    assert X.encode_keyword("test") == "test"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: FAIL with `AttributeError: module 'xhs_batch' has no attribute 'encode_keyword'`

- [ ] **Step 3: 实现 encode_keyword**

In `xhs_batch.py`, replace the "纯函数占位" comment block with:

```python
# ── 纯函数（无 js/cdp 依赖，可单测） ─────────────────────

def encode_keyword(kw):
    """URL 编码搜索词。"""
    return urllib.parse.quote(kw, safe='')
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py .claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py
git commit -m "feat(xhs): add encode_keyword with test"
```

---

## Task 3: 纯函数 waterfall_sort（TDD）— 瀑布流排序

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`
- Modify: `.claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py`

- [ ] **Step 1: 追加失败测试**

Append to `tests/test_xhs_batch_pure.py`:

```python
def test_waterfall_sort_3col_2row():
    # 3 列 x 2 排；同排 y 差 <100
    items = [
        {'id': 'a', 'x': 196, 'y': 100}, {'id': 'b', 'x': 451, 'y': 110}, {'id': 'c', 'x': 706, 'y': 95},
        {'id': 'd', 'x': 196, 'y': 400}, {'id': 'e', 'x': 451, 'y': 410}, {'id': 'f', 'x': 706, 'y': 405},
    ]
    # 排1(y~100): 按 x 升序 a,b,c；排2(y~400): d,e,f
    assert X.waterfall_sort(items) == ['a', 'b', 'c', 'd', 'e', 'f']


def test_waterfall_sort_gap_splits_rows_and_x_within_row():
    # y 差 150 >= 100 → 两排；排内按 x 升序
    items = [
        {'id': 'a', 'x': 451, 'y': 100}, {'id': 'b', 'x': 196, 'y': 100},   # 排1 → b,a
        {'id': 'c', 'x': 451, 'y': 250}, {'id': 'd', 'x': 196, 'y': 250},   # 排2 → d,c
    ]
    assert X.waterfall_sort(items) == ['b', 'a', 'd', 'c']


def test_waterfall_sort_empty():
    assert X.waterfall_sort([]) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: FAIL (3 new tests) with `AttributeError: ... has no attribute 'waterfall_sort'`

- [ ] **Step 3: 实现 waterfall_sort**

In `xhs_batch.py`, after `encode_keyword`, add:

```python
def waterfall_sort(items):
    """items: [{id, x, y}]。按瀑布流阅读顺序排序：y 差 <100 视为同排，
    排内按 x 升序，逐排从左到右。返回 id 列表。算法见 references/waterfall-layout.md。"""
    if not items:
        return []
    ordered = sorted(items, key=lambda it: (it['y'], it['x']))
    rows, current, last_y = [], [], None
    for it in ordered:
        if current and last_y is not None and abs(it['y'] - last_y) > 100:
            rows.append(current)
            current = []
        current.append(it)
        last_y = it['y']
    if current:
        rows.append(current)
    for row in rows:
        row.sort(key=lambda it: it['x'])
    flat = []
    for row in rows:
        for it in row:
            flat.append(it['id'])
    return flat
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py .claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py
git commit -m "feat(xhs): add waterfall_sort with tests"
```

---

## Task 4: 纯函数 compute_threads（TDD）— 评论线程去重

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`
- Modify: `.claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py`

- [ ] **Step 1: 追加失败测试**

Append to `tests/test_xhs_batch_pure.py`:

```python
def test_compute_threads_levels_and_reply_to():
    comments = [
        {'lvl': 1, 'nick': 'Alice', 'content': 'hi'},
        {'lvl': 2, 'nick': 'Bob',   'content': 're'},      # 回复 Alice
        {'lvl': 1, 'nick': 'Carol', 'content': 'yo'},
        {'lvl': 2, 'nick': 'Dave',  'content': 're2'},     # 回复 Carol
    ]
    out = X.compute_threads(comments)
    assert out[0]['thread_id'] == 1 and out[0]['reply_to'] == ''
    assert out[1]['thread_id'] == 1 and out[1]['reply_to'] == 'Alice'
    assert out[2]['thread_id'] == 2 and out[2]['reply_to'] == ''
    assert out[3]['thread_id'] == 2 and out[3]['reply_to'] == 'Carol'


def test_compute_threads_does_not_mutate_input():
    comments = [{'lvl': 1, 'nick': 'A', 'content': 'x'}]
    X.compute_threads(comments)
    assert 'thread_id' not in comments[0]


def test_compute_threads_empty():
    assert X.compute_threads([]) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: FAIL (3 new) with `AttributeError: ... has no attribute 'compute_threads'`

- [ ] **Step 3: 实现 compute_threads**

In `xhs_batch.py`, after `waterfall_sort`, add:

```python
def compute_threads(comments):
    """给评论列表打 thread_id / reply_to。
    1级(lvl==1)= 新线程；2级(lvl==2, 祖先含 reply-container)= 归属当前线程。
    reply_to = 向前找本线程内上一个不同昵称者。返回新列表（不修改入参）。
    消除 xhs_crawl.py / xhs_export.py 里重复的逻辑。"""
    out = [dict(c) for c in comments]
    thread_id = 0
    current_thread = 0
    for c in out:
        if c.get('lvl') == 1:
            thread_id += 1
            current_thread = thread_id
            c['thread_id'] = thread_id
            c['reply_to'] = ''
        else:
            c['thread_id'] = current_thread
            c['reply_to'] = ''
    for i, c in enumerate(out):
        if c.get('lvl') == 2:
            for j in range(i - 1, -1, -1):
                if out[j].get('nick') != c.get('nick'):
                    c['reply_to'] = out[j].get('nick', '')
                    break
    return out
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py .claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py
git commit -m "feat(xhs): add compute_threads with tests"
```

---

## Task 5: 纯函数 状态 IO（TDD）— 断点续爬 + 幂等

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`
- Modify: `.claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py`

- [ ] **Step 1: 追加失败测试**

Append to `tests/test_xhs_batch_pure.py`:

```python
def test_state_default():
    s = X.default_state('kw', 5)
    assert s == {'keyword': 'kw', 'target': 5, 'done': [], 'failed': [], 'order': []}


def test_state_roundtrip(tmp_path):
    d = str(tmp_path)
    assert X.load_state(d) is None                      # 不存在
    X.save_state(d, X.default_state('kw', 5))
    s = X.load_state(d)
    assert s['keyword'] == 'kw' and s['target'] == 5
    # 保存 done/failed 后能读回
    s['done'] = ['abc12345']; s['failed'] = [{'id': 'fff', 'reason': 'empty_meta', 'attempts': 3}]
    X.save_state(d, s)
    s2 = X.load_state(d)
    assert s2['done'] == ['abc12345'] and s2['failed'][0]['reason'] == 'empty_meta'


def test_seed_done_from_disk_filters(tmp_path):
    d = str(tmp_path)
    X.save_state(d, X.default_state('kw', 5))           # state.json 不应被当成笔记
    open(os.path.join(d, 'abcdef12.json'), 'w').write('{}')   # 合法 hex id
    open(os.path.join(d, 'zzzzzzz.json'), 'w').write('{}')    # 非 hex → 排除
    open(os.path.join(d, 'readme.txt'), 'w').write('x')       # 非 json → 排除
    seeded = X.seed_done_from_disk(d)
    assert 'abcdef12' in seeded
    assert 'state.json' not in seeded
    assert all(len(i) == 8 for i in seeded)             # 只收 8 位 hex
    assert 'zzzzzzz' not in seeded
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: FAIL (3 new) with `AttributeError: ... has no attribute 'default_state'`

- [ ] **Step 3: 实现状态 IO**

In `xhs_batch.py`, after `compute_threads`, add:

```python
STATE_FILENAME = 'state.json'


def _state_path(outdir):
    return os.path.join(outdir, STATE_FILENAME)


def default_state(keyword, target):
    return {'keyword': keyword, 'target': target, 'done': [], 'failed': [], 'order': []}


def load_state(outdir):
    p = _state_path(outdir)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_state(outdir, state):
    os.makedirs(outdir, exist_ok=True)
    with open(_state_path(outdir), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def seed_done_from_disk(outdir):
    """扫描 outdir 下 {id}.json（排除 state.json 与非 8 位 hex id），返回已完成 id 集合。
    启动时与 state.done 取并集 → 即便进程在'存 JSON 后写 state 前'崩了，重跑也不重爬。"""
    done = set()
    if not os.path.isdir(outdir):
        return done
    hexset = set('0123456789abcdefABCDEF')
    for fp in glob.glob(os.path.join(outdir, '*.json')):
        name = os.path.basename(fp)
        if name == STATE_FILENAME:
            continue
        stem = os.path.splitext(name)[0]
        if len(stem) == 8 and all(ch in hexset for ch in stem):
            done.add(stem)
    return done
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py .claude/skills/xhs-crawler/tests/test_xhs_batch_pure.py
git commit -m "feat(xhs): add state IO (resume + idempotent seed) with tests"
```

---

## Task 6: DOM 工具函数 — safe_js / safe_cdp / jitter / 验证 / 关闭

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`

这些函数引用 harness 注入的 `js`/`cdp`/`ensure_daemon`/`ensure_real_tab`（调用时解析，定义时不解析），逻辑从原 `xhs_crawl.py` 移植。完整代码必须内联（Task 10 会删除源文件）。

- [ ] **Step 1: 替换 DOM 函数占位块**

In `xhs_batch.py`, replace the "DOM/编排函数占位" comment block with:

```python
# ── DOM 工具函数（harness 内运行，引用 js/cdp 全局） ──────

BAD_ELEMENTS = ['发布', '下载APP', '登录', '注册']


def safe_js(s):
    try:
        return js(s)
    except Exception:
        ensure_daemon(); ensure_real_tab(); time.sleep(1.0)
        try:
            return js(s)
        except Exception:
            return None


def safe_cdp(method, **kw):
    try:
        return cdp(method, **kw)
    except Exception:
        ensure_daemon(); ensure_real_tab(); time.sleep(1.0)
        try:
            return cdp(method, **kw)
        except Exception:
            return None


def jitter(lo, hi):
    return random.uniform(lo, hi)


def delay_after_open():
    return jitter(2, 4)


def delay_scroll():
    return jitter(1, 2)


def delay_expand():
    return jitter(1.5, 3)


def verify_click_target(cx, cy):
    """elementFromPoint 验证坐标处元素。ok=True 可点；isCard=是否 .note-item 后代；
    bad=坏元素。见 gotcha #17。"""
    return safe_js(r'''
var el = document.elementFromPoint(%d, %d);
if (!el) return {ok:false, reason:'no_element'};
var tag = el.tagName;
var cls = el.className || '';
var text = (el.textContent || '').substring(0, 50).trim();
var chain = [];
var p = el;
for (var i = 0; i < 6 && p; i++) {
    var c = p.className || '';
    var t = (p.textContent || '').substring(0, 30).trim();
    chain.push(p.tagName + (c ? '.' + c.split(' ')[0] : '') + (t ? ' "' + t.substring(0,20) + '"' : ''));
    p = p.parentElement;
}
var isCard = false;
p = el;
for (var i = 0; i < 8 && p; i++) {
    if (p.classList && p.classList.contains('note-item')) { isCard = true; break; }
    p = p.parentElement;
}
var bad = false, badReason = '';
var badList = %s;
for (var i = 0; i < badList.length; i++) {
    if (text.indexOf(badList[i]) >= 0) { bad = true; badReason = badList[i]; break; }
    if (cls.indexOf('channel') >= 0 && text.indexOf('发布') >= 0) { bad = true; badReason = 'channel-发布'; break; }
}
return {ok: !bad && isCard, bad: bad, badReason: badReason, isCard: isCard, tag: tag, cls: cls.substring(0,80), text: text.substring(0,40), chain: chain};
''' % (cx, cy, json.dumps(BAD_ELEMENTS)))


def click_card_with_verify(cx, cy):
    """验证 + hover + 点击。返回 (clicked, info)。见 gotcha #3/#17。"""
    info = verify_click_target(cx, cy)
    if not info:
        return False, {"error": "verify_failed"}
    if info.get('bad'):
        print("  ⚠ 跳过: 坐标(%d,%d) → %s | %s" % (cx, cy, info.get('badReason'), info.get('text', '')), flush=True)
        return False, info
    if not info.get('isCard'):
        print("  ⚠ 非卡片: (%d,%d) → %s %s \"%s\"" % (cx, cy, info.get('tag', ''), info.get('cls', ''), info.get('text', '')), flush=True)
        chain = info.get('chain', [])
        if chain:
            print("    chain: " + ' → '.join(chain[:4]), flush=True)
        return False, info
    safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy)
    time.sleep(jitter(0.3, 0.5))
    safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", clickCount=1)
    safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", clickCount=1)
    print("  ✓ 点击: (%d,%d) → %s %s \"%s\"" % (cx, cy, info.get('tag', ''), info.get('cls', ''), info.get('text', '')), flush=True)
    return True, info


def wait_mask_gone(timeout=5):
    """关闭浮窗后轮询 mask 消失。见 gotcha #11。"""
    for _ in range(int(timeout / 0.3)):
        d = safe_js('return document.querySelector(".note-detail-mask") ? getComputedStyle(document.querySelector(".note-detail-mask")).display : "none";')
        if d == 'none':
            return True
        time.sleep(0.3)
    return False
```

- [ ] **Step 2: 语法自检**

Run: `python3 -c "import ast; ast.parse(open('.claude/skills/xhs-crawler/scripts/xhs_batch.py').read())"`
Expected: 无输出。

- [ ] **Step 3: 确认 import 仍安全（守卫未误触发）**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: PASS (10 tests) — 新增的 DOM 函数定义不引用全局直到调用，不影响 import。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py
git commit -m "feat(xhs): add DOM helper functions (safe_js/cdp, click verify, mask wait)"
```

---

## Task 7: 卡片收集 / 定位 / 关闭浮窗

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`

- [ ] **Step 1: 在 wait_mask_gone 之后追加**

```python
def collect_cards():
    """收集搜索页 .note-item 卡片 → [{id, x, y}]（中心坐标）。去重，仅 .note-item 内。
    见 gotcha #12（搜索页元素误判）。"""
    raw = safe_js(r'''
var out = [];
document.querySelectorAll('.note-item').forEach(function(item) {
    var a = item.querySelector('a[href*="/explore/"]');
    if (!a) return;
    var m = /\/explore\/([a-z0-9]+)/i.exec(a.href);
    if (!m) return;
    var rr = item.getBoundingClientRect();
    if (rr.width <= 0 || rr.height <= 0) return;
    out.push({id: m[1], x: Math.round(rr.x + rr.width/2), y: Math.round(rr.y + rr.height/2)});
});
return out;
''') or []
    seen = set(); uniq = []
    for c in raw:
        if c['id'] in seen:
            continue
        seen.add(c['id']); uniq.append(c)
    return uniq


def get_card_rect(note_id):
    """按 id 找卡片中心坐标。不 scrollIntoView（gotcha #2）。返回 {x,y} 或 None。"""
    return safe_js(r'''
var a = document.querySelector('a[href*="/explore/%s"]');
if (!a) return null;
var card = a;
for (var i = 0; i < 8 && card; i++) {
    if (card.classList && card.classList.contains('note-item')) break;
    card = card.parentElement;
}
if (!card || !card.classList || !card.classList.contains('note-item')) return null;
var rr = card.getBoundingClientRect();
if (rr.width <= 0 || rr.height <= 0) return null;
return {x: Math.round(rr.x + rr.width/2), y: Math.round(rr.y + rr.height/2)};
''' % note_id)


def close_overlay():
    """关浮窗：mask 区点击 → 等 mask 消失；失败兜底 Escape。见 gotcha #11。"""
    safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=50, y=400)
    time.sleep(jitter(0.2, 0.4))
    safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=50, y=400, button="left", clickCount=1)
    safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=50, y=400, button="left", clickCount=1)
    if not wait_mask_gone(timeout=3):
        safe_cdp("Input.dispatchKeyEvent", type="rawKeyDown", windowsVirtualKeyCode=27, key="Escape")
        safe_cdp("Input.dispatchKeyEvent", type="keyUp", windowsVirtualKeyCode=27, key="Escape")
        wait_mask_gone(timeout=2)
    time.sleep(jitter(0.5, 1.0))
```

- [ ] **Step 2: 语法自检**

Run: `python3 -c "import ast; ast.parse(open('.claude/skills/xhs-crawler/scripts/xhs_batch.py').read())"`
Expected: 无输出。

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py
git commit -m "feat(xhs): add collect_cards, get_card_rect, close_overlay"
```

---

## Task 8: 评论加载 + 单篇提取 extract_note

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`

从原 `xhs_crawl.py` 移植 meta + 评论提取，封装为 `wait_for_comments()` 与 `extract_note(note_id)`。后者返回 `(ok, data)` 并调用 `compute_threads`。

- [ ] **Step 1: 在 close_overlay 之后追加 wait_for_comments**

```python
def wait_for_comments():
    """滚动加载评论（stall≥5 判底）+ 展开 .show-more/.expand-btn（hover-gated）。见 gotcha #3/#10。"""
    last = 0; stall = 0
    for _ in range(60):
        safe_js('var s=document.querySelector(".note-scroller");if(s){s.scrollTop=s.scrollHeight;}return 1;')
        time.sleep(delay_scroll())
        c = safe_js('return document.querySelectorAll(".comment-item").length;') or 0
        if c == last:
            stall += 1
        else:
            stall = 0; last = c
        if stall >= 5:
            break
    for _ in range(80):
        btn = safe_js(r'''
var best = null, bestY = Infinity;
var all1 = document.querySelectorAll('.show-more');
for (var i = 0; i < all1.length; i++) {
    var el = all1[i]; var t = el.textContent.trim();
    if (!/展开/.test(t) && !/查看/.test(t)) continue;
    el.scrollIntoView({block:"center"});
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (r.y < bestY) { bestY = r.y; best = {t:t, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}; }
}
var all2 = document.querySelectorAll('.expand-btn');
for (var i = 0; i < all2.length; i++) {
    var el = all2[i]; var t = el.textContent.trim();
    if (t.indexOf('展开') < 0) continue;
    el.scrollIntoView({block:"center"});
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (r.y < bestY) { bestY = r.y; best = {t:t, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}; }
}
return best;
''')
        if not btn:
            break
        safe_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=btn['x'], y=btn['y'])
        time.sleep(jitter(0.3, 0.5))
        safe_cdp("Input.dispatchMouseEvent", type="mousePressed", x=btn['x'], y=btn['y'], button="left", clickCount=1)
        safe_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=btn['x'], y=btn['y'], button="left", clickCount=1)
        time.sleep(delay_expand())
```

- [ ] **Step 2: 追加 extract_note**

```python
def extract_note(note_id):
    """提取当前已打开浮窗的笔记。返回 (ok, data)。
    失败判定 = meta 为空（无标题），见 spec。返回 data 含 note_id/meta/comments/total_comments。"""
    meta = safe_js(r'''
var title = (document.querySelector("#detail-title")||{}).textContent || document.title || "";
var descEl = document.querySelector("#detail-desc,.desc");
var desc = descEl ? (descEl.innerText||"").replace(/\s+/g," ").trim() : "";
var bar = document.querySelector('.engage-bar, [class*="engage"]');
var barText = bar ? bar.innerText.replace(/\s+/g,' ').trim() : "";
var hasVideo = !!document.querySelector('video');
var slides = document.querySelectorAll('.swiper-slide');
var noteImgs = []; var seen = {};
slides.forEach(function(s) {
    var img = s.querySelector('img');
    if (!img) return; var src = img.src || '';
    if (!src || seen[src]) return; seen[src] = true;
    noteImgs.push(src);
});
var active = document.querySelector('.swiper-slide-active img');
var activeSrc = active ? active.src : '';
var startIdx = noteImgs.indexOf(activeSrc);
if (startIdx > 0) {
    var ordered = [];
    for (var i = 0; i < noteImgs.length; i++) {
        ordered.push(noteImgs[(startIdx + i) % noteImgs.length]);
    }
    noteImgs = ordered;
}
return {title:title, desc:desc, barText:barText, hasVideo:hasVideo, noteImgs:noteImgs};
''') or {}
    if not meta or not meta.get('title'):
        return False, {'note_id': note_id, 'reason': 'empty_meta'}

    wait_for_comments()
    total = safe_js('return document.querySelectorAll(".comment-item").length;') or 0
    comments = safe_js(r'''
var out = [];
document.querySelectorAll(".comment-item").forEach(function(it) {
    try {
        var p = it.parentElement, lvl = 1;
        while (p) { if (p.classList && p.classList.contains("reply-container")) { lvl=2; break; } p=p.parentElement; }
        var nick = (it.querySelector(".name")||{}).textContent||"";
        nick = nick.replace(/\s+/g," ").trim();
        var contentEl = it.querySelector(".note-text")
            || it.querySelector(".ai-comment-text-container")
            || it.querySelector(".text-content")
            || it.querySelector(".desc");
        var content = contentEl ? (contentEl.innerText||"").replace(/\s+/g," ").trim() : "";
        var locEl = it.querySelector(".location");
        var ip = locEl ? (locEl.textContent||"").replace(/\s+/g," ").trim() : "";
        var dateEl = it.querySelector(".date");
        var dateText = "";
        if (dateEl) { var d=(dateEl.textContent||"").replace(/\s+/g," ").trim(); dateText=ip?d.replace(ip,"").trim():d; }
        function cnt(s){var e=it.querySelector(s);if(!e)return"0";var t=(e.textContent||"").replace(/\s+/g,"").trim();return /^\d+$/.test(t)?t:"0";}
        var likes=cnt(".interactions .like .count")||cnt(".like .count");
        var replies=cnt(".interactions .reply .count")||cnt(".reply .count");
        var imgs=[];
        it.querySelectorAll("img").forEach(function(img){
            var src=img.src||""; var cls=img.className||"";
            if(src&&src.indexOf("avatar")<0&&cls.indexOf("emoji")<0) imgs.push(src);
        });
        if(nick||content) out.push({lvl:lvl,nick:nick,content:content,date:dateText,ip:ip,likes:likes,replies:replies,imgs:imgs});
    } catch(e) {}
});
return out;
''') or []
    comments = compute_threads(comments)
    return True, {'note_id': note_id, 'meta': meta, 'comments': comments, 'total_comments': total}
```

- [ ] **Step 3: 语法自检**

Run: `python3 -c "import ast; ast.parse(open('.claude/skills/xhs-crawler/scripts/xhs_batch.py').read())"`
Expected: 无输出。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py
git commit -m "feat(xhs): add wait_for_comments and extract_note (returns ok,data)"
```

---

## Task 9: health_check + run_batch 主编排

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_batch.py`

- [ ] **Step 1: 用真实实现替换 run_batch 占位（含 health_check）**

Replace the existing `run_batch()` function (the scaffold one that just prints) with:

```python
def health_check(note_count):
    """每 N 篇心跳：document.title 异常则重连。真正的单调用恢复由 safe_js 兜底。"""
    title = safe_js('return document.title;')
    if title is None:
        print("  [health] #%d 连接异常，重连..." % note_count, flush=True)
        try:
            ensure_daemon(); ensure_real_tab()
        except Exception as e:
            print("  [health] 重连失败: %s" % e, flush=True)


def run_batch():
    keyword = os.environ.get('XHS_KEYWORD', '').strip()
    if not keyword:
        print("ERROR: 必须设置 XHS_KEYWORD"); return
    target = int(os.environ.get('XHS_TARGET', '20'))
    max_retry = int(os.environ.get('XHS_MAX_RETRY', '2'))
    outdir = os.environ.get('XHS_OUTDIR') or os.path.join(
        'xhs_data', datetime.datetime.now().strftime('%Y%m%d') + '_' + keyword[:10])
    total_attempts = max_retry + 1

    ensure_daemon(); ensure_real_tab()

    # 1) 会话首次导航到搜索页（不触发 gotcha #16）
    url = ('https://www.xiaohongshu.com/search_result?keyword='
           + encode_keyword(keyword) + '&source=web_explore_feed')
    new_tab(url)
    wait_for_load()
    # 2) 滚动加载更多卡片
    for _ in range(6):
        safe_js('window.scrollBy(0, 1200);')
        time.sleep(0.8)
    # 3) 收集 + 瀑布流排序
    cards = collect_cards()
    order = waterfall_sort(cards)
    # 回顶，确保点击时卡片在视口（gotcha #14）
    safe_js('window.scrollTo(0, 0);')
    time.sleep(0.5)

    # 4) 状态：加载 + 双保险 seed（state.json 的 done ∪ 磁盘已存 JSON）
    state = load_state(outdir) or default_state(keyword, target)
    state['order'] = order
    done = set(state.get('done', [])) | seed_done_from_disk(outdir)
    state['done'] = sorted(done)
    save_state(outdir, state)

    pending = [i for i in order if i not in done]
    print("目标 %d 篇，实际收 %d 张卡片，已完成 %d，待爬 %d" % (
        target, len(order), len(done), len(pending)), flush=True)

    idx = 0
    for note_id in order:
        if note_id in done:
            continue
        if len(done) >= target:
            break
        idx += 1
        print("\n[%d/%d] %s" % (len(done) + 1, target, note_id), flush=True)

        success = False
        last_reason = 'unknown'
        for attempt in range(1, total_attempts + 1):
            if attempt > 1:
                close_overlay()
                time.sleep(jitter(0.5, 1.0))
            rect = get_card_rect(note_id)
            if not rect:
                last_reason = 'card_not_found'
                print("  ✗ 找不到卡片，重试 %d/%d" % (attempt, total_attempts), flush=True)
                continue
            clicked, _ = click_card_with_verify(rect['x'], rect['y'])
            if not clicked:
                last_reason = 'click_verify_failed'
                print("  ✗ 点击未通过验证，重试 %d/%d" % (attempt, total_attempts), flush=True)
                time.sleep(jitter(0.5, 1.0))
                continue
            time.sleep(delay_after_open())
            ok, data = extract_note(note_id)
            if ok:
                # 增量落盘：先写笔记 JSON，再更新 state（崩溃安全）
                with open(os.path.join(outdir, note_id + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                done.add(note_id)
                state['done'] = sorted(done)
                save_state(outdir, state)
                print("  ✓ ok (%d 评论, %d 图)" % (
                    data['total_comments'], len(data['meta'].get('noteImgs', []))), flush=True)
                success = True
                break
            else:
                last_reason = data.get('reason', 'empty')
                print("  ✗ 提取失败(%s)，重试 %d/%d" % (last_reason, attempt, total_attempts), flush=True)

        if not success:
            state['failed'].append({'id': note_id, 'reason': last_reason, 'attempts': total_attempts})
            save_state(outdir, state)
            print("  ✗✗ 放弃 %s → failed(%s)" % (note_id, last_reason), flush=True)
            close_overlay()

        # 每 5 篇健康检查
        if idx % 5 == 0:
            health_check(idx)

        # 笔记间限速 + 15% 长停顿（防封，见 SKILL.md 速度控制）
        time.sleep(jitter(3, 8))
        if random.random() < 0.15:
            time.sleep(jitter(5, 10))

    # 收尾
    state['done'] = sorted(done)
    save_state(outdir, state)
    failed = state.get('failed', [])
    print("\n==== 完成 ====", flush=True)
    print("已爬 %d 篇，失败 %d 篇 → %s" % (len(done), len(failed), outdir), flush=True)
    if failed:
        print("失败: " + ', '.join(f['id'] for f in failed), flush=True)
```

- [ ] **Step 2: 语法自检**

Run: `python3 -c "import ast; ast.parse(open('.claude/skills/xhs-crawler/scripts/xhs_batch.py').read())"`
Expected: 无输出。

- [ ] **Step 3: 确认 import 安全（守卫未误触发 run_batch）**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: PASS (10 tests) — run_batch 现已实现，但因 `'js' not in dir()`，import 时不触发。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_batch.py
git commit -m "feat(xhs): implement run_batch orchestrator (resume/retry/incremental/health)"
```

---

## Task 10: 删除 xhs_crawl.py

**Files:**
- Delete: `.claude/skills/xhs-crawler/scripts/xhs_crawl.py`

- [ ] **Step 1: 确认逻辑已迁移（抽查）**

Run: `grep -c "verify_click_target\|wait_mask_gone\|empty_meta" .claude/skills/xhs-crawler/scripts/xhs_batch.py`
Expected: ≥3（函数与失败原因都已在新文件中）。

- [ ] **Step 2: 删除文件**

```bash
git rm .claude/skills/xhs-crawler/scripts/xhs_crawl.py
```

- [ ] **Step 3: 删除遗留 pycache**

```bash
rm -f .claude/skills/xhs-crawler/scripts/__pycache__/xhs_crawl.cpython-*.pyc
```

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(xhs): remove xhs_crawl.py (logic merged into xhs_batch.py)"
```

---

## Task 11: xhs_export.py — 并行下载 + 删除重复线程逻辑

**Files:**
- Modify: `.claude/skills/xhs-crawler/scripts/xhs_export.py`

目标：① 加 `download_all`（ThreadPoolExecutor 并行）；② `build_excel` 先预下载所有图片、嵌入时按 URL 查本地路径（不再逐张下载）；③ 删除重复的线程逻辑。

- [ ] **Step 1: 加并行下载器**

In `scripts/xhs_export.py`, add `from concurrent.futures import ThreadPoolExecutor` to the top imports (after the existing `import json, os, sys, ...` line). Then after the existing `download_image` function, add:

```python
def download_all(urls, img_dir, prefix):
    """并行下载去重图片到 img_dir。返回 {url: local_path}（所有 url，含已存在的）。"""
    os.makedirs(img_dir, exist_ok=True)
    url_map = {}
    for idx, url in enumerate(dict.fromkeys(urls)):          # 去重保序
        url_map[url] = os.path.join(img_dir, '%s_%d.jpg' % (prefix, idx))
    def work(item):
        download_image(item[0], item[1])
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, url_map.items()))
    return url_map
```

`download_image` 本身保持不变（仍带 Referer 头 + 缓存）。

- [ ] **Step 2: build_excel 预下载所有图片**

In `build_excel`, immediately after the line `all_dl_map = {}  # url -> local path` (near the top of the function, before the note loop), insert a pre-download pass:

```python
    # 预下载所有图片（并行），嵌入阶段按 url 查本地路径
    all_urls = []
    for n in notes:
        all_urls.extend(n.get('meta', {}).get('noteImgs', []))
        for c in n.get('comments', []):
            all_urls.extend(c.get('imgs', [])[:2])
    all_dl_map = download_all(all_urls, img_dir, 'img')
```

Then **delete** the original `all_dl_map = {}  # url -> local path` line (now superseded).

- [ ] **Step 3: 嵌入阶段改用 all_dl_map，去掉逐张下载**

In the **post-image** loop, replace:

```python
            fpath = os.path.join(img_dir, f'post_{note_idx}_{img_idx}.jpg')
            download_image(img_url, fpath)
            all_dl_map[img_url] = fpath

            if img_idx > 0:
```

with:

```python
            fpath = all_dl_map.get(img_url, os.path.join(img_dir, 'post_%d_%d.jpg' % (note_idx, img_idx)))

            if img_idx > 0:
```

In the **comment-image** loop, replace:

```python
                        fpath = os.path.join(img_dir, f'cmt_{comment_seq}.jpg')
                        download_image(img_url, fpath)
                        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
```

with:

```python
                        fpath = all_dl_map.get(img_url, os.path.join(img_dir, 'cmt_%d.jpg' % comment_seq))
                        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
```

(两处嵌入仍用 `os.path.exists + getsize` 守卫，下载失败则该格留空——行为不变，只是下载已是并行预完成。)

- [ ] **Step 4: 删除重复线程逻辑**

In `build_excel`, find the comment-thread recompute block:

```python
            # 构建线程关系
            thread_id = 0; current_thread = 0
            for c in comments:
                if c['lvl'] == 1:
                    thread_id += 1; current_thread = thread_id
                    c['thread_id'] = thread_id; c['reply_to'] = ''
                else:
                    c['thread_id'] = current_thread; c['reply_to'] = ''
            for i, c in enumerate(comments):
                if c['lvl'] == 2:
                    for j in range(i-1, -1, -1):
                        if comments[j]['nick'] != c['nick']:
                            c['reply_to'] = comments[j]['nick']; break
```

Replace with:

```python
            # 线程关系已由 xhs_batch.compute_threads 写入 JSON，直接信任，不重算。
```

- [ ] **Step 5: 语法自检**

Run: `python3 -c "import ast; ast.parse(open('.claude/skills/xhs-crawler/scripts/xhs_export.py').read())"`
Expected: 无输出。

- [ ] **Step 6: 干跑导出（用任意现有 JSON 目录，若无则跳过）**

Run: `ls .claude/skills/xhs-crawler/xhs_data 2>/dev/null || ls xhs_data 2>/dev/null || echo "无数据，跳过干跑"`
若有数据目录 `D`：`python3 .claude/skills/xhs-crawler/scripts/xhs_export.py <D> /tmp/xhs_test.xlsx`
Expected: 生成 xlsx 无异常；线程关系（回复→）来自 JSON、与改前一致；图片嵌入正常。

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/xhs-crawler/scripts/xhs_export.py
git commit -m "perf(xhs): parallel image download + drop duplicated thread logic"
```

---

## Task 12: 更新 SKILL.md — 指向 xhs_batch.py + 断点续爬说明

**Files:**
- Modify: `.claude/skills/xhs-crawler/SKILL.md`

- [ ] **Step 1: 替换 Step 3 章节**

Open `.claude/skills/xhs-crawler/SKILL.md`. Find the "### Step 3: 一趟跑完（关键！）" section (整段伪代码). Replace that entire section (from "### Step 3" up to but not including "### Step 4: 导出 Excel") with:

```markdown
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
```

- [ ] **Step 2: 更新"前提"中的脚本引用（如有）**

Run: `grep -n "xhs_crawl\|xhs_export\|一趟提取" .claude/skills/xhs-crawler/SKILL.md`
对每个 `xhs_crawl` 引用：改为 `xhs_batch`（extract_note）或删除。`xhs_export` 引用保留（仍用于 Step 4）。

- [ ] **Step 3: 更新 Step 4 导出章节（指向新文件名，若已变）**

Step 4 提到 `scripts/xhs_export.py` — 文件名未变，保持。仅确认路径仍正确。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/xhs-crawler/SKILL.md
git commit -m "docs(xhs): rewrite Step 3 to use xhs_batch.py; document resume"
```

---

## Task 13: 全量验证

**Files:** 无（仅验证）

- [ ] **Step 1: 两个脚本语法自检**

Run:
```bash
python3 -c "import ast; ast.parse(open('.claude/skills/xhs-crawler/scripts/xhs_batch.py').read()); ast.parse(open('.claude/skills/xhs-crawler/scripts/xhs_export.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 2: 纯函数全量单测**

Run: `cd .claude/skills/xhs-crawler && python3 -m pytest tests/test_xhs_batch_pure.py -v`
Expected: PASS (10 tests)。

- [ ] **Step 3: 守卫验证 — 普通 python 不触发 run_batch**

Run: `python3 .claude/skills/xhs-crawler/scripts/xhs_batch.py; echo "exit=$?"`
Expected: 无 `[xhs_batch]` / 无 `run_batch` 输出，`exit=0`（守卫生效，import 安全）。

- [ ] **Step 4: harness 入口验证 — 守卫为 True 时执行（需带 KEYWORD，否则 run_batch 早退）**

Run: `XHS_KEYWORD="" browser-harness < .claude/skills/xhs-crawler/scripts/xhs_batch.py 2>&1 | tail -5`
Expected: 打印 `ERROR: 必须设置 XHS_KEYWORD`（证明 `'js' in dir()` 守卫为 True，run_batch 被调用）。⚠️ 此步会连真实浏览器；若 Chrome 未连接可跳过，靠 Step 1-3 已充分验证逻辑。

- [ ] **Step 5: 真实冒烟测试（用户侧，需登录态）**

在已登录 Chrome 上：
```bash
XHS_KEYWORD="<小词>" XHS_TARGET=3 \
  browser-harness < .claude/skills/xhs-crawler/scripts/xhs_batch.py
```
确认：① 3 篇 `{id}.json` 落盘 ② `state.json` done=3 ③ Ctrl-C 后重跑跳过已完成 ④ export 生成 xlsx 且图片嵌入、回复关系正确。

- [ ] **Step 6: 最终 commit（若有改动）**

```bash
git add -A .claude/skills/xhs-crawler
git commit -m "test(xhs): full verification (ast, pytest, guard, smoke)"
```

---

## Self-Review（写计划后自检）

**Spec 覆盖**：
- §1 文件结构 / 删 xhs_crawl.py → Task 1, 10 ✓
- §2 断点续爬 state.json + 双保险 seed → Task 5（IO）+ Task 9（run_batch 用法）✓
- §3 增量落盘 → Task 9（先写 JSON 再写 state）✓
- §4 单篇重试 + 失败日志 → Task 9（retry 循环 + failed[]）✓
- §5 连接健康检查 → Task 9（health_check）✓
- §6 export 并行下载 + 删重复线程 → Task 11 ✓
- §7 限速 → Task 9（jitter + 15% 长停顿）✓
- SKILL.md 更新 → Task 12 ✓
- 测试/验证（ast + 单测 + 实跑）→ Task 13 ✓

**占位符扫描**：无 TBD/TODO；每个代码步骤含完整代码；DOM 函数全量内联（Task 10 删源后仍可用）。

**类型/命名一致性**：`extract_note(note_id) -> (ok, data)`；data 含 `note_id/meta/comments/total_comments`；`compute_threads` 在 extract_note 与 export 间签名一致；`seed_done_from_disk` 只收 8 位 hex（与小红书 8 位 id 一致，state 测试覆盖）。

**遗留**：Step 4（harness 入口）与 Step 5（冒烟）依赖真实浏览器/登录态，标注为可跳过/用户侧，逻辑验证不依赖它们。
