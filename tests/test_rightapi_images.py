import io

import httpx
import pytest
from PIL import Image

from stylemate.rightapi_images import RightAPIImageClient


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_async_generation_submits_polls_and_downloads_without_leaking_key() -> None:
    requests: list[httpx.Request] = []
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        requests.append(request)
        if request.url.path == "/draw/v1/images/generations":
            payload = __import__("json").loads(request.content)
            assert request.headers["Authorization"] == "Bearer relay-secret"
            assert payload["async"] is True
            assert payload["model"] == "gpt-image-2"
            assert "imageSize" not in payload
            assert payload["image"][0].startswith("data:image/png;base64,")
            return httpx.Response(200, json={"task_id": "task_123", "status": "queued"})
        if request.url.path == "/v1/tasks/task_123":
            polls += 1
            if polls == 1:
                return httpx.Response(200, json={"task_id": "task_123", "status": "in_progress"})
            return httpx.Response(
                200,
                json={
                    "task_id": "task_123",
                    "data": [{"url": "https://cdn.example.com/result.png"}],
                },
            )
        if request.url.host == "cdn.example.com":
            assert "Authorization" not in request.headers
            return httpx.Response(200, content=png_bytes(), headers={"content-type": "image/png"})
        return httpx.Response(404)

    client = RightAPIImageClient(
        api_key="relay-secret",
        model="gpt-image-2",
        transport=httpx.MockTransport(handler),
        poll_interval=0,
        max_poll_attempts=3,
    )

    result = client.generate(png_bytes(), "image/png", "Create a flat lay")

    Image.open(io.BytesIO(result)).verify()
    assert [request.method for request in requests] == ["POST", "GET", "GET", "GET"]


def test_completed_task_accepts_inline_base64_image() -> None:
    encoded = __import__("base64").b64encode(png_bytes()).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "inline_1"})
        return httpx.Response(
            200,
            json={"data": [{"b64_json": encoded}]},
        )

    client = RightAPIImageClient(
        api_key="relay-secret",
        model="gpt-image-2",
        transport=httpx.MockTransport(handler),
        poll_interval=0,
        max_poll_attempts=1,
    )

    assert client.generate(png_bytes(), "image/png", "flat lay") == png_bytes()


def test_failed_async_task_raises_safe_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "failed_1"})
        return httpx.Response(
            200,
            json={"status": "failed", "error": {"message": "secret upstream detail"}},
        )

    client = RightAPIImageClient(
        api_key="relay-secret",
        model="gpt-image-2",
        transport=httpx.MockTransport(handler),
        poll_interval=0,
        max_poll_attempts=1,
    )

    with pytest.raises(RuntimeError, match="异步绘图任务失败") as raised:
        client.generate(png_bytes(), "image/png", "flat lay")
    assert "secret upstream detail" not in str(raised.value)


def test_async_task_stops_after_bounded_polling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "slow_1"})
        return httpx.Response(200, json={"status": "processing"})

    client = RightAPIImageClient(
        api_key="relay-secret",
        model="gpt-image-2",
        transport=httpx.MockTransport(handler),
        poll_interval=0,
        max_poll_attempts=2,
    )

    with pytest.raises(TimeoutError, match="等待超时"):
        client.generate(png_bytes(), "image/png", "flat lay")
