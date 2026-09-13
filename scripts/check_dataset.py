#!/usr/bin/env python3
"""Validate processed StyleGen pairs and create manual-QA contact sheets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stylegen.dataset import make_qa_sheets, validate_processed_split, validate_split_disjointness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/processed"))
    parser.add_argument("--splits", nargs="+", default=("train", "val", "test"))
    parser.add_argument("--size", type=int, choices=(512, 1024), default=512)
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--qa-dir", type=Path, default=Path("outputs/dataset-qa"))
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failed = False
    for split in args.splits:
        split_dir = args.root / split
        result = validate_processed_split(split_dir, expected_size=args.size)
        state = "OK" if result.valid else "FAILED"
        print(f"{split}: {state}, pairs={result.pair_count}, issues={len(result.issues)}")
        for issue in result.issues[:50]:
            print(f"  - {issue}", file=sys.stderr)
        if result.valid and args.sample > 0:
            sheets = make_qa_sheets(
                split_dir,
                args.qa_dir / split,
                sample_size=args.sample,
                seed=args.seed,
            )
            print(f"  QA sheets: {len(sheets)} in {args.qa_dir / split}")
        failed = failed or not result.valid
    overlap_issues = validate_split_disjointness(args.root, args.splits)
    for issue in overlap_issues:
        print(f"  - {issue}", file=sys.stderr)
    failed = failed or bool(overlap_issues)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
