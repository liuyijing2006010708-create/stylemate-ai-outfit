"""Cross-page regressions: fake only the paid provider, run real app logic."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from stylemate.demo import DEMO_GARMENT_IMAGE, demo_payload
from stylemate.operations import OperationGate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workflow(monkeypatch):
    garment, plan = demo_payload()
    calls = []

    class FakeAI:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def analyze_garment(self, *args): return garment.model_copy(deep=True)
        def plan_outfits(self, *args, **kwargs):
            calls.append(kwargs)
            return plan.model_copy(deep=True)
        def generate_outfit_image(self, *args, **kwargs):
            return DEMO_GARMENT_IMAGE.read_bytes()

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    monkeypatch.setattr("stylemate.operations.GATE", OperationGate(cooldown=0))
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / 'app.py')!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if not st.session_state.get("test_initialized"):
    st.session_state.test_initialized = True
    st.session_state.api_key = "workflow-fake-key"
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "上班", "韩系简约")
    ns["_run_plan"](st.session_state.pending_garment, False)
    st.rerun()
if st.button("TEST: new batch"):
    ns["_start_analysis"](DEMO_GARMENT_IMAGE.read_bytes(), "旅行", "极简")
    ns["_run_plan"](st.session_state.pending_garment, True)
    st.rerun()
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    return app, calls


def test_second_batch_never_writes_images_into_first_batch(workflow):
    app, _ = workflow
    assert app.session_state["history"][0]["images"] == {}
    next(b for b in app.button if b.label == "TEST: new batch").click().run()
    assert not app.exception
    assert len(app.session_state["history"][0]["images"]) == 3
    assert app.session_state["history"][1]["images"] == {}


def test_saved_look_is_isolated_when_model_reuses_ids(workflow):
    app, _ = workflow
    next(b for b in app.button if b.key == "saved-look-01").click().run()
    saved_key = next(iter(app.session_state["saved_details"]))
    assert app.session_state["saved_details"][saved_key]["image"] is None
    next(b for b in app.button if b.label == "TEST: new batch").click().run()
    assert not app.exception
    assert app.session_state["saved_details"][saved_key]["image"] is None
    next(b for b in app.button if b.key == "saved-look-01").click().run()
    assert len(app.session_state["saved_details"]) == 2


def test_text_only_configuration_has_no_image_action(workflow):
    app, _ = workflow
    app.session_state["image_enabled"] = False
    app.run()
    assert not any(b.key and b.key.startswith("retry-image-") for b in app.button)


def test_api_settings_return_keeps_existing_batch_and_tasks(workflow):
    app, _ = workflow
    batch_id = app.session_state["batch_id"]
    app.session_state["image_tasks"] = {"look-01": {"task_id": "pending-task", "status": "timeout"}}
    next(b for b in app.button if b.label == "⚙ API 设置").click().run()
    next(b for b in app.button if b.label == "返回应用").click().run()
    assert not app.exception
    assert app.session_state["stage"] == "results"
    assert app.session_state["batch_id"] == batch_id
    assert app.session_state["image_tasks"]["look-01"]["task_id"] == "pending-task"
    assert any(b.label == "继续查询这张图" for b in app.button)


def test_input_can_resume_previous_results(workflow):
    app, _ = workflow
    batch_id = app.session_state["batch_id"]
    next(b for b in app.button if b.label == "↻ 重新搭配").click().run()
    next(b for b in app.button if b.label == "继续上次搭配").click().run()
    assert not app.exception
    assert app.session_state["stage"] == "results"
    assert app.session_state["batch_id"] == batch_id


def test_confirmation_edits_survive_api_settings(workflow):
    app, _ = workflow
    app.session_state["pending_garment"] = demo_payload()[0]
    app.session_state["pending_source"] = DEMO_GARMENT_IMAGE.read_bytes()
    app.session_state["stage"] = "confirm"
    app.run()
    next(w for w in app.text_input if w.label == "颜色").set_value("深棕色").run()
    next(b for b in app.button if b.label == "⚙ API 设置").click().run()
    next(b for b in app.button if b.label == "返回应用").click().run()
    assert not app.exception and app.session_state["stage"] == "confirm"
    assert next(w for w in app.text_input if w.label == "颜色").value == "深棕色"


def test_upload_is_required_before_live_recognition(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "no-network-key")
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert next(b for b in app.button if b.label == "✦ 识别我的单品").disabled


def test_crossed_crop_edges_show_warning_and_prevent_recognition(monkeypatch):
    from types import SimpleNamespace
    import streamlit as st

    data = DEMO_GARMENT_IMAGE.read_bytes()
    uploaded = SimpleNamespace(name="photo.png", size=len(data), getvalue=lambda: data)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-crop-key")
    monkeypatch.setattr(st, "file_uploader", lambda *a, **kw: uploaded)
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    app.slider(key="crop_l").set_value(80)
    app.slider(key="crop_r").set_value(20)
    app.run()
    assert not app.exception
    assert any("裁剪范围无效" in w.value for w in app.warning)
    assert next(b for b in app.button if b.label == "✦ 识别我的单品").disabled
    app.slider(key="crop_r").set_value(100).run()
    assert not app.exception
    assert not next(b for b in app.button if b.label == "✦ 识别我的单品").disabled


def test_completed_image_has_download_on_its_result_card(workflow):
    app, _ = workflow
    next(b for b in app.button if b.key == "retry-image-look-01").click().run()
    assert not app.exception
    assert any(b.key == "result-dl-look-01" for b in app.download_button)


def test_demo_replacement_cannot_make_paid_call():
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    next(b for b in app.button if b.label == "暂不配置，仅查看固定 Demo").click().run()
    next(b for b in app.button if "查看固定 Demo" in b.label).click().run()
    assert all(b.disabled for b in app.button if b.key and b.key.startswith("regen-"))


def test_saved_item_can_be_removed_after_a_new_batch(workflow):
    app, _ = workflow
    next(b for b in app.button if b.key == "saved-look-01").click().run()
    saved_key = next(iter(app.session_state["saved_details"]))
    next(b for b in app.button if b.label == "TEST: new batch").click().run()
    next(b for b in app.button if b.key == f"unsave-{saved_key}").click().run()
    assert not app.exception
    assert saved_key not in app.session_state["saved_details"]


def test_history_has_text_export(workflow):
    app, _ = workflow
    assert any(b.label == "下载搭配清单" for b in app.download_button)


def test_clear_session_data_preserves_only_api_and_rate_limit_identity(workflow):
    app, _ = workflow
    session_id = app.session_state["session_id"]
    next(b for b in app.button if b.key == "saved-look-01").click().run()
    next(w for w in app.checkbox if w.key == "confirm-clear-data").check().run()
    next(b for b in app.button if b.key == "clear-session-data").click().run()
    assert not app.exception
    assert app.session_state["api_key"] == "workflow-fake-key"
    assert app.session_state["session_id"] == session_id
    assert app.session_state["source_image"] is None
    assert app.session_state["plan"] is None
    assert not app.session_state["history"]
    assert not app.session_state["saved_details"]


def test_valid_upload_recovers_after_corrupted_file():
    script = f'''
import runpy
from types import SimpleNamespace
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / 'app.py')!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
def uploaded(data):
    return SimpleNamespace(name="same.png", size=len(data), getvalue=lambda: data)
valid = DEMO_GARMENT_IMAGE.read_bytes()
ns["prepared_upload"](uploaded(valid))
assert ns["prepared_upload"](uploaded(b"broken")) is None
assert st.session_state.prep_error
assert ns["prepared_upload"](uploaded(valid)) is not None
assert st.session_state.prep_error == ""
'''
    app = AppTest.from_string(script).run()
    assert not app.exception


def test_custom_protocol_and_image_model_survive_settings_roundtrip():
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    next(w for w in app.selectbox if w.label == "服务商预设").set_value("自定义").run()
    next(w for w in app.text_input if w.label == "API Key（官方或中转站）").set_value("fake-config-key")
    next(w for w in app.selectbox if w.label == "文本接口协议").set_value("chat_completions")
    next(w for w in app.text_input if w.label == "图片编辑模型").set_value("custom-image-model")
    next(b for b in app.button if b.label == "保存并开始使用").click().run()
    assert not app.exception and app.session_state["stage"] == "input"
    next(b for b in app.button if b.label == "⚙ API 设置").click().run()
    assert not app.exception
    assert next(w for w in app.selectbox if w.label == "服务商预设").value == "自定义"
    assert next(w for w in app.selectbox if w.label == "文本接口协议").value == "chat_completions"
    assert next(w for w in app.text_input if w.label == "图片编辑模型").value == "custom-image-model"


def test_address_diagnostic_needs_no_key_or_model_request(monkeypatch):
    checked = []
    monkeypatch.setattr("stylemate.runtime.verify_service_address",
                        lambda address: checked.append(address) or "DNS 检查通过")
    app = AppTest.from_file(str(ROOT / "cloud_app.py")).run()
    next(b for b in app.button if b.label == "检查地址 / DNS（不调用模型）").click().run()
    assert not app.exception
    assert checked and app.session_state["api_key"] == ""
    assert any("DNS 检查通过" in m.value for m in app.success)


def test_gender_age_reach_planning_and_persist_across_pages(workflow):
    app, calls = workflow
    next(b for b in app.button if b.label == "↻ 重新搭配").click().run()
    next(w for w in app.selectbox if w.label == "性别（可选）").set_value("女")
    next(w for w in app.selectbox if w.label == "年龄段（可选）").set_value("25–34 岁")
    app.run()
    next(b for b in app.button if b.label == "TEST: new batch").click().run()
    assert not app.exception
    assert "性别：女" in calls[-1]["preferences"]
    assert "年龄段：25–34 岁" in calls[-1]["preferences"]
    next(b for b in app.button if b.label == "↻ 重新搭配").click().run()
    assert next(w for w in app.selectbox if w.label == "性别（可选）").value == "女"
    assert next(w for w in app.selectbox if w.label == "年龄段（可选）").value == "25–34 岁"


def test_edited_garment_does_not_keep_conflicting_recognition_notes():
    script = f'''
import runpy
import streamlit as st
from stylemate.demo import demo_payload
ns = runpy.run_path({str(ROOT / 'app.py')!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
garment, _ = demo_payload()
garment.preservation_notes = ["黑色皮革"]
for field in ["category", "subcategory", "color", "material", "pattern", "fit"]:
    st.session_state["confirm_" + field] = getattr(garment, field)
st.session_state.confirm_seasons = "、".join(garment.seasons)
st.session_state.confirm_styles = "、".join(garment.styles)
st.session_state.confirm_color = "白色"
assert "黑色皮革" not in ns["edited_garment"](garment).preservation_notes
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
