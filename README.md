<img src="https://raw.githubusercontent.com/browser-use/media/main/browser-harness/banner-ink.svg" alt="Browser Harness" width="100%" />

# Browser Harness ♞

Connect an LLM directly to your real browser with a thin, editable CDP harness. For browser tasks where you need **complete freedom**.

One websocket to Chrome, nothing between. The agent writes what's missing during execution. The harness improves itself every run.

```
  ● agent: wants to upload a file
  │
  ● agent-workspace/agent_helpers.py → helper missing
  │
  ● agent writes it                         agent_helpers.py
  │                                                       + custom helper
  ✓ file uploaded
```

**You will never use the browser again.**

## Setup prompt

Paste into Claude Code or Codex:

```text
Set up https://github.com/browser-use/browser-harness for me.

Read `install.md` and follow the steps to install browser-harness and connect it to my browser.
```

The agent will open `chrome://inspect/#remote-debugging`. Tick the checkbox so the agent can connect to your browser:

<img src="docs/setup-remote-debugging.png" alt="Remote debugging setup" width="520" style="border-radius: 12px;" />

Click Allow when the per-attach popup appears (Chrome 144+):

<img src="docs/allow-remote-debugging.png" alt="Allow remote debugging popup" width="520" style="border-radius: 12px;" />

See [agent-workspace/domain-skills/](agent-workspace/domain-skills/) for example tasks.

## Free Browser Use Cloud browsers

Stealth, sub-agents, or headless deployment.<br>
**Browser Use Cloud free tier: 3 concurrent browsers, proxies, captcha solving, and more. No card required.**

- Grab a key at [cloud.browser-use.com/new-api-key](https://cloud.browser-use.com/new-api-key)
- Or let the agent sign up itself via [docs.browser-use.com/llms.txt](https://docs.browser-use.com/llms.txt) (setup flow + challenge context included).

## Architecture (~1k lines across 4 core files)

- `install.md` — first-time install and browser bootstrap
- `SKILL.md` — day-to-day usage
- `src/browser_harness/` — protected core package
- `agent-workspace/agent_helpers.py` — helper code the agent edits
- `agent-workspace/domain-skills/` — reusable site-specific skills the agent edits

## Contributing

PRs and improvements welcome. The best way to help: **contribute a new domain skill** under [agent-workspace/domain-skills/](agent-workspace/domain-skills/) for a site or task you use often (LinkedIn outreach, ordering on Amazon, filing expenses, etc.). Each skill teaches the agent the selectors, flows, and edge cases it would otherwise have to rediscover.

- **Skills are written by the harness, not by you.** Just run your task with the agent — when it figures something non-obvious out, it files the skill itself (see [SKILL.md](SKILL.md)). Please don't hand-author skill files; agent-generated ones reflect what actually works in the browser.
- Open a PR with the generated `agent-workspace/domain-skills/<site>/` folder — small and focused is great.
- Bug fixes, docs tweaks, and helper improvements are equally welcome.
- Browse existing skills (`github/`, `linkedin/`, `amazon/`, ...) to see the shape.

If you're not sure where to start, open an issue and we'll point you somewhere useful.

## Domain skills

Set `BH_DOMAIN_SKILLS=1` to enable [agent-workspace/domain-skills/](agent-workspace/domain-skills/) — community-contributed per-site playbooks `goto_url` surfaces by domain. Contribute via PR.

## Xiaohongshu Crawler Skill

A Claude Code skill for batch crawling Xiaohongshu (小红书/RedNote) notes — search, extract content + comments, download images, and export to Excel.

**This is a [Claude Code](https://claude.ai/code) skill**, not a standalone tool. It runs inside Claude Code via browser-harness CDP.

### What it does

1. **Search** — searches XHS for any keyword, reads results in waterfall layout order (left→right, top→bottom)
2. **Crawl** — opens each note card, extracts title, description, post images, and all comments (including nested replies and AI Q&A summaries)
3. **Download** — saves all post images and comment images to disk
4. **Export** — generates an Excel file with:
   - Color-coded post rows (each post gets a unique color)
   - Indented comment rows (↳ replies shown with lighter font)
   - Embedded images directly in cells
   - One sheet, all data together

### Quick start

```bash
# Search and crawl 5 notes
bh <<'PY'
search_xhs("ai产品经理焦虑", limit=5)
PY

# Export to Excel
bh <<'PY'
export_to_excel("xhs_ai_pm.xlsx")
PY
```

### Output structure

```
Excel 单 Sheet 结构：
┌──────────┬──────────┬────────┬──────────┬──────────┐
│ 标题      │ 正文      │ 点赞数  │ 帖子图片   │ 作者      │
│ AI产品经理…│ AI产品…  │ 1234   │ [嵌入图]  │ 用户A    │ ← 帖子行（蓝底）
│  ↳ 回复    │ 好文！   │ 56     │          │ 用户B    │ ← 评论行（同蓝底）
│  ↳ 回复    │ 同感     │ 12     │ [嵌入图]  │ 用户C    │ ← 带图评论
├──────────┼──────────┼────────┼──────────┼──────────┤
│ 下一篇帖子…│ ...      │ ...    │ [嵌入图]  │ 用户D    │ ← 绿底
│ ...       │ ...      │ ...    │          │          │
└──────────┴──────────┴────────┴──────────┴──────────┘
```

### Key features

- **Waterfall layout sorting** — 5-column masonry grid, reads cards in visual order
- **Comment expansion** — auto-expands "展开 N 条回复" and AI Q&A summaries
- **Image embedding** — post images and comment images embedded directly in Excel cells
- **Anti-scrape speed control** — randomized delays between actions to avoid bans
- **Stall detection** — stops scrolling when no new comments load (THE END)

### Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill entry point — instructions for Claude Code |
| `scripts/xhs_crawl.py` | Single note crawl (pipe to browser-harness) |
| `scripts/xhs_export.py` | Excel export with image embedding |
| `references/selectors.md` | DOM selector reference for all XHS elements |
| `references/waterfall-layout.md` | 5-column masonry sorting algorithm |
| `references/gotchas.md` | Known issues and workarounds |

### Requirements

- Claude Code
- browser-harness installed and connected to your browser
- Xiaohongshu logged in (cookies must be active)
- Python 3 with `openpyxl` (`pip install openpyxl`)

---

[The Bitter Lesson of Agent Harnesses](https://browser-use.com/posts/bitter-lesson-agent-harnesses) · [Web Agents That Actually Learn](https://browser-use.com/posts/web-agents-that-actually-learn)
