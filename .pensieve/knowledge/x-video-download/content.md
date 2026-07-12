---
id: x-video-download
type: knowledge
title: 下载 X/Twitter 视频为 mp4 — GraphQL TweetResultByRestId + CDP getResponseBody
status: active
created: 2026-07-11
updated: 2026-07-11
tags: [pensieve, knowledge, x, twitter, video, cdp]
---

# 下载 X/Twitter 视频为 mp4

## Summary

X 推文里的视频 `<video src="blob:...">` 是 HLS-over-MSE，DOM 拿不到直链。可靠方法：用 CDP 抓 `TweetResultByRestId` GraphQL 响应，从 `video_info.variants` 取最高 bitrate 的完整 mp4。图片直接从 `<img>` 改 `name=orig` 下。

## Content

### 图片（简单）

DOM 里 `<img src="https://pbs.twimg.com/media/...?format=jpg&name=medium">`。把 `name=` 改成 `name=orig` 拿原图，urllib 直接下（带 `Referer: https://x.com/`）。

### 视频（DOM 拿不到直链）

`<video src="blob:...">` 是 HLS-over-MSE，分片是 `.m4s`（不是完整文件，也不是能喂 ffmpeg 的 m3u8）。`auth_token` 是 HttpOnly，`document.cookie` 读不到。

完整流程（全部用 browser-harness）：
1. `cdp("Network.enable")` + `drain_events()` 清旧事件。
2. `goto_url(status_url)` 重新加载详情页 → 触发新鲜 `TweetResultByRestId` GraphQL 请求。
3. `drain_events()` 里找 `Network.requestWillBeSent`，url 含 `/graphql/` + `TweetResultByRestId` → 记 `requestId`、`url`、从 headers 取 `authorization`（bearer）。
4. `cdp("Network.getResponseBody", requestId=rid)` → 读响应体 JSON。
5. 递归搜 `video_info.variants`（`content_type=="video/mp4"`），按 bitrate 降序选最高。
6. urllib 直接下该 mp4 url（无需 ffmpeg；变体本身是完整 mp4）。

### 踩过的坑

- `1.1/statuses/show.json` 在新 X 上 **404**（旧 REST 端点已删），别用。
- 单 `play()` 触发后，performance/fetch/XHR **都抓不到 m3u8**（X 渲染时就预取了 manifest，且 MSE 分片不走主线程 fetch）。别走这条路。
- bearer 必须从 CDP `Network.requestWillBeSent` 事件的请求头里抓（GraphQL 调用在 worker 里，主线程 fetch patch 抓不到）。
- cookie 用 `cdp("Network.getCookies")` 拿（能读 HttpOnly 的 auth_token）。
- 兜底：若 getResponseBody 失败，用抓到的 graphQL url + bearer + cookie 重放。

## When to Use

- 需要下载 X/Twitter 推文的视频或原图时。
