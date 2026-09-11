from __future__ import annotations

from pathlib import Path

from .models import GarmentAnalysis, Outfit, OutfitPlan


ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"

DEMO_GARMENT = GarmentAnalysis(
    category="外套",
    subcategory="短款皮夹克",
    color="黑色",
    material="皮革",
    pattern="纯色",
    fit="宽松",
    seasons=["秋冬", "早春"],
    styles=["韩系简约", "City Boy", "美式复古"],
    preservation_notes=["短款比例", "银色中轴拉链", "利落翻领", "细腻黑色皮纹"],
)

DEMO_PLAN = OutfitPlan(
    outfits=[
        Outfit(
            id="look-01",
            style="韩系简约",
            top="白色修身圆领 T",
            outerwear="用户的黑色短款皮夹克",
            bottom="深灰阔腿西裤",
            shoes="白色德训鞋",
            bag="黑色单肩包",
            accessories=["细银色项链"],
            reason="干净的黑白灰配色让皮衣成为视觉重心；阔腿裤平衡短款上装的量感，银饰呼应拉链，通勤利落但不过分正式。",
            compatibility_score=92,
            image_prompt="Korean minimalist office flat lay with white tee, charcoal wide-leg trousers, white trainers, black shoulder bag and a silver necklace.",
        ),
        Outfit(
            id="look-02",
            style="City Boy",
            top="浅灰重磅连帽卫衣",
            outerwear="用户的黑色短款皮夹克",
            bottom="水洗黑直筒牛仔裤",
            shoes="灰色复古跑鞋",
            bag="黑色斜挎包",
            accessories=["棒球帽"],
            reason="卫衣叠穿拉出层次，水洗牛仔裤延续低饱和色调；跑鞋与斜挎包降低皮衣的硬朗感，更适合轻松通勤。",
            compatibility_score=88,
            image_prompt="Relaxed City Boy flat lay with gray hoodie, washed-black jeans, retro runners, sling bag and baseball cap.",
        ),
        Outfit(
            id="look-03",
            style="美式复古",
            top="棕白格纹法兰绒衬衫",
            outerwear="用户的黑色短款皮夹克",
            bottom="烟草棕工装裤",
            shoes="深棕工装靴",
            bag="深棕皮质托特包",
            accessories=["复古银色腕表"],
            reason="棕色系棉布与黑色皮革形成材质对比，格纹补充复古叙事；工装靴稳住下装比例，让整体粗犷但有秩序。",
            compatibility_score=84,
            image_prompt="American vintage flat lay with brown plaid flannel, tobacco carpenter pants, work boots, leather tote and vintage watch.",
        ),
    ]
)

DEMO_IMAGES = {
    "look-01": ASSET_DIR / "demo-look-01.png",
    "look-02": ASSET_DIR / "demo-look-02.png",
    "look-03": ASSET_DIR / "demo-look-03.png",
}
DEMO_GARMENT_IMAGE = ASSET_DIR / "demo-garment.png"


def demo_payload() -> tuple[GarmentAnalysis, OutfitPlan]:
    """Return isolated validated demo data for a no-key product tour."""
    return DEMO_GARMENT.model_copy(deep=True), DEMO_PLAN.model_copy(deep=True)

