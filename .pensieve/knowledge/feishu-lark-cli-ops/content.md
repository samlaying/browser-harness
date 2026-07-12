---
id: feishu-lark-cli-ops
type: knowledge
title: lark-cli 飞书文档操作手册 — 上传/权限/bot坑/block批量改
status: active
created: 2026-07-11
updated: 2026-07-11
tags: [pensieve, knowledge, feishu, lark, lark-cli, docx]
---

# lark-cli 飞书文档操作手册

## Summary

用 lark-cli 操作飞书文档的可靠姿势：**建文档优先用 SA 账号**、内容**导入成 docx（别建 markdown 类型）**、**建完直接设公开可读**。bot 身份有权限坑，改用户拥有的文档必须 `--as user`。profile/凭证位置见 [[knowledge/feishu-ci-profiles/content]]。

## Content

### 账号选择（最重要）

**★ 建飞书文档/资源优先用 SA 账号 `cli_aa823d7922f8dbc3`（飞书用户4228SA），不要用林承列个人号 `cli_a9772deff9b95cdd`。**
- SA 的 user token 自带 `drive:file:upload + drive:drive.metadata:readonly + docx:document:create` 等（早就授权好，token `needs_refresh` 自动刷新），**不用 re-auth**。
- 林承列个人号默认**缺** `drive:file:upload`，首次建文档报 missing_scope，得走 device-flow 补授权（长阻塞轮询 open.feishu.cn 会因 `can't assign requested address` 断网让 device_code 失效；改用 `auth login --no-wait --json` 拿链接、用户授权后再 `--device-code` 续）。
- 造物 SAMLAB 内容库走命名 profile **`zaowu-samlab`**（app `cli_aada61b189b95cd1`，独立租户 `bcnogixo2vb2.feishu.cn`，用户 SAM `ou_eca8f13ae7885de95916f8a6187a3e4d`）。按租户/用途在 SA 与 zaowu-samlab 之间选。

### 上传内容：导入成 docx，别用 markdown 类型

用 lark-cli 把 .md/.docx 传到飞书时，**导入成 docx 云文档**（`drive +import --type docx`），不要 `markdown +create` 建成 markdown 文件类型——后者在飞书里读着"太难受"（标题/表格/列表渲染差），用户明确否过。
- 命令：`cd <dir> && lark-cli drive +import --profile cli_aa823d7922f8dbc3 --as user --file "./x.md" --type docx --name "标题" --folder-token <tok>`
  - `--file` / `@file` 都**必须相对路径**（绝对路径报 invalid_argument；CWD 要在文件所在目录）。
  - `--folder-token` 省略则进根目录。import 返回 `data.token` 即新文档 token；也可传 .docx 源文件，同样 `--type docx`。
- 也可以 `markdown +create --as user --profile <profile> --name X.md --file ./X.md`（走 drive 上传，需 `drive:file:upload`），产物 `url` 形如 `...feishu.cn/file/<token>`——但渲染差，**优先用 import docx**。
- 删文件：`drive +delete --file-token <tok> --type file --yes`（high-risk，需用户确认）。

### 建完直接设公开可读

docx / markdown 新建默认 `tenant_readable`（同租户凭链接可读），**别的账号/未登录浏览器打开会"无权限/申请权限"**。用户偏好建完就直接公开可读：
```bash
lark-cli --profile cli_aa823d7922f8dbc3 drive permission.public patch --as user \
  --token <docx_token> --type docx \
  --data '{"external_access":true,"link_share_entity":"anyone_readable","share_entity":"anyone","invite_external":true}' --yes
```
- ⚠ high-risk-write，`--yes` 必须等用户确认后才能加。改前可用 `permission.public get` 查现状。enum 见 `lark-cli schema drive.permission.public.patch`。
- **参数坑（已消歧）**：`link_share_entity:"anyone_readable"` 单独设无效，**必须同时 `external_access:true` 才生效**。`external_access` 默认就是 true（通常已满足），但 patch 时显式带上更稳。

### bot 身份的坑

- `docs +create --doc-format markdown --as bot` 能成功创建并写入，但 `permission_grant` 给当前用户会 **failed**——app 缺 `docs:permission.member:create` 等 scope，文档被 bot 拥有、**用户打不开**。
- 要用户能打开：让用户跑（`!` 前缀在会话里跑）`lark-cli auth login --scope "docx:document:create docs:permission.member:create drive:file:upload drive:drive.metadata:readonly"`（阻塞、输出验证 URL，浏览器授权），之后 `--as user` 重建文档，用户即拥有、立即可开。bot 拥有的旧文档可删。
- 读取校验：`docs +fetch --doc <id> --as bot` 看 content 字段是否写入成功。

### 改文档（block_delete / str_replace）

- bot 即使有 write scope，对**用户拥有的 wiki/docx 也只能读不能改**——返回 `ok:true` 但 `"result":"failed"` + warning `degrade_code=4030004 No permission`，不持久化（坑：只看 ok 字段会误以为成功）。
- 必须用 `--as user` 且 user token 有 `docx:document:write_only` scope（默认没有，需 re-auth 加）。
- 批量删块：`docs +update --command block_delete --block-id "id1,id2,..."`（逗号分隔，每批 ≤50 稳）；先 `docs +fetch --detail with-ids` 拿 block id，只删顶层空 `<p>`（跳过 `<table>` 内的，否则空单元格可能坏表）。
- wiki URL `/wiki/<node_token>` 的 node_token 可直接当 `--doc` 用，底层会解析到真实 docx token。

## When to Use

- 用 lark-cli 往飞书传内容/建文档时（导入 docx、设公开、选 SA 账号）。
- 遇到 bot 建的文档打不开、missing_scope、permission_grant failed 时。
- 需要批量改飞书文档 block 时。
