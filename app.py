from __future__ import annotations

import html
import hashlib
import io
import os
import re
import time
import uuid
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

from stylemate import __version__
from stylemate.consistency import (
    PlanRejected,
    diversity_issues,
    diversity_pair_issues,
    plan_issues,
    preference_issues,
)
from stylemate.demo import DEMO_GARMENT_IMAGE, DEMO_IMAGES, demo_payload
from stylemate.diagnostics import log_event, new_request_id, trace
from stylemate.models import GarmentAnalysis, OutfitPlan
from stylemate.openai_service import StyleMateAI
from stylemate.preprocessing import adjust, background_removal_available, quality_notes
from stylemate.ranking import rank_outfits
from stylemate.runtime import (
    APIConfig,
    DEFAULT_BASE_URL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_TEXT_MODEL,
    RunMode,
    decide_run_mode,
    guess_preset,
    normalize_api_key,
    provider_display_name,
    safe_connection_error,
    verify_api_key,
    verify_image_endpoint,
    verify_service_address,
)
from stylemate.operations import GATE
from stylemate.security import protect_provider_logs
from stylemate.styles import APP_CSS
from stylemate.uploads import InvalidImage, validate_upload


load_dotenv()
protect_provider_logs()
st.set_page_config(page_title="StyleMate · AI 穿搭助手", page_icon="✦", layout="wide")
st.markdown(APP_CSS, unsafe_allow_html=True)

OCCASIONS = ["上班", "上课", "约会", "旅行", "聚会"]
STYLES = ["韩系简约", "City Boy", "美式复古", "极简", "Old Money", "Y2K"]
TEMPERATURES = ["炎热 ≥28°C", "温暖 20–27°C", "凉爽 10–19°C", "寒冷 0–9°C", "严寒 <0°C"]
WEATHER = ["晴", "多云", "阴", "小雨", "大雨", "雪", "大风"]
COMMUTES = ["短途步行", "步行较久（>20 分钟）", "主要在室内", "骑自行车 / 电动车", "开车"]
BUDGETS = ["不限", "经济", "中等", "高端"]
GENDERS = ["不提供", "女", "男", "非二元／其他"]
AGE_GROUPS = ["不提供", "12 岁及以下", "13–17 岁", "18–24 岁", "25–34 岁",
              "35–44 岁", "45–59 岁", "60 岁及以上"]

# 中转站协议预设（第 10 项）：预设决定接口路径与协议，普通用户只需 Key 和模型。
PRESET_OPENAI = "OpenAI 官方"
PRESET_COMPATIBLE = "通用 OpenAI 兼容接口"
PRESET_RIGHTAPI = "RightAPI（异步生图）"
PRESET_CUSTOM = "高级自定义"
PRESET_LABELS = (PRESET_COMPATIBLE, PRESET_OPENAI, PRESET_RIGHTAPI, PRESET_CUSTOM)
PRESET_URLS = {
    PRESET_OPENAI: DEFAULT_BASE_URL,
    PRESET_RIGHTAPI: "https://rightapi.ai/codex/v1",
}
PRESET_PROTOCOLS = {
    PRESET_OPENAI: "responses",
    PRESET_RIGHTAPI: "responses",
    PRESET_COMPATIBLE: "chat_completions",
}
PRESET_KEYS = {
    PRESET_OPENAI: "openai",
    PRESET_COMPATIBLE: "compatible",
    PRESET_RIGHTAPI: "rightapi",
    PRESET_CUSTOM: "custom",
}


