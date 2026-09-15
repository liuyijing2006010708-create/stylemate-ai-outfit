import io
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def test_release_identifier_visible_without_api_key():
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    assert not app.exception
    assert any("版本 0.3.1" in item.value for item in app.caption)


def test_first_visit_defaults_to_generic_openai_compatible_provider():
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    preset = next(x for x in app.selectbox if x.label == "服务商预设")

    assert preset.value == "通用 OpenAI 兼容接口"
    assert any(x.label == "API Base URL" for x in app.text_input)
    protocol = next(x for x in app.selectbox if x.label == "文本接口协议")
    assert protocol.value == "chat_completions"


def test_cloud_visitors_do_not_inherit_server_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "server-key-must-stay-private")
    first = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    assert not first.exception
    assert first.session_state["api_key"] == ""
    assert first.session_state["stage"] == "api"
    first.session_state["api_key"] = "visitor-one-key"
    second = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    assert not second.exception
    assert second.session_state["api_key"] == ""
    assert first.session_state["api_key"] == "visitor-one-key"


def test_partial_image_failure_preserves_other_results_and_retry_only_one(monkeypatch):
    from stylemate.demo import demo_payload, DEMO_GARMENT_IMAGE
    calls = []
    garment, plan = demo_payload()
    failed_id = plan.outfits[1].id

    class FakeAI:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def analyze_garment(self, *args): return garment
        def plan_outfits(self, *args, **kwargs): return plan
        def generate_outfit_image(self, source, mime, garment_arg, outfit, **kwargs):
            calls.append(outfit.id)
            if outfit.id == failed_id and calls.count(failed_id) == 1:
                kwargs["task_state"].update(task_id="saved_task", status="timeout")
                raise TimeoutError("secret provider payload")
            return DEMO_GARMENT_IMAGE.read_bytes()

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    # Run actual app functions through a Streamlit script context.
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.plan is None:
    st.session_state.api_key = "test-only-key"
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "上班", "韩系简约")
    ns["_run_plan"](st.session_state.pending_garment, True)
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert len(app.session_state["result_images"]) == 2
    assert app.session_state["image_tasks"][failed_id]["task_id"] == "saved_task"
    assert "secret" not in str(app.session_state["image_errors"])
    assert len(calls) == 3
    retry = next(button for button in app.button if button.key == f"retry-image-{failed_id}")
    retry.click().run()
    assert not app.exception
    assert len(app.session_state["result_images"]) == 3
    assert len(calls) == 4 and calls[-1] == failed_id


def test_text_check_does_not_depend_on_image_config(monkeypatch):
    calls = []
    monkeypatch.setattr("stylemate.runtime.verify_api_key", lambda *a, **k: calls.append(k))
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    next(x for x in app.text_input if x.label == "API Key（官方或中转站）").set_value("isolated-test-key")
    next(x for x in app.text_input if x.label == "生图 Base URL（可选）").set_value("http://localhost")
    next(x for x in app.button if x.label == "测试文本接口").click().run()
    assert not app.exception
    assert calls and calls[0]["base_url"] == "https://api.openai.com/v1"


def test_clear_keys_removes_both_widget_values_and_batch_credentials():
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    app.session_state["api_key"] = "clear-me"
    app.session_state["api_image_key"] = "clear-image"
    app.run()
    next(x for x in app.button if x.label == "清除当前会话 Key").click().run()
    assert not app.exception
    assert app.session_state["api_key"] == app.session_state["api_image_key"] == ""
    assert app.session_state["text_key_input"] == app.session_state["image_key_input"] == ""
    assert app.session_state["batch_config"] is None


def test_app_startup_uses_environment_key_for_private_use(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "personal-key")
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.exception
    assert app.session_state["stage"] == "input"
    assert app.session_state["api_key"] == "personal-key"


def test_rightapi_preset_fills_protocol_and_path():
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    next(x for x in app.text_input if x.label == "API Key（官方或中转站）").set_value("relay-key")
    next(x for x in app.selectbox if x.label == "服务商预设").set_value("RightAPI（异步生图）")
    app.run()
    next(x for x in app.button if x.label == "保存并开始使用").click().run()
    assert not app.exception
    assert app.session_state["api_base_url"] == "https://rightapi.ai/codex/v1"
    assert app.session_state["api_text_api"] == "responses"
    assert app.session_state["stage"] == "input"


