# new-api 网关用法（翻译/分类/识图）

> 真相来源：本地 `lark/account/servers/RackNerd/new-api/index.md`（含密钥/部署/渠道，未纳入 git）。本文件只摘录本 skill 用到的部分 + 实战教训。

## 连接

| 项 | 值 |
|---|---|
| OpenAI 兼容入口 | `http://<YOUR_SERVER_IP>:3000/v1/chat/completions` |
| 鉴权 | `Authorization: Bearer <NEWAPI_TOKEN>` |
| 令牌 | 在服务器用 `cli-anything-newapi token create` 建，或 Web UI（`http://<YOUR_SERVER_IP>:3000`）复制 |

**令牌走环境变量 `NEWAPI_TOKEN`，不要写进脚本/进 git。** 本 skill 的 `x_enrich.py` 即如此读取。

## 本 skill 用到的模型

| 模型 | 上游 | 用途 |
|---|---|---|
| `Qwen/Qwen3-VL-8B-Instruct` | 硅基流动 | **★ 默认视觉模型**：图文感知，出译文+图片理解/OCR+分类+标签（x_enrich 默认） |
| `Qwen/Qwen3-VL-32B-Instruct` | 硅基流动 | 更强的视觉模型（按质量换速度/成本，`NEWAPI_MODEL` 切换） |
| `deepseek-ai/DeepSeek-V3.2` / `Qwen/Qwen3-32B` | 硅基流动 | 纯文本备选（不要图时省成本） |
| `@cf/moonshotai/kimi-k2.7-code` | Cloudflare | ❌ 视觉走不通（image_url 报 400）+ 易 429 限流，**别用来识图** |

> ⚠️ **VL 模型默认不在渠道里**：硅基流动渠道（channel 1）出厂只开了文本模型，VL 报 `model_not_found`。需手动加（见下方教训 3）。

## 调用（OpenAI 兼容，多模态）

```python
# x_enrich.py 的核心调用形态：正文 + 配图(base64) 一起喂 VL 模型
import urllib.request, json, base64
img_b64 = base64.b64encode(urllib.request.urlopen(urllib.request.Request(
    img_url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://x.com/'})).read()).decode()
content = [
    {"type": "text", "text": "<prompt>\n推文正文:\n" + text},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64}},
]
body = json.dumps({"model": "Qwen/Qwen3-VL-8B-Instruct",
                   "messages": [{"role": "user", "content": content}]}).encode()
req = urllib.request.Request("http://<YOUR_SERVER_IP>:3000/v1/chat/completions", data=body,
    headers={"Authorization": f"Bearer {NEWAPI_TOKEN}", "Content-Type": "application/json"})
d = json.loads(urllib.request.urlopen(req, timeout=150).read())
content = d["choices"][0]["message"]["content"]
```

## 实战教训（踩过的坑）

1. **令牌额度会耗尽**：曾用一个小额度测试令牌跑 13 条 Kimi（推理模型，贵）就透支到负数 → 之后全 `401 Invalid token`。
   - 解法：用**无限额度**的 pool 令牌；或在服务器建大额度令牌。
   - 401 持续不退避 = 额度没了（不是短时限流）；诊断：ssh 上去 `cli-anything-newapi --json token list` 看 `remain_quota`。

2. **Kimi 视觉走不通**：`@cf/moonshotai/kimi-k2.7-code` 传 `image_url` 直接 `400 Bad Request`（尽管文档标"视觉"），且 CF 渠道易 `429` 限流。→ **识图用 Qwen3-VL（硅基流动渠道），不用 Kimi。**

3. **VL 模型要手动加到渠道**：硅基流动渠道默认只有文本模型，直接调 `Qwen/Qwen3-VL-8B-Instruct` 报 `model_not_found / No available channel`。ssh 上去加：
   ```bash
   ssh racknerd 'V=/root/new-api-cli/venv; export NEW_API_CONFIG=/root/new-api-cli/profiles.json
   $V/bin/cli-anything-newapi -P local channel update --id 1 \
     --models "deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1,Qwen/Qwen3-32B,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen3-Coder-30B-A3B-Instruct,Qwen/Qwen3-VL-8B-Instruct,Qwen/Qwen3-VL-32B-Instruct"'
   ```
   （`--models` 是**全量替换**，要把原有模型一起带上。）

4. **`pbs.twimg.com` 图必须 base64**：X 有防盗链，硅基流动/上游 fetcher 直接传 URL 会报 "image URL must be a valid and downloadable URL"。必须先下载（带 `Referer: https://x.com/`）→ base64 → `data:image/jpeg;base64,...` 直传。喂 VL 时用 `name=medium`（不用 orig）控 base64 体积。

5. **ocr-space 不可靠**：对推文图常 `502 read operation timed out`（上游本身慢，base64 也救不了）。已弃用，识图统一走 Qwen3-VL。

6. **并发**：Qwen3-VL 在硅基流动渠道 RPM 较高，并发 3~5 一般 OK；遇 429/401 `x_enrich.py` 内置退避。

## 想拿可下载的视频 mp4？

网关模型帮不了（视频是 blob）。走 CDP：`Network.enable` → 重载详情页 → 抓 `TweetResultByRestId` GraphQL 请求的 `requestId` + bearer → `Network.getResponseBody` → 解析 `video_info.variants` 选最高 bitrate。完整流程见 `~/.claude/projects/.../memory/x-video-download-recipe.md`。
