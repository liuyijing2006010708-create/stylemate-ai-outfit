"""RightAPI's asynchronous image-generation adapter."""

from __future__ import annotations

import base64
import io
import ipaddress
import re
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from PIL import Image, UnidentifiedImageError
from .security import PublicTransport, validate_url, protect_provider_logs


SUBMIT_URL = "https://www.rightapi.ai/draw/v1/images/generations"
TASK_URL_PREFIX = "https://www.rightapi.ai/v1/tasks"
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_RESULT_BYTES = 20 * 1024 * 1024


class RightAPIError(RuntimeError):
    """A safe, user-presentable RightAPI failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RightAPIImageClient:
    """Submit one image task, wait for it, and return validated image bytes."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        transport: httpx.BaseTransport | None = None,
        poll_interval: float = 2.0,
        max_poll_attempts: int = 90,
        sleep: Callable[[float], None] = time.sleep,
        max_wait: float = 180.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key.strip():
            raise ValueError("API Key 不能为空。")
        if max_poll_attempts < 1 or poll_interval < 0:
            raise ValueError("轮询配置无效。")
        self.api_key = api_key.strip()
        self.model = model
        self.transport = transport
        self.poll_interval = poll_interval
        self.max_poll_attempts = max_poll_attempts
        self.sleep = sleep
        self.max_wait = max_wait
        self.clock = clock

    def generate(self, image_bytes: bytes, mime_type: str, prompt: str, *,
                 task_state: dict | None = None, on_progress: Callable | None = None) -> bytes:
        self._validate_source(image_bytes, mime_type)
        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "image": [f"data:{mime_type};base64,{encoded}"],
            "n": 1,
            "size": "1024x1024",
            "async": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        state = task_state if task_state is not None else {}
        if state.get("status") in {"submitting", "unknown"} and not state.get("task_id"):
            raise RightAPIError("提交结果未知，请先在服务商后台确认任务，避免重复计费。")
        if state.get("status") in {"failed", "cancelled", "canceled", "error"}:
            raise RightAPIError("异步绘图任务失败；如需重新提交，请明确创建新任务。")
        started = self.clock()
        def progress(status):
            state["status"] = status
            if on_progress:
                on_progress(state)
        protect_provider_logs()
        with httpx.Client(
            headers=headers,
            timeout=httpx.Timeout(60.0, connect=15.0),
            transport=self.transport or PublicTransport(),
            follow_redirects=False,
            trust_env=False,
        ) as api_client:
            task_id = state.get("task_id")
            if not task_id:
                progress("submitting")
                try:
                    submitted = self._request_json(api_client, "POST", SUBMIT_URL, json=payload)
                    task_id = submitted.get("task_id") or submitted.get("id")
                except Exception:
                    progress("unknown")
                    raise
            if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
                progress("unknown")
                raise RightAPIError("异步绘图接口没有返回有效的任务编号。")
            state["task_id"] = task_id
            progress("queued")

            transient_errors = 0
            for attempt in range(self.max_poll_attempts):
                remaining = self.max_wait - (self.clock() - started)
                if remaining <= 0:
                    break
                try:
                    task = self._request_json(
                        api_client, "GET", f"{TASK_URL_PREFIX}/{task_id}",
                        timeout=min(30.0, remaining),
                    )
                except RightAPIError as exc:
                    transient_errors += 1
                    state["query_errors"] = transient_errors
                    progress("query_error")
                    if transient_errors >= 3 or exc.status_code not in {None, 429, 500, 502, 503, 504}:
                        raise
                    self.sleep(min(2 ** transient_errors, max(0, self.max_wait - (self.clock() - started))))
                    continue
                transient_errors = 0
                status = str(task.get("status", "")).lower()
                if status in {"failed", "cancelled", "canceled", "error"}:
                    progress(status)
                    raise RightAPIError("RightAPI 异步绘图任务失败，请检查模型权限或账户额度。")
                if status in {"completed", "succeeded", "success"} or (not status and task.get("data")):
                    progress("downloading")
                    result = self._completed_image(task)
                    progress("completed")
                    return result
                if status not in {"queued", "pending", "processing", "in_progress", "running"}:
                    progress("query_error")
                    raise RightAPIError("RightAPI 返回了无法识别的任务状态。")
                progress(status)
                if attempt + 1 < self.max_poll_attempts:
                    self.sleep(min(self.poll_interval * (1 + attempt / 5), 5,
                                   max(0, self.max_wait - (self.clock() - started))))

        progress("timeout")
        raise TimeoutError("RightAPI 异步绘图等待超时，请稍后重试。")

    def _completed_image(self, task: dict[str, Any]) -> bytes:
        data = task.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise RightAPIError("异步绘图任务已完成，但没有返回可用图片。")
        item = data[0]
        inline = item.get("b64_json")
        if isinstance(inline, str):
            try:
                result = base64.b64decode(inline, validate=True)
            except (ValueError, TypeError) as exc:
                raise RightAPIError("RightAPI 返回的图片数据无效。") from exc
            return self._validate_result(result)
        url = item.get("url")
        if not isinstance(url, str):
            raise RightAPIError("异步绘图任务已完成，但没有返回可用图片。")
        self._validate_result_url(url)
        return self._download_result(url)

    def _download_result(self, url: str) -> bytes:
        # Deliberately use a separate client with no Authorization header.
        with httpx.Client(
            timeout=httpx.Timeout(60.0, connect=15.0),
            transport=self.transport or PublicTransport(),
            follow_redirects=False,
            trust_env=False,
        ) as download_client:
            try:
                with download_client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0]
                    if content_type and not content_type.startswith("image/"):
                        raise RightAPIError("RightAPI 结果地址返回的不是图片。")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESULT_BYTES:
                            raise RightAPIError("RightAPI 返回的图片超过 20 MB 限制。")
                        chunks.append(chunk)
            except httpx.HTTPError as exc:
                raise RightAPIError("无法下载 RightAPI 生成的图片。") from exc
        return self._validate_result(b"".join(chunks))

    @staticmethod
    def _request_json(
        client: httpx.Client,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise RightAPIError(
                f"RightAPI 请求失败（HTTP {status_code}）。",
                status_code=status_code,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise RightAPIError("无法连接 RightAPI 异步绘图接口。") from exc
        if not isinstance(payload, dict):
            raise RightAPIError("RightAPI 返回的数据格式无效。")
        return payload

    @staticmethod
    def _validate_source(image_bytes: bytes, mime_type: str) -> None:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise ValueError("RightAPI 仅支持 JPG、PNG 或 WEBP 输入图片。")
        if not image_bytes or len(image_bytes) > MAX_SOURCE_BYTES:
            raise ValueError("输入图片必须大于 0 且不超过 10 MB。")

    @staticmethod
    def _validate_result_url(url: str) -> None:
        validate_url(url)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise RightAPIError("RightAPI 返回了不安全的图片地址。")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            return
        if not address.is_global:
            raise RightAPIError("RightAPI 返回了不安全的图片地址。")

    @staticmethod
    def _validate_result(image_bytes: bytes) -> bytes:
        if not image_bytes or len(image_bytes) > MAX_RESULT_BYTES:
            raise RightAPIError("RightAPI 返回的图片大小无效。")
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise RightAPIError("RightAPI 返回的文件不是有效图片。") from exc
        return image_bytes
