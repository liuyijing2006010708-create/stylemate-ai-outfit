# 配置指南

StyleMate 支持在页面中配置 API，也支持本地通过 `.env` 提供默认值。公开部署入口 `cloud_app.py` 会忽略服务器环境中的 API Key，避免维护者的 Key 被访客共享使用。

## 本地环境变量

将示例文件复制为本地配置：

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
| -------- | -------- | ------- | ----------- |
| `OPENAI_API_KEY` | 真实模型调用需要 | 空 | 文本 API Key；未单独配置生图 Key 时也用于生图 |
| `OPENAI_BASE_URL` | 否 | `https://api.openai.com/v1` | 文本接口 Base URL |
| `OPENAI_IMAGE_BASE_URL` | 否 | 空 | 生图 Base URL；为空时复用文本 Base URL |
| `OPENAI_TEXT_MODEL` | 否 | `gpt-4.1-mini` | 视觉识别和搭配规划模型 |
| `OPENAI_IMAGE_MODEL` | 否 | `gpt-image-1` | 图片编辑或异步生图模型 |
| `OPENAI_TEXT_API` | 否 | `chat_completions` | `chat_completions` 或 `responses` |

`.env` 已被 `.gitignore` 忽略。不要把真实 Key 写入 `.env.example`、源码、Issue、Pull Request 或截图。

## 页面配置

首次打开页面会进入 API 配置。页面支持：

- OpenAI 官方预设。
- 通用 OpenAI-compatible endpoint。
- 已实现专用协议适配的 RightAPI 异步生图预设。
- 高级自定义配置。

通用与高级配置允许分别设置文本和生图 Base URL、模型和 API Key。生图 Key 留空时复用文本 Key；生图 Base URL 留空时复用文本 Base URL。

页面中保存的 Key 只存在于当前 Streamlit 会话内存，不会写回 `.env` 或项目文件。清除会话 Key 不会取消第三方已经接收的请求或删除第三方记录。

## 配置优先级

本地入口 `app.py` 的初始值来自环境变量，之后以当前页面会话保存的配置为准。公开入口 `cloud_app.py` 不读取服务器的 `OPENAI_API_KEY`，但仍使用非敏感环境变量作为初始 Base URL、模型和协议值。

每个已开始的搭配批次保存当时的 API 配置，用于异步任务续查；之后修改页面配置不会把新 Key 用于旧任务。

## 地址与连接检查

- Base URL 必须是可解析的 HTTPS 公网地址。
- URL 不能包含用户名、密码、查询参数或片段。
- 地址 / DNS 检查不发送 Key、图片或模型请求。
- 文本接口测试会发送一次最小请求，可能产生服务商费用。
- 生图检查只查询模型列表；它不创建图片，也不能证明实际编辑协议、余额或模型权限可用。

遇到 Clash Fake-IP 时，程序会尝试通过 Cloudflare 加密 DNS 查询真实公网地址。该回退只发送域名，不发送 Key、图片或提示词；失败时不会绕过公网地址校验。

## 常见问题

### 鉴权失败

核对 API Key、Base URL、模型权限，以及 Key 是否属于当前配置的服务商。不要把完整 Key 粘贴到 Issue 或日志中。

### 模型或接口不存在

使用服务商提供的确切模型 ID，并确认所选文本协议与服务端实现一致。部分兼容服务只实现 Chat Completions，没有实现 Responses API。

### 文本成功但生图失败

文本和图片是独立能力。确认生图 Base URL、图片模型和 Key 均正确，并确认服务实现兼容的图片编辑接口或项目中已有的专用异步适配器。更多要求见 [Provider 指南](providers.md)。

### 公开部署没有读取服务器 Key

这是预期行为。`cloud_app.py` 通过 `PUBLIC_DEPLOYMENT` 禁止把维护者环境中的 API Key 交给访客；每位访客应在页面中配置自己的 Key。
