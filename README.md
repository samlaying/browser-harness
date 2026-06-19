<img src="https://raw.githubusercontent.com/browser-use/media/main/browser-harness/banner-ink.svg" alt="Browser Harness" width="100%" />

# Browser Harness ♞

> 🌐 中文文档：[README.zh-CN.md](README.zh-CN.md)

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

## Xiaohongshu Media Skill

A companion to the crawler above. Where the crawler grabs **text + comments** from the DOM, the media skill grabs **original videos + full-resolution images + avatars** by reading `window.__INITIAL_STATE__` (server-injected, with signed URLs) — then downloads each note's media immediately, while its signed video URL is still valid. (The DOM only exposes compressed thumbnails, and `<video>` is a blob/MSE stream you can't scrape directly.)

### ⚠️ Log in to your own account first

This skill drives **your real, logged-in Chrome session** through browser-harness. It reads `__INITIAL_STATE__` from the live page and reuses the browser's cookies for fallback requests, so:

- Connect browser-harness to your everyday **Google Chrome** — not a headless or throwaway browser.
- Log in to Xiaohongshu with **your own account** in that Chrome and keep that session's cookies active.
- If you hit a login wall mid-run, log in yourself and retry — never type credentials from a screenshot.

### What it does

1. **Search** — opens the search page for a keyword and scrolls to load the waterfall
2. **Collect** — reads `.note-item` cards in visual (waterfall) order
3. **Per note** — close the previous overlay → click-verify → read `__INITIAL_STATE__` for the signed `masterUrl`, full-res images, and avatar
4. **Download immediately** — media is downloaded the instant it's extracted (signed video URLs expire); video falls back `masterUrl → backupUrls → re-fetch a fresh signature via HTTP`
5. **Export** — generates an Excel summary (title, author, type, video link, image count, avatar, likes/saves/comments, IP, thumbnail)

### Rate limiting (built in, anti-ban)

- **Randomized 3–8 s pause** between notes
- **Bounded download pool** — `XHS_WORKERS` concurrent downloads (default 3), keeping the browser loop and downloads decoupled (no CDP contention)
- **Exponential backoff** on failed downloads (`2^attempt` s)
- **CDP reconnect every 5 notes** to survive long sessions

### Quick start

```bash
XHS_KEYWORD="北京约会" XHS_LIMIT=20 XHS_WORKERS=4 \
XHS_RUN_DIR="xhs_media_data/$(date +%Y%m%d)_北京约会" \
browser-harness < .claude/skills/xhs-media/scripts/xhs_media_batch.py
```

Resume after a crash — every note's JSON is checkpointed, so re-running the downloader only fills the gaps:

```bash
XHS_WORKERS=4 python3 .claude/skills/xhs-media/scripts/xhs_media_download.py xhs_media_data/20260619_北京约会/
```

### Files

| File | Purpose |
|------|---------|
| `.claude/skills/xhs-media/SKILL.md` | Skill entry point — instructions for Claude Code |
| `scripts/xhs_media_extract.py` | Read `__INITIAL_STATE__` for media (PRIMARY) + HTTP fallback |
| `scripts/xhs_media_batch.py` | Single-session batch driver + async download queue |
| `scripts/xhs_media_download.py` | Downloader (video / images / avatar) + thread pool + Excel |
| `scripts/video_transcriber.py` | Optional: Groq Whisper, mp4 → txt |
| `scripts/ocr_processor.py` | Optional: OCR.space, jpg → txt |
| `references/initial-state.md` | `__INITIAL_STATE__` field map |
| `references/gotchas.md` | 11 known pitfalls |

### Requirements

- Claude Code
- browser-harness installed and connected to your **logged-in** Chrome
- Xiaohongshu logged in with **your own account** (cookies active)
- `requests` + `openpyxl`, installed into the browser-harness Python env (the harness runs in its own uv-managed env, so a plain `pip install` won't be visible to it):
  ```bash
  uv pip install --python ~/.local/share/uv/tools/browser-harness/bin/python requests openpyxl
  ```

### Crawler vs. Media

| Skill | Source | Gets |
|-------|--------|------|
| `xhs-crawler` | DOM | text + comments |
| `xhs-media` | `__INITIAL_STATE__` | original video + full-res images + avatar |

Use them together: media for the files, crawler for the comments, then merge.

---

[The Bitter Lesson of Agent Harnesses](https://browser-use.com/posts/bitter-lesson-agent-harnesses) · [Web Agents That Actually Learn](https://browser-use.com/posts/web-agents-that-actually-learn)
