from types import SimpleNamespace

import pytest

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


def test_separate_image_key_is_only_sent_to_image_client():
    created = []
    def factory(**kwargs):
        created.append(kwargs)
        return object()
    StyleMateAI(api_key="text-only", image_api_key="image-only",
                base_url="https://example.com/v1", client_factory=factory)
    assert [client["api_key"] for client in created] == ["text-only", "image-only"]


def test_plan_prompt_carries_conditions_preferences_and_distinct_goals() -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def parse(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(output_parsed=None)

    fake_client = SimpleNamespace(responses=FakeResponses())
    service = StyleMateAI(
        api_key="relay-key",
        base_url="https://relay.example.com/v1",
        text_model="relay-vision",
        text_api="responses",
        client_factory=lambda **_: fake_client,
    )
    garment = GarmentAnalysis(
        category="上装", subcategory="短款皮夹克", color="深棕色", material="皮革",
        pattern="无", fit="修身", seasons=["秋季"], styles=["美式复古"],
    )
    with pytest.raises(RuntimeError):
        service.plan_outfits(
            garment, "上班", "美式复古",
            conditions="气温：寒冷 0–9°C；天气：小雨；通勤：步行较久",
            preferences="禁用单品（任何一套都不得出现）：高跟鞋",
        )

    prompt = str(captured["input"])
    assert "寒冷 0–9°C" in prompt and "小雨" in prompt
    assert "高跟鞋" in prompt and "硬性约束" in prompt
    instructions = str(captured["instructions"])
    assert "稳妥" in instructions and "进阶" in instructions and "突破" in instructions
    assert "面料、鞋子和外套" in instructions
    assert "骑行" in instructions and "长外套" in instructions
