# Gemini 生图已知坑点

## 1. 发送按钮点击不可靠

**问题**：用 `click_at_xy` 或 JS `btn.click()` 点击 Gemini 的蓝色发送按钮，经常不生效。

**原因**：Gemini 的发送按钮可能有复杂的事件监听，CDP 的合成点击事件不被信任。

**解决**：始终用 Enter 键发送。先 `Input.insertText` 输入提示词，再 `Input.dispatchKeyEvent` 按 Enter：

```python
# ❌ 不可靠
js('document.querySelector("button[aria-label=\'Send message\']").click()')

# ✅ 可靠
cdp("Input.insertText", text=prompt)
cdp("Input.dispatchKeyEvent", type="rawKeyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13)
cdp("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
```

## 2. 中文输入法问题

**问题**：直接用 `js` 的 `input.value = "中文"` 赋值，中文可能无法正确触发 Gemini 的输入事件。

**解决**：用 CDP 的 `Input.insertText`，它模拟真实输入，支持中文和特殊字符。

## 3. blob URL 无法直接下载

**问题**：Gemini 生成的图片使用 `blob:` URL（如 `blob:https://gemini.google.com/xxx`），无法通过 HTTP 下载。

**解决**：用 Canvas 将 blob 图片转为 base64 data URL，再解码保存：

```javascript
var canvas = document.createElement('canvas');
canvas.width = img.naturalWidth;
canvas.height = img.naturalHeight;
canvas.getContext('2d').drawImage(img, 0, 0);
return canvas.toDataURL('image/png');
```

## 4. "Creating your image" 状态判断

**问题**：图片生成中和生成完成的 DOM 状态变化不够明显。

**解决**：双重检查——"Creating your image" 文字消失 **且** `img.naturalWidth > 200`：

```python
creating = js('return document.body.innerText.includes("Creating your image");')
imgs = js('var c=0; document.querySelectorAll("img").forEach(function(i){if(i.naturalWidth>200)c++}); return c;')
if not creating and imgs > 0:
    print("Done!")
```

## 5. 多张图片时取错图

**问题**：页面上可能有多个 `blob:` 图片（头像、icon 等），下载到的不是目标图。

**解决**：用 `naturalWidth > 200` 过滤小图，或按尺寸精确匹配：

```javascript
// 取最新的大图
var imgs = document.querySelectorAll("img[src^='blob:']");
var best = null;
for (var i = 0; i < imgs.length; i++) {
    if (imgs[i].naturalWidth > 200) best = imgs[i];
}
```

## 6. 未登录 Gemini 会跳转登录页

**问题**：Chrome 未登录 Google 账号，或登录已过期，打开 `gemini.google.com` 会跳转到登录页。

**表现**：URL 变为 `accounts.google.com/...`，页面显示登录表单。

**解决**：检测到登录页时停止操作，告知用户需要先登录 Google。不要代替用户输入密码。

## 7. 同一会话上下文污染

**问题**：在同一 Gemini 会话中连续生成多张不同风格的图片，后续提示词可能受前面对话上下文影响。

**解决**：如果需要完全独立的图片风格，新开 Gemini 会话（导航回 `gemini.google.com/images` 首页）。
