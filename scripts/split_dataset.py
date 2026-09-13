#!/usr/bin/env python3
"""Create deterministic train/val/test JSON files from one Polyvore collection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stylegen.dataset import load_polyvore_outfits, split_records, write_split_annotations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/splits"))
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outfits, report = load_polyvore_outfits(args.annotations, args.images_root)
    if not outfits:
        print("No usable outfits found; nothing was written.", file=sys.stderr)
        return 1
    splits = split_records(
        outfits,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )
    write_split_annotations(splits, args.output_dir)
    print(" ".join(f"{name}={len(rows)}" for name, rows in splits.items()))
    print(f"Excluded unresolved outfits/items: {len(report.issues)} issue(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
