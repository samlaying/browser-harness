# 飞书多维表格 Schema + lark-cli 写法

`x_to_lark.py` 用 `lark-cli base` 操作飞书多维表格（Bitable）。本文件记录字段 schema 和关键命令。

## 字段 schema（12 列）

| 字段 | type | 写入值 | 说明 |
|---|---|---|---|
| 序号 | number | `1, 2, ...` | 行号 |
| 作者 | text | `@handle` | |
| 时间 | text | `9h \| 2026-07-02T13:42:02.000Z` | 相对 + ISO |
| 原文 | text | 英文全文 | show-more 已展开 |
| 中文翻译 | text | Qwen3-VL 译文 | `enriched.zh` |
| 分类 | select | `项目\|趋势\|观点\|通用\|其他` | 单选，选项预定义 |
| 标签 | text | `Claude Code, Fable` | 逗号拼接（动态标签用 text 不用多选） |
| 点赞 | number | `60` | |
| 图片 | text | URL，多张换行 | 阶段 1 是 URL 列；要内嵌缩略图需附件字段（见下） |
| 视频 | text | status URL（仅视频帖） | 非视频帖留空 |
| OCR | text | 图片理解+OCR | `enriched.img`（Qwen3-VL 视觉输出：描述图 + 提取图中文字） |
| 链接 | text | `https://x.com/.../status/<id>` | |

建表时 `--fields` 的 JSON 即这份 schema（`x_to_lark.py` 里 `FIELDS` 常量）。

## 关键 lark-cli 命令

### 建表（含 schema）

```bash
lark-cli base +base-create --as user \
  --name "X 推文巡检 20260703" \
  --table-name "推文" \
  --fields '[{"name":"序号","type":"number"},...,{"name":"分类","type":"select","options":[{"name":"项目"},...]},...]'
```
返回里有 `app_token`（= base_token）和 `url`。`x_to_lark.py` 会自动解析。

### 批量写记录（≤200 行/批）

```bash
lark-cli base +record-batch-create --as user \
  --base-token <bt> --table-id 推文 \
  --json '{"fields":["序号","作者",...],"rows":[[1,"@h","..."],[2,...]]}'
```
- `fields` 是列名顺序；`rows` 是行数组，每行按 `fields` 顺序，空值用 `null`。
- `--table-id` 可传 table ID（`tbl...`）**或表名**（`推文`）。
- 单批最多 200 行；超过需分批。

### 读记录（核对用）

```bash
lark-cli base +record-list --as user --base-token <bt> --table-id 推文 --page-size 100
```

## CellValue 写值规则（happy path）

| 字段类型 | 写入值 |
|---|---|
| text / phone / url | `"字符串"` |
| number / currency / percent | `12.5`（数字，非字符串） |
| select（单选） | `"选项名"`（须匹配已定义选项） |
| multi-select | `["标签A","标签B"]` |
| datetime | `"2026-03-24 10:00:00"` |
| checkbox | `true` / `false` |
| null | 清空单元格（允许时） |

> 系统/只读字段（`auto_number`、公式、lookup、`created_at` 等）不要写。附件字段不能当普通 CellValue 写——见下。

## 鉴权：★ 必须用 SA 账号

lark-cli 有多个 profile（app/账号）。**默认 profile（猎聘/同道）没有 `base:*` scope**，建/写多维表格会 `missing_scope: base:app:create` 失败。

**必须用 SA 账号** profile `cli_aa823d7922f8dbc3`（用户 `飞书用户4228SA`，有完整 `base:app:*/base:table:*/base:record:*` scope）。

- 手动 lark-cli 命令：每条加 `--profile cli_aa823d7922f8dbc3`（或 `--as user` 配合该 profile）。
- `x_to_lark.py`：设环境变量 `LARK_PROFILE=cli_aa823d7922f8dbc3`，脚本会自动给所有 lark-cli 调用加 `--profile`。
- 查 profile 状态：`lark-cli auth status --profile cli_aa823d7922f8dbc3`（SA 的 token `needs_refresh` 是正常的，下次调用自动刷新）。
- 查所有账号：`lark-cli auth list`；profile 列表：config 在 `~/.lark-cli/config.json`。

> SA 账号的 base scope 是早就授权好的，无需重新走 device-flow 登录。其它 profile 要用 base 得先 `lark-cli auth login --scope "base:app:create base:table:* base:record:*"` 补授权（device-flow，需浏览器扫码）。

## 设为公开（任何人凭链接可看）

```bash
lark-cli drive permission.public patch \
  --profile cli_aa823d7922f8dbc3 --as user \
  --token <base_token> --type bitable \
  --data '{"link_share_entity":"anyone_readable","external_access_entity":"open"}' \
  --yes
# 复查：lark-cli drive permission.public get --profile cli_aa823d7922f8dbc3 --as user --token <bt> --type bitable
```
- `link_share_entity`：`anyone_readable`（只读公开）/ `anyone_readwrite`（公开可编辑）/ `open`（关闭）。
- `external_access_entity: open` 让组织外部也能访问（要"全网公开"必须开）。
- `permission.public patch` 是 **high-risk-write**，需 `--yes`（用户确认后才能加）。

## 想要图片内嵌（附件字段）？

当前 `图片` 列是 URL 文本。要像 Excel 那样**内嵌缩略图**，需另建一个 `attachment` 字段，逐张上传（同样要 SA profile）：

```bash
lark-cli base +record-upload-attachment \
  --profile cli_aa823d7922f8dbc3 --as user \
  --base-token <bt> --table-id 推文 --record-id <rid> \
  --field-name 图片附件 --file path/to/img.jpg
```

50 条 × 多图，工作量大但可控。可写一个独立原子脚本 `x_upload_images.py` 串 `+record-upload-attachment`（按 tid 对齐本地 `x_images/` 文件与 record_id）。本 skill 暂未包含，按需添加。
