# X (Twitter) 站点坑点

## 1. 滚动必须"逼近底部"才触发 lazy-load（最关键的坑）

**现象**：手动滚 X 首页能无限出新的老推文；但脚本用 `window.scrollBy(0, 900)` 小步滚，永远到不了底部，lazy-load 不触发，于是一直在"已加载的窗口"里转，全是已收过的推文。

**根因**：X 的无限滚动靠底部哨兵触发追加。小步滚时，底部离视口还很远（页面总高几万 px，tab 在中间），哨兵没进视口 → 不追加。

**解法**：每轮滚**约一屏**（`0.9 × innerHeight`），多轮下来逼近底部，lazy-load 触发，页面高度持续涨、更老的推文冒出来。

```python
def human_scroll():
    vh = safe_js('return window.innerHeight;') or 800
    safe_js(f"window.scrollBy(0, {int(vh * 0.9)})")
    time.sleep(jitter(0.25, 0.5))   # 给 lazy-load 反应时间
```

**别用** `window.scrollTo(0, scrollHeight)` 一次跳到底——会跳过中间被虚拟化移除的推文（X 只保留 ~5-7 条在 DOM）。增量滚 + 每轮提取，才能在每条推文离开 DOM 前抓到。

## 2. stall 判定：overlap ≠ 到底

**坑**：深度往下扫时，中间段本就是上一次已收过的推文（overlap 100%）。若用"0 新增"当停止信号，一进重叠区就误停。

**解法**：stall 只在"**既无新推文、页面高度也不增长**"时才算到底。页面还在涨（lazy-load 在追加）就继续，哪怕本轮全是旧推文。

```python
ph = safe_js('return document.documentElement.scrollHeight;') or 0
grew = (ph - prev_ph) > 50
stuck = (new == 0) and (not grew)      # 两个条件同时成立才算卡住
stall = stall + 1 if stuck else 0
if stall >= 6: break                    # 真的到底了
```

## 3. show-more 用 JS `.click()` 即可展开

X 长推在 feed 里被截断，带 `[data-testid="tweet-text-show-more-link"]`。**实测 JS `.click()` 直接展开**（X 是 React，但这个按钮不 hover-gated），无需坐标 hover 点击。

```javascript
// 点掉当前 DOM 里所有 show-more；React 异步重渲染，调用方需 sleep 后再取全文
[...document.querySelectorAll('[data-testid="tweet-text-show-more-link"]')]
    .forEach(l => l.click());
```

展开是异步的，点完 `sleep(0.7)` 再读 `[data-testid="tweetText"]` 的 `innerText`。

## 4. 图片原图：过滤 `/media/` + 升级 `name=orig`

X 的图片：`https://pbs.twimg.com/media/<id>?format=jpg&name=medium`。三点：

- **必须过滤路径含 `/media/`**——否则会把头像 `pbs.twimg.com/profile_images/...` 也收进来。
- 存档用：`name=medium` → `name=orig` 拿原图（Excel 嵌图用 orig）。
- **喂视觉模型时**：反用 `name=medium`（小、够理解）+ **必须 base64 直传**——X 有防盗链，网关/上游 fetcher 直接传 URL 报 "image URL must be valid and downloadable"。下载（带 `Referer: https://x.com/`）→ base64 → `data:image/jpeg;base64,...`。

```javascript
// 抓取阶段（存 tweets.json 的 imgs）：orig
var seen = {};
var imgs = [...a.querySelectorAll('img')]
    .filter(i => /pbs\.twimg\.com\/media\//.test(i.src))
    .map(i => i.src.replace(/name=\w+/, 'name=orig'))
    .filter(u => seen[u] ? false : (seen[u] = true));
```

```python
# 富化阶段（喂 Qwen3-VL）：降 medium + base64
url = re.sub(r'name=\w+', 'name=medium', img_url)
raw = urllib.request.urlopen(urllib.request.Request(url,
    headers={'User-Agent':'Mozilla/5.0','Referer':'https://x.com/'}), timeout=15).read()
data_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
```

## 5. 视频没有可下载直链（blob）

DOM 里 `<video src="blob:...">` 是 HLS-over-MSE，分片是 `.m4s`，**不是完整 mp4 也拿不到 m3u8**。`auth_token` 是 HttpOnly，`document.cookie` 读不到。

本 skill 阶段 1 只记 `has_video + video.poster(缩略图) + status URL`。要可下载 mp4，走 CDP 的 Network 流程（`TweetResultByRestId` GraphQL 响应里的 `video_info.variants`）——见 `references/gateway.md` 末尾的链接。

## 6. 别在会话中途重新导航到 home

X 是 SPA，`window.location.href = home_url` 不触发 Vue Router，卡片不重渲染。批量抓取全程留在搜索/home 页操作（关浮窗/点下一篇），中途不重新导航。本 skill 的 `x_fetch.py` attach 现有 home 标签后只 `scrollBy`，不 `goto`。

## 7. 虚拟化：每轮提取，别攒着

X feed 只保留 ~5-7 条 article 在 DOM，滚出去的就移除。所以**每轮滚动后立即提取**当前窗口的推文（去重），而不是"滚到底再一次性提取"——后者会丢中间段。
