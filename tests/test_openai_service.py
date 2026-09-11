from types import SimpleNamespace

from stylemate.models import GarmentAnalysis, Outfit
from stylemate.openai_service import StyleMateAI


def test_service_passes_relay_configuration_to_openai_client() -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    service = StyleMateAI(
        api_key="relay-key",
        base_url="https://relay.example.com/v1/",
        text_model="relay-vision",
        image_model="relay-image",
        text_api="chat_completions",
        client_factory=fake_client_factory,
    )

    assert captured == {
        "api_key": "relay-key",
        "base_url": "https://relay.example.com/v1",
        "timeout": 180.0,
        "max_retries": 0,
    }
    assert service.text_model == "relay-vision"
    assert service.image_model == "relay-image"
    assert service.text_api == "chat_completions"


def test_chat_completions_mode_sends_current_image_to_relay() -> None:
    captured: dict[str, object] = {}
    garment = GarmentAnalysis(
        category="上装",
        subcategory="一字肩蕾丝长袖上衣",
        color="白色",
        material="蕾丝",
        pattern="花卉",
        fit="修身",
        seasons=["春季"],
        styles=["甜美"],
        preservation_notes=["一字肩领口"],
    )

    class FakeCompletions:
        def parse(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=garment))])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    service = StyleMateAI(
        api_key="relay-key",
        base_url="https://relay.example.com/v1",
        text_model="relay-vision",
        image_model="relay-image",
        text_api="chat_completions",
        client_factory=lambda **_: fake_client,
    )

    result = service.analyze_garment(b"current-upload", "image/jpeg")

    assert result.display_name == "白色一字肩蕾丝长袖上衣"
    messages = captured["messages"]
    image_url = messages[1]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")


def test_rightapi_image_generation_uses_async_adapter() -> None:
    captured: dict[str, object] = {}

    class FakeRightAPIImages:
        def generate(self, image_bytes: bytes, mime_type: str, prompt: str) -> bytes:
            captured.update(image_bytes=image_bytes, mime_type=mime_type, prompt=prompt)
            return b"generated-image"

    def image_factory(**kwargs: object) -> FakeRightAPIImages:
        captured.update(kwargs)
        return FakeRightAPIImages()

    service = StyleMateAI(
        api_key="relay-key",
        base_url="https://rightapi.ai/codex/v1",
        text_model="gpt-5.6-luna",
        image_model="gpt-image-2",
        client_factory=lambda **_: object(),
        rightapi_image_factory=image_factory,
    )
    garment = GarmentAnalysis(
        category="上装",
        subcategory="蕾丝上衣",
        color="白色",
        material="蕾丝",
        pattern="花卉",
        fit="修身",
        seasons=["春季"],
        styles=["甜美"],
        preservation_notes=["一字肩领口"],
    )
    outfit = Outfit(
        id="look-1",
        style="约会造型",
        top="白色蕾丝上衣",
        outerwear="无",
        bottom="半身裙",
        shoes="玛丽珍鞋",
        bag="手提包",
        accessories=[],
        reason="色彩协调",
        compatibility_score=88,
        image_prompt="pair with a satin skirt",
    )

    result = service.generate_outfit_image(b"source", "image/jpeg", garment, outfit)

    assert result == b"generated-image"
    assert captured["api_key"] == "relay-key"
    assert captured["model"] == "gpt-image-2"
    assert captured["image_bytes"] == b"source"
    assert "top-down fashion flat-lay" in str(captured["prompt"])


def test_split_image_base_url_creates_separate_image_client() -> None:
    created: list[dict[str, object]] = []

    def fake_client_factory(**kwargs: object) -> object:
        created.append(dict(kwargs))
        return object()

    service = StyleMateAI(
        api_key="sk-text-img-demo",
        base_url="https://relay.example.com/v1",
        image_base_url="https://relay-draw.example.com/v1",
        text_model="relay-vision",
        image_model="relay-image",
        text_api="chat_completions",
        client_factory=fake_client_factory,
    )

    assert len(created) == 2
    text_client, image_client = created
    assert text_client["base_url"] == "https://relay.example.com/v1"
    assert image_client["base_url"] == "https://relay-draw.example.com/v1"
    assert service.image_client is not service.client


def test_image_protocol_is_selected_from_image_base_url() -> None:
    captured: dict[str, object] = {}

    class FakeRightAPIImages:
        pass

    def image_factory(**kwargs: object) -> FakeRightAPIImages:
        captured.update(kwargs)
        return FakeRightAPIImages()

    service = StyleMateAI(
        api_key="sk-text-img-demo",
        base_url="https://relay.example.com/v1",
        image_base_url="https://rightapi.ai/draw/v1",
        text_model="relay-vision",
        image_model="gpt-image-2",
        text_api="chat_completions",
        client_factory=lambda **_: object(),
        rightapi_image_factory=image_factory,
    )

    assert service.image_generation_mode == "rightapi_async"
    assert captured == {"api_key": "sk-text-img-demo", "model": "gpt-image-2"}


def test_separate_image_key_is_only_sent_to_image_client():
    created = []
    def factory(**kwargs):
        created.append(kwargs)
        return object()
    StyleMateAI(api_key="text-only", image_api_key="image-only",
                base_url="https://example.com/v1", client_factory=factory)
    assert [client["api_key"] for client in created] == ["text-only", "image-only"]
