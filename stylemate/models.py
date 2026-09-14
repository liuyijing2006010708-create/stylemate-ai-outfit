from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class GarmentAnalysis(BaseModel):
    category: str = Field(description="服装大类，例如外套、衬衫")
    subcategory: str = Field(description="只填写具体品类，不重复颜色，例如短款皮夹克")
    color: str = Field(description="主色；滚边、纽扣等辅色细节写入 preservation_notes")
    material: str
    pattern: str
    fit: str
    seasons: list[str] = Field(min_length=1, max_length=4)
    styles: list[str] = Field(min_length=1, max_length=5)
    preservation_notes: list[str] = Field(
        default_factory=list,
        description="生成效果图时必须保留的原单品视觉特征",
    )

    @property
    def display_name(self) -> str:
        subcategory = self.subcategory.strip()
        color = re.split(r"[，,；;]", self.color, maxsplit=1)[0].strip()
        if not color or subcategory.startswith(color):
            return subcategory
        return f"{color}{subcategory}"

    @property
    def tags(self) -> list[str]:
        values = [self.subcategory, self.color, self.fit, *self.seasons[:1]]
        return [value for value in values if value]


class Outfit(BaseModel):
    id: str
    style: str
    top: str
    outerwear: str
    bottom: str
    shoes: str
    bag: str
    accessories: list[str] = Field(default_factory=list, max_length=4)
    reason: str
    compatibility_score: int = Field(ge=0, le=100)
    image_prompt: str = Field(
        description="仅描述要补全的搭配元素、构图和风格，不重新设计用户单品"
    )

    @field_validator("compatibility_score", mode="before")
    @classmethod
    def normalize_score(cls, value: object) -> int:
        if isinstance(value, float) and 0 <= value <= 1:
            return round(value * 100)
        return int(value)

    @property
    def pieces(self) -> list[str]:
        # 完整单品清单：页面列表、历史与导出都来自这里，与生图提示词同源。
        values = [self.top, self.outerwear, self.bottom, self.shoes, self.bag,
                  *self.accessories]
        return [value for value in values if value.strip() and value.strip() != "无"]


class OutfitPlan(BaseModel):
    outfits: list[Outfit] = Field(min_length=3, max_length=3)
