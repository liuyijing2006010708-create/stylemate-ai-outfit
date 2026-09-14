"""Runtime decisions that keep live uploads separate from the product demo."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
from .consistency import PlanRejected
from .security import UnsafeURL, validate_url, resolve_public, secure_http_client, protect_provider_logs
from .operations import BusyError
from .rightapi_images import RightAPIError
from .uploads import InvalidImage

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
)


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TEXT_MODEL = "gpt-5.6-luna"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
# RightAPI 与 RightCode（right.codes）是同一家中转平台，共用同一套协议。
RIGHTAPI_HOSTS = {"rightapi.ai", "www.rightapi.ai", "right.codes", "www.right.codes"}


class RunMode(str, Enum):
    LIVE = "live"
    DEMO = "demo"


@dataclass(frozen=True)
class APIConfig:
    api_key: str = field(repr=False)
    base_url: str
    image_base_url: str
    text_model: str
    image_model: str
    text_api: str
    image_api_key: str = field(default="", repr=False)

    @classmethod
    def from_values(
        cls,
        *,
        api_key: str | None,
        base_url: str | None,
        image_base_url: str | None = None,
        image_api_key: str | None = None,
        text_model: str | None,
        image_model: str | None,
        text_api: str | None,
    ) -> "APIConfig":
        key = normalize_api_key(api_key)
        if not key:
            raise ValueError("API Key 不能为空。")
        protocol = (text_api or "responses").strip().lower()
        if protocol not in {"responses", "chat_completions"}:
            raise ValueError("文本接口必须是 responses 或 chat_completions。")
        normalized_base_url = normalize_base_url(base_url)
        image_base_url_value = (image_base_url or "").strip()
        normalized_image_base_url = normalize_base_url(image_base_url_value or base_url)
        return cls(
            api_key=key,
            base_url=normalized_base_url,
            image_base_url=normalized_image_base_url,
            text_model=normalize_model_id(text_model or DEFAULT_TEXT_MODEL),
            image_model=normalize_model_id(image_model or DEFAULT_IMAGE_MODEL),
            text_api=protocol,
            image_api_key=normalize_api_key(image_api_key) or key,
        )


def normalize_api_key(value: str | None) -> str:
    return (value or "").strip()


def normalize_model_id(value: str) -> str:
    model_id = value.strip()
    if not MODEL_ID_PATTERN.fullmatch(model_id):
        raise ValueError("模型名称格式无效。")
    return model_id


def normalize_base_url(value: str | None) -> str:
    raw = (value or DEFAULT_BASE_URL).strip()
    validate_url(raw)
    if len(raw) > 2048:
        raise ValueError("Base URL 过长。")
    parsed = urlsplit(raw)
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Base URL 不能包含用户名或密码。")
    if parsed.query or parsed.fragment:
        raise ValueError("Base URL 不能包含查询参数或片段。")
    hostname = parsed.hostname.lower()
    is_loopback = hostname == "localhost"
    try:
        is_loopback = is_loopback or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
        raise ValueError("中转站必须使用 HTTPS；仅本机 localhost 可使用 HTTP。")
    path = parsed.path.rstrip("/")
    if hostname in RIGHTAPI_HOSTS and path in {"", "/v1", "/codex"}:
        path = "/codex/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def provider_display_name(base_url: str) -> str:
    try:
        hostname = urlsplit(normalize_base_url(base_url)).hostname or ""
    except ValueError:
        return "自定义中转站"
    if hostname in {"rightapi.ai", "www.rightapi.ai"}:
        return "RightAPI"
    if hostname in {"right.codes", "www.right.codes"}:
        return "RightCode"
    if hostname == "api.openai.com":
        return "OpenAI"
    return "兼容接口"


def is_rightcode_host(hostname: str) -> bool:
    """右 API / RightCode 共用一个平台，判断是否走其异步生图协议。"""

    return hostname in RIGHTAPI_HOSTS


def image_generation_mode(base_url: str) -> str:
    """Return the image protocol selected for a configured provider."""

    try:
        hostname = urlsplit(normalize_base_url(base_url)).hostname or ""
    except ValueError:
        return "openai_edits"
    if is_rightcode_host(hostname):
        return "rightapi_async"
    return "openai_edits"


def guess_preset(base_url: str) -> str:
    """Preset key matching a stored base URL; unknown relays stay custom."""

    try:
        hostname = urlsplit(normalize_base_url(base_url)).hostname or ""
    except ValueError:
        return "custom"
    if hostname in RIGHTAPI_HOSTS:
        return "rightapi"
    if hostname == "api.openai.com":
        return "openai"
    return "custom"


def safe_connection_error(error: Exception) -> str:
    """Map provider failures to actionable messages without echoing responses."""

    if isinstance(error, BusyError):
        return "操作繁忙或过于频繁，请等待至少 10 秒后重试（每 10 分钟最多 8 次）。"
    cause = error
    for _ in range(6):
        if isinstance(cause, UnsafeURL):
            return {
                "fake_ip": "检测到代理 Fake-IP，已尝试通过 Cloudflare 加密 DNS 查询真实公网 IP，但查询未成功。"
                           "请检查网络能否访问 1.1.1.1:443，或在 Clash 为 API 域名配置 Fake-IP 例外后重试。不要把 Base URL 改成保留 IP。",
                "dns_failure": "地址校验失败：DNS 无法解析服务域名。请核对 Base URL 拼写、网络和代理 DNS 设置后重试。",
                "non_public": "地址校验失败：域名解析到了内网或保留地址。请使用真实公网 API 地址；不要关闭安全校验。",
            }.get(cause.reason, "地址校验失败：仅允许 HTTPS 公网地址，不允许本机、内网、带账号密码或格式异常的 URL。")
        cause = getattr(cause, "__cause__", None)
        if cause is None:
            break
    if isinstance(error, TimeoutError):
        return "等待超时；已提交的图片任务可继续查询，不会重复提交。"
    # Only fixed machine codes are compared; response bodies are never shown.
    body = getattr(error, "body", None)
    code = body.get("code") if isinstance(body, dict) else None
    code = code or getattr(error, "code", None)
    if code == "model_not_found":
        return "模型不存在或无权访问：请核对模型名称是否为该服务商支持的确切名称。"
    if code == "insufficient_quota":
        return "余额或额度不足：请在中转站充值或更换额度更高的 Key。"
    status_code = getattr(error, "status_code", None)
    if status_code in {400, 422}:
        return "请求不兼容：请检查模型名称、文本协议和图片接口支持情况。"
    if status_code in {401, 403}:
        return "鉴权失败：请检查 API Key 是否正确、有效并有该模型权限。"
    if status_code == 402:
        return "中转站账户余额不足，请充值后再试。"
    if status_code == 404:
        return "接口不存在：请检查 API Base URL 是否包含正确的渠道路径和 /v1。"
    if status_code == 408:
        return "服务商响应超时，请稍后重试；已提交的图片任务可继续查询。"
    if status_code == 429:
        return "请求被限流或额度已用完，请稍后重试并检查账户额度。"
    if isinstance(status_code, int) and status_code >= 500:
        return "中转站或其上游服务暂时异常，请稍后重试。"
    # These classes only ever carry fixed, locally written messages.
    if isinstance(error, (InvalidImage, RightAPIError, PlanRejected)):
        return str(error)
    if error.__class__.__name__ in {"APIConnectionError", "APITimeoutError"}:
        return "无法连接中转站，请检查网络、域名和 HTTPS 证书。"
    return "连接验证失败，请检查 Base URL、API Key、网络和中转站权限。"


def verify_service_address(base_url: str) -> str:
    """DNS-only preflight: never send credentials, photos or model requests."""
    normalized = normalize_base_url(base_url)
    parts = urlsplit(normalized)
    resolve_public(parts.hostname, parts.port or 443)
    return "地址格式与公网 DNS 校验通过；尚未验证 HTTPS 连通性、Key、模型或额度。"


def decide_run_mode(
    has_upload: bool,
    api_key: str | None,
    *,
    demo_requested: bool,
) -> RunMode:
    """Reject ambiguous requests instead of silently substituting demo data."""

    if demo_requested:
        return RunMode.DEMO
    if not normalize_api_key(api_key):
        raise ValueError("请先配置 API Key，再识别自己的图片。")
    if not has_upload:
        raise ValueError("请先上传一张服装图片。")
    return RunMode.LIVE


def verify_api_key(
    api_key: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    text_model: str | None = None,
    text_api: str = "responses",
    client_factory: Callable[..., Any] = OpenAI,
) -> None:
    """Test the selected text endpoint; never infer success from an HTTP error."""

    key = normalize_api_key(api_key)
    if not key:
        raise ValueError("API Key 不能为空。")
    normalized_base_url = normalize_base_url(base_url)
    extra = {"http_client": secure_http_client(timeout=15.0)} if client_factory is OpenAI else {}
    protect_provider_logs()
    client = client_factory(
        api_key=key,
        base_url=normalized_base_url,
        timeout=15.0,
        max_retries=0,
        **extra,
    )
    try:
        if text_api == "chat_completions":
            result = client.chat.completions.create(
                model=text_model or DEFAULT_TEXT_MODEL,
                messages=[{"role": "user", "content": "Reply OK."}],
                max_completion_tokens=32,
            )
            if not result.choices:
                raise RuntimeError("文本接口未返回有效结果。")
        elif text_api == "responses":
            result = client.responses.create(model=text_model or DEFAULT_TEXT_MODEL,
                                             input="Reply OK.", max_output_tokens=32)
            if not result.output:
                raise RuntimeError("文本接口未返回有效结果。")
        else:
            raise ValueError("不支持的文本协议。")
    finally:
        if hasattr(client, "close"):
            client.close()


def verify_image_endpoint(config: APIConfig) -> str:
    """Metadata is optional and is explicitly not an image generation test."""
    if image_generation_mode(config.image_base_url) == "rightapi_async":
        return "已识别异步协议；实际生图待验证（不创建收费任务）。"
    with OpenAI(api_key=config.image_api_key, base_url=config.image_base_url,
                http_client=secure_http_client(timeout=15.0), max_retries=0) as client:
        try:
            models = client.models.list()
        except Exception as exc:
            if getattr(exc, "status_code", None) in {404, 405, 501}:
                return "服务不支持模型列表；实际生图待验证，可保存后试用。"
            raise
        if config.image_model not in {model.id for model in models.data}:
            return "模型列表未列出所选模型；请核对名称，实际生图待验证。"
        return "模型列表可用；图片编辑能力仍需实际生成验证。"