def test_confirm_page_renders_editable_fields(monkeypatch):
    from types import SimpleNamespace

    from stylemate.demo import DEMO_GARMENT_IMAGE, demo_payload
    garment, _plan = demo_payload()

    class FakeAI:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def analyze_garment(self, *args): return garment

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.stage != "confirm":
    st.session_state.api_key = "test-only-key"
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "上班", "韩系简约")
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert app.session_state["stage"] == "confirm"
    labels = {x.label for x in app.text_input}
    assert {"品类", "颜色", "材质", "版型", "适合季节（用、分隔）"} <= labels
    assert any("调用" in x.value for x in app.radio if x.label == "本次生成范围")
    source_identity = next(x for x in app.markdown if 'class="source-title"' in x.value)
    assert source_identity.proto.allow_html


def test_input_page_offers_conditions_preferences_and_photo_helpers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "personal-key")
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.exception
    assert {"气温", "天气", "通勤方式"} <= {box.label for box in app.selectbox}
    assert {"不喜欢的颜色", "禁用单品（任何一套都不会出现）", "版型偏好"} <= {x.label for x in app.text_input}
    assert any("预算档位" in box.label for box in app.selectbox)
    commute = next(box for box in app.selectbox if box.label == "通勤方式")
    assert "骑自行车 / 电动车" in commute.options
    assert "开车" in commute.options


def test_history_records_runs_and_results_offer_export(monkeypatch):
    from stylemate.demo import DEMO_GARMENT_IMAGE, demo_payload
    garment, plan = demo_payload()

    class FakeAI:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def analyze_garment(self, *args): return garment
        def plan_outfits(self, *args, **kwargs): return plan
        def generate_outfit_image(self, source, mime, garment_arg, outfit, **kwargs):
            return DEMO_GARMENT_IMAGE.read_bytes()

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.plan is None:
    st.session_state.api_key = "test-only-key"
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "上班", "韩系简约")
    ns["_run_plan"](st.session_state.pending_garment, True)
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    history = app.session_state["history"]
    assert len(history) == 1
    assert "黑色短款皮夹克" in history[0]["label"]
    assert len(history[0]["images"]) == 3
    assert any("本次会话历史与导出" in expander.label for expander in app.expander)
    assert any("下载效果图" in button.label for button in app.download_button)


def test_saved_looks_are_viewable_and_downloadable():
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    next(b for b in app.button if b.label == "暂不配置，仅查看固定 Demo").click().run()
    next(b for b in app.button if "查看固定 Demo" in b.label).click().run()
    next(b for b in app.button if b.key == "saved-look-01").click().run()
    details = app.session_state["saved_details"]
    saved_key = f"{app.session_state['batch_id']}:look-01"
    assert saved_key in details
    # 收藏内容必须是完整单品数据（含必须保留的原单品外套）
    assert "用户的黑色短款皮夹克" in details[saved_key]["pieces"]
    # 收藏必须能查看：页面有“我的收藏”区，含清单与下载按钮
    assert any("我的收藏" in e.label for e in app.expander)
    markdown = "\n".join(item.value for item in app.markdown)
    assert "白色修身圆领 T" in markdown
    assert any(b.key == f"saved-dl-{saved_key}" for b in app.download_button)
    # 再次点击取消收藏，条目随之移除
    next(b for b in app.button if b.key == "saved-look-01").click().run()
    assert saved_key not in app.session_state["saved_details"]


