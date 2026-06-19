---
name: comment-to-topic
description: |
  Analyze scraped social media comments (小红书, 抖音, etc.) to extract
  content topic recommendations, user pain points, debate maps, and
  reusable material. Trigger when user has scraped comment/note data
  (JSON, CSV, Excel) and needs structured analysis for content planning.
  Keywords: 评论分析, 选题, 选题库, 评论区, topic extraction, comment
  analysis, content planning, 用户需求分析, 痛点分析.
---

# Comment-to-Topic

## Overview

Transform scraped social media comments into structured content topic recommendations.

**Core principle**: Every recommendation must be traceable to specific user comments. No "I think this is a good topic" — only "X users said Y, therefore Z is a valid topic."

**Outputs**: Pain point inventory, debate maps, topic recommendation cards with evidence, user persona segments, material library, and analytical insights.

## Process

### Phase 1 — Data Ingestion

1. Read the target directory structure. Identify data format (JSON, CSV, Excel, or mixed).
2. Open 2-3 sample files to discover the schema. Note available fields: note title, note content, comment text, comment likes, reply structure, user info, timestamps, image references.
3. Count total notes and estimate total comments.
4. Record the discovered schema — reference it throughout later phases.
5. If data exceeds context capacity, process in batches of 5-7 notes. Write intermediate findings to a temp file after each batch. Merge all intermediate findings before Phase 3.

### Phase 2 — Comment Classification

Read every comment and classify each into one of six signal types:

| Signal | Pattern | Content Value |
|--------|---------|---------------|
| 高频提问 | "有没有推荐…""怎么才能…""能不能出一期…" | Direct tutorial topic |
| 场景追问 | "男生可以用吗""学生党有平替吗""适合送妈妈吗" | Segment-specific topic |
| 对立观点 | Two users disagree on the same point | Debate / 破误区 content |
| 决策问题 | "在哪里买""多少钱""怎么选" | High-conversion content |
| 情绪表达 | "受够了""崩溃""终于找到了" | Empathy / 共鸣 content |
| 故事叙述 | User shares detailed personal experience | Case study material |

For each classified comment, record:
- **Original text** (verbatim — never paraphrase)
- Signal type
- Emotion tag (anger / frustration / confusion / desire / relief / humor / etc.)
- Scene tag if identifiable (commuting / dorm / office / kitchen / etc.)
- Identity tag if identifiable (student / parent / professional / beginner / etc.)
- Like count (resonance proxy)

### Phase 3 — Pattern Extraction

After classifying all comments, extract patterns across the full dataset:

**3a. Frequency**: Which signal types dominate? Which pain points recur across different notes? Cluster by concept, not by word — "迷茫""不知道方向""不知道自己适合什么" may be one concept.

**3b. Debate Mapping**: Identify topics where users hold opposing views. For each debate: state both sides with representative comments. Rate intensity (mild ↔ heated).

**3c. Gap Identification**: Questions that existing content doesn't answer. Scenarios no one covers. Decision-stage queries with no good resources.

**3d. User Segmentation**: Group commenters by identifiable traits. For each segment: what they care about, what language they use, what they struggle with.

### Phase 4 — Topic Generation

Generate topic recommendations following these rules:

**Rule 1 — Evidence required.** Each recommendation includes 1-3 verbatim supporting comments. No evidence, no topic.

**Rule 2 — User language.** Use phrasing from actual comments, not editorial vocabulary. If users say "我真的受够了", the topic shouldn't be "关于XX的深度思考".

**Rule 3 — Topic type must be explicit.**

| Type | When | Example |
|------|------|---------|
| 破误区 | Common misconception with opposing evidence | 《试错不是免费的：没钱的人怎么成长》 |
| 教程 | Repeated "how to" questions | 《夏天清爽香水推荐：从评论区扒出来的真需求》 |
| 共鸣 | Strong emotional resonance | 《没人兜底的人，怎么给自己兜底》 |
| 对比/测评 | Users debate competing options | 《5款vibe coding工具实测：评论区吵翻了的那个到底行不行》 |
| 深度 | Multi-layered topic worth exploring | 《不想上班 ≠ 适合创业》 |

**Rule 4 — Each card must include:**
- Recommended title + 2 alternatives
- Core angle (what unique perspective you bring)
- Opening hook (derived from a real comment)
- Target reader segment
- Resonance level (high / medium / low — based on comment frequency and emotion intensity)
- Source comments (verbatim, with like counts)

### Phase 5 — Material Extraction

Separately extract reusable material:

- **Gold Quotes**: Comments usable directly as hooks, subtitles, or openers. Must have strong emotion, specific scene, or memorable phrasing.
- **Data Points**: "X out of Y comments mentioned…", "The most-liked comment (Z likes) said…"
- **Counter-arguments**: Opposing viewpoints for article nuance, each citing original comment.

### Phase 6 — Output Assembly

Generate output files in `analysis/` subdirectory of the data project. See `references/output-templates.md` for exact templates.

```
[project_dir]/
├── analysis/
│   ├── 00-overview.md
│   ├── 01-pain-points.md
│   ├── 02-debate-map.md
│   ├── 03-topic-recommendations.md
│   ├── 04-user-personas.md
│   ├── 05-material-library.md
│   └── 06-insights.md
```

### Phase 7 — Quality Validation

Before finalizing, check each topic recommendation:

- [ ] Has ≥1 verbatim supporting comment
- [ ] Uses user language, not editorial language
- [ ] Targets a specific reader segment (not "everyone")
- [ ] Offers a clear angle (not just a subject)
- [ ] Opening hook could stop someone mid-scroll

Remove or revise any recommendation that fails ≥2 criteria.

## Guidelines

### On Authenticity

**Never paraphrase user comments.** When you translate "我真的受够了每次洗完还有一股腥味" into "用户反映清洁效果不佳", you lose the emotional texture that makes content resonate. Store verbatim. Analyze structurally. Quote authentically.

### On Batch Processing

If total comments exceed single-pass capacity:
1. Process notes in batches of 5-7
2. After each batch, write intermediate findings to `analysis/_batch_[n].md`
3. After all batches, merge intermediates and run pattern extraction on the combined set
4. Delete intermediate files after merge

### On Accumulating Across Runs

When running this Skill multiple times:
1. Each run's output goes into a dated subdirectory: `analysis/20260620/`
2. Maintain a cumulative `insights-ledger.md` in the project root
3. Track which topics have been written and published — mark as consumed
4. New runs reference previous insights to distinguish emerging vs. persistent themes

### On Cross-Platform Data

When analyzing comments from multiple platforms:
- Same-signal comments from different platforms reinforce each other
- 抖音 comments: more emotional, fragmented, impulse-driven
- 小红书 comments: more scene-specific, detailed, decision-oriented
- Note the platform source for each comment in analysis

### On Prioritization

When there are too many potential topics, prioritize by:
1. Frequency × Emotion intensity (most signals, strongest feelings)
2. Debate presence (topics with opposing views generate more engagement)
3. Specificity (concrete scenarios beat abstract themes)
4. Gap score (how poorly existing content covers this)
