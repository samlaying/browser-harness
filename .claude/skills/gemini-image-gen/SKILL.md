---
name: gemini-image-gen
description: |
  使用 Google Gemini 生成图片。触发条件：用户提到"用 Gemini 生图"、"Gemini 生成图片"、
  "AI 配图"、"生成封面"、"生成插图"，或需要为文章/公众号/小红书生成配图时自动触发。
  前提：browser-harness 已连接 Chrome，且 Chrome 中已登录 Gemini (gemini.google.com)。
---

# Gemini 图片生成

通过 browser-harness 控制已登录的 Chrome 浏览器，在 Gemini Images 页面生成图片并下载。

## 前提

1. browser-harness 已安装（`uv tool install -e ~/browser-harness`）
2. Chrome 已连接（`chrome://inspect` 勾选远程调试）
3. **已登录 Google 账号**，且能访问 `gemini.google.com/images`
4. Gemini 页面已打开（如果没有，用 `new_tab("https://gemini.google.com/images")` 打开）

## 浏览器说明

- 使用 **browser-harness 连接的 Chrome 实例**（通过 CDP 协议）
- 如果用户有多个 Chrome 实例，确保 Gemini 所在的那个已连接到 daemon
- Gemini 需要 Google 账号登录，未登录会跳转到登录页（遇到登录页时停止并告知用户）

## 单张图片生成流程

### Step 1: 打开 Gemini Images 页面

```bash
browser-harness <<'PY'
new_tab("https://gemini.google.com/images")
wait_for_load()
print(page_info())
PY
```

### Step 2: 输入提示词并发送

```bash
browser-harness <<'PY'
import time

# 聚焦输入框
js('''
var el = document.querySelector("div[contenteditable='true']");
if (el) el.focus();
return !!el;
''')
time.sleep(0.5)

# 输入提示词（用 CDP insertText，避免中文输入法问题）
cdp("Input.insertText", text="YOUR_PROMPT_HERE")
time.sleep(0.5)

# 按 Enter 发送（不要用鼠标点击发送按钮——点击不可靠）
cdp("Input.dispatchKeyEvent", type="rawKeyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)
time.sleep(0.1)
cdp("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)
PY
```

### Step 3: 等待图片生成

```bash
browser-harness <<'PY'
import time

for i in range(30):
    time.sleep(2)
    creating = js('return document.body.innerText.includes("Creating your image");')
    imgs = js('var c=0; document.querySelectorAll("img").forEach(function(i){if(i.naturalWidth>200)c++}); return c;')
    print(f"  Check {i+1}: {imgs} images, creating={creating}")
    if not creating and imgs and imgs > 0:
        print("Image generated!")
        break
PY
```

### Step 4: 下载图片（blob URL → 本地文件）

Gemini 生成的图片是 `blob:` URL，无法直接下载。需要用 Canvas 转为 base64 再保存：

```bash
browser-harness <<'PY'
import base64

result = js('''
var imgs = document.querySelectorAll("img[src^='blob:']");
var best = null;
for (var i = 0; i < imgs.length; i++) {
    if (imgs[i].naturalWidth > 200) best = imgs[i];
}
if (!best) return null;
var canvas = document.createElement('canvas');
canvas.width = best.naturalWidth;
canvas.height = best.naturalHeight;
canvas.getContext('2d').drawImage(best, 0, 0);
return canvas.toDataURL('image/png');
''')

if result and result.startswith('data:image'):
    b64 = result.split(',', 1)[1]
    img_bytes = base64.b64decode(b64)
    out = "/path/to/output.png"
    with open(out, 'wb') as f:
        f.write(img_bytes)
    print(f"Saved: {out} ({len(img_bytes)} bytes)")
PY
```

## 多张图片生成

在同一会话中可连续生成多张图片。每张图片生成后：

1. 下载当前图片
2. **滚动到页面底部**找到输入框
3. 输入下一条提示词
4. 按 Enter 发送
5. 重复等待-下载流程

**注意**：Gemini 会话有上下文，新提示词可能参考之前的图片风格。如果需要完全独立的风格，建议新开会话。

## 提示词技巧

| 技巧 | 说明 |
|------|------|
| 用英文 | 英文提示词生成质量通常更高 |
| 指定比例 | "Aspect ratio 16:9" / "Square format" / "3:4" |
| 描述风格 | "minimalist flat design" / "watercolor" / "3D render" |
| 避免文字 | "No text overlay" / "no words" — 防止生成乱码文字 |
| 描述情绪 | "warm and encouraging" / "clean and professional" |
| 指定场景 | 具体描述场景元素，比抽象描述效果更好 |

## 反爬 / 注意事项

| 规则 | 说明 |
|------|------|
| 发送用 Enter | 鼠标点击发送按钮不可靠，始终用 Enter 键 |
| 等待创建完成 | 检查 "Creating your image" 文字消失 + 图片 naturalWidth > 200 |
| blob URL 转换 | 必须用 Canvas → toDataURL → base64 解码保存 |
| 不要频繁请求 | 每张图片间隔 3-5 秒，避免触发限流 |
| 登录状态 | 未登录会跳转登录页，此时停止并告知用户 |

## 已知限制

- **图片质量**：取决于 Gemini 模型版本（当前 Nano Banana 2）
- **文字生成**：AI 生成的图片中文字通常乱码，需要后期处理
- **下载格式**：Canvas 转换后固定为 PNG 格式
- **并发**：同一会话一次只能生成一张图片

## 参考

- 提示词技巧详见 [references/prompt-tips.md](references/prompt-tips.md)
- 已知坑点详见 [references/gotchas.md](references/gotchas.md)
