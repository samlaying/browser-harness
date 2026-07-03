# new-api 网关用法（翻译/分类/识图）

> 真相来源：`/Users/sam/lark/account/servers/RackNerd/new-api/index.md`（含密钥/部署/渠道）。本文件只摘录本 skill 用到的部分 + 实战教训。

## 连接

| 项 | 值 |
|---|---|
| OpenAI 兼容入口 | `http://192.227.138.214:3000/v1/chat/completions` |
| 鉴权 | `Authorization: Bearer <NEWAPI_TOKEN>` |
| 令牌 | 在服务器用 `cli-anything-newapi token create` 建，或 Web UI（`http://192.227.138.214:3000`）复制 |

**令牌走环境变量 `NEWAPI_TOKEN`，不要写进脚本/进 git。** 本 skill 的 `x_enrich.py` 即如此读取。

## 本 skill 用到的模型

| 模型 | 上游 | 用途 |
|---|---|---|
| `@cf/moonshotai/kimi-k2.7-code` | Cloudflare | **翻译 + 分类 + 打标**（推理模型，262k 上下文） |
| `ocr-space` | OCR.space | 图片文字识别（经 `ocr-adapter`） |
| `deepseek-ai/DeepSeek-V3.2` / `Qwen/Qwen3-32B` | 硅基流动 | 便宜的文本模型备选（翻译分类也够用，省额度） |

## 调用（OpenAI 兼容）

```python
# x_enrich.py 的核心调用形态
import urllib.request, json
body = json.dumps({
    "model": "@cf/moonshotai/kimi-k2.7-code",
    "messages": [{"role": "user", "content": "<prompt>"}],
}).encode()
req = urllib.request.Request(
    "http://192.227.138.214:3000/v1/chat/completions", data=body,
    headers={"Authorization": f"Bearer {NEWAPI_TOKEN}", "Content-Type": "application/json"})
d = json.loads(urllib.request.urlopen(req, timeout=120).read())
content = d["choices"][0]["message"]["content"]   # 推理模型的最终答案（reasoning_content 是思考过程，忽略）
```

## 实战教训（踩过的坑）

1. **令牌额度会耗尽**：推理模型（Kimi）很贵。曾用一个小额度测试令牌（`server-smoke`）跑 13 条 Kimi 就透支到负数 → 之后全 `401 Invalid token`。
   - 解法：用**无限额度**的 pool 令牌；或在服务器建大额度令牌。
   - 401 持续不退避 = 额度没了（不是短时限流）；诊断：ssh 上去 `cli-anything-newapi --json token list` 看 `remain_quota`。

2. **Kimi 视觉走不通**：`@cf/moonshotai/kimi-k2.7-code` 传 `image_url` 直接 `400 Bad Request`（尽管文档标"视觉"）。→ **图片识别用 `ocr-space`，不用 Kimi。**

3. **ocr-space 易超时**：对 `pbs.twimg.com` 的远程图常 `502 read operation timed out`，base64 直传也救不了（是 OCR.space 上游本身慢）。当前不可靠，OCR 列留空待恢复。

4. **并发别太猛**：并发 5 一般 OK；若令牌有 RPM 限制，降并发到 2 + 401 时长退避（20s）。`x_enrich.py` 已内置退避。

## 想拿可下载的视频 mp4？

网关模型帮不了（视频是 blob）。走 CDP：`Network.enable` → 重载详情页 → 抓 `TweetResultByRestId` GraphQL 请求的 `requestId` + bearer → `Network.getResponseBody` → 解析 `video_info.variants` 选最高 bitrate。完整流程见 `~/.claude/projects/.../memory/x-video-download-recipe.md`。
