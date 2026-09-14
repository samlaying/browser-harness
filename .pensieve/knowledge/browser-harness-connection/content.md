---
id: browser-harness-connection
type: knowledge
title: browser-harness 与 Chrome 的连接机制与排错
status: active
created: 2026-07-11
updated: 2026-07-17
tags: [pensieve, knowledge, browser-harness, cdp, debugging, proxy]
---

# browser-harness 与 Chrome 的连接机制与排错

## Summary

browser-harness 的 daemon 自动连"运行中的 Chrome"。本机调试 Chrome 走 `--remote-debugging-pipe`（管道模式），**不开 TCP 端口**。判断是否连上**只看 `browser-harness --doctor` 的 `active browser connections`，不要 curl 扫端口**。

## Content

### 连的是哪个 Chrome

目标浏览器是 **Google Chrome，Profile 1**：`/Users/sam/Library/Application Support/Google/Chrome/Profile 1`（不是默认 Default）。
- 可执行：`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，UA Chrome 149
- 登录态：X (`x.com/home`)、BOSS直聘 等
- 保持这个 Profile-1 Chrome 运行、相关站点登录，就是目标。**用户明确要求"不要去找其他额外的浏览器"。**

### 判断是否连上（关键）

**直接跑 `browser-harness --doctor`，看 `active browser connections` 行。** 不要用 `curl localhost:9222` / `lsof -i :9222` / 扫 9220–9555——调试 Chrome 走 pipe 不开 TCP，扫端口全空会**误判成"没连上"**，白让用户重启 Chrome。

- `active browser connections — 1` + 能看到当前页 URL（如 `(1) Home / X — https://x.com/home`）= 已连上。
- 真没连上的标志：doctor 同时显示 `chrome running` + `active browser connections — 0`（daemon 可能 FAIL）。
- **doctor 可能误报 FAIL**（v0.1.0 实测）：`daemon alive FAIL` + `active browser connections — 0`，但实际连接正常——以 `print(page_info())` 实测为准，返回真实 url/title 即已连上，别因 doctor FAIL 去 reload / 重启 Chrome。2026-07-17 爬「面试啰嗦」前命中（doctor 全 FAIL，page_info 秒回飞书文档真实 URL）。

### inline 环境变量透传

`VAR=x browser-harness <<PY` 形式的 inline 环境变量**会透传**给 daemon 执行的脚本。

### 误连了别的 Chrome 怎么办

命令行看不到 `--remote-debugging-port`（chrome://version 只显示 flag-switches），但 harness 能连上——连接细节由 daemon 管理，无需手动指定端口。若误连别的 Chrome 实例：关掉其他 Chrome 后跑 `browser-harness --reload` 让 daemon 重连，再 `--doctor` 看 active page 是否正确（如 x.com/home）。

### 系统代理（Clash/Surge）拦 localhost → 加 no_proxy

**症状和"没连上"不同**：`browser-harness --doctor` 可能显示连上了，但实际调用（`page_info()` 等）无输出/超时/卡住，或报 WS 错误、`CDP no close frame`。关键线索：本机装了 Clash/Surge 类代理（监听 `127.0.0.1:7897` 之类）。

**根因**：macOS 系统代理对 localhost 也没放行，`proxy_bypass("127.0.0.1")` 返回 False：
- `get_ws_url()` 用 urllib 探 `/json/version` → 被代理转发 → 代理返回 **502**（不是 Chrome 的 404）→ ws_path 回退不触发 → "not live"。
- WS 握手 → websockets 想走 SOCKS 代理 → 缺 `python-socks` → 报错。

**修复（一个变量同时修两条路）**：

```bash
export no_proxy=127.0.0.1,localhost NO_PROXY=127.0.0.1,localhost
browser-harness --reload    # daemon 必须 fresh 重启才继承新环境
```

`no_proxy` 让 `proxy_bypass` 返回 True、`getproxies()` 清空——urllib 探测和 WS 握手一次修好，**不用重启 Chrome、不丢标签页**。reload 后 `page_info()` 返回真实 url/title 即通。

**注意 daemon 环境的层次**：inline `VAR=x browser-harness <<PY` 只透传给 daemon 执行的*脚本*（见上节）；但 urllib/WS 探测发生在 *daemon 进程本身*，由 daemon **启动时**的环境决定——所以改 `no_proxy` 后必须 `--reload` 让 daemon 带新变量重启，光在调用时 inline 不够。

