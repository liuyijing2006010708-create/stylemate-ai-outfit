from __future__ import annotations

import html
import io
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

from stylemate.demo import DEMO_GARMENT_IMAGE, DEMO_IMAGES, demo_payload
from stylemate.models import GarmentAnalysis, OutfitPlan
from stylemate.openai_service import StyleMateAI
from stylemate.ranking import rank_outfits
from stylemate.runtime import (
    APIConfig,
    DEFAULT_BASE_URL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_TEXT_MODEL,
    RunMode,
    decide_run_mode,
    normalize_api_key,
    provider_display_name,
    safe_connection_error,
    image_generation_mode,
    verify_api_key,
    verify_image_endpoint,
)
from stylemate.operations import GATE
from stylemate.security import protect_provider_logs
from stylemate.styles import APP_CSS


load_dotenv()
protect_provider_logs()
st.set_page_config(page_title="StyleMate · AI 穿搭助手", page_icon="✦", layout="wide")
st.markdown(APP_CSS, unsafe_allow_html=True)

OCCASIONS = ["上班", "上课", "约会", "旅行", "聚会"]
STYLES = ["韩系简约", "City Boy", "美式复古", "极简", "Old Money", "Y2K"]


def init_state() -> None:
    environment_key = (
        "" if globals().get("PUBLIC_DEPLOYMENT", False)
        else normalize_api_key(os.getenv("OPENAI_API_KEY"))
    )
    defaults = {
        "stage": "input" if environment_key else "api",
        "api_key": environment_key,
        "api_source": "environment" if environment_key else "",
        "api_image_key": "",
        "image_enabled": True,
        "session_id": uuid.uuid4().hex,
        "image_tasks": {},
        "image_errors": {},
        "batch_config": None,
        "api_base_url": os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        "api_image_base_url": os.getenv("OPENAI_IMAGE_BASE_URL", ""),
        "api_text_model": os.getenv("OPENAI_TEXT_MODEL", DEFAULT_TEXT_MODEL),
        "api_image_model": os.getenv("OPENAI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
        "api_text_api": os.getenv("OPENAI_TEXT_API", "responses"),
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
        "regenerated": set(),
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
    with right:
        if show_reset and show_api_settings:
            reset_col, api_col = st.columns(2)
            with reset_col:
                if st.button("↻ 重新搭配", width="stretch"):
                    st.session_state.stage = "input"
                    st.rerun()
            with api_col:
                if st.button("⚙ API 设置", width="stretch"):
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
                    st.session_state.stage = "api"
                    st.rerun()
        else:
            status = "API 已配置" if key_ready else "需要配置 API Key"
            st.markdown(f'<div class="api-state"><strong>✦</strong> {status}</div>', unsafe_allow_html=True)
    st.markdown('<div style="border-bottom:1px solid #dfe2e8;margin:.85rem 0 1.7rem"></div>', unsafe_allow_html=True)


def safe_image(data: bytes | Path) -> Image.Image:
    if isinstance(data, Path):
        return Image.open(data)
    return Image.open(io.BytesIO(data))


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


def generate_one(ai, outfit):
    state = st.session_state.image_tasks.setdefault(outfit.id, {})
    progress = st.empty()
    labels = {"submitting": "正在提交", "queued": "排队中", "pending": "排队中",
              "running": "生成中", "processing": "生成中", "in_progress": "生成中",
              "downloading": "下载中", "completed": "完成", "timeout": "等待超时",
              "query_error": "查询暂时失败", "unknown": "提交结果待确认"}
    try:
        result = ai.generate_outfit_image(
            st.session_state.source_image, st.session_state.source_mime,
            st.session_state.garment, outfit, task_state=state,
            on_progress=lambda item: progress.caption(labels.get(item["status"], "任务结束")),
        )
        st.session_state.result_images[outfit.id] = result
        state["status"] = "completed"
        st.session_state.image_errors.pop(outfit.id, None)
    except Exception as exc:
        st.session_state.image_errors[outfit.id] = safe_connection_error(exc)
        if not state.get("status"):
            state["status"] = "unknown"


def run_generation(uploaded_file, occasion: str, preferred_style: str, generate_images: bool) -> None:
    keys = [st.session_state.api_key]
    if generate_images:
        keys.append(st.session_state.api_image_key or st.session_state.api_key)
    with GATE.claim(st.session_state.session_id, *keys):
        _run_generation(uploaded_file, occasion, preferred_style, generate_images)
    st.rerun()


def _run_generation(uploaded_file, occasion: str, preferred_style: str, generate_images: bool) -> None:
    mode = decide_run_mode(
        has_upload=uploaded_file is not None,
        api_key=st.session_state.api_key,
        demo_requested=False,
    )
    if mode is not RunMode.LIVE:
        raise RuntimeError("实时生成模式选择异常")

    source = uploaded_file.getvalue()
    source_mime = uploaded_file.type
    config = current_config()
    with service(config) as ai, st.status("正在理解你的单品…", expanded=True) as status:
        garment = ai.analyze_garment(source, source_mime)
        st.write(f"识别完成：{garment.display_name}")
        status.update(label="正在规划候选搭配…")
        plan = ai.plan_outfits(garment, occasion, preferred_style)
        plan = OutfitPlan(outfits=rank_outfits(plan.outfits, preferred_style))
        images: dict[str, bytes] = {}
        # Persist text and each task before making the next potentially failing call.
        st.session_state.update(stage="results", garment=garment, plan=plan,
            result_images=images, source_image=source, source_mime=source_mime,
            occasion=occasion, preferred_style=preferred_style, recognition_demo=False,
            result_images_demo=not generate_images, image_tasks={}, image_errors={},
            batch_config=config)
        if generate_images:
            for index, outfit in enumerate(plan.outfits, start=1):
                status.update(label=f"正在生成效果图 {index}/3…")
                generate_one(ai, outfit)
        else:
            for index, outfit in enumerate(plan.outfits):
                fallback = list(DEMO_IMAGES.values())[index]
                images[outfit.id] = fallback.read_bytes()
                st.session_state.result_images[outfit.id] = images[outfit.id]
        status.update(label="搭配已保存；未完成的图片可在结果页单独处理", state="complete")


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
        image_tasks={}, image_errors={}, batch_config=None,
    )
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
              <p>支持 OpenAI 官方接口与兼容 OpenAI 协议的中转站。Key 只保存在当前应用会话中，不写入项目文件。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with form:
        st.markdown('<div class="setup-title">API 配置</div>', unsafe_allow_html=True)
        api_key_input = st.text_input(
            "API Key（官方或中转站）",
            type="password",
            placeholder="输入中转站提供的 Key",
            help="留空时保留当前会话已经配置的 Key。",
            key="text_key_input",
        )
        base_url_input = st.text_input(
            "API Base URL",
            value=st.session_state.api_base_url,
            placeholder="https://your-relay.example.com/v1",
            help="通常需要以 /v1 结尾；公网中转站必须使用 HTTPS。",
        )
        image_base_url_input = st.text_input(
            "生图 Base URL（可选）",
            value=st.session_state.api_image_base_url,
            placeholder="留空则与文本 Base URL 相同",
            help=(
                "部分中转站的生图接口域名/路径与文本不同，可在此单独填写；"
                "留空时自动复用上面的 API Base URL。"
            ),
        )
        separate_image_key = st.checkbox("生图使用独立 Key", value=bool(st.session_state.api_image_key))
        image_key_input = st.text_input("生图 API Key", type="password", disabled=not separate_image_key,
                                       key="image_key_input",
                                       help="不勾选时复用文本 Key；勾选后留空保留已保存的生图 Key。")
        image_enabled = st.checkbox("启用生图功能", value=st.session_state.image_enabled)
        if provider_display_name(base_url_input) == "RightAPI":
            st.info(
                "已识别 RightAPI：保存时会自动使用文本渠道地址 "
                "`https://rightapi.ai/codex/v1`。生成真实平铺图时，程序会自动调用 "
                "RightAPI 的异步绘图接口并等待任务完成。"
            )
        with st.expander("模型与协议", expanded=True):
            text_model_input = st.text_input(
                "视觉/文本模型",
                value=st.session_state.api_text_model,
                help="必须是中转站实际支持且能读取图片的模型名称。",
            )
            image_model_input = st.text_input(
                "图片编辑模型",
                value=st.session_state.api_image_model,
                help=(
                    "只有开启真实平铺图时使用；RightAPI 推荐 gpt-image-2，"
                    "其他中转站需支持 /images/edits。"
                ),
            )
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
        st.caption("文本测试会发送一次小请求，可能计费；生图检查仅检查模型列表，不创建图片任务。")
        def draft_config(target=None):
            image_key = (normalize_api_key(image_key_input) or st.session_state.api_image_key) if separate_image_key else ""
            text_key = normalize_api_key(api_key_input) or st.session_state.api_key
            if target == "text":
                return APIConfig.from_values(api_key=text_key, base_url=base_url_input,
                    text_model=text_model_input, image_model=DEFAULT_IMAGE_MODEL, text_api=text_api_input)
            if separate_image_key and not image_key and image_enabled:
                raise ValueError("请填写生图 Key。")
            if target == "image":
                return APIConfig.from_values(api_key=image_key or text_key,
                    base_url=image_base_url_input or base_url_input,
                    text_model=DEFAULT_TEXT_MODEL, image_model=image_model_input, text_api="responses")
            return APIConfig.from_values(
                api_key=text_key,
                base_url=base_url_input, image_base_url=image_base_url_input if image_enabled else "",
                image_api_key=image_key, text_model=text_model_input,
                image_model=image_model_input if image_enabled else DEFAULT_IMAGE_MODEL, text_api=text_api_input)
        test_text, test_image = st.columns(2)
        with test_text:
            if st.button("测试文本接口", width="stretch"):
                try:
                    config = draft_config("text")
                    with GATE.claim(st.session_state.session_id, config.api_key):
                        verify_api_key(config.api_key, base_url=config.base_url,
                                       text_model=config.text_model, text_api=config.text_api)
                    st.success("文本测试成功；图片识别能力将在上传后验证。")
                except Exception as exc:
                    st.error(safe_connection_error(exc))
        with test_image:
            if st.button("检查生图接口", disabled=not image_enabled, width="stretch"):
                try:
                    config = draft_config("image")
                    with GATE.claim(st.session_state.session_id, config.image_api_key):
                        st.info(verify_image_endpoint(config))
                except Exception as exc:
                    st.error("生图检查失败（可关闭生图继续使用文本）：" + safe_connection_error(exc))
        verify_connection = st.checkbox("保存前测试文本接口（可能产生少量费用）", value=False)
        if st.button("保存并开始使用", type="primary", width="stretch"):
            try:
                config = draft_config()
                if verify_connection:
                    with GATE.claim(st.session_state.session_id, config.api_key), st.spinner("正在验证连接…"):
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
                st.session_state.api_image_base_url = config.image_base_url
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
                st.session_state.stage = "input"
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


def render_input() -> None:
    header()
    has_key = bool(st.session_state.api_key)
    image_mode = image_generation_mode(
        st.session_state.api_image_base_url or st.session_state.api_base_url
    )
    copy_col, form_col = st.columns([.82, 1.18], gap="large")
    with copy_col:
        st.markdown(
            """
            <div class="hero-copy">
              <h1>从一件单品，<br>开始<em>三种可能</em></h1>
              <p>上传你衣橱里的一件单品，AI 会识别它，并为场景、天气与偏好生成完整搭配。</p>
              <div class="garment-mark" aria-hidden="true"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with form_col:
        uploaded = st.file_uploader(
            "拖入照片，或点击选择",
            type=["jpg", "jpeg", "png", "webp"],
            help="支持 JPG、PNG、WEBP · 最大 10 MB",
            disabled=not has_key,
        )
        st.markdown('<div class="question">⌖ 今天准备去哪？</div>', unsafe_allow_html=True)
        occasion = st.radio("场景", OCCASIONS, horizontal=True, label_visibility="collapsed")
        st.markdown('<div class="question">♢ 更偏爱哪种风格？</div>', unsafe_allow_html=True)
        preferred_style = st.radio("风格", STYLES, horizontal=True, label_visibility="collapsed")
        generate_images = st.toggle(
            "生成真实平铺效果图",
            value=False,
            help=(
                "RightAPI 会提交 3 个异步绘图任务并逐个等待完成；可能需要几分钟。"
                if image_mode == "rightapi_async"
                else "开启后会额外调用 3 次图像编辑 API；关闭时使用内置示意图。"
            ),
            disabled=not has_key or not st.session_state.image_enabled,
        )
        button_label = "✦ 生成我的穿搭" if has_key else "✦ 查看固定 Demo"
        if st.button(button_label, type="primary", width="stretch"):
            try:
                if has_key:
                    run_generation(uploaded, occasion, preferred_style, generate_images and st.session_state.image_enabled)
                else:
                    run_demo(occasion, preferred_style)
            except Exception as exc:  # API failures should stay visible and recoverable in UI.
                st.error(f"生成失败：{safe_connection_error(exc)}")
        if not has_key:
            note = "固定 Demo 不会读取你上传的图片；请进入 API 设置后再识别自己的单品。"
        elif image_mode == "rightapi_async":
            note = "RightAPI 异步绘图已启用；开启效果图后会等待三张任务依次完成。"
        else:
            note = "关闭效果图开关可先低成本验证识别与搭配规划。"
        st.markdown(f'<div class="mode-note">{note}</div>', unsafe_allow_html=True)


def feedback_button(label: str, bucket: str, look_id: str) -> None:
    active = look_id in st.session_state[bucket]
    text = f"✓ {label}" if active else label
    if st.button(text, key=f"{bucket}-{look_id}", width="stretch"):
        values = set(st.session_state[bucket])
        if active:
            values.remove(look_id)
        else:
            values.add(look_id)
        st.session_state[bucket] = values
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
    elif st.session_state.result_images_demo:
        st.info("单品识别与搭配文案来自本次上传图片；下方三张穿搭图暂为版式示意。开启“生成真实平铺效果图”可生成对应图片。")

    columns = st.columns(3, gap="large")
    for index, (column, outfit) in enumerate(zip(columns, plan.outfits), start=1):
        with column:
            style_name = html.escape(outfit.style)
            st.markdown(
                f"""
                <div class="look-head">
                  <span class="look-index">LOOK {index:02d}</span>
                  <span class="look-style">{style_name}</span>
                  <span class="look-score">{outfit.compatibility_score}%</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            result = st.session_state.result_images.get(outfit.id)
            if result:
                st.image(safe_image(result), width="stretch")
            elif not st.session_state.recognition_demo:
                task = st.session_state.image_tasks.get(outfit.id, {})
                st.warning(st.session_state.image_errors.get(outfit.id, "图片尚未完成。"))
                task_id = task.get("task_id")
                if task_id:
                    st.caption(f"任务编号：{task_id}")
                terminal = task.get("status") in {"failed", "cancelled", "canceled", "error"}
                needs_new = terminal or (not task_id and task.get("status") in {"unknown", "submitting"})
                confirmed = not needs_new or st.checkbox("确认重新提交这张图（可能再次计费；请先核对服务商后台）", key=f"confirm-{outfit.id}")
                label = "继续查询这张图" if task_id and not terminal else "重试这张图"
                if st.button(label, key=f"retry-image-{outfit.id}", disabled=not confirmed):
                    try:
                        config = st.session_state.batch_config
                        with GATE.claim(st.session_state.session_id, config.image_api_key), service(config) as ai:
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
                feedback_button("收藏", "saved", outfit.id)
            with regen_col:
                if st.button("换一套", key=f"regen-{outfit.id}", width="stretch"):
                    values = set(st.session_state.regenerated)
                    values.add(outfit.id)
                    st.session_state.regenerated = values
                    st.toast("已记录：下一轮将降低相似搭配的权重。")
            with st.expander("查看搭配详情"):
                st.write(f"原单品：{outfit.outerwear}")
                st.write(f"图像生成描述：{outfit.image_prompt}")
                st.caption("当前评分由模型候选分与显式风格偏好组成；V2 可替换为 FashionCLIP 排序器。")

    feedback_count = len(st.session_state.liked) + len(st.session_state.saved)
    if feedback_count:
        st.markdown(
            f'<div class="preference-note">已记录 {feedback_count} 个正向偏好，下一轮会优先参考。</div>',
            unsafe_allow_html=True,
        )


init_state()
if st.session_state.stage == "api":
    render_api_setup()
elif st.session_state.stage == "results" and st.session_state.plan:
    render_results()
else:
    render_input()
