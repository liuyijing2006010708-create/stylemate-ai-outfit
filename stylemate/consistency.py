"""One source of truth for outfit data.

The page list, the flat-lay prompt and the completeness check all read the
same structured Outfit fields. Generated pixels still require visual review.
"""

from __future__ import annotations

from .models import GarmentAnalysis, Outfit, OutfitPlan

REQUIRED_FIELDS = (("top", "上装"), ("bottom", "下装"), ("shoes", "鞋子"), ("reason", "搭配理由"))
DIVERSITY_FIELDS = ("top", "outerwear", "bottom", "shoes", "bag")
DIVERSITY_THRESHOLD = 2


class PlanRejected(RuntimeError):
    """Only carries locally composed messages: field labels and user input."""


def outfit_issues(outfit: Outfit, index: int) -> list[str]:
    return [
        f"LOOK {index:02d} 缺少{label}"
        for field, label in REQUIRED_FIELDS
        if not (getattr(outfit, field) or "").strip()
    ]


def plan_issues(plan: OutfitPlan) -> list[str]:
    """Field-level validation of a freshly generated plan; empty list is clean."""

    issues: list[str] = []
    ids = [outfit.id.strip() for outfit in plan.outfits]
    if not all(ids) or len(set(ids)) != len(ids):
        issues.append("搭配编号为空或重复，请重新生成")
    for index, outfit in enumerate(plan.outfits, start=1):
        issues.extend(outfit_issues(outfit, index))
    return issues


def _diversity_value(outfit: Outfit, field: str, original: str) -> str:
    """空值、“无”和必须保留的原单品都不作为重复判断依据。"""

    text = (getattr(outfit, field) or "").strip()
    if not text or text == "无":
        return ""
    if original and original in text:
        return ""
    return text.lower()


def diversity_pair_issues(
    first: Outfit, second: Outfit, first_index: int, second_index: int,
    garment: GarmentAnalysis | None = None,
) -> list[str]:
    original = (garment.display_name or "").strip() if garment else ""
    shared = sum(
        1 for field in DIVERSITY_FIELDS
        if _diversity_value(first, field, original)
        and _diversity_value(first, field, original) == _diversity_value(second, field, original)
    )
    if shared >= DIVERSITY_THRESHOLD:
        return [f"LOOK {first_index:02d} 与 LOOK {second_index:02d} 过于相似，差异度不足"]
    return []


def diversity_issues(
    plan: OutfitPlan, garment: GarmentAnalysis | None = None,
) -> list[str]:
    issues: list[str] = []
    for first in range(len(plan.outfits)):
        for second in range(first + 1, len(plan.outfits)):
            issues.extend(diversity_pair_issues(
                plan.outfits[first], plan.outfits[second], first + 1, second + 1, garment,
            ))
    return issues


def preference_issues(plan: OutfitPlan, banned_terms: list[str]) -> list[str]:
    """Hard constraints such as 禁用高跟鞋 must survive every look."""

    terms = [term.strip() for term in banned_terms if term.strip()]
    if not terms:
        return []
    issues: list[str] = []
    for index, outfit in enumerate(plan.outfits, start=1):
        text = " ".join(
            [outfit.top, outfit.outerwear, outfit.bottom, outfit.shoes, outfit.bag,
             *outfit.accessories]
        )
        for term in terms:
            if term in text:
                issues.append(f"LOOK {index:02d} 包含禁用单品「{term}」")
    return issues


def build_image_prompt(garment: GarmentAnalysis, outfit: Outfit) -> str:
    """Compose the flat-lay prompt from the same fields the page displays."""

    look: list[str] = []
    for label, value in (
        ("top", outfit.top),
        ("outer layer", outfit.outerwear),
        ("bottoms", outfit.bottom),
        ("footwear", outfit.shoes),
        ("bag", outfit.bag),
    ):
        if (value or "").strip() and value.strip() != "无":
            look.append(f"- {label}: {value.strip()}")
    if outfit.accessories:
        look.append("- accessories: " + "、".join(piece.strip() for piece in outfit.accessories))
    if not look:
        raise ValueError("搭配缺少任何单品描述，无法生成效果图。")
    return f"""
Create a premium, photorealistic, top-down fashion flat-lay on a true white studio background.

The uploaded image contains the user's real garment: {garment.display_name}.
Preserve that exact garment as faithfully as possible: its color, silhouette, material,
pattern, construction, and these identity details: {', '.join(garment.preservation_notes) or 'overall look'}.
Do not redesign or duplicate the uploaded garment.

The complete look must contain exactly these pieces (names are in Chinese; render each faithfully):
{chr(10).join(look)}

All pieces must be fully visible, realistically scaled, neatly separated, and arranged in
an editorial but practical composition. No person, mannequin, text, logo, or watermark.
""".strip()
