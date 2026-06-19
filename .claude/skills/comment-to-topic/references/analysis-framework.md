# Analysis Framework — Detailed Methodology

## 1. Data Ingestion Protocol

### Schema Discovery

When first reading scraped data, identify these field categories:

**Note-level fields**:
- `noteId` / `noteUrl` — unique identifier
- `title` / `content` — the original post
- `authorName` / `authorId` — post author
- `likeCount` / `commentCount` / `shareCount` — engagement metrics
- `publishTime` — when the post was published
- `tags` / `topics` — platform-assigned labels

**Comment-level fields**:
- `commentId` — unique identifier
- `commentText` — the actual comment (this is your primary data)
- `userName` — commenter identity
- `likeCount` — resonance proxy (higher = more people agree)
- `commentTime` — temporal context
- `level` — 1st-level (direct comment) vs 2nd-level (reply to comment)
- `parentCommentText` — for 2nd-level comments, what they're replying to
- `imageUrls` — any images in the comment

### Prioritization When Data Is Large

If total notes > 20 or total comments > 1000:

1. **Sort by comment count** — notes with more comments have richer signal
2. **Sort by recency** — comments from last 3 months are most relevant
3. **Flag debate-rich notes** — notes where replies-to-comments ratio is high (users are arguing, not just reacting)
4. Process high-priority notes first, then expand if context allows

### Handling Incomplete Data

Common issues with scraped data:
- Long comments truncated to "..." → note these as data gaps, don't infer content
- Missing timestamps → still usable, just lose temporal analysis
- No like counts → lose resonance proxy, rely on frequency instead
- No reply structure → lose debate detection, focus on first-level signals

## 2. Signal Classification — Deep Dive

### 高频提问 (High-Frequency Questions)

**Detection patterns**:
- Interrogative words: 什么, 怎么, 哪个, 有没有, 能不能, 可以吗
- Request words: 推荐, 求, 出一期, 讲讲
- Problem statements: 不知道..., 找不到..., 不会...

**What makes it "high-frequency"**:
- Same question asked 3+ times across different notes or by different users
- Same question with high like count (others want the answer too)
- Semantically equivalent questions with different wording

**Content application**: Each high-frequency question = one potential tutorial/教程 article. Group semantically equivalent questions together.

### 场景追问 (Scene-Specific Questions)

**Detection patterns**:
- Identity qualifiers: 男生, 学生党, 宝妈, 上班族, 40岁, 敏感肌
- Situation qualifiers: 通勤, 出差, 宿舍, 夏天, 冬天, 预算有限
- Use-case qualifiers: 送人, 自用, 入门, 进阶, 平替

**What makes it valuable**:
- The user has already imagined themselves using the product/content
- They just need content that speaks to their specific context
- These are the easiest topics to write because the demand is explicit

**Content application**: Each scene question = one segment-specific article. The more specific the scene, the higher the conversion potential.

### 对立观点 (Opposing Views)

**Detection patterns**:
- Reply chains where users disagree
- Contradictory statements across comments on the same note
- "但是…", "然而…", "我不同意…", "你试试就知道了"
- Like distribution: both sides get significant likes (not one-sided)

**What makes it valuable**:
- Single-perspective topics are one-dimensional
- Debate indicates the topic has depth and multiple valid angles
- Readers are more likely to engage with content that acknowledges both sides

**Content application**: Each debate = one 破误区 or 对比 article. Structure: present both sides → acknowledge validity of each → offer your synthesized judgment.

### 决策问题 (Decision Queries)

**Detection patterns**:
- Purchase intent: 哪里买, 多少钱, 链接, 小样, 试用
- Comparison: A还是B, 哪个更好, 值不值得
- Risk assessment: 踩坑, 后悔, 交智商税, 值得买吗

**Content application**: High commercial value. These readers are close to action. Content that answers decision questions well can directly influence conversion.

### 情绪表达 (Emotional Expressions)

