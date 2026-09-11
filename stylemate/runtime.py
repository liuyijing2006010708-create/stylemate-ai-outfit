"""Runtime decisions that keep live uploads separate from the product demo."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

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
    api_key: str
    base_url: str
    image_base_url: str
    text_model: str
    image_model: str
    text_api: str

    @classmethod
    def from_values(
        cls,
        *,
        api_key: str | None,
        base_url: str | None,
        image_base_url: str | None = None,
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
    return "自定义中转站"


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


def safe_connection_error(error: Exception) -> str:
    """Map provider failures to actionable messages without echoing responses."""

    status_code = getattr(error, "status_code", None)
    if status_code in {401, 403}:
        return "鉴权失败：请检查 API Key 是否正确、有效并有该模型权限。"
    if status_code == 402:
        return "中转站账户余额不足，请充值后再试。"
    if status_code == 404:
        return "接口不存在：请检查 API Base URL 是否包含正确的渠道路径和 /v1。"
    if status_code == 429:
        return "请求被限流或额度已用完，请稍后重试并检查账户额度。"
    if isinstance(status_code, int) and status_code >= 500:
        return "中转站或其上游服务暂时异常，请稍后重试。"
    if error.__class__.__name__ in {"APIConnectionError", "APITimeoutError"}:
        return "无法连接中转站，请检查网络、域名和 HTTPS 证书。"
    return "连接验证失败，请检查 Base URL、API Key、网络和中转站权限。"


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
        raise ValueError("请先配置 OpenAI API Key，再识别自己的图片。")
    if not has_upload:
        raise ValueError("请先上传一张服装图片。")
    return RunMode.LIVE


def verify_api_key(
    api_key: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    text_model: str | None = None,
    client_factory: Callable[..., Any] = OpenAI,
) -> None:
    """Validate credentials with a metadata-only API request."""

    key = normalize_api_key(api_key)
    if not key:
        raise ValueError("API Key 不能为空。")
    normalized_base_url = normalize_base_url(base_url)
    client = client_factory(
        api_key=key,
        base_url=normalized_base_url,
        timeout=15.0,
        max_retries=0,
    )

    try:
        hostname = urlsplit(normalized_base_url).hostname or ""
    except ValueError:
        hostname = ""

    # RightAPI / RightCode 不提供标准的 /v1/models 接口，改用轻量 chat 请求验证。
    # 鉴权通过但模型名/协议细节不对时（400/404/422），说明网络与 Key 已打通，
    # 不算连接失败，留待真实请求进一步确认。
    if is_rightcode_host(hostname):
        try:
            client.chat.completions.create(
                model=text_model or "gpt-5.6-luna",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,
            )
        except (AuthenticationError, PermissionDeniedError, APIConnectionError, APITimeoutError):
            raise
        except Exception as exc:
            # 对 400/422 等模型/协议错误做更具体的提示，避免被 safe_connection_error 吞掉
            status_code = getattr(exc, "status_code", None)
            if status_code in {400, 404, 422}:
                return
            raise
    else:
        client.models.list()