def test_replace_look_swaps_single_look_without_image_cost(monkeypatch):
    from stylemate.demo import DEMO_GARMENT_IMAGE, demo_payload
    from stylemate.models import Outfit
    garment, plan = demo_payload()
    captured = {}
    image_calls = []

    replacement = Outfit(
        id="fresh-1", style="法式休闲", top="奶白色针织开衫",
        outerwear="用户的黑色短款皮夹克", bottom="米色锥形九分裤",
        shoes="黑色切尔西靴", bag="焦糖色公文包", accessories=["金色细手镯"],
        reason="换一种温柔的通勤思路", compatibility_score=86,
        image_prompt="soft french casual flat lay",
    )

    class FakeAI:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def analyze_garment(self, *args): return garment
        def plan_outfits(self, *args, **kwargs): return plan
        def regenerate_outfit(self, garment_arg, occasion, style, *, avoid,
                              conditions="", preferences=""):
            captured["avoid"] = avoid
            captured["preferences"] = preferences
            captured["conditions"] = conditions
            return replacement.model_copy(deep=True)
        def generate_outfit_image(self, source, mime, garment, outfit, **kwargs):
            image_calls.append(outfit.id)
            return DEMO_GARMENT_IMAGE.read_bytes()

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.plan is None:
    st.session_state.api_key = "replace-look-test-key"
    st.session_state.pref_banned = "高跟鞋"
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "上班", "韩系简约",
                          "气温：凉爽 10–19°C；天气：多云；通勤：短途步行")
    ns["_run_plan"](st.session_state.pending_garment, False)
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    old_first = plan.outfits[0]
    kept_ids = [o.id for o in plan.outfits[1:]]
    next(b for b in app.button if b.key == f"regen-{old_first.id}").click().run()
    assert not app.exception
    outfits = app.session_state["plan"].outfits
    # 恰好替换一套：新 LOOK 进入原位置，另外两套原样保留
    assert outfits[0].id != old_first.id and outfits[0].style == "法式休闲"
    assert [o.id for o in outfits[1:]] == kept_ids
    # 替换请求带上了偏好、环境与“避开现有三套”的要求
    assert "高跟鞋" in captured["preferences"]
    assert "凉爽" in captured["conditions"]
    assert len(captured["avoid"]) == 3
    # 不自动生成任何图片：无生图调用，新 LOOK 的图需单独点击
    assert image_calls == []
    assert app.session_state["result_images"] == {}
    # 历史同步为新方案
    assert app.session_state["history"][0]["looks"][0]["style"] == "法式休闲"
    # 单独生成新 LOOK 的图：一次调用即成功，历史图片同步
    next(b for b in app.button if b.key == f"retry-image-{outfits[0].id}").click().run()
    assert not app.exception
    assert image_calls == [outfits[0].id]
    assert app.session_state["history"][0]["images"][outfits[0].id]


def test_replace_rejects_clone_and_keeps_plan(monkeypatch):
    from stylemate.demo import DEMO_GARMENT_IMAGE, demo_payload
    garment, plan = demo_payload()

    class FakeAI:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def analyze_garment(self, *args): return garment
        def plan_outfits(self, *args, **kwargs): return plan
        def regenerate_outfit(self, *args, **kwargs):
            return plan.outfits[0].model_copy(deep=True)  # 与被替换 LOOK 相同

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.plan is None:
    st.session_state.api_key = "replace-clone-test-key"
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "上班", "韩系简约")
    ns["_run_plan"](st.session_state.pending_garment, False)
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    before = [o.id for o in app.session_state["plan"].outfits]
    next(b for b in app.button if b.key == f"regen-{before[0]}").click().run()
    assert not app.exception
    # 新 LOOK 与被替换的过于相似 → 拒绝，原方案保持不变
    assert [o.id for o in app.session_state["plan"].outfits] == before
    assert any("过于相似" in e.value for e in app.error)


def test_api_page_shows_privacy_and_cost_notice():
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    assert any("隐私、费用与数据保存说明" in expander.label for expander in app.expander)
    markdown = "\n".join(item.value for item in app.markdown)
    assert "第三方服务商" in markdown
    assert "不保存" in markdown or "不会被保存" in markdown


