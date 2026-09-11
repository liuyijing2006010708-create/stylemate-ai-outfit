from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


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
        def plan_outfits(self, *args): return plan
        def generate_outfit_image(self, source, mime, garment, outfit, **kwargs):
            calls.append(outfit.id)
            if outfit.id == failed_id and calls.count(failed_id) == 1:
                kwargs["task_state"].update(task_id="saved_task", status="timeout")
                raise TimeoutError("secret provider payload")
            return DEMO_GARMENT_IMAGE.read_bytes()

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    # Run actual app functions through a Streamlit script context.
    script = f'''
import runpy
from types import SimpleNamespace
import streamlit as st
from stylemate.demo import DEMO_GARMENT_IMAGE
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.plan is None:
    st.session_state.api_key = "test-only-key"
    ns["_run_generation"](SimpleNamespace(getvalue=lambda: DEMO_GARMENT_IMAGE.read_bytes(), type="image/png"), "上班", "韩系简约", True)
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