def init_state() -> None:
    environment_key = (
        "" if globals().get("PUBLIC_DEPLOYMENT", False)
        else normalize_api_key(os.getenv("OPENAI_API_KEY"))
    )
    defaults = {
        "stage": "input" if environment_key else "api",
        "api_key": environment_key,
        "api_source": "environment" if environment_key else "",
        "api_preset": PRESET_COMPATIBLE,
        "api_return_stage": "input",
        "api_image_key": "",
        "image_enabled": True,
        "session_id": uuid.uuid4().hex,
        "image_tasks": {},
        "image_errors": {},
        "batch_config": None,
        "batch_id": "",
        "api_base_url": os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        "api_image_base_url": os.getenv("OPENAI_IMAGE_BASE_URL", ""),
        "api_text_model": os.getenv("OPENAI_TEXT_MODEL", DEFAULT_TEXT_MODEL),
        "api_image_model": os.getenv("OPENAI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
        "api_text_api": os.getenv("OPENAI_TEXT_API", "chat_completions"),
        "demo_access": False,
        "garment": None,
        "plan": None,
        "result_images": {},
        "source_image": None,
        "source_mime": "image/png",
        "occasion": OCCASIONS[0],
        "preferred_style": STYLES[0],
        "recognition_demo": True,
        "result_images_demo": True,
        "liked": set(),
        "saved": set(),
        "pending_garment": None,
        "pending_source": None,
        "pending_mime": "image/jpeg",
        "confirm_occasion": OCCASIONS[0],
        "confirm_style": STYLES[0],
        "confirm_conditions": "",
        "last_request_id": "",
        "history": [],
        "saved_details": {},
        "rotate_deg": 0,
        "bg_removed": False,
        "prep_sig": "",
        "prep_error": "",
        "crop_l": 0,
        "crop_t": 0,
        "crop_r": 100,
        "crop_b": 100,
        # 阴影键：控件状态会随页面切换被 Streamlit 回收，这里另存一份，保证偏好跨页不丢。
        "sel_occasion": OCCASIONS[0],
        "sel_style": STYLES[0],
        "cond_temperature": TEMPERATURES[2],
        "cond_weather": WEATHER[0],
        "cond_commute": COMMUTES[0],
        "pref_colors": "",
        "pref_banned": "",
        "pref_fit": "",
        "pref_budget": "不限",
        "pref_notes": "",
        "pref_gender": "不提供",
        "pref_age_group": "不提供",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if not st.session_state.api_key and not st.session_state.demo_access:
        st.session_state.stage = "api"


def header(show_reset: bool = False, show_api_settings: bool = True) -> None:
    key_ready = bool(st.session_state.api_key)
    left, right = st.columns([5, 2], vertical_alignment="center")
    with left:
        st.markdown('<div class="brand">StyleMate</div>', unsafe_allow_html=True)
        st.caption(f"版本 {__version__}")
    with right:
        if show_reset and show_api_settings:
            reset_col, api_col = st.columns(2)
            with reset_col:
                if st.button("↻ 重新搭配", width="stretch"):
                    st.session_state.stage = "input"
                    st.rerun()
            with api_col:
                if st.button("⚙ API 设置", width="stretch"):
                    st.session_state.api_return_stage = st.session_state.stage
                    st.session_state.stage = "api"
                    st.rerun()
        elif show_api_settings:
            status_col, api_col = st.columns([1.25, 1])
            with status_col:
                provider = provider_display_name(st.session_state.api_base_url)
                status = f"{provider} 已配置" if key_ready else "Demo 模式"
                st.markdown(f'<div class="api-state"><strong>✦</strong> {status}</div>', unsafe_allow_html=True)
            with api_col:
                if st.button("⚙ API 设置", width="stretch"):
                    st.session_state.api_return_stage = st.session_state.stage
                    st.session_state.stage = "api"
                    st.rerun()
        else:
            status = "API 已配置" if key_ready else "需要配置 API Key"
            st.markdown(f'<div class="api-state"><strong>✦</strong> {status}</div>', unsafe_allow_html=True)
    st.markdown('<div style="border-bottom:1px solid #dfe2e8;margin:.85rem 0 1.7rem"></div>', unsafe_allow_html=True)
    if st.session_state.stage == "input" and st.session_state.plan:
        if st.button("继续上次搭配", help="保留原文字、图片与异步任务，不重新调用 API。"):
            st.session_state.stage = "results"
            st.rerun()


def safe_image(data: bytes | Path) -> Image.Image:
    if isinstance(data, Path):
        return Image.open(data)
    return Image.open(io.BytesIO(data))


def download_image(data: bytes, key: str) -> None:
    with safe_image(data) as picture:
        suffix = (picture.format or "PNG").lower().replace("jpeg", "jpg")
        mime = Image.MIME.get(picture.format, "application/octet-stream")
    st.download_button("下载效果图", data=data, mime=mime,
                       file_name=f"stylemate-{uuid.uuid5(uuid.NAMESPACE_URL, key).hex[:12]}.{suffix}",
                       key=key, width="stretch")


def current_config() -> APIConfig:
    return APIConfig.from_values(
        api_key=st.session_state.api_key,
        base_url=st.session_state.api_base_url,
        image_base_url=st.session_state.api_image_base_url,
        image_api_key=st.session_state.api_image_key,
        text_model=st.session_state.api_text_model,
        image_model=st.session_state.api_image_model,
        text_api=st.session_state.api_text_api,
    )


@contextmanager
def service(config):
    ai = StyleMateAI(api_key=config.api_key, base_url=config.base_url,
                     image_base_url=config.image_base_url, image_api_key=config.image_api_key,
                     text_model=config.text_model, image_model=config.image_model,
                     text_api=config.text_api)
    try:
        yield ai
    finally:
        ai.close()


def generate_one(ai, outfit) -> None:
    state = st.session_state.image_tasks.setdefault(outfit.id, {})
    progress = st.empty()
    labels = {"submitting": "正在提交", "queued": "排队中", "pending": "排队中",
              "running": "生成中", "processing": "生成中", "in_progress": "生成中",
              "downloading": "下载中", "completed": "完成", "timeout": "等待超时",
              "query_error": "查询暂时失败", "unknown": "提交结果待确认"}
    request_id = new_request_id()
    state["request_id"] = request_id
    try:
        with trace(request_id, "image", model=getattr(ai, "image_model", ""),
                   protocol=getattr(ai, "image_generation_mode", "")):
            result = ai.generate_outfit_image(
                st.session_state.source_image, st.session_state.source_mime,
                st.session_state.garment, outfit, task_state=state,
                on_progress=lambda item: progress.caption(labels.get(item["status"], "任务结束")),
            )
        st.session_state.result_images[outfit.id] = result
        state["status"] = "completed"
        st.session_state.image_errors.pop(outfit.id, None)
        refresh_history_latest()
        # 已收藏的 LOOK 后续生成图片时，收藏条目同步补图。
        saved = st.session_state.saved_details.get(look_key(outfit.id))
        if saved is not None:
            saved["image"] = result
        log_event(request_id, "image", "task_saved", status="completed",
                  retries=state.get("query_errors", 0))
    except Exception as exc:
        message = safe_connection_error(exc)
        st.session_state.image_errors[outfit.id] = f"{message}（请求编号 {request_id}）"
        if not state.get("status"):
            state["status"] = "unknown"
        log_event(request_id, "image", "task_stopped", status=state.get("status", ""),
                  retries=state.get("query_errors", 0))


def start_analysis(image_bytes: bytes | None, occasion: str, preferred_style: str,
                   conditions: str = "") -> None:
    keys = [st.session_state.api_key]
    with GATE.claim(st.session_state.session_id, *keys, scope="identify"):
        _start_analysis(image_bytes, occasion, preferred_style, conditions)
    st.rerun()


def _start_analysis(image_bytes: bytes | None, occasion: str, preferred_style: str,
                    conditions: str = "") -> None:
    mode = decide_run_mode(
        has_upload=image_bytes is not None,
        api_key=st.session_state.api_key,
        demo_requested=False,
    )
    if mode is not RunMode.LIVE:
        raise RuntimeError("实时生成模式选择异常")
    source, source_mime = validate_upload(image_bytes)
    config = current_config()
    request_id = new_request_id()
    st.session_state.last_request_id = request_id
    with service(config) as ai:
        with trace(request_id, "analyze", model=config.text_model, protocol=config.text_api):
            garment = ai.analyze_garment(source, source_mime)
    for field in ("category", "subcategory", "color", "material", "pattern", "fit"):
        st.session_state[f"confirm_{field}"] = getattr(garment, field)
    st.session_state.confirm_seasons = "、".join(garment.seasons)
    st.session_state.confirm_styles = "、".join(garment.styles)
    st.session_state.confirm_notes = "、".join(garment.preservation_notes)
    st.session_state.update(
        stage="confirm", pending_garment=garment, pending_source=source,
        pending_mime=source_mime, confirm_occasion=occasion,
        confirm_style=preferred_style, confirm_conditions=conditions,
        last_request_id=request_id, image_tasks={}, image_errors={},
    )


def record_history(label: str, plan: OutfitPlan) -> None:
    entry = {
        "batch_id": st.session_state.batch_id,
        "label": label,
        "time": time.strftime("%H:%M"),
        "looks": [
            {"style": outfit.style, "pieces": outfit.pieces,
             "score": outfit.compatibility_score}
            for outfit in plan.outfits
        ],
        "images": dict(st.session_state.result_images),
    }
    # 会话内历史，最多 4 条；刷新页面即清空。
    st.session_state.history = ([entry] + list(st.session_state.history))[:4]


def refresh_history_latest() -> None:
    """Only update the history entry belonging to the active batch."""

    if not st.session_state.history or not st.session_state.plan:
        return
    entry = next((entry for entry in st.session_state.history
                  if entry.get("batch_id") == st.session_state.batch_id), None)
    if entry is None:
        return
    entry["looks"] = [
        {"style": outfit.style, "pieces": outfit.pieces,
         "score": outfit.compatibility_score}
        for outfit in st.session_state.plan.outfits
    ]
    entry["images"] = dict(st.session_state.result_images)


def preferences_text() -> str:
    parts = []
    gender = st.session_state.get("pref_gender", "不提供")
    age_group = st.session_state.get("pref_age_group", "不提供")
    if gender in GENDERS and gender != "不提供":
        parts.append(f"用户自填性别：{gender}")
    if age_group in AGE_GROUPS and age_group != "不提供":
        parts.append(f"用户自填年龄段：{age_group}")
        if age_group in AGE_GROUPS[1:3]:
            parts.append("优先适龄、日常、舒适且方便活动的搭配")
    if parts:
        parts.append("性别和年龄仅作穿搭参考，以用户明确风格和舒适需求为准，不刻板限制风格；不要从照片推断个人身份")
    colors = (st.session_state.get("pref_colors") or "").strip()
    banned = (st.session_state.get("pref_banned") or "").strip()
    fit = (st.session_state.get("pref_fit") or "").strip()
    budget = (st.session_state.get("pref_budget") or "").strip()
    notes = (st.session_state.get("pref_notes") or "").strip()
    if colors:
        parts.append(f"不喜欢的颜色：{colors}")
    if banned:
        parts.append(f"禁用单品（任何一套都不得出现）：{banned}")
    if fit:
        parts.append(f"版型偏好：{fit}")
    if budget and budget != "不限":
        parts.append(f"预算档位：{budget}")
    if notes:
        parts.append(f"其他要求：{notes}")
    return "；".join(parts)


def banned_terms() -> list[str]:
    return re.split(r"[、,，;；]", (st.session_state.get("pref_banned") or ""))


def run_plan(garment: GarmentAnalysis, generate_images: bool) -> None:
    keys = [st.session_state.api_key]
    if generate_images:
        keys.append(st.session_state.api_image_key or st.session_state.api_key)
    with GATE.claim(st.session_state.session_id, *keys, scope="generate"):
        _run_plan(garment, generate_images)
    st.rerun()


def _run_plan(garment: GarmentAnalysis, generate_images: bool) -> None:
    config = current_config()
    request_id = new_request_id()
    st.session_state.last_request_id = request_id
    with service(config) as ai, st.status("正在规划候选搭配…", expanded=True) as status:
        with trace(request_id, "plan", model=config.text_model, protocol=config.text_api):
            plan = ai.plan_outfits(
                garment, st.session_state.confirm_occasion,
                st.session_state.confirm_style,
                conditions=st.session_state.get("confirm_conditions", ""),
                preferences=preferences_text(),
            )
        issues = (plan_issues(plan) + diversity_issues(plan, garment)
                  + preference_issues(plan, banned_terms()))
        if issues:
            raise PlanRejected("搭配方案未通过校验（" + "；".join(issues) + "），请重新生成。")
        plan = OutfitPlan(outfits=rank_outfits(plan.outfits, st.session_state.confirm_style))
        # Persist text and each task before making the next potentially failing call.
        st.session_state.update(stage="results", garment=garment, plan=plan,
            result_images={}, source_image=st.session_state.pending_source,
            source_mime=st.session_state.pending_mime,
            occasion=st.session_state.confirm_occasion,
            preferred_style=st.session_state.confirm_style,
            recognition_demo=False, result_images_demo=False, image_tasks={},
            image_errors={}, batch_config=config, batch_id=uuid.uuid4().hex,
            pending_garment=None,
            pending_source=None, last_request_id=request_id)
        record_history(
            f"{garment.display_name} · {st.session_state.occasion} · {st.session_state.preferred_style}",
            plan,
        )
        if generate_images:
            for index, outfit in enumerate(plan.outfits, start=1):
                status.update(label=f"正在生成效果图 {index}/3…")
                generate_one(ai, outfit)
        status.update(label="搭配已保存；图片可稍后在结果页逐张生成", state="complete")


def run_demo(occasion: str, preferred_style: str) -> None:
    if decide_run_mode(False, "", demo_requested=True) is not RunMode.DEMO:
        raise RuntimeError("Demo 模式选择异常")
    garment, plan = demo_payload()
    plan = OutfitPlan(outfits=rank_outfits(plan.outfits, preferred_style))
    st.session_state.update(
        stage="results",
        garment=garment,
        plan=plan,
        result_images={key: path.read_bytes() for key, path in DEMO_IMAGES.items()},
        source_image=DEMO_GARMENT_IMAGE.read_bytes(),
        source_mime="image/png",
        occasion=occasion,
        preferred_style=preferred_style,
        recognition_demo=True,
        result_images_demo=True,
        image_tasks={}, image_errors={}, batch_config=None, batch_id=uuid.uuid4().hex,
    )
    record_history(f"{garment.display_name} · {occasion} · {preferred_style}", plan)
    st.rerun()


def render_api_setup() -> None:
    header(show_api_settings=False)
    left, form = st.columns([.9, 1.1], gap="large")
    with left:
        st.markdown(
            """
            <div class="api-copy">
              <div class="eyebrow">首次使用</div>
              <h1>连接你的<br><em>AI 接口</em></h1>
              <p>默认支持采用 OpenAI 协议的通用接口：填写服务商提供的 Key、Base URL 和模型名即可。特殊异步生图服务可选择对应适配器。Key 只保存在当前应用会话中，不写入项目文件。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with form:
        st.markdown('<div class="setup-title">API 配置</div>', unsafe_allow_html=True)
        preset_keys = [PRESET_KEYS[label] for label in PRESET_LABELS]
        default_preset = guess_preset(st.session_state.api_base_url)
        preset_index = preset_keys.index(default_preset) if default_preset in preset_keys else preset_keys.index("custom")
        if st.session_state.api_preset in PRESET_LABELS:
            preset_index = PRESET_LABELS.index(st.session_state.api_preset)
        preset = st.selectbox(
            "服务商预设",
            PRESET_LABELS,
            index=preset_index,
            format_func=lambda label: label,
            help="默认选择通用兼容接口；官方接口或已支持的异步服务可使用预设。",
        )
        api_key_input = st.text_input(
            "API Key（官方或中转站）",
            type="password",
            placeholder="输入服务商提供的 Key",
            help="留空时保留当前会话已经配置的 Key。",
            key="text_key_input",
        )
        effective_base = PRESET_URLS.get(preset)
        if effective_base:
            st.caption(f"接口地址（预设自动填写）：{effective_base}")
        else:
            base_url_input = st.text_input(
                "API Base URL",
                value=st.session_state.api_base_url,
                placeholder="https://your-relay.example.com/v1",
                help="通常需要以 /v1 结尾；公网中转站必须使用 HTTPS。",
            )
            effective_base = base_url_input
        if preset == PRESET_RIGHTAPI:
            st.info(
                "已选择 RightAPI：保存时自动使用文本渠道地址 "
                "`https://rightapi.ai/codex/v1`。生成真实平铺图时，程序会自动调用 "
                "RightAPI 的异步绘图接口并等待任务完成。"
            )
        advanced_open = preset == PRESET_CUSTOM
        with st.expander("高级选项（模型与生图接口）", expanded=advanced_open):
            text_model_input = st.text_input(
                "视觉/文本模型",
                value=st.session_state.api_text_model,
                help="必须是服务商实际支持且能读取图片的模型名称。",
            )
            image_base_url_input = st.text_input(
                "生图 Base URL（可选）",
                value=st.session_state.api_image_base_url,
                placeholder="留空则与文本 Base URL 相同",
                help=(
                    "部分服务商的生图接口域名/路径与文本不同，可在此单独填写；"
                    "留空时自动复用文本接口地址。"
                ),
            )
            separate_image_key = st.checkbox("生图使用独立 Key", value=bool(st.session_state.api_image_key))
            image_key_input = st.text_input("生图 API Key", type="password", disabled=not separate_image_key,
                                            key="image_key_input",
                                            help="不勾选时复用文本 Key；勾选后留空保留已保存的生图 Key。")
            image_enabled = st.checkbox("启用生图功能", value=st.session_state.image_enabled)
            image_model_input = st.text_input(
                "图片编辑模型", value=st.session_state.api_image_model,
                help="填写所选生图服务商实际支持的模型名；不会随文本预设切换而覆盖。",
            )
            if preset in {PRESET_COMPATIBLE, PRESET_CUSTOM}:
                protocol_options = ("responses", "chat_completions")
                current_protocol = st.session_state.api_text_api
                protocol_index = protocol_options.index(current_protocol) if current_protocol in protocol_options else 0
                text_api_input = st.selectbox(
                    "文本接口协议",
                    protocol_options,
                    index=protocol_index,
                    format_func=lambda value: (
                        "Responses API（官方或完整兼容站）"
                        if value == "responses"
                        else "Chat Completions（兼容性更广）"
                    ),
                )
            else:
                text_api_input = PRESET_PROTOCOLS[preset]
                st.caption(
                    f"协议（预设自动填写）：{text_api_input}；"
                    f"图片编辑模型：{image_model_input}。生图 Base URL 留空时复用文本接口地址。"
                )
        st.caption("文本测试会发送一次小请求，可能计费；生图检查仅检查模型列表，不创建图片任务。")
        st.caption("遇到 Clash Fake-IP 时自动使用 Cloudflare 加密 DNS，仅发送服务域名，不发送 Key、图片或对话；不会修改代理设置。")
        if st.button("检查地址 / DNS（不调用模型）", width="stretch"):
            targets = [("文本接口", effective_base)]
            if image_enabled and image_base_url_input.strip() and image_base_url_input.strip() != effective_base:
                targets.append(("生图接口", image_base_url_input.strip()))
            for label, address in targets:
                try:
                    with GATE.claim(st.session_state.session_id, scope=f"dns-{label}"):
                        st.success(f"{label}：{verify_service_address(address)}")
                except Exception as exc:
                    st.error(f"{label}：{safe_connection_error(exc)}")
            st.caption("该检查只验证地址与 DNS（含 Fake-IP 加密解析回退），不验证 HTTPS 连通性、Key、模型或额度。")
        def draft_config(target=None):
            image_key = (normalize_api_key(image_key_input) or st.session_state.api_image_key) if separate_image_key else ""
            text_key = normalize_api_key(api_key_input) or st.session_state.api_key
            if target == "text":
                return APIConfig.from_values(api_key=text_key, base_url=effective_base,
                    text_model=text_model_input, image_model=DEFAULT_IMAGE_MODEL, text_api=text_api_input)
            if separate_image_key and not image_key and image_enabled:
                raise ValueError("请填写生图 Key。")
            if target == "image":
                return APIConfig.from_values(api_key=image_key or text_key,
                    base_url=image_base_url_input or effective_base,
                    text_model=DEFAULT_TEXT_MODEL, image_model=image_model_input, text_api=text_api_input)
            return APIConfig.from_values(
                api_key=text_key,
                base_url=effective_base, image_base_url=image_base_url_input if image_enabled else "",
                image_api_key=image_key, text_model=text_model_input,
                image_model=image_model_input if image_enabled else DEFAULT_IMAGE_MODEL, text_api=text_api_input)
        test_text, test_image = st.columns(2)
        with test_text:
            if st.button("测试文本接口", width="stretch"):
                try:
                    config = draft_config("text")
                    with GATE.claim(st.session_state.session_id, config.api_key, scope="verify"):
                        verify_api_key(config.api_key, base_url=config.base_url,
                                       text_model=config.text_model, text_api=config.text_api)
                    st.success("文本测试成功；图片识别能力将在上传后验证。")
                except Exception as exc:
                    st.error(safe_connection_error(exc))
        with test_image:
            if st.button("检查生图接口", disabled=not image_enabled, width="stretch"):
                try:
                    config = draft_config("image")
                    with GATE.claim(st.session_state.session_id, config.image_api_key, scope="verify"):
                        st.info(verify_image_endpoint(config))
                except Exception as exc:
                    st.error("生图检查失败（可关闭生图继续使用文本）：" + safe_connection_error(exc))
        verify_connection = st.checkbox("保存前测试文本接口（可能产生少量费用）", value=False)
        if st.button("保存并开始使用", type="primary", width="stretch"):
            try:
                config = draft_config()
                if verify_connection:
                    with GATE.claim(st.session_state.session_id, config.api_key, scope="verify"), st.spinner("正在验证连接…"):
                        verify_api_key(
                            config.api_key,
                            base_url=config.base_url,
                            text_model=config.text_model,
                            text_api=config.text_api,
                        )
            except ValueError as exc:
                st.error(safe_connection_error(exc))
            except Exception as exc:
                st.error(safe_connection_error(exc))
            else:
                st.session_state.api_key = config.api_key
                st.session_state.api_base_url = config.base_url
                st.session_state.api_image_base_url = image_base_url_input.strip() if image_enabled else ""
                st.session_state.api_preset = preset
                st.session_state.api_image_key = config.image_api_key if separate_image_key else ""
                st.session_state.image_enabled = image_enabled
                st.session_state.api_text_model = config.text_model
                st.session_state.api_image_model = config.image_model
                st.session_state.api_text_api = config.text_api
                st.session_state.api_source = "session"
                st.session_state.demo_access = False
                st.session_state.stage = "input"
                st.rerun()
        st.link_button(
            "前往 OpenAI 平台创建 Key ↗",
            "https://platform.openai.com/api-keys",
            width="stretch",
        )
        if st.session_state.api_key:
            if st.button("返回应用", width="stretch"):
                target = st.session_state.api_return_stage
                can_resume = ((target == "results" and st.session_state.plan is not None)
                              or (target == "confirm" and st.session_state.pending_garment is not None))
                st.session_state.stage = target if can_resume else "input"
                st.rerun()
            def clear_keys():
                st.session_state.api_key = ""
                st.session_state.api_image_key = ""
                st.session_state.batch_config = None
                st.session_state.image_tasks = {}
                st.session_state.image_errors = {}
                st.session_state.plan = None
                st.session_state.text_key_input = ""
                st.session_state.image_key_input = ""
                st.session_state.api_source = ""
                st.session_state.demo_access = False
                st.session_state.stage = "api"
            st.button("清除当前会话 Key", width="stretch", on_click=clear_keys)
        else:
            if st.button("暂不配置，仅查看固定 Demo", width="stretch"):
                st.session_state.demo_access = True
                st.session_state.stage = "input"
                st.rerun()
        st.caption("中转站会接收你上传的图片和提示词；请确认其隐私政策与计费规则可信。")
        with st.expander("隐私、费用与数据保存说明"):
            st.markdown(
                "- 你上传的图片和提示词会发送到**你所配置的第三方服务商**（官方或中转站），并按其规则计费。\n"
                "- 本站**不保存到项目文件或数据库**；Key、图片和结果暂存在服务器上与你的浏览器连接对应的会话内存中。"
                "刷新或断线可能丢失会话，实际释放时间由托管平台管理；请及时下载结果。\n"
                "- 页底可主动清除会话中的照片、搭配、收藏和偏好；API Key 可在设置中单独清除。"
                "清除本地会话不会删除服务商已有记录，也不会取消已提交的生图任务。\n"
                "- 错误日志只包含请求编号、阶段、模型与耗时等诊断信息，不含 Key、图片或服务商返回内容。\n"
                "- 服务商可能按其自身政策记录请求数据，请先确认其隐私政策与计费规则可信再使用。\n"
                "- 本工具仅提供穿搭建议，效果图为 AI 生成示意图，不代表实物。"
            )


def rotate_by(delta: int) -> None:
    st.session_state.rotate_deg = (st.session_state.rotate_deg + delta) % 360


def remember(widget_key: str, shadow_key: str) -> None:
    """把控件当前值写入阴影键：控件状态会随页面切换被回收，阴影键不会。"""

    st.session_state[shadow_key] = st.session_state[widget_key]


def prepared_upload(uploaded) -> bytes | None:
    """Reset per-photo adjustments when a new file arrives, then apply them.

    安全校验永远先于任何预处理：先 validate_upload 拦截伪造与像素炸弹，
    再对已归一化的字节做旋转/裁剪。
    """

    if uploaded is None:
        st.session_state.prep_error = ""
        st.session_state.prep_sig = ""
        return None
    st.session_state.prep_error = ""
    try:
        original = uploaded.getvalue()
        data, _mime = validate_upload(original)
    except InvalidImage as exc:
        st.session_state.prep_error = str(exc)
        return None
    signature = hashlib.sha256(original).hexdigest()
    if st.session_state.prep_sig != signature:
        st.session_state.prep_sig = signature
        st.session_state.rotate_deg = 0
        st.session_state.bg_removed = False
        st.session_state.prep_error = ""
        for key, value in (("crop_l", 0), ("crop_t", 0), ("crop_r", 100), ("crop_b", 100)):
            st.session_state[key] = value
    return adjust(
        data,
        rotation=st.session_state.rotate_deg,
        crop=(st.session_state.crop_l, st.session_state.crop_t,
              st.session_state.crop_r, st.session_state.crop_b),
        remove_background=st.session_state.bg_removed,
    )


def render_input() -> None:
    header()
    has_key = bool(st.session_state.api_key)
    copy_col, form_col = st.columns([.82, 1.18], gap="large")
    with copy_col:
        st.markdown(
            """
            <div class="hero-copy">
              <h1>从一件单品，<br>开始<em>三种可能</em></h1>
              <p>上传你衣橱里的一件单品，AI 会识别它，并在你确认识别结果后生成完整搭配。</p>
              <div class="garment-mark" aria-hidden="true"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with form_col:
        uploaded = st.file_uploader(
            "拖入照片，或点击选择",
            type=["jpg", "jpeg", "png", "webp"],
            key="photo-upload",
            help="支持 JPG、PNG、WEBP · 最大 10 MB",
            disabled=not has_key,
        )
        prepared = prepared_upload(uploaded) if has_key else None
        crop_invalid = False
        if prepared is not None:
            with st.expander("拍照小助手（旋转 / 裁剪 / 质量检查）"):
                left_col, right_col = st.columns([1.2, 1])
                with left_col:
                    st.image(safe_image(prepared), width="stretch")
                with right_col:
                    rotate_a, rotate_b = st.columns(2)
                    with rotate_a:
                        st.button("↺ 左转 90°", on_click=rotate_by, args=(-90,),
                                  width="stretch")
                    with rotate_b:
                        st.button("↻ 右转 90°", on_click=rotate_by, args=(90,),
                                  width="stretch")
                    st.caption("裁剪出主体所在的区域（百分比）")
                    crop_top = st.slider("上边", 0, 90, key="crop_t")
                    crop_bottom = st.slider("下边", 10, 100, key="crop_b")
                    crop_left = st.slider("左边", 0, 90, key="crop_l")
                    crop_right = st.slider("右边", 10, 100, key="crop_r")
                    crop_invalid = crop_left >= crop_right or crop_top >= crop_bottom
                    if crop_invalid:
                        st.warning("裁剪范围无效：左边必须小于右边，上边必须小于下边。调整后才能识别。")
                    if background_removal_available():
                        st.checkbox("尝试去除背景（可选，需本机已安装 rembg）",
                                    key="bg_removed")
                for note in quality_notes(prepared):
                    st.caption(f"⚠ {note}")
        elif has_key and st.session_state.get("prep_error"):
            st.warning(f"图片未通过安全检查：{st.session_state.prep_error}")
        st.markdown('<div class="question">关于穿着者（可选）</div>', unsafe_allow_html=True)
        gender_col, age_col = st.columns(2)
        with gender_col:
            st.selectbox("性别（可选）", GENDERS,
                         index=GENDERS.index(st.session_state.pref_gender),
                         key="prefs_gender", persist_state="session",
                         on_change=partial(remember, "prefs_gender", "pref_gender"))
        with age_col:
            st.selectbox("年龄段（可选）", AGE_GROUPS,
                         index=AGE_GROUPS.index(st.session_state.pref_age_group),
                         key="prefs_age_group", persist_state="session",
                         on_change=partial(remember, "prefs_age_group", "pref_age_group"))
        st.caption("可不提供，不从照片猜测。仅在本会话保存；生成搭配和换一套时随偏好发送给你配置的 API 服务商。")
        st.markdown('<div class="question">⌖ 今天准备去哪？</div>', unsafe_allow_html=True)
        occasion = st.radio("场景", OCCASIONS, horizontal=True, label_visibility="collapsed",
                            index=OCCASIONS.index(st.session_state.sel_occasion),
                            key="occ_widget", persist_state="session",
                            on_change=partial(remember, "occ_widget", "sel_occasion"))
        st.markdown('<div class="question">♢ 更偏爱哪种风格？</div>', unsafe_allow_html=True)
        preferred_style = st.radio("风格", STYLES, horizontal=True, label_visibility="collapsed",
                                   index=STYLES.index(st.session_state.sel_style),
                                   key="style_widget", persist_state="session",
                                   on_change=partial(remember, "style_widget", "sel_style"))
        st.markdown('<div class="question">☁ 今天天气与通勤？</div>', unsafe_allow_html=True)
        temp_col, weather_col, commute_col = st.columns(3)
        with temp_col:
            temperature = st.selectbox(
                "气温", TEMPERATURES, index=TEMPERATURES.index(st.session_state.cond_temperature),
                key="temp_widget", persist_state="session",
                on_change=partial(remember, "temp_widget", "cond_temperature"))
        with weather_col:
            weather = st.selectbox(
                "天气", WEATHER, index=WEATHER.index(st.session_state.cond_weather),
                key="weather_widget", persist_state="session",
                on_change=partial(remember, "weather_widget", "cond_weather"))
        with commute_col:
            commute = st.selectbox(
                "通勤方式", COMMUTES, index=COMMUTES.index(st.session_state.cond_commute),
                key="commute_widget", persist_state="session",
                on_change=partial(remember, "commute_widget", "cond_commute"))
        with st.expander("我的偏好档案（本次会话记住，切换页面不丢失）"):
            pref_a, pref_b = st.columns(2)
            with pref_a:
                st.text_input("不喜欢的颜色", placeholder="例如：荧光绿", key="prefs_colors",
                              value=st.session_state.pref_colors, persist_state="session",
                              on_change=partial(remember, "prefs_colors", "pref_colors"))
                st.text_input("禁用单品（任何一套都不会出现）", placeholder="例如：高跟鞋、紧身裤",
                              key="prefs_banned", value=st.session_state.pref_banned,
                              persist_state="session",
                              on_change=partial(remember, "prefs_banned", "pref_banned"))
            with pref_b:
                st.text_input("版型偏好", placeholder="例如：宽松、不紧身", key="prefs_fit",
                              value=st.session_state.pref_fit, persist_state="session",
                              on_change=partial(remember, "prefs_fit", "pref_fit"))
                st.selectbox("预算档位", BUDGETS, key="prefs_budget",
                             index=BUDGETS.index(st.session_state.pref_budget),
                             persist_state="session",
                             on_change=partial(remember, "prefs_budget", "pref_budget"))
            st.text_input("其他要求", placeholder="例如：需要能装电脑的包", key="prefs_notes",
                          value=st.session_state.pref_notes, persist_state="session",
                          on_change=partial(remember, "prefs_notes", "pref_notes"))
        button_label = "✦ 识别我的单品" if has_key else "✦ 查看固定 Demo"
        if st.button(button_label, type="primary", width="stretch",
                     disabled=has_key and (prepared is None or crop_invalid)):
            conditions = f"气温：{temperature}；天气：{weather}；通勤：{commute}"
            if has_key and st.session_state.get("prep_error"):
                st.error(f"图片未通过安全检查：{st.session_state.prep_error}")
            else:
                try:
                    if has_key:
                        start_analysis(prepared, occasion, preferred_style, conditions)
                    else:
                        run_demo(occasion, preferred_style)
                except Exception as exc:  # API failures should stay visible and recoverable in UI.
                    st.error(f"识别失败：{safe_connection_error(exc)}")
                    if st.session_state.last_request_id:
                        st.caption(f"请求编号 {st.session_state.last_request_id} · 可凭编号在服务日志中定位本次流程")
        st.markdown(
            '<div class="mode-note">流程：识别单品（1 次调用）→ 确认识别结果 → 生成三套搭配（1 次调用）；'
            '平铺效果图每张另计 1 次生图调用，可逐张生成。</div>',
            unsafe_allow_html=True,
        )
        if not has_key:
            st.markdown(
                '<div class="mode-note">固定 Demo 不会读取你上传的图片；请进入 API 设置后再识别自己的单品。</div>',
                unsafe_allow_html=True,
            )


def edited_garment(garment: GarmentAnalysis) -> GarmentAnalysis:
    def split_list(value: str, fallback: list[str]) -> list[str]:
        parts = [part.strip() for part in re.split(r"[、,，;；/]", value or "") if part.strip()]
        return parts or fallback

    def cleaned(value: str, fallback: str) -> str:
        value = (value or "").strip()
        return value or fallback

    data = garment.model_dump()
    data.update(
        category=cleaned(st.session_state.confirm_category, garment.category),
        subcategory=cleaned(st.session_state.confirm_subcategory, garment.subcategory),
        color=cleaned(st.session_state.confirm_color, garment.color),
        material=cleaned(st.session_state.confirm_material, garment.material),
        pattern=cleaned(st.session_state.confirm_pattern, garment.pattern),
        fit=cleaned(st.session_state.confirm_fit, garment.fit),
        seasons=split_list(st.session_state.confirm_seasons, garment.seasons),
        styles=split_list(st.session_state.confirm_styles, garment.styles),
    )
    notes = st.session_state.get("confirm_notes", "、".join(garment.preservation_notes))
    structural_edit = any(data[field] != getattr(garment, field)
                          for field in ("category", "subcategory", "color", "material", "pattern", "fit"))
    # Do not silently retain the old color/material in a free-text recognition note.
    data["preservation_notes"] = (
        [] if structural_edit and notes == "、".join(garment.preservation_notes)
        else split_list(notes, [])
    )
    return GarmentAnalysis(**data)


def render_confirm() -> None:
    garment: GarmentAnalysis = st.session_state.pending_garment
    header()
    title_col, source_col = st.columns([.9, 1.1], gap="large")
    with title_col:
        st.markdown(
            """
            <div class="results-head">
              <h1>确认识别结果</h1>
              <p>识别可能出错；修改后，后续三套搭配将使用修改后的信息。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with source_col:
        image_col, info_col = st.columns([1, 4], vertical_alignment="center")
        with image_col:
            st.image(safe_image(st.session_state.pending_source), width="stretch")
        with info_col:
            st.markdown(
                '<div class="source-title">AI 识别</div>'
                f'<div class="source-name">{html.escape(garment.display_name)}</div>',
                unsafe_allow_html=True,
            )
    st.markdown('<div class="source-rail"></div>', unsafe_allow_html=True)

    edit_col, gap_col, scope_col = st.columns([1.15, .1, 1], gap="large")
    with edit_col:
        st.markdown('<div class="question">核对并修改单品信息</div>', unsafe_allow_html=True)
        category_col, sub_col = st.columns(2)
        with category_col:
            st.text_input("品类", value=garment.category, key="confirm_category", persist_state="session")
        with sub_col:
            st.text_input("具体品类", value=garment.subcategory, key="confirm_subcategory", persist_state="session")
        color_col, material_col = st.columns(2)
        with color_col:
            st.text_input("颜色", value=garment.color, key="confirm_color", persist_state="session")
        with material_col:
            st.text_input("材质", value=garment.material, key="confirm_material", persist_state="session")
        pattern_col, fit_col = st.columns(2)
        with pattern_col:
            st.text_input("图案", value=garment.pattern, key="confirm_pattern", persist_state="session")
        with fit_col:
            st.text_input("版型", value=garment.fit, key="confirm_fit", persist_state="session")
        st.text_input("适合季节（用、分隔）", value="、".join(garment.seasons), key="confirm_seasons", persist_state="session")
        st.text_input("风格标签（用、分隔）", value="、".join(garment.styles), key="confirm_styles", persist_state="session")
        st.text_area("需保留的细节（可修改，用、分隔）",
                     value="、".join(garment.preservation_notes), key="confirm_notes", persist_state="session")
        st.caption("若修改颜色、材质或版型但未修改细节说明，旧的识别细节将不再传入，避免冲突。")
    with scope_col:
        st.markdown('<div class="question">生成范围与费用</div>', unsafe_allow_html=True)
        options = ["仅生成文字搭配（再调用 1 次）"]
        if st.session_state.image_enabled:
            options.append("文字 + 全部 3 张平铺图（再调用 4 次）")
        scope = st.radio("本次生成范围", options, index=0, label_visibility="collapsed",
                         help="默认只生成文字；平铺图也可稍后在结果页逐张生成。")
        generate_images = scope != options[0]
        st.caption(
            "调用次数：识别已完成 1 次；文字搭配规划 1 次；"
            "每张真实平铺图另计 1 次生图调用，按你的服务商计费。"
        )
        if st.button("✦ 用这份信息生成三套搭配", type="primary", width="stretch"):
            try:
                run_plan(edited_garment(garment), generate_images)
            except Exception as exc:
                st.error(f"生成失败：{safe_connection_error(exc)}")
                if st.session_state.last_request_id:
                    st.caption(f"请求编号 {st.session_state.last_request_id} · 可凭编号在服务日志中定位本次流程")
        if st.button("← 重新上传", width="stretch"):
            st.session_state.stage = "input"
            st.session_state.pending_garment = None
            st.session_state.pending_source = None
            st.rerun()


def feedback_button(label: str, bucket: str, look_id: str) -> None:
    item_key = look_key(look_id)
    active = item_key in st.session_state[bucket]
    text = f"✓ {label}" if active else label
    if st.button(text, key=f"{bucket}-{look_id}", width="stretch"):
        values = set(st.session_state[bucket])
        if active:
            values.remove(item_key)
        else:
            values.add(item_key)
        st.session_state[bucket] = values
        st.rerun()


def replace_look(outfit) -> None:
    keys = [st.session_state.api_key]
    with GATE.claim(st.session_state.session_id, *keys, scope="generate"):
        _replace_look(outfit)
    st.rerun()


def _replace_look(old) -> None:
    """只替换一套 LOOK：一次文本调用；不自动生图、不影响其他两套。"""

    if st.session_state.recognition_demo:
        raise PlanRejected("固定 Demo 不调用 API；请配置 Key 并上传自己的单品。")
    plan: OutfitPlan = st.session_state.plan
    index = next(i for i, item in enumerate(plan.outfits) if item.id == old.id)
    others = [item for item in plan.outfits if item.id != old.id]
    garment: GarmentAnalysis = st.session_state.garment
    config = current_config()
    request_id = new_request_id()
    st.session_state.last_request_id = request_id
    with service(config) as ai:
        with trace(request_id, "replace", model=config.text_model, protocol=config.text_api):
            fresh = ai.regenerate_outfit(
                garment, st.session_state.occasion, st.session_state.preferred_style,
                avoid=["；".join(item.pieces) for item in plan.outfits],
                conditions=st.session_state.get("confirm_conditions", ""),
                preferences=preferences_text(),
            )
    fresh = fresh.model_copy(update={"id": f"look-{uuid.uuid4().hex[:8]}"})
    # 校验：新 LOOK 对另外两套和被替换的原 LOOK 都要有清晰差异，且遵守禁用单品
    candidate = OutfitPlan(outfits=[fresh, *others])
    issues = (plan_issues(candidate) + diversity_issues(candidate, garment)
              + preference_issues(candidate, banned_terms()))
    if diversity_pair_issues(fresh, old, 0, 0, garment):
        issues.append(f"新 LOOK 与被替换的 LOOK {index + 1:02d} 过于相似，未替换")
    if issues:
        raise PlanRejected("替换方案未通过校验（" + "；".join(issues) + "），请重试。")
    st.session_state.plan = OutfitPlan(
        outfits=others[:index] + [fresh] + others[index:],
    )
    # 旧图与任务状态随旧 LOOK 一起清理；新 LOOK 的效果图由用户单独发起，避免额外费用
    st.session_state.result_images.pop(old.id, None)
    st.session_state.image_tasks.pop(old.id, None)
    st.session_state.image_errors.pop(old.id, None)
    refresh_history_latest()


def look_key(look_id: str) -> str:
    return f"{st.session_state.batch_id}:{look_id}"


def save_look_button(outfit, look_index: int) -> None:
    item_key = look_key(outfit.id)
    active = item_key in st.session_state.saved
    label = f"✓ 收藏" if active else "收藏"
    if st.button(label, key=f"saved-{outfit.id}", width="stretch"):
        if active:
            st.session_state.saved.discard(item_key)
            st.session_state.saved_details.pop(item_key, None)
        else:
            if len(st.session_state.saved_details) >= 20:
                st.warning("本会话最多收藏 20 套，请先移除不需要的收藏。")
                return
            st.session_state.saved.add(item_key)
            st.session_state.saved_details[item_key] = {
                "label": f"{st.session_state.garment.display_name} · {st.session_state.occasion}",
                "style": outfit.style,
                "pieces": outfit.pieces,
                "reason": outfit.reason,
                "score": outfit.compatibility_score,
                "image": st.session_state.result_images.get(outfit.id),
                "time": time.strftime("%H:%M"),
            }
        st.rerun()


def render_saved_section() -> None:
    details = st.session_state.get("saved_details") or {}
    with st.expander(f"我的收藏（本会话 · {len(details)} 套）"):
        if not details:
            st.caption("在结果页点击“收藏”后，这里可以随时查看和下载。")
            return
        for look_id, detail in details.items():
            st.markdown(
                f"**{detail['time']} · {html.escape(detail['label'])} · "
                f"{html.escape(detail['style'])}（{detail['score']}%）**"
            )
            st.markdown(" · ".join(html.escape(piece) for piece in detail["pieces"]))
            if detail.get("image"):
                download_image(detail["image"], f"saved-dl-{look_id}")
            else:
                st.caption("这张还没有生成效果图。")
            st.download_button("下载收藏清单",
                               data="\n".join([detail["label"], detail["style"],
                                               *detail["pieces"], detail["reason"]]),
                               file_name="stylemate-favorite.txt", mime="text/plain",
                               key=f"saved-text-{look_id}")
            if st.button("移除收藏", key=f"unsave-{look_id}"):
                st.session_state.saved.discard(look_id)
                st.session_state.saved_details.pop(look_id, None)
                st.rerun()


def render_results() -> None:
    garment: GarmentAnalysis = st.session_state.garment
    plan: OutfitPlan = st.session_state.plan
    header(show_reset=True)

    title_col, source_col = st.columns([.9, 1.1], gap="large")
    with title_col:
        display_name = html.escape(garment.display_name)
        st.markdown(
            f"""
            <div class="results-head">
              <h1>为你生成的 3 套穿搭</h1>
              <p>{display_name} · {st.session_state.occasion} · {st.session_state.preferred_style}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with source_col:
        image_col, info_col = st.columns([1, 4], vertical_alignment="center")
        with image_col:
            st.image(safe_image(st.session_state.source_image), width="stretch")
        with info_col:
            tags = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in garment.tags)
            st.markdown(
                f'<div class="source-title">你的单品</div><div class="source-name">{display_name}</div><div class="tags">{tags}</div>',
                unsafe_allow_html=True,
            )
    st.markdown('<div class="source-rail"></div>', unsafe_allow_html=True)

    if st.session_state.recognition_demo:
        st.info("当前为固定 Demo，未读取任何上传图片。配置 API Key 后才能识别你自己的单品。")

    columns = st.columns(3, gap="large")
    for index, (column, outfit) in enumerate(zip(columns, plan.outfits), start=1):
        with column:
            style_name = html.escape(outfit.style)
            st.markdown(
                f"""
                <div class="look-head">
                  <span class="look-index">LOOK {index:02d}</span>
                  <span class="look-style">{style_name}</span>
                  <span class="look-score">AI 推荐度 {outfit.compatibility_score}/100</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            result = st.session_state.result_images.get(outfit.id)
            if result:
                st.image(safe_image(result), width="stretch")
                download_image(result, f"result-dl-{outfit.id}")
            elif not st.session_state.recognition_demo and not st.session_state.image_enabled:
                st.info("生图已关闭；如需效果图，请先在 API 设置中启用生图。")
            elif not st.session_state.recognition_demo:
                task = st.session_state.image_tasks.get(outfit.id, {})
                error = st.session_state.image_errors.get(outfit.id)
                if error:
                    st.warning(error)
                else:
                    st.info("这张图还未生成；可单独生成，不影响其他两套结果。")
                task_id = task.get("task_id")
                if task_id:
                    st.caption(f"任务编号：{task_id}")
                terminal = task.get("status") in {"failed", "cancelled", "canceled", "error"}
                needs_new = terminal or (not task_id and task.get("status") in {"unknown", "submitting"})
                confirmed = not needs_new or st.checkbox("确认重新提交这张图（可能再次计费；请先核对服务商后台）", key=f"confirm-{outfit.id}")
                if task_id and not terminal:
                    label = "继续查询这张图"
                elif task:
                    label = "重试这张图"
                else:
                    label = "生成这张效果图（1 次生图调用）"
                if st.button(label, key=f"retry-image-{outfit.id}", disabled=not confirmed):
                    try:
                        config = st.session_state.batch_config
                        with GATE.claim(st.session_state.session_id, config.image_api_key, scope="image"), service(config) as ai:
                            if needs_new:
                                st.session_state.image_tasks[outfit.id] = {}
                            generate_one(ai, outfit)
                        st.rerun()
                    except Exception as exc:
                        st.error(safe_connection_error(exc))
            if st.session_state.result_images_demo:
                st.markdown('<div class="look-image-label">示意效果图</div>', unsafe_allow_html=True)
            pieces = "".join(f"<li>{html.escape(piece)}</li>" for piece in outfit.pieces)
            reason = html.escape(outfit.reason)
            st.markdown(
                f"""
                <div class="look-body">
                  <ul class="piece-list">{pieces}</ul>
                  <div class="reason"><strong>为什么适合</strong><p>{reason}</p></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            like_col, save_col, regen_col = st.columns(3)
            with like_col:
                feedback_button("喜欢", "liked", outfit.id)
            with save_col:
                save_look_button(outfit, index)
            with regen_col:
                if st.button("换一套", key=f"regen-{outfit.id}", width="stretch",
                             disabled=st.session_state.recognition_demo,
                             help="重新生成这一套搭配（1 次文本调用）；效果图需另行单独生成，不会自动扣费。"):
                    try:
                        replace_look(outfit)
                    except Exception as exc:
                        st.error(safe_connection_error(exc))
                        if st.session_state.last_request_id:
                            st.caption(f"请求编号 {st.session_state.last_request_id} · 可凭编号在服务日志中定位本次流程")
            with st.expander("查看搭配详情"):
                st.write(f"外套：{outfit.outerwear}")
                st.write(f"搭配风格提示：{outfit.image_prompt}")
                st.caption("当前评分由模型候选分与显式风格偏好组成；V2 可替换为 FashionCLIP 排序器。")

    feedback_count = len(st.session_state.liked) + len(st.session_state.saved)
    if feedback_count:
        st.markdown(
            f'<div class="preference-note">本会话标记了 {feedback_count} 次喜欢或收藏；生成要求以偏好档案为准。</div>',
            unsafe_allow_html=True,
        )

    render_saved_section()

    with st.expander("本次会话历史与导出（仅保存在当前会话，刷新后即清空）"):
        entries = st.session_state.get("history") or []
        if not entries:
            st.caption("还没有生成记录；生成一次搭配后会出现在这里。")
        for index, entry in enumerate(entries):
            st.markdown(f"**{entry['time']} · {html.escape(entry['label'])}**")
            lines = [
                f"LOOK {order:02d} {look['style']}（AI 推荐度 {look['score']}/100）："
                + " + ".join(piece for piece in look["pieces"] if piece)
                for order, look in enumerate(entry["looks"], start=1)
            ]
            st.code("\n".join(lines), language=None)
            st.download_button("下载搭配清单", data="\n".join([entry["label"], *lines]),
                               mime="text/plain", file_name="stylemate-outfits.txt",
                               key=f"history-text-{entry.get('batch_id', index)}")
            if entry["images"]:
                buttons = st.columns(len(entry["images"]))
                for column, (look_id, blob) in zip(buttons, entry["images"].items()):
                    with column:
                        download_image(blob, f"dl-{entry.get('batch_id', index)}-{look_id}")


def clear_session_data() -> None:
    # Keep configuration and limiter identity; clear only this visitor's content.
    for key in list(st.session_state):
        if key.startswith(("pref", "confirm_", "cond_", "crop_")) or key in {
            "garment", "plan", "pending_garment", "pending_source", "pending_mime",
            "source_image", "source_mime", "result_images", "image_tasks", "image_errors",
            "history", "saved", "saved_details", "liked", "batch_id", "batch_config",
            "rotate_deg", "bg_removed", "photo-upload", "sel_occasion", "sel_style",
            "occ_widget", "style_widget", "temp_widget", "weather_widget", "commute_widget",
            "occasion", "last_request_id",
        }:
            del st.session_state[key]
    st.session_state.stage = "input" if st.session_state.api_key or st.session_state.demo_access else "api"


def render_data_controls() -> None:
    with st.expander("会话数据与隐私"):
        st.caption("照片、搭配、历史及最多 20 套收藏仅保留在服务器会话内存中，不写入项目文件或数据库。"
                   "清除后无法恢复，请先下载。已提交的生图任务不会因此取消，仍可能计费。")
        confirmed = st.checkbox("我已下载需要保留的结果，确认清除照片、搭配、收藏和偏好",
                                key="confirm-clear-data")
        st.button("清除会话数据（保留 API 设置）", key="clear-session-data",
                  disabled=not confirmed, on_click=clear_session_data)


init_state()
if st.session_state.stage == "api":
    render_api_setup()
elif st.session_state.stage == "confirm" and st.session_state.pending_garment:
    render_confirm()
elif st.session_state.stage == "results" and st.session_state.plan:
    render_results()
else:
    render_input()
render_data_controls()
