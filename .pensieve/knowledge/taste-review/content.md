---
id: taste-review-content
type: knowledge
title: 代码品味审查知识库
status: active
created: 2026-02-28
updated: 2026-02-28
tags: [pensieve, knowledge, review, taste]
---

# 代码品味审查知识库

用于代码审查的核心哲学、预警信号与经典案例。

## 来源

- Linus Torvalds 公开分享与 Linux Kernel 风格
- John Ousterhout《A Philosophy of Software Design》
- Google Engineering Practices（Code Review 指南）

## 支撑资料

`source/` 目录可放项目定制参考。语言风格指南建议从官方仓库拉取：

- Google Style Guides: https://github.com/google/styleguide

示例（项目使用 Python + TypeScript）：

```bash
mkdir -p source/google-style-guides
curl -o source/google-style-guides/pyguide.md https://raw.githubusercontent.com/google/styleguide/gh-pages/pyguide.md
curl -o source/google-style-guides/tsguide.html https://raw.githubusercontent.com/google/styleguide/gh-pages/tsguide.html
```

## 摘要

该知识库融合三条主线：

1. Linus：通过数据结构和重写消除特殊分支
2. Ousterhout：通过模块深度与抽象控制复杂度
3. Google：以代码健康为目标，按优先级审查

## 适用场景

- 需要为审查意见提供理论依据
- 需要识别“可运行但不可维护”的实现
- 需要统一团队对复杂度和代码健康的判断口径

---

## 核心原则

### 1) Linus：好品味（Good Taste）

核心思想：
- 通过重构消除特殊情况，而不是堆条件分支
- 先想数据结构，再写控制流
- 控制嵌套深度与函数长度
- 用户可见行为是硬边界（不要随意改变）

### 2) Ousterhout：复杂度管理

三大复杂度症状：

1. **Change amplification**：小改动牵一发动全身
2. **Cognitive load**：改动前需要理解太多前置信息
3. **Unknown unknowns**：不清楚还要改哪里

设计要点：
- 接口要简单、模块要“深”
- 把复杂度尽量下沉到底层
- 至少做两版设计对比（Design it twice）

### 3) Google：代码健康优先

审查顺序建议：

`Design -> Functionality -> Complexity -> Tests -> Naming -> Comments -> Style -> Docs`

实践重点：
- 小而自洽的变更更容易高质量审查
- 改善代码健康的改动不应因“追求完美”被长期阻塞

---

## 预警信号清单

### 结构预警

| 信号 | 阈值 | 严重级别 |
|---|---|---|
| 嵌套层级 | > 3 层 | CRITICAL |
| 函数长度 | > 100 行 | CRITICAL |
| 局部变量数量 | > 10 | WARNING |
| 资源清理路径 | 多出口且分散清理 | WARNING |

### 错误处理预警

| 信号 | 描述 | 严重级别 |
|---|---|---|
| 防御式默认值泛滥 | 例如 `?? 0` / `|| default` 到处出现 | WARNING |
| 异常处理压过主逻辑 | try/catch 比业务代码还多 | CRITICAL |
| fallback 掩盖上游问题 | 导致问题不暴露 | WARNING |

### 模块与接口预警

| 信号 | 描述 | 严重级别 |
|---|---|---|
| 浅模块 | 接口复杂度接近实现复杂度 | CRITICAL |
| 信息泄漏 | 模块内部决策暴露到外部 | CRITICAL |
| 命名困难 | 难以命名、难以解释 | WARNING |

---

## 经典引用（原文）

### Linus Torvalds

- "Bad programmers worry about the code. Good programmers worry about data structures."
- "If you need more than 3 levels of indentation, you're screwed anyway."
- "Sometimes you can see a problem in a different way and rewrite it so that the special case goes away."

### John Ousterhout

- "Shallow modules don't help much in the battle against complexity."
- "Design it twice. You'll end up with a much better result."

### Google Code Review

- "A CL that improves the overall code health of the system should not be delayed for perfection."

---

## 经典案例

### 1) 链表删除：消除特殊分支

**坏味道（存在头节点特殊分支）**：

```c
void remove_list_entry(List *list, Entry *entry) {
    Entry *prev = NULL;
    Entry *walk = list->head;
    while (walk != entry) {
        prev = walk;
        walk = walk->next;
    }
    if (prev == NULL) {
        list->head = entry->next;
    } else {
        prev->next = entry->next;
    }
}
```

**好味道（统一路径）**：

```c
void remove_list_entry(List *list, Entry *entry) {
    Entry **indirect = &list->head;
    while (*indirect != entry)
        indirect = &(*indirect)->next;
    *indirect = entry->next;
}
```

关键点：使用间接指针后，“删除头节点”和“删除中间节点”是同一操作。

### 2) 防御式默认值 vs 快速失败

**不推荐**：

```typescript
function processUser(user: User | null) {
    const name = user?.name ?? "Unknown";
    const email = user?.email ?? "";
    sendEmail(email, `Hello ${name}`);
}
```

**推荐**：

```typescript
function processUser(user: User) {
    sendEmail(user.email, `Hello ${user.name}`);
}
```

关键点：不要吞掉上游错误；让类型系统和测试尽早暴露问题。

---

## 审查落地建议

- 先看设计与复杂度，再看风格细节
- 先抓会导致回归的问题，再处理可选优化
- 所有审查意见尽量绑定“可验证证据”（日志、测试、行为）
- 可沉淀的结论及时写入 `decision` 或 `maxim`
