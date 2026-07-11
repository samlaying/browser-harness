---
name: xhs-publish
description: 用 browser-harness 在小红书创作者中心发布或暂存图文笔记。触发词——发布小红书、xhs 发布、图文笔记、发布笔记、暂存草稿、暂存离开、上传图文、原创声明、小红书发布页自动化、creator.xiaohongshu.com/publish。覆盖上传图片、填标题/正文/#话题、开原创声明、暂存离开/发布全流程；含 closed shadow 按钮、d-switch、#话题空格确认、导航丢内容等已知坑。
---

# xhs-publish

用 browser-harness 驱动用户**已登录**的 Chrome，在 `creator.xiaohongshu.com/publish/publish` 自动化图文笔记的发布 / 暂存。所有操作经 `browser-harness <<'PY' ... PY` heredoc 执行。

## 前置
- browser-harness 连到已登录小红书创作者中心的 Chrome（右上角有账号头像）。
- 图文发布页 URL：`.../publish/publish?source=official&from=menu&target=image`
- 若当前是视频页（`target=video`），先切 tab（步骤 1）。
- 素材就绪：图片（jpg/png/webp）、标题、正文、#话题列表。

## Process

### 1. 切到图文 tab（仅 target=video 时）
点「上传图文」tab。DOM 精确匹配文本，排除 `x=-9999` 的隐藏 tooltip 副本：
```python
pos = js(r"""(()=>{const h=[...document.querySelectorAll('a,span,div,button,li')].filter(e=>{const t=(e.textContent||'').trim();return t==='上传图文'&&e.children.length===0;});const r=h[0]&&h[0].getBoundingClientRect();return h[0]?{x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}:null;})()""")
click_at_xy(pos['x'], pos['y']); wait_for_load()   # URL 应变 target=image
```

### 2. 上传图片
`input[type=file]` 是 `multiple`，accept jpg/jpeg/png/webp，一次传全部：
```python
upload_file("input[type=file]", [img0, img1, ...])   # 绝对路径列表
```
等待上传完成——**以 `N/18` 文本为准**（数 `<img>` 会混入头像图，不准）：
```python
import time
for _ in range(30):
    time.sleep(2)
    cnt = js(r"(()=>(document.body.innerText.match(/\d+\/18/)||[''])[0])()")
    busy = js(r"(()=>/上传中|上传失败/.test(document.body.innerText))()")
    if cnt and cnt.startswith(f'{N}/') and not busy: break
```

### 3. 填标题
定位 `input[placeholder*="标题"]`，`click_at_xy` + `type_text`：
```python
loc = js(r"""(()=>{const i=[...document.querySelectorAll('input')].find(x=>/标题/.test(x.placeholder||''));if(!i)return null;const r=i.getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};})()""")
click_at_xy(loc['x'], loc['y']); time.sleep(0.3)
type_text('标题文本')   # insertText，支持中文/emoji，对 Vue 受控 input 也会触发 input 事件
```

### 4. 填正文 + #话题
正文是 tiptap（`.ProseMirror`）富文本。
```python
# 定位正文框：document.querySelector('.ProseMirror').getBoundingClientRect()
click_at_xy(body_x, body_y); time.sleep(0.3)
type_text(DESC)            # 描述，含 \n 换行
press_key("Enter")         # ⚠️ 用 Enter 把话题行和描述隔开
for t in topics:
    type_text('#'); time.sleep(0.3)
    type_text(t); time.sleep(1.0)    # 等候选弹窗
    press_key(' '); time.sleep(0.55) # ⚠️ 敲空格确认话题（不是点选候选）
```
验证：`.ProseMirror` 内 `a[data-topic],a.topic,.tiptap-topic` 节点数 == 话题数，且无纯文本 `#残留`。

