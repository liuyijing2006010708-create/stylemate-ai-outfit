from stylemate.demo import demo_payload
from stylemate.models import GarmentAnalysis, Outfit
from stylemate.ranking import rank_outfits


def test_pieces_include_outerwear_and_skip_placeholders() -> None:
    outfit = Outfit(
        id="look-x", style="极简", top="白色 T 恤", outerwear="无", bottom="牛仔裤",
        shoes="帆布鞋", bag="帆布包", accessories=[], reason="干净",
        compatibility_score=85, image_prompt="minimal look",
    )
    assert outfit.pieces == ["白色 T 恤", "牛仔裤", "帆布鞋", "帆布包"]
    layered = outfit.model_copy(update={"outerwear": "黑色皮衣"})
    assert "黑色皮衣" in layered.pieces


def test_demo_payload_is_complete() -> None:
    garment, plan = demo_payload()
    assert garment.display_name == "黑色短款皮夹克"
    assert len(plan.outfits) == 3
    assert all(outfit.outerwear for outfit in plan.outfits)
    assert all(0 <= outfit.compatibility_score <= 100 for outfit in plan.outfits)


def test_garment_display_name_does_not_repeat_color() -> None:
    garment = GarmentAnalysis(
        category="上衣",
        subcategory="黑色细肩带吊带背心",
        color="黑色",
        material="弹力面料",
        pattern="纯色",
        fit="修身",
        seasons=["夏季"],
        styles=["Y2K"],
    )

    assert garment.display_name == "黑色细肩带吊带背心"


def test_garment_display_name_uses_primary_color_only() -> None:
    garment = GarmentAnalysis(
        category="上衣",
        subcategory="针织开衫",
        color="黑色，领口与门襟带灰色滚边",
        material="针织",
        pattern="纯色",
        fit="宽松",
        seasons=["秋季"],
        styles=["极简"],
    )

    assert garment.display_name == "黑色针织开衫"


def test_ranker_boosts_exact_preference_without_mutating_source() -> None:
    _, plan = demo_payload()
    original = plan.outfits[0].compatibility_score
    ranked = rank_outfits(plan.outfits, "韩系简约")
    matching = next(item for item in ranked if item.style == "韩系简约")
    assert matching.compatibility_score == min(99, original + 3)
    assert plan.outfits[0].compatibility_score == original
