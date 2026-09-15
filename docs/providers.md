# Provider 与协议指南

StyleMate 的主要集成边界是协议，而不是服务商品牌。文本接口通过 OpenAI Python SDK 调用，通用端点需要实现项目实际使用的 OpenAI-compatible API 行为。

## 支持矩阵

| Capability | Protocol or endpoint | Notes |
| ---------- | -------------------- | ----- |
| 服装视觉识别 | Responses API 或 Chat Completions | 模型必须支持图片输入和结构化输出解析 |
| 搭配规划 | Responses API 或 Chat Completions | 返回内容需要满足 Pydantic 结构化模型 |
| 单套替换 | Responses API 或 Chat Completions | 与搭配规划使用同一文本协议 |
| 平铺图 | OpenAI-compatible Image Edits | 调用配置端点下的图片编辑能力 |

## OpenAI

OpenAI 官方预设使用：

```env
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_TEXT_MODEL=gpt-4.1-mini
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_TEXT_API=responses
```

模型是否可用取决于账号权限和当前服务端支持。仓库中的默认值是配置默认值，不是对所有账号权限的保证。

## OpenAI-compatible endpoints

任意兼容服务都通过自定义 Base URL、API Key 和模型 ID 接入，不需要在源码中增加 Provider 名称。示例：

```env
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.example.com/v1
OPENAI_IMAGE_BASE_URL=https://images.example.com/v1
OPENAI_TEXT_MODEL=provider-vision-model
OPENAI_IMAGE_MODEL=provider-image-model
OPENAI_TEXT_API=chat_completions
```

使用前应确认：

- Base URL 是 HTTPS 公网地址，通常包含服务商要求的版本路径。
- 文本模型可以接收图片，并兼容 SDK 的结构化输出解析。
- `OPENAI_TEXT_API` 与服务实现一致；兼容范围不完整时通常先尝试 `chat_completions`。
- 若需要平铺图，服务需要实现与 OpenAI SDK `images.edit` 兼容的图片编辑能力。
- 文本与生图使用不同网关时，分别设置 Base URL；需要不同凭据时在页面启用独立生图 Key。

“支持 OpenAI-compatible”不表示所有第三方服务的所有模型都已逐一验证。具体模型、请求限制、数据保留和费用由对应服务商决定。

## 验证边界

- 地址 / DNS 检查：只验证 URL 和公网解析，不验证 Key、模型或费用。
- 文本接口测试：发送一次最小文本请求，可能计费。
- 生图模型检查：尝试读取模型列表，不创建图片；服务不提供列表时可以保存后再进行受控实测。
- 自动化测试：使用 Fake client 或 `httpx.MockTransport`，不会访问真实 Provider。

真实验收应只使用维护者自己的 Key 和无敏感信息的测试图片，先验证文本，再只生成一张图片。