### 5. 原创声明
`.custom-switch-card`（文字「原创声明」）内 `.d-switch`：
```python
# 开关：用 JS .click()，不要 coordinate click（页面滚动会让坐标落空）
js(r"""(()=>{const c=[...document.querySelectorAll('.custom-switch-card')].find(c=>/原创声明/.test(c.textContent||''));if(c)c.querySelector('.d-switch').click();})()""")
```
开启后弹**二次确认框**。「声明原创」按钮初始 `disabled`（class 含 `disabled`），需先勾同意须知 checkbox，按钮才启用：
```python
# 1) coordinate click 弹窗内 .d-checkbox-simulator（勾「同意须知」）
# 2) 按钮 disabled 变 false 后，coordinate click「声明原创」
```

### 6. 暂存离开 / 发布   ⚠️ closed shadow（核心坑）
按钮组 `.publish-page-publish-btn`（`button.ce-btn.white`=暂存离开，`ce-btn.bg-red`=发布）挂在 **closed shadow root** 内。
- `element.shadowRoot` → `null`；`document.querySelectorAll('.ce-btn')` → 空；递归 walk open shadow 也找不到。
- 主文档还有 1 个 src 为空的 iframe，是**误导**（按钮不在 iframe，contentDocument 访问到也是空 button 列表）。
- **唯一解：CDP pierce**：
```python
doc = cdp("DOM.getDocument", depth=-1, pierce=True)
found = []
def walk(n):
    if not n: return
    if (n.get('nodeName') or '').lower() == 'button':
        a = n.get('attributes') or []
        d = dict(zip(a[0::2], a[1::2]))
        if 'ce-btn' in d.get('class',''): found.append({'nodeId':n['nodeId'],'class':d['class']})
    for c in (n.get('children') or []): walk(c)
    for s in (n.get('shadowRoots') or []): walk(s)   # pierce 下 closed shadow 也在此展开
    if n.get('contentDocument'): walk(n['contentDocument'])
walk(doc['root'])
leave = next(b for b in found if 'white' in b['class'])   # 暂存离开；'bg-red' 是发布
box = cdp("DOM.getBoxModel", nodeId=leave['nodeId'])
b = box['model']['border']; cx, cy = int(sum(b[0::2])/4), int(sum(b[1::2])/4)
click_at_xy(cx, cy)   # compositor 层点击能命中 closed shadow 内元素
```

## Gotchas（实战血泪）
- **不要点任何导航**（「首页」/ logo / 后退）→ 触发跳转 + 表单重置，**标题/正文/话题/图片全丢**。整个流程在一个 tab 内完成，最后才点暂存离开/发布。
- **closed shadow 按钮只能 CDP pierce**，JS / iframe / contentDocument 都无解。
- **d-switch / d-checkbox 用 JS `.click()`**，不要 coordinate click——页面滚动会让坐标落空（原创声明开关坐标会在点击瞬间从 y≈982 跳到 y≈462）。
- **#话题必须逐个 `#词` + 空格**：一次性 `type_text` 整段 `#标签` 只是纯文本，不触发话题选择，发出去没有话题链接。
- **描述与话题间用 `press_key("Enter")`**：`type_text` 末尾的 `\n` 在 tiptap 不换行，会让首个话题插进描述末尾、把末尾文字（如「耐心」）挤到话题后面。
- **`type_text`（insertText）** 支持中文/emoji，但绕过框架事件——标题/正文用它 OK，填完检查字数计数 / 发布按钮是否启用。
- 数已上传图片以 `N/18` 文本为准，别数 `<img>`（混入 sns-avatar 头像）。

## 验证清单（发布前必过）
- [ ] URL `target=image`
- [ ] `N/18` == 图片数
- [ ] 标题 input.value 正确
- [ ] `.ProseMirror` 话题节点数 == 话题数，无纯文本 `#残留`
- [ ] 原创声明 `.d-switch-simulator` 不再 unchecked
- [ ] **发布（非暂存）前截图给用户确认**——发布不可逆