def test_prepared_upload_validates_before_preprocessing():
    import base64
    import struct
    import zlib

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", 40000, 40000, 8, 2, 0, 0, 0)
    bomb = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"\x00" * 120003)) + chunk(b"IEND", b""))
    small = io.BytesIO()
    Image.new("RGB", (8, 6)).save(small, format="PNG")
    bomb_b64 = base64.b64encode(bomb).decode()
    small_b64 = base64.b64encode(small.getvalue()).decode()
    script = f'''
import base64
import io
import runpy
from types import SimpleNamespace
import streamlit as st
from PIL import Image
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if not st.session_state.get("prep_checked"):
    st.session_state.prep_checked = True
    def upload(raw):
        return SimpleNamespace(getvalue=lambda: raw, name="photo.png", size=len(raw))
    st.session_state.prep_valid = ns["prepared_upload"](upload(base64.b64decode({small_b64!r})))
    st.session_state.prep_bomb = ns["prepared_upload"](upload(base64.b64decode({bomb_b64!r})))
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    # 合法图片正常返回归一化字节
    valid = app.session_state["prep_valid"]
    assert isinstance(valid, bytes)
    with Image.open(io.BytesIO(valid)) as image:
        assert image.format == "JPEG"
    # 像素炸弹被安全校验拦截：报“像素过大”，而不是预处理阶段的“已损坏”
    assert app.session_state["prep_bomb"] is None
    assert "像素过大" in app.session_state["prep_error"]


def test_preferences_persist_across_page_switches(monkeypatch):
    from stylemate.demo import demo_payload
    monkeypatch.setenv("OPENAI_API_KEY", "personal-key")
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    next(x for x in app.text_input if x.label == "禁用单品（任何一套都不会出现）").set_value("高跟鞋、紧身裤")
    next(x for x in app.text_input if x.label == "不喜欢的颜色").set_value("荧光绿")
    next(x for x in app.selectbox if x.label == "天气").set_value("小雨")
    app.run()
    assert app.session_state["pref_banned"] == "高跟鞋、紧身裤"
    # 离开输入页（确认页没有这些控件），再返回
    garment, _plan = demo_payload()
    app.session_state["pending_garment"] = garment
    app.session_state["stage"] = "confirm"
    app.run()
    app.session_state["stage"] = "input"
    app.run()
    assert not app.exception
    assert app.session_state["pref_banned"] == "高跟鞋、紧身裤"
    assert app.session_state["pref_colors"] == "荧光绿"
    assert app.session_state["cond_weather"] == "小雨"
    widget = next(x for x in app.text_input if x.label == "禁用单品（任何一套都不会出现）")
    assert widget.value == "高跟鞋、紧身裤"


def test_retry_success_syncs_history_and_export(monkeypatch):
    from stylemate.demo import DEMO_GARMENT_IMAGE, demo_payload
    garment, plan = demo_payload()

    class FakeAI:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def analyze_garment(self, *args): return garment
        def plan_outfits(self, *args, **kwargs): return plan
        def generate_outfit_image(self, *args, **kwargs):
            return DEMO_GARMENT_IMAGE.read_bytes()

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    # 独立 Key：GATE 按 Key 哈希限流，避免与前面测试的重试点击共享 10 秒冷却。
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.plan is None:
    st.session_state.api_key = "retry-history-test-key"
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "上班", "韩系简约")
    ns["_run_plan"](st.session_state.pending_garment, False)
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    first_id = plan.outfits[0].id
    gen = next(b for b in app.button if b.key == f"retry-image-{first_id}")
    gen.click().run()
    assert not app.exception
    assert app.session_state["result_images"].get(first_id)
    # 补生成的图片必须进入最近一次历史，并出现对应下载按钮
    history = app.session_state["history"]
    assert history[0]["images"].get(first_id) == DEMO_GARMENT_IMAGE.read_bytes()
    assert any(first_id in button.key for button in app.download_button)
    # 页面清单必须包含外套（完整单品数据）
    markdown = "\n".join(item.value for item in app.markdown)
    assert "用户的黑色短款皮夹克" in markdown


def test_confirm_edits_flow_into_the_plan(monkeypatch):
    from types import SimpleNamespace

    from stylemate.demo import DEMO_GARMENT_IMAGE, demo_payload
    garment, plan = demo_payload()
    captured = {}

    class FakeAI:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def analyze_garment(self, *args): return garment
        def plan_outfits(self, received, *args, **kwargs):
            captured["garment"] = received
            return plan
        def generate_outfit_image(self, *args, **kwargs):
            return DEMO_GARMENT_IMAGE.read_bytes()

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.plan is None and st.session_state.pending_garment is None:
    st.session_state.api_key = "test-only-key"
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "上班", "韩系简约")
if st.session_state.plan is None and st.session_state.pending_garment is not None:
    pending = st.session_state.pending_garment
    st.session_state.confirm_color = "深棕色"
    st.session_state.confirm_category = pending.category
    st.session_state.confirm_subcategory = pending.subcategory
    st.session_state.confirm_material = pending.material
    st.session_state.confirm_pattern = pending.pattern
    st.session_state.confirm_fit = pending.fit
    st.session_state.confirm_seasons = "、".join(pending.seasons)
    st.session_state.confirm_styles = "、".join(pending.styles)
    ns["_run_plan"](ns["edited_garment"](pending), False)
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert captured["garment"].color == "深棕色"
    assert app.session_state["stage"] == "results"
    assert app.session_state["result_images"] == {}
    # 文字模式默认不生成图片；每套图可单独发起（第 13 项）
    assert any("生成这张效果图" in button.label for button in app.button)
