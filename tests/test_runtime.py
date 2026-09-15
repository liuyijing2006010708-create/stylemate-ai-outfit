import pytest
from types import SimpleNamespace

from stylemate.runtime import (
    APIConfig,
    RunMode,
    decide_run_mode,
    normalize_api_key,
    normalize_base_url,
    provider_display_name,
    safe_connection_error,
    verify_api_key,
)


def test_uploaded_image_without_key_never_silently_uses_demo() -> None:
    with pytest.raises(ValueError, match="API Key"):
        decide_run_mode(has_upload=True, api_key="", demo_requested=False)


def test_demo_requires_an_explicit_user_choice() -> None:
    assert decide_run_mode(False, "", demo_requested=True) is RunMode.DEMO
    assert decide_run_mode(True, "sk-test", demo_requested=False) is RunMode.LIVE


def test_live_generation_requires_an_uploaded_image() -> None:
    with pytest.raises(ValueError, match="上传"):
        decide_run_mode(False, "sk-test", demo_requested=False)


def test_api_key_is_trimmed_and_verified_without_being_returned_by_client() -> None:
    calls: list[str] = []

    class FakeResponses:
        def create(self, **kwargs) -> object:
            calls.append("text-tested")
            return SimpleNamespace(output=[{"type": "message"}])

    class FakeClient:
        def __init__(self, *, api_key: str, base_url: str, timeout: float, max_retries: int) -> None:
            calls.append(api_key)
            calls.append(base_url)
            calls.append(f"{timeout}:{max_retries}")
            self.responses = FakeResponses()

    assert normalize_api_key("  sk-secret-value  ") == "sk-secret-value"
    verify_api_key(
        "  sk-secret-value  ",
        base_url="https://relay.example.com/v1/",
        client_factory=FakeClient,
    )
    assert calls == [
        "sk-secret-value",
        "https://relay.example.com/v1",
        "15.0:0",
        "text-tested",
    ]


def test_relay_config_normalizes_base_url_and_models() -> None:
    config = APIConfig.from_values(
        api_key=" relay-key ",
        base_url="https://relay.example.com/v1/",
        text_model=" vendor/vision-model ",
        image_model=" vendor/image-model ",
        text_api="chat_completions",
    )

    assert config.api_key == "relay-key"
    assert config.base_url == "https://relay.example.com/v1"
    assert config.text_model == "vendor/vision-model"
    assert config.image_model == "vendor/image-model"
    assert config.text_api == "chat_completions"


def test_unknown_provider_uses_generic_display_name() -> None:
    base_url = "https://relay.example.com/v1"

    assert normalize_base_url(base_url) == base_url
    assert provider_display_name(base_url) == "兼容接口"


def test_default_models_are_not_tied_to_a_specific_relay() -> None:
    config = APIConfig.from_values(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        text_model=None,
        image_model=None,
        text_api=None,
    )

    assert config.text_model == "gpt-4.1-mini"
    assert config.image_model == "gpt-image-1"
    assert config.text_api == "chat_completions"


@pytest.mark.parametrize(
    "url",
    [
        "http://relay.example.com/v1",
        "https://user:pass@relay.example.com/v1",
        "https://relay.example.com/v1?token=secret",
        "file:///tmp/fake-api",
    ],
)
def test_relay_base_url_rejects_unsafe_values(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_base_url(url)


def test_local_http_relay_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_base_url("http://localhost:4000/v1/")


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "Key"),
        (402, "余额"),
        (404, "Base URL"),
        (429, "限流"),
        (500, "中转站"),
    ],
)
def test_connection_errors_are_safe_and_actionable(status_code: int, expected: str) -> None:
    error = RuntimeError("upstream response may contain secrets")
    error.status_code = status_code  # type: ignore[attr-defined]

    message = safe_connection_error(error)

    assert expected in message
    assert "secrets" not in message


def test_image_base_url_falls_back_to_text_base_url_when_blank() -> None:
    config = APIConfig.from_values(
        api_key="sk-text-img-demo",
        base_url="https://relay.example.com/v1",
        image_base_url="   ",
        text_model="vendor/vision-model",
        image_model="vendor/image-model",
        text_api="chat_completions",
    )
    assert config.image_base_url == "https://relay.example.com/v1"


def test_image_base_url_is_kept_when_provider_splits_text_and_image() -> None:
    config = APIConfig.from_values(
        api_key="sk-text-img-demo",
        base_url="https://relay.example.com/v1",
        image_base_url="https://relay-draw.example.com/v1/",
        text_model="vendor/vision-model",
        image_model="vendor/image-model",
        text_api="chat_completions",
    )
    assert config.base_url == "https://relay.example.com/v1"
    assert config.image_base_url == "https://relay-draw.example.com/v1"
