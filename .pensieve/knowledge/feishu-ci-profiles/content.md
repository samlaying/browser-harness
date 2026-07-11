---
id: feishu-ci-profiles
type: knowledge
title: 飞书 CI Profile 凭证位置
status: active
created: 2026-07-10
updated: 2026-07-10
tags: [pensieve, knowledge, feishu, lark, profiles, credentials]
---

# 飞书 CI Profile 凭证位置

## Summary

三个飞书 CI profile 的用途、appId、登录用户，以及各自 token / app secret 存在本地哪里。
AI 或人查到这里就知道每个账号是干嘛的、去哪拿凭证。

## Content

### 三个 profile

| Profile | appId | 登录用户 | 用途 | 文档存放 |
|---|---|---|---|---|
| 造物SAMLAB | `cli_aada61b189b95cd1` | SAM | 主线内容（核心/主） | wiki（不公开） |
| 猎聘 | `cli_a9772deff9b95cdd` | 昀和（林承列） | 上班用（工作） | 飞书文件夹（公开） |
| SA | `cli_aa823d7922f8dbc3` | 飞书用户4228SA | 同步造物SAMLAB + 生活琐事 | 飞书文件夹（公开） |

> **SA 同步造物SAMLAB**：建同名 wiki，放公开文件夹，格式与造物SAMLAB 原版（私有）不同。
> **归档规则**：各账号建文档必须放进自己的对应位置（造物SAMLAB→wiki；猎聘/SA→各自的公开飞书文件夹），不得散落随机位置。

### SA 已知归档文件夹

SA 账号根目录文件夹很多且较杂，按主题归到下表的已知文件夹；新主题先建专属文件夹再用。

| 文件夹 | folder_token | 用途 |
|---|---|---|
| 职场 | `BzDPfro1ol4pmfdHUsqc1gcln0B` | 职场类内容（小红书职场选题调研等） |

- 职场文件夹 URL：https://pcnlp18cy9bm.feishu.cn/drive/folder/BzDPfro1ol4pmfdHUsqc1gcln0B
- 上传内容到此文件夹（**用 docx 导入，别建 markdown 文件类型——md 读着难受**）：`lark-cli --profile cli_aa823d7922f8dbc3 drive +import --as user --type docx --folder-token BzDPfro1ol4pmfdHUsqc1gcln0B --file <相对路径.md> --name <名>`
  - `--file` 只收相对路径（cd 到对应目录或用相对路径），`--type docx` 把本地 .md 导入成飞书在线文档
  - 也可以传 .docx 源文件，同样 `--type docx`

### 凭证 / token 在哪

都由 **lark-cli 本地加密缓存**：

- 配置：`~/.lark-cli/config.json`
- App secret：`~/Library/Application Support/lark-cli/appsecret_<appId>.enc`
- 用户 token：`~/Library/Application Support/lark-cli/<appId>_<open_user_id>.enc`

查某账号 token 状态 / 拿凭证：

```bash
lark-cli --profile <appId> auth status
```

## When to Use

- 要用某账号调飞书 CI、需要它的 token / 凭证时，先查上面表拿 appId，再 `auth status`。
- 要往某账号上传内容（md/文档）时，先查「SA 已知归档文件夹」确定落点；新主题先建专属文件夹，别散落根目录。
