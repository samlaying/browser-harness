# `window.__INITIAL_STATE__` 字段地图

点击卡片打开笔记浮窗后，小红书 SPA 把笔记完整数据注入 `window.__INITIAL_STATE__.note.noteDetailMap[noteId].note`。直接在浏览器里读这个全局变量，就能拿到 DOM 里没有的**原视频 mp4 + 全分辨率原图 + 头像**，无需额外发 HTTP 请求。

以下路径已对照真实抓包 `_raw_data.json`（视频笔记，实测下载成功）逐字段校验。

## 顶层结构

```
window.__INITIAL_STATE__.note.noteDetailMap
  └── [noteId]
       └── .note   ← 取这个对象
            ├── type         "video" | "normal"
            ├── noteId
            ├── title
            ├── desc
            ├── ipLocation
            ├── time / lastUpdateTime        (毫秒时间戳，挑"最新"笔记用)
            ├── xsecToken                    (FALLBACK 拼 URL 用)
            ├── tagList[]                    每项 .name
            ├── interactInfo{ likedCount, collectedCount, commentCount, shareCount }  ← 字符串如 "218"
            ├── user{ userId, nickname, avatar, (imageb, images) }
            ├── video                        (仅 type=="video")
            └── imageList[]                  (图文笔记的全部原图；视频笔记通常是封面)
```

## 视频（type=="video"）

**正确路径**（实测可下载）：

```
note.video.media.stream.h264[0].masterUrl        ← 签名 mp4，会过期，当篇立即下
note.video.media.stream.h264[0].backupUrls[]     ← 同一 stream 节点内，unsigned CDN，masterUrl 过期顶上
```

`h264[0]` 还含 `format:"mp4"`、`videoCodec:"h264"`、`width/height/duration/size/fps`、`backupUrls[]`。

> ⚠️ **不要用 `video.consumer.originVideoKey`** —— `redbook-download/redbook.py` 先试这条，但实测抓包里 **`video.consumer` 根本不存在**，那条是死代码。直接取 `stream.h264[0].masterUrl`。
>
> ⚠️ **`backupUrls` 在 `h264[0]` 内**（per-stream），不是 `video.media.backupUrls`。

masterUrl 形如 `http://sns-video-zl.xhscdn.com/.../xxx.mp4?sign=...&t=6a28328b`——`t=` 是过期时间点（Unix 时间戳 hex）。**抓到后必须当篇立即下载**，不能攒着批量后下。

## 图片

```
note.imageList[]
  ├── .urlDefault        ← 首选
  ├── .url
  └── .infoList[]        ← 每项 { imageScene: "WB_PRV"|"WB_DFT", url, width, height }
```

取法：每张先取 `urlDefault || url`，再遍历 `infoList` 按 `width*height` 取**面积最大**那档的 `url` 覆盖。`WB_DFT` 通常是大图。结果即全分辨率原图（比 DOM `.swiper-slide img` 的压缩缩略图大）。

## 头像

```
note.user.avatar         ← 真实字段，已填充
note.user.imageb         ← 实测为空，仅 fallback
note.user.images         ← 同上
```

取 `avatar || imageb || images`。

## 互动计数

`interactInfo.{likedCount,collectedCount,commentCount,shareCount}` 全是**字符串**（如 `"218"`）。保持原样，导出时按需转 int。

## 挑笔记的规则

`noteDetailMap` 可能有多个 key（点过的卡片都会进）。按 noteId 精确取最稳；noteId 未知时按 `lastUpdateTime || time` 取最大（最近点的）那条。
