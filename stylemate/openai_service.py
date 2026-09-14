from __future__ import annotations

import base64
import io
import os
from typing import Any, Callable, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from .models import GarmentAnalysis, Outfit, OutfitPlan
from .consistency import build_image_prompt
from .rightapi_images import RightAPIImageClient
from .security import secure_http_client, protect_provider_logs
from .uploads import ensure_image_bytes
from .runtime import (
    APIConfig,
    DEFAULT_BASE_URL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_TEXT_MODEL,
    image_generation_mode,
)


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class StyleMateAI:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        image_base_url: str | None = None,
        image_api_key: str | None = None,
        text_model: str | None = None,
        image_model: str | None = None,
        text_api: str | None = None,
        client_factory: Callable[..., Any] = OpenAI,
        rightapi_image_factory: Callable[..., Any] = RightAPIImageClient,
    ) -> None:
        config = APIConfig.from_values(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
            image_base_url=image_base_url or os.getenv("OPENAI_IMAGE_BASE_URL", ""),
            image_api_key=image_api_key,
            text_model=text_model or os.getenv("OPENAI_TEXT_MODEL", DEFAULT_TEXT_MODEL),
            image_model=image_model or os.getenv("OPENAI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
            text_api=text_api or os.getenv("OPENAI_TEXT_API", "responses"),
        )
        protect_provider_logs()
        self.client = client_factory(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=180.0,
            max_retries=0,
            **({"http_client": secure_http_client(timeout=180.0)} if client_factory is OpenAI else {}),
        )
        self.image_client = (
            client_factory(
                api_key=config.image_api_key,
                base_url=config.image_base_url,
                timeout=180.0,
                max_retries=0,
                **({"http_client": secure_http_client(timeout=180.0)} if client_factory is OpenAI else {}),
            )
            if config.image_base_url != config.base_url or config.image_api_key != config.api_key
            else self.client
        )
        self.text_model = config.text_model
        self.image_model = config.image_model
        self.text_api = config.text_api
        self.image_generation_mode = image_generation_mode(config.image_base_url)
        self.rightapi_images = (
            rightapi_image_factory(api_key=config.image_api_key, model=config.image_model)
            if self.image_generation_mode == "rightapi_async"
            else None
        )

    def close(self):
        self.client.close()
        if self.image_client is not self.client:
            self.image_client.close()

    @staticmethod
    def _data_url(image_bytes: bytes, mime_type: str) -> str:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    def analyze_garment(self, image_bytes: bytes, mime_type: str) -> GarmentAnalysis:
        if self.text_api == "chat_completions":
            response = self.client.chat.completions.parse(
                model=self.text_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是严谨的服装商品分析师。只描述画面中最主要的一件服装；"
                            "不猜测品牌、价格或不可见结构。所有字段使用简洁中文。"
                            "subcategory 只写服装品类，不包含颜色；color 只写主色，"
                            "滚边、纽扣和装饰等辅色细节写入 preservation_notes。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "识别这件服装的品类、颜色、材质、图案、版型、"
                                    "适合季节和风格，并列出生成搭配图时必须保持的视觉细节。"
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": self._data_url(image_bytes, mime_type),
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                response_format=GarmentAnalysis,
            )
            parsed = response.choices[0].message.parsed if response.choices else None
            if not parsed:
                raise RuntimeError("服装识别没有返回结构化结果")
            return parsed

        response = self.client.responses.parse(
            model=self.text_model,
            instructions=(
                "你是严谨的服装商品分析师。只描述画面中最主要的一件服装；"
                "不猜测品牌、价格或不可见结构。所有字段使用简洁中文。"
                "subcategory 只写服装品类，不包含颜色；color 只写主色，"
                "滚边、纽扣和装饰等辅色细节写入 preservation_notes。"
            ),
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "识别这件服装的品类、颜色、材质、图案、版型、"
                                "适合季节和风格，并列出生成搭配图时必须保持的视觉细节。"
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": self._data_url(image_bytes, mime_type),
                            "detail": "high",
                        },
                    ],
                }
            ],
            text_format=GarmentAnalysis,
        )
        if not response.output_parsed:
            raise RuntimeError("服装识别没有返回结构化结果")
        return response.output_parsed

    def plan_outfits(
        self,
        garment: GarmentAnalysis,
        occasion: str,
        preferred_style: str,
        *,
        conditions: str = "",
        preferences: str = "",
    ) -> OutfitPlan:
        user_prompt = (
            f"用户单品：{garment.model_dump_json(ensure_ascii=False)}\n"
            f"场景：{occasion}\n偏好风格：{preferred_style}\n"
            "每套包含上装、外套、下装、鞋、包、配饰、中文理由、0-100 兼容度，"
            "以及一段用于生成无人物平铺图的英文 image_prompt。"
        )
        if conditions:
            user_prompt += f"\n环境与活动：{conditions}"
        if preferences:
            user_prompt += f"\n用户硬性约束（必须逐条遵守）：{preferences}"
        instructions = (
            "你是专业造型师和推荐系统候选生成器。输出恰好三套完整搭配，按位置给定明确目标："
            "第 1 套“稳妥”，最安全耐看；第 2 套“进阶”，在配色或材质上更有造型感；"
            "第 3 套“突破”，在轮廓、颜色或风格方向上明显更大胆但仍适合场景。"
            "三套之间至少在下装、鞋或整体方向上有一处清晰差异，不得只微调配饰。"
            "必须包含用户原单品，不得更换它；"
            "兼容度分数要保守且能反映场景、色彩、廓形和材质协调度。"
            "若有环境与活动信息，按高温、降雨、寒冷等条件调整面料、鞋子和外套。"
            "若用户选择骑行，避免妨碍车轮或行动的长外套、过宽裤脚和不防滑鞋；"
            "若用户选择开车，优先考虑坐姿舒适和上下车便利。"
            "用户硬性约束是硬性要求：禁用单品不得以任何形式出现在任何一套中。"
        )
        if self.text_api == "chat_completions":
            response = self.client.chat.completions.parse(
                model=self.text_model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=OutfitPlan,
            )
            parsed = response.choices[0].message.parsed if response.choices else None
            if not parsed:
                raise RuntimeError("搭配规划没有返回结构化结果")
            return parsed

        response = self.client.responses.parse(
            model=self.text_model,
            instructions=instructions,
            input=user_prompt,
            text_format=OutfitPlan,
        )
        if not response.output_parsed:
            raise RuntimeError("搭配规划没有返回结构化结果")
        return response.output_parsed

    def regenerate_outfit(
        self,
        garment: GarmentAnalysis,
        occasion: str,
        preferred_style: str,
        *,
        avoid: list[str],
        conditions: str = "",
        preferences: str = "",
    ) -> Outfit:
        """Regenerate exactly one look, clearly different from `avoid` entries."""

        avoid_lines = "\n".join(f"- {index}: {text}" for index, text in enumerate(avoid, start=1))
        user_prompt = (
            f"用户单品：{garment.model_dump_json(ensure_ascii=False)}\n"
            f"场景：{occasion}\n偏好风格：{preferred_style}\n"
            f"现有搭配（新搭配必须与每一套都明显不同）：\n{avoid_lines}\n"
            "只输出一套新搭配，字段与之前相同：上装、外套、下装、鞋、包、配饰、"
            "中文理由、0-100 兼容度、英文 image_prompt。"
        )
        if conditions:
            user_prompt += f"\n环境与活动：{conditions}"
        if preferences:
            user_prompt += f"\n用户硬性约束（必须逐条遵守）：{preferences}"
        instructions = (
            "你是专业造型师。针对被替换的位置生成恰好一套新搭配："
            "必须包含用户原单品且不得更换它；与列出的每一套现有搭配相比，"
            "至少在下装、鞋或整体风格方向上有一处清晰差异，不得只换配饰。"
            "兼容度分数保守且可解释。"
            "骑行时避免妨碍行动的长外套、过宽裤脚和不防滑鞋；"
            "开车时优先考虑坐姿舒适和上下车便利。"
            "用户硬性约束是硬性要求：禁用单品不得以任何形式出现。"
        )
        if self.text_api == "chat_completions":
            response = self.client.chat.completions.parse(
                model=self.text_model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=Outfit,
            )
            parsed = response.choices[0].message.parsed if response.choices else None
            if not parsed:
                raise RuntimeError("单套替换没有返回结构化结果")
            return parsed

        response = self.client.responses.parse(
            model=self.text_model,
            instructions=instructions,
            input=user_prompt,
            text_format=Outfit,
        )
        if not response.output_parsed:
            raise RuntimeError("单套替换没有返回结构化结果")
        return response.output_parsed

    def generate_outfit_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        garment: GarmentAnalysis,
        outfit: Outfit,
        *,
        task_state: dict | None = None,
        on_progress: Callable | None = None,
    ) -> bytes:
        extension = mime_type.split("/")[-1].replace("jpeg", "jpg")
        image_file = io.BytesIO(image_bytes)
        image_file.name = f"garment.{extension}"
        # Same structured fields the results page renders, so the image
        # cannot drift from the text plan.
        prompt = build_image_prompt(garment, outfit)
        if self.rightapi_images is not None:
            if task_state is not None:
                return self.rightapi_images.generate(image_bytes, mime_type, prompt,
                                                     task_state=task_state, on_progress=on_progress)
            return self.rightapi_images.generate(image_bytes, mime_type, prompt)

        result = self.image_client.images.edit(
            model=self.image_model,
            image=image_file,
            prompt=prompt,
            size="1024x1024",
            quality="medium",
        )
        if not result.data or not result.data[0].b64_json:
            raise RuntimeError("图像模型没有返回可用图片")
        return ensure_image_bytes(base64.b64decode(result.data[0].b64_json))
