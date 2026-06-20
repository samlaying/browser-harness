# xhs-media 已知坑点

## 1. 签名视频 URL 与下载解耦

`video.media.stream.h264[0].masterUrl` 带 `?sign=...&t=<hex>`。`t=` 是**生成时间戳**（不是过期时刻），真正有效期由 `sign=`（HMAC）控制——小红书视频 CDN 签名实测能撑**数小时**。所以一次爬取（几分钟）内基本不会过期。

但下载仍是耗时网络 I/O（10MB+ 视频），**不能在浏览器循环里同步跑**——会把 3~8s 反爬节奏拖成几十秒。

**解决（异步生产者-消费者）**：
- 浏览器循环只提取 + 写 `{noteId}.json` 检查点 + 入队，立即下一篇。
- N 个后台 worker（`XHS_WORKERS`，默认 3）并发下载，只做 requests I/O，不碰 js/cdp。
- 兜底链：`masterUrl` 失败 → 换 `backupUrls[]`（unsigned CDN，寿命更长）→ 还失败用入队快照的 cookies 调 `fetch_via_http(noteId, xsecToken)` 重取**新鲜签名 URL** 再下。
- 下载带 `Referer: https://www.xiaohongshu.com/`。
- 循环结束 `pool.join()` 等队列排空再建 Excel。详见 [SKILL.md](../SKILL.md) Step 3。

## 2. 取 `stream.h264[0].masterUrl`，不是 `consumer.originVideoKey`

**问题**：参考项目 `redbook-download/redbook.py` 先试 `video.consumer.originVideoKey` 拼 CDN——但真实抓包里 **`video.consumer` 节点不存在**，那条分支永远走不到，白白浪费一次判断。

**解决**：直接读 `video.media.stream.h264[0].masterUrl`。`backupUrls` 也在同一个 `h264[0]` 对象里（不是 `video.media.backupUrls`）。详见 [initial-state.md](initial-state.md)。

## 3. PRIMARY / FALLBACK 双路径

**PRIMARY**：浮窗打开后浏览器里的 `window.__INITIAL_STATE__` 通常已含被点笔记全数据（含 masterUrl）。`xhs_media_extract.py` 的 `PRIMARY_JS` 在浏览器内只抠媒体字段、return 小对象。

**FALLBACK**：若 PRIMARY 返回字段空（video 笔记没 videoUrl、或 noteDetailMap 里没该 noteId），用 `xsecToken`（也从 `__INITIAL_STATE__` 取）拼 `https://www.xiaohongshu.com/explore/{id}?xsec_token=...&xsec_source=pc_search`，带上经 `cdp("Network.getAllCookies")` 取出的浏览器 cookies 做服务端 GET，正则解析 HTML 里的 `__INITIAL_STATE__`。两条路径共用 `normalize_note()` 映射。

## 4. `js()` 只 return 小对象——否则 "chain too long"

**问题**：`window.__INITIAL_STATE__` 整包很大，直接 `js('return window.__INITIAL_STATE__')` 会触发 returnByValue 序列化 "chain too long" 错误。

**解决**：在 JS 内完成字段提取，只 return 扁平小对象（`videoUrl`、`imageUrls[]` 截断、`avatar` 等标量/短数组）。`backupUrls` 截断取前 2 条。

## 5. xsec_token 只能靠点击卡片获得

**问题**：直接 `goto_url("https://www.xiaohongshu.com/explore/{id}")` 会 404（`xsec_token` 缺失）。

**解决**：永远从搜索结果页**点击卡片**打开笔记浮窗。这就是 xhs-media 必须复用 xhs-crawler 点击流的原因。FALLBACK 拼 URL 时，token 也从点击后注入的 `__INITIAL_STATE__.noteDetailMap[id].note.xsecToken` 取。

## 6. blob 视频——不能从 DOM 抓

**问题**：`<video>` 的 `src` 是 `blob:` URL（MSE 流媒体），DOM 里没有 mp4 直链。

**解决**：视频地址**只能**来自 `__INITIAL_STATE__` 的 `masterUrl`，不能从 `<video>` 元素抓。这正是 xhs-media 相对 xhs-crawler 的核心增量。

## 7. SPA 不重新导航（继承自 xhs-crawler #16）

**问题**：小红书是 Vue SPA，`window.location.href = ...` 回搜索页不会重渲染卡片。

**解决**：批量必须**单个 browser-harness 会话**内完成，留在搜索页操作，关闭浮窗后直接点下一篇。不重新导航。

## 8. 点击前验证 + Retina 偏移（继承自 xhs-crawler #17）

**问题**：Retina 屏（devicePixelRatio=2）下 CDP 坐标可能偏移，点卡片实际落在侧边栏"发布"按钮。

**解决**：点击前 `elementFromPoint(x,y)` 验证目标是 `.note-item` 子元素、且不是"发布/下载APP/登录/注册"。非卡片则跳过。`click_card_with_verify` 已封装。

## 9. CDP 长会话掉线（继承自 xhs-crawler #18）

**问题**：单次会话超 ~2 分钟 CDP 可能断连。

**解决**：`safe_js`/`safe_cdp` 异常时 `ensure_daemon(); ensure_real_tab()` 重连。批量循环每 5 篇主动重连一次。

## 10. harness exec 时 `__name__ != '__main__'`

**问题**：browser-harness 用 `exec(code, globals())` 执行 piped 脚本，piped 代码的 `__name__` 是 `'browser_harness.run'`，**不是** `'__main__'`。所以 `if __name__=='__main__':` 守卫在 piped 脚本里**不会触发**。

**解决**：
- piped 脚本（`xhs_media_batch.py`、`xhs_media_extract.py` 的 standalone）直接 module-level 执行；`xhs_media_extract.py` 用 `if 'ensure_daemon' in globals():` 判断是否在 harness 里跑。
- 纯 CLI（`xhs_media_download.py`，`python3` 子进程调用）正常用 `if __name__=='__main__'`。

## 11. 不能 import xhs_crawl（会触发它的爬取）

**问题**：`xhs-crawler/scripts/xhs_crawl.py` 的提取逻辑在 module level（无 `__main__` 守卫），`import xhs_crawl` 会立刻执行一整轮爬取。

**解决**：`xhs_media_batch.py` 把需要的点击/验证/关闭 helper **逐字复制**进来（标 `SYNC` 注释），而非 import。改这些函数要同步回 `xhs_crawl.py`。
