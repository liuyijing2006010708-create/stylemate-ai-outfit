#!/usr/bin/env python3
"""Validate and zip processed StyleGen data, then print its SHA-256."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stylegen.dataset import validate_processed_split, validate_split_disjointness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/processed"))
    parser.add_argument("--output", type=Path, default=Path("outputs/stylegen-dataset.zip"))
    parser.add_argument("--splits", nargs="+", default=("train", "val", "test"))
    parser.add_argument("--size", type=int, choices=(512, 1024), default=512)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    for split in args.splits:
        result = validate_processed_split(root / split, expected_size=args.size)
        if not result.valid:
            print(f"Refusing to package invalid split {split}: {result.issues[:3]}", file=sys.stderr)
            return 1
    overlap_issues = validate_split_disjointness(root, args.splits)
    if overlap_issues:
        print(f"Refusing to package overlapping splits: {overlap_issues[:3]}", file=sys.stderr)
        return 1
    output = args.output.resolve()
    if root == output or root in output.parents:
        print("Archive output must be outside the processed dataset directory.", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for split in args.splits:
            for path in sorted((root / split).rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root))
    hasher = hashlib.sha256()
    with output.open("rb") as archive_file:
        while chunk := archive_file.read(1024 * 1024):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    print(f"archive={output}\nsha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
