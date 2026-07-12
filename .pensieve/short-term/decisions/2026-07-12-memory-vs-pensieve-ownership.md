---
id: memory-vs-pensieve-ownership
type: decision
title: 项目技术知识与个人记忆的所有权边界
status: active
created: 2026-07-12
updated: 2026-07-12
tags: [pensieve, decision, memory, knowledge, ownership]
---

# 项目技术知识与个人记忆的所有权边界

## 一句话结论
> 项目技术知识（browser-harness 连接/排错、xhs-crawler 运行坑、lark-cli 操作、VL/OCR 模型等"在哪/怎么调/踩过什么坑"）归 `.pensieve/knowledge/`；个人记忆（`~/.claude/.../memory/`）只留 user 偏好、feedback 工作方式、个人 project 上下文。

## 上下文链接
- 相关：[[knowledge/xhs-crawler-ops/content]]
- 相关：[[knowledge/feishu-lark-cli-ops/content]]
- 相关：[[knowledge/browser-harness-connection/content]]

## Context

这个项目长期把技术笔记（harness 连接调试、xhs-crawler 运行坑、lark-cli 飞书操作、VL/OCR 模型）堆在个人记忆里——18 条记忆里有 10 条是技术参考。三个问题：①个人记忆和项目知识混在一起，检索噪音大；②技术笔记在 `~/.claude` 下、不进 git、不随仓库走、不能交叉互链、不可跨会话复用；③pensieve 的 `knowledge/`（定位就是"已探索的文件位置/模块边界/调试路径"）反而空置，只有 2 条。

## Problem

新的技术经验该写哪？没有明确边界 → 默认全塞个人记忆 → 重复堆叠 → 定期返工清理（本次整理就是：10 条技术记忆迁回 pensieve）。

## Alternatives Considered
- **全留个人记忆**：技术笔记不进 git、不随项目走、和偏好混在一起，噪音大，且 doctor/graph 检索不到。被否。
- **全进 pensieve**：个人偏好 / feedback / 个人 IP 与财务上下文也进项目仓库——泄露隐私、跨项目不通用、混入公开 repo。被否。

## Decision

按语义分层切所有权：

- **进 `.pensieve/knowledge/`**（进 git、随仓库、可互链）：项目特有、可复用、面向"是哪个文件/在哪/怎么查/踩过什么坑/症状→根因→定位"的技术知识。
- **留个人记忆**：纯个人的 user 身份/偏好、feedback 工作方式、个人 project 上下文（公众号 IP、财务规划、AI 百科组织模型等）。

判定口诀：新经验入库前先问"这是项目技术还是个人偏好"——技术调试/操作配方/脚本行为 → pensieve knowledge；个人风格/偏好/私人项目方向 → 记忆。

## Consequence

本次整理落地：个人记忆 18 → 8（只剩 user/feedback/个人 project）；pensieve `knowledge/` 2 → 7。新经验按此边界分流，避免再次堆叠返工。

## 探索减负
- **下次可以少问什么**：不用再问"这条写记忆还是 pensieve"——项目技术调试/操作配方默认 pensieve knowledge，个人偏好默认记忆。
- **下次可以少查什么**：找技术参考直接看 `.pensieve/knowledge/`（doctor/graph 可检索），不用翻个人记忆目录。
- **失效条件**：若该项目不再用 pensieve 做 knowledge 主库、或个人记忆系统被废弃，此边界需重新界定。