**边界**：`xhs_export.py` 用 urllib 下小红书 CDN 的远程图片，走系统代理是正常的（远程 host，`no_proxy` 不影响）——只有连 CDP（localhost）的调用才需要 `no_proxy`。

- 实测：2026-07-12 爬「一天拆解一个ai产品」，首次 `browser-harness` 调用无输出，加 `no_proxy` + `--reload` 后秒通，20/20 爬完。

### 活动标签页是死页（hung tab）→ js/page_info 卡死

**症状**和系统代理阻塞几乎一样：`browser-harness --doctor` 显示 `active browser connections — 1`、连的也是对的本地 Chrome，但 `js()` / `page_info()` 全超时（`Runtime.evaluate timed out`）。**根因不同**：daemon 连的浏览器是对的，只是**当前活动标签页停在一个加载不出来的死页**（如某已不可达的内网地址 `http://10.x.x.x:port/`），`Runtime.evaluate` 在那个死页的 JS 上下文里卡住。本机无代理、`no_proxy` 已设、`--reload` 也救不了——因为重连的还是同一台浏览器、同一个活动死页。

**诊断**：`cdp("Target.getTargets", {})` 列出所有 page target，看活动页 URL 是否是个打不开的地址；`curl` 该地址 HTTP 000 = 不可达（确认是死页而非连错浏览器）。

**修复**：`new_tab("https://www.xiaohongshu.com/")` 开一个新鲜响应的标签页（它成为活动页），再 `page_info()` 秒回。不必重启 Chrome、不必 `--reload`、不必动代理。死页留在后台不碍事——`run_batch` 入口只在找不到 `search_result` 标签时对「当前活动标签」`goto_url`，活动页换成响应页即可。

- 实测：2026-07-24 爬「快手运营管培校招」前命中——doctor 显示连上本地 Chrome（Profile 1，xhs 已登录），但活动页是 `http://10.123.179.15:8648/`（COPAW 服务器，已换网络不可达），`js` 全超时；`new_tab` 开 xhs 页后秒通，20/20 爬完。

### 外部 playwright 脚本复用日常 Chrome（ws 直连 + 进程内 no_proxy）

上面讲的是 browser-harness **daemon 自己**连 Chrome。**外部 playwright 脚本**（如 `miaoshou/miaoshou-tiktok-automation.js`）要共享同一台日常 Chrome 时，解法不同：

日常 Chrome 经 `chrome://inspect` 勾选「Allow remote debugging」（Way 1）开远程调试 → **开 TCP 端口**（动态，写进 `~/Library/Application Support/Google/Chrome/DevToolsActivePort`：第一行端口、第二行 ws path），**但不开 HTTP `/json/version`**。

- ❌ `chromium.connectOverCDP("http://127.0.0.1:<port>")` 失败：playwright 先 GET `/json/version` 找 ws URL → Way 1 没开这个 endpoint（Clash 拦 127.0.0.1 时还先返回 502）。
- ✅ 读 `DevToolsActivePort` 拼 **ws URL 直连**：`ws://127.0.0.1:${port}${wsPath}`，跳过 HTTP 发现。daemon 也是这么连的。
- ✅ `no_proxy` 必须**进程内设**（`process.env.no_proxy = "127.0.0.1,localhost"`），别只靠外部 `export`——node 脚本和 daemon 各跑各的 shell，playwright 的 WS 否则会走 Clash 的 SOCKS 卡住/报 `CDP no close frame`。

Chrome 重启端口会变，但每次读 `DevToolsActivePort` 自动跟上，不用改代码。

- 实测：2026-07-12 miaoshou 脚本 ws 直连日常 Chrome（妙手 ERP 已登录），sort/find-1688/select/batch-supply 全跑通（详见 `miaoshou-ops`）。

## When to Use

- 调试/确认 harness 是否连上浏览器时（先看 doctor，别扫端口）。
- 外部 playwright 脚本要共享日常 Chrome 时（ws 直连 `DevToolsActivePort` + 进程内 `no_proxy`）。
- 需要确认连的是哪个 Chrome profile 时。
- harness 连错浏览器、需要重连时。
- harness 调用无输出/卡住、报 WS 或 `CDP no close frame`，且本机有 Clash/Surge 代理时（先试 `no_proxy` + `--reload`，别重启 Chrome）。
