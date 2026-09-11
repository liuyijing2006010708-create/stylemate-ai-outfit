from stylemate.demo import demo_payload
from stylemate.ranking import rank_outfits


def test_demo_payload_is_complete() -> None:
    garment, plan = demo_payload()
    assert garment.display_name == "黑色短款皮夹克"
    assert len(plan.outfits) == 3
    assert all(outfit.outerwear for outfit in plan.outfits)
    assert all(0 <= outfit.compatibility_score <= 100 for outfit in plan.outfits)


def test_ranker_boosts_exact_preference_without_mutating_source() -> None:
    _, plan = demo_payload()
    original = plan.outfits[0].compatibility_score
    ranked = rank_outfits(plan.outfits, "韩系简约")
    matching = next(item for item in ranked if item.style == "韩系简约")
    assert matching.compatibility_score == min(99, original + 3)
    assert plan.outfits[0].compatibility_score == original

