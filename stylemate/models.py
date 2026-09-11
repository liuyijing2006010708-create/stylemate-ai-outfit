from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GarmentAnalysis(BaseModel):
    category: str = Field(description="服装大类，例如外套、衬衫")
    subcategory: str = Field(description="具体品类，例如短款皮夹克")
    color: str
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
        return f"{self.color}{self.subcategory}"

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
        return [
            self.top,
            self.bottom,
            self.shoes,
            self.bag,
            *self.accessories,
        ]


class OutfitPlan(BaseModel):
    outfits: list[Outfit] = Field(min_length=3, max_length=3)

