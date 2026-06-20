# Gemini 生图提示词技巧

## 基本结构

一个好的图片提示词包含 4 个要素：

```
[主体] + [场景/环境] + [风格/氛围] + [技术约束]
```

示例：
```
A cozy desk scene with a laptop displaying a todo list app, a cup of coffee,
and a small potted plant. Warm lighting, minimalist style, soft colors.
The mood is encouraging and hopeful, not intimidating.
No text overlay. Aspect ratio 16:9.
```

## 比例/尺寸

| 用途 | 比例 | 提示词 |
|------|------|--------|
| 公众号封面 | 2.35:1 | "Aspect ratio 2.35:1" 或 "900x383" |
| 公众号文中插图 | 16:9 | "Aspect ratio 16:9" |
| 小红书封面 | 3:4 | "Aspect ratio 3:4" 或 "Square format" |
| 方形头像 | 1:1 | "Square format" |

## 风格关键词

### 科技/商业
- `minimalist flat design` — 扁平简约
- `clean modern illustration` — 干净现代插画
- `corporate Memphis` — 企业孟菲斯风
- `isometric 3D` — 等距 3D

### 温暖/生活
- `watercolor style` — 水彩风
- `cozy warm lighting` — 温暖灯光
- `soft pastel colors` — 柔和粉彩
- `Studio Ghibli inspired` — 吉卜力风

### 专业/严肃
- `professional photograph` — 专业摄影
- `editorial illustration` — 社论插画
- `dark moody atmosphere` — 暗调氛围

## 情绪关键词

| 想要的感觉 | 关键词 |
|-----------|--------|
| 鼓励 | encouraging, hopeful, warm, inviting |
| 专业 | professional, clean, sharp, polished |
| 有趣 | playful, fun, whimsical, quirky |
| 安静 | calm, peaceful, serene, minimal |
| 紧张 | dramatic, intense, bold, striking |

## 避免生成文字

Gemini 生成的图片中的文字通常是乱码。如需文字，建议后期叠加：

```
No text, no words, no letters, no typography.
```

## 负面提示词

用 "not" 排除不想要的元素：

```
not scary, not dark, not cluttered, not photorealistic
```

## 实战案例

### 公众号封面（科技文章）
```
A clean, modern illustration for a tech blog article about first coding projects.
Show a cozy desk scene with a laptop displaying a simple todo list app,
a cup of coffee, and a small potted plant. Warm lighting, minimalist style,
soft colors. The mood is encouraging and hopeful, not intimidating.
No text overlay. Aspect ratio 16:9.
```

### 概念图（对比/二选一）
```
A simple, clean infographic illustration showing two doors side by side.
Left door labeled 'Practice' with a warm glow, right door labeled 'Product'
with a bright spotlight. The Practice door is welcoming and achievable,
the Product door is more polished but distant. Minimalist flat design,
soft pastel colors, no text, conceptual illustration. Square format.
```

### 情感共鸣图
```
A person sitting at a desk looking at a laptop screen with a mix of
frustration and determination. Empty coffee cups scattered around.
Warm lamp light. The scene feels relatable and human, not sterile.
No text. Aspect ratio 16:9.
```

### 数据/信息图背景
```
Abstract geometric background with subtle gradient from blue to purple.
Clean, modern, suitable for overlaying text and charts.
No objects, no people, no text. Minimalist. Aspect ratio 16:9.
```
