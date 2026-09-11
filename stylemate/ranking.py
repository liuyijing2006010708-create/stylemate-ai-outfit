from __future__ import annotations

from .models import Outfit


def rank_outfits(outfits: list[Outfit], preferred_style: str) -> list[Outfit]:
    """Apply a transparent V1 preference adjustment and return best-first results.

    This is deliberately small and inspectable. It is the seam where a future
    FashionCLIP/Polyvore compatibility model can be plugged in.
    """
    ranked: list[Outfit] = []
    for outfit in outfits:
        score = outfit.compatibility_score
        if preferred_style.lower() in outfit.style.lower():
            score = min(99, score + 3)
        ranked.append(outfit.model_copy(update={"compatibility_score": score}))
    return sorted(ranked, key=lambda item: item.compatibility_score, reverse=True)

