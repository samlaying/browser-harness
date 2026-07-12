<img src="https://raw.githubusercontent.com/browser-use/media/main/browser-harness/banner-ink.svg" alt="Browser Harness" width="100%" />

# Browser Harness ♞

> 🌐 English: [README.md](README.md)

用一套薄而可编辑的 CDP 线束，把 LLM 直接接到你自己的浏览器。适合需要**完全自由**的浏览器任务。

一条 WebSocket 连到 Chrome，中间没有任何东西。缺的 helper，agent 在执行时自己写。线束每跑一次都在自我改进。

```
  ● agent：想上传一个文件
  │
  ● agent-workspace/agent_helpers.py → 缺这个 helper
  │
  ● agent 自己写上                            agent_helpers.py
  │                                                          + 新 helper
  ✓ 文件已上传
```

**你将再也不需要自己开浏览器了。**

## 安装提示词

粘贴进 Claude Code 或 Codex：

```text
帮我配置 https://github.com/browser-use/browser-harness。

阅读 `install.md`，按步骤安装 browser-harness 并连到我的浏览器。
```

Agent 会打开 `chrome://inspect/#remote-debugging`，勾选复选框让它能连上你的浏览器：

<img src="docs/setup-remote-debugging.png" alt="Remote debugging setup" width="520" style="border-radius: 12px;" />

每次连接弹窗时点 Allow（Chrome 144+）：

<img src="docs/allow-remote-debugging.png" alt="Allow remote debugging popup" width="520" style="border-radius: 12px;" />

示例任务见 [agent-workspace/domain-skills/](agent-workspace/domain-skills/)。

## 免费的 Browser Use 云浏览器

隐身、子 agent、或无头部署。<br>
**Browser Use Cloud 免费档：3 个并发浏览器、代理、验证码自动解决等。无需绑卡。**

- 到 [cloud.browser-use.com/new-api-key](https://cloud.browser-use.com/new-api-key) 领一个 key
- 或让 agent 自己通过 [docs.browser-use.com/llms.txt](https://docs.browser-use.com/llms.txt) 注册（含注册流程 + 挑战上下文）。

## 架构（4 个核心文件，约 1k 行）

- `install.md` — 首次安装与浏览器引导
- `SKILL.md` — 日常使用
- `src/browser_harness/` — 受保护的核心包
- `agent-workspace/agent_helpers.py` — agent 编辑的 helper 代码
- `agent-workspace/domain-skills/` — agent 编辑的可复用站点技能

## 贡献

欢迎 PR 与改进。最好的贡献方式：**提交一个新的 domain skill** 到 [agent-workspace/domain-skills/](agent-workspace/domain-skills/)，针对你常用的站点或任务（LinkedIn 外联、Amazon 下单、报销填报等）。每个技能教会 agent 那些 selector、流程和坑点，省得它每次重新摸索。

- **技能由线束自己写，不是你手写。** 你只管用 agent 跑任务——当它摸索出非显而易见的规律时，它会自己归档成技能（见 [SKILL.md](SKILL.md)）。请不要手工编写技能文件；agent 生成的才反映浏览器里真正能用的东西。
- 把生成的 `agent-workspace/domain-skills/<site>/` 目录提个 PR——小而聚焦就很好。
- 同样欢迎 bug 修复、文档微调和 helper 改进。
- 浏览现有技能（`github/`、`linkedin/`、`amazon/`…）看看长什么样。

不确定从哪开始就开个 issue，我们给你指个方向。

## Domain skills

设 `BH_DOMAIN_SKILLS=1` 启用 [agent-workspace/domain-skills/](agent-workspace/domain-skills/) —— 社区贡献的、按域名由 `goto_url` 自动浮现的站点手册。欢迎提 PR。

## 内置 skills

这个 fork 在 [`.claude/skills/`](.claude/skills/) 下附带了一个通过 harness 在 Claude Code 里运行的 skill：

- [`xhs-crawler`](.claude/skills/xhs-crawler/SKILL.md) — 批量爬取小红书笔记（正文 + 评论 + 图片 → Excel）

## 如何使用

### 浏览器要求

用你日常使用的 **Google Chrome**（或 Chromium）——不要用无头浏览器或一次性浏览器。**先登录**你要爬取的站点（X、小红书等），再启动 harness；harness 复用你浏览器的 cookies，不会让你输入密码。完整连接步骤与排错见 [install.md](install.md)。

### 速率限制与反爬

不要贪多——一天内反复大规模爬取，绝大多数平台都会触发登录墙、验证码或 IP 封禁。每个技能内置了保护措施（随机延迟、并发上限、指数退避），但它们替代不了常识。

---

[The Bitter Lesson of Agent Harnesses](https://browser-use.com/posts/bitter-lesson-agent-harnesses) · [Web Agents That Actually Learn](https://browser-use.com/posts/web-agents-that-actually-learn)
