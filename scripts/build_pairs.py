#!/usr/bin/env python3
"""Build StyleGen reference-to-flat-lay pairs from a Polyvore split."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stylegen.dataset import DEFAULT_CAPTION, build_pair_dataset, load_polyvore_outfits


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--split", choices=("train", "val", "test"), required=True)
    parser.add_argument("--limit", type=int, help="Maximum pairs to build")
    parser.add_argument("--size", type=int, choices=(512, 1024), default=512)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--caption", default=DEFAULT_CAPTION)
    parser.add_argument("--reference-policy", choices=("apparel", "first", "random"), default="apparel")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outfits, load_report = load_polyvore_outfits(args.annotations, args.images_root)
    if args.limit is not None:
        if args.limit < 1:
            print("--limit must be positive", file=sys.stderr)
            return 2
        outfits = outfits[: args.limit]
    report = build_pair_dataset(
        outfits,
        args.output_root / args.split,
        size=args.size,
        seed=args.seed,
        caption=args.caption,
        reference_policy=args.reference_policy,
        overwrite=args.overwrite,
    )
    print(
        f"split={args.split} requested={report.requested} created={report.created} "
        f"skipped={report.skipped} source_issues={len(load_report.issues)}"
    )
    for issue in report.issues[:20]:
        print(f"  - {issue}", file=sys.stderr)
    return 0 if report.created else 1


if __name__ == "__main__":
    raise SystemExit(main())