**Detection patterns**:
- Strong adjectives: 受够了, 崩溃, 感动, 惊喜, 后悔
- Exclamation / emphasis: 太xxx了!, 真的xxx!
- Personal vulnerability: 说实话, 讲真, 我其实...

**What makes it valuable**:
- Emotional comments are the raw material for hooks and openings
- They tell you the emotional register your content should match
- High-emotion comments with high likes indicate shared feelings

**Content application**: Gold material for article openings, subtitles, and social media hooks. Never rewrite — use verbatim.

### 故事叙述 (Stories / Experiences)

**Detection patterns**:
- Narrative structure: first-person, temporal markers (去年, 上个月, 之前)
- Specific details: numbers, dates, product names, outcomes
- Length: typically longer than other comment types

**What makes it valuable**:
- Stories are case studies waiting to happen
- They provide concrete, relatable examples
- They often contain implicit lessons

**Content application**: With permission/ anonymization, these become article case studies. Even without explicit permission, the patterns in stories reveal what experiences are common.

## 3. Pattern Extraction — Methodology

### Concept Clustering (Not Word Counting)

Raw word frequency is misleading. "迷茫", "不知道方向", "不知道自己适合什么", "每天混日子" are different words but one concept: **方向感缺失**.

**Method**:
1. Group comments by the underlying need/problem, not by surface wording
2. Name each cluster with a concise label (2-5 words)
3. Count how many distinct comments fall in each cluster
4. Rank clusters by count

### Cross-Note Pattern Detection

A pattern is "cross-note" when the same concept appears in comments on multiple different notes. This is stronger evidence than high frequency on a single note (which might be driven by the note's framing).

**Method**:
1. For each concept cluster, list which notes it appears in
2. A concept appearing in 3+ notes is a strong signal
3. A concept appearing in only 1 note may still be valid if the comment has high engagement

### Debate Intensity Scoring

For each identified debate:
- **Mild**: Users express different preferences ("I prefer A", "I prefer B")
- **Moderate**: Users challenge each other's reasoning ("A doesn't work because…")
- **Heated**: Users question each other's competence/experience ("You clearly haven't tried…")

Heated debates produce the most engaging content because they involve real stakes.

## 4. Topic Quality Assessment

### The "Scroll-Stop" Test

Read the proposed title as if you're scrolling your feed. Would it make you stop? If not, the title is too abstract, too editorial, or too generic.

### The "So What" Test

After reading the topic angle, ask: "So what? Why should my reader care?" If the answer is just "because it's informative", the topic needs more emotional or practical specificity.

### The "Specificity Ladder"

Abstract ← → Specific

- "年轻人该怎么成长" ← too abstract
- "年轻人要不要试错" ← better, but still broad
- "没有试错成本的人怎么试错" ← specific and resonant
- "一天不上班就怕交不起房租的人怎么给自己攒选择权" ← extremely specific, will stop scrolls

Aim for the bottom half of this ladder.

### The "One Reader" Test

Can you describe exactly one person who would benefit from this topic? Not "年轻人" but "24岁，换了三份工作，存款不到一万，爸妈催着考公，但自己不想回去"。If you can't describe one specific reader, the topic isn't ready.

## 5. Edge Cases

### Low-engagement comment sections
If a note has < 20 comments, the signal may be too thin. Combine with other notes on the same topic. If the topic only appears once with low engagement, it's a weak signal.

### Bot/spam comments
Detect by: generic praise ("好棒!"), emoji-only, promotional links, identical text across notes. Exclude these from analysis.

### Sarcastic/ironic comments
Context-dependent. "太好用了（不是）" is negative despite positive words. Use surrounding comments and reply context to interpret.

### Platform-specific noise
小红书: "蹲蹲""求链接" are engagement signals, not topic signals. 抖音: emoji floods, duet reactions. Filter these out of topic analysis but note them as engagement patterns.
