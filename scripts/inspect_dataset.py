#!/usr/bin/env python3
"""Inspect Polyvore annotations, resolved images and a few outfit previews."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stylegen.dataset import compose_flat_lay, load_polyvore_outfits


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--show", type=int, default=5, help="Number of outfits to print")
    parser.add_argument("--preview-dir", type=Path, help="Optional directory for flat-lay previews")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outfits, report = load_polyvore_outfits(args.annotations, args.images_root)
    print(
        f"outfits={report.total_outfits} usable={report.usable_outfits} "
        f"resolved_items={report.resolved_items} missing_items={report.missing_items}"
    )
    for outfit in outfits[: max(0, args.show)]:
        print(f"\n[{outfit.outfit_id}] {len(outfit.items)} items")
        for item in outfit.items:
            print(f"  - {item.item_id} | {item.name} | category={item.category_id} | {item.image_path}")
        if args.preview_dir:
            args.preview_dir.mkdir(parents=True, exist_ok=True)
            compose_flat_lay(outfit.items, size=512).save(args.preview_dir / f"{outfit.outfit_id}.jpg")
    if report.issues:
        print(f"\nIssues ({len(report.issues)} total; first 20 shown):", file=sys.stderr)
        for issue in report.issues[:20]:
            print(f"  - {issue}", file=sys.stderr)
    return 0 if outfits else 1


if __name__ == "__main__":
    raise SystemExit(main())
