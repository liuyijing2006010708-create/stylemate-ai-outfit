"""Secure, deterministic Polyvore-to-StyleGen dataset preparation.

The module intentionally depends only on Pillow and the standard library so the
data pipeline can be validated locally before renting a GPU.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image, ImageOps, UnidentifiedImageError


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
MAX_IMAGE_PIXELS = 40_000_000
DEFAULT_CAPTION = "Create a coordinated flat-lay outfit containing the reference item."
NON_APPAREL_WORDS = {
    "bag",
    "belt",
    "boot",
    "bracelet",
    "earring",
    "glasses",
    "handbag",
    "hat",
    "jewelry",
    "necklace",
    "purse",
    "ring",
    "shoe",
    "sneaker",
    "sunglasses",
    "watch",
}


@dataclass(frozen=True)
class ItemRecord:
    item_id: str
    index: str
    name: str
    category_id: str
    image_path: Path


@dataclass(frozen=True)
class OutfitRecord:
    outfit_id: str
    items: tuple[ItemRecord, ...]
    raw_record: dict[str, Any] = field(repr=False, compare=False)


@dataclass(frozen=True)
class LoadReport:
    total_outfits: int
    usable_outfits: int
    resolved_items: int
    missing_items: int
    issues: tuple[str, ...]


@dataclass(frozen=True)
class BuildReport:
    requested: int
    created: int
    skipped: int
    issues: tuple[str, ...]


@dataclass(frozen=True)
class DatasetValidation:
    valid: bool
    pair_count: int
    issues: tuple[str, ...]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_component(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip(".-")
    return cleaned[:120] or fallback


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Annotation file not found: {path}")
    if path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("Annotation JSON exceeds the 256 MB safety limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        for key in ("outfits", "data", "sets"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError("Annotation JSON must be a list of outfit objects")
    return value


def _url_stem(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    without_query = value.split("?", 1)[0].rstrip("/")
    stem = Path(without_query).stem
    return _safe_component(stem, "") or None


def _candidate_paths(images_root: Path, set_id: str, item: dict[str, Any]) -> list[Path]:
    index = _safe_component(item.get("index"), "")
    explicit_id = next(
        (
            _safe_component(item.get(key), "")
            for key in ("item_id", "image_id", "id")
            if item.get(key) is not None
        ),
        "",
    )
    image_stem = _url_stem(item.get("image") or item.get("image_url"))
    stems = [stem for stem in (explicit_id, index, image_stem) if stem]
    directories = [images_root, images_root / set_id]
    candidates: list[Path] = []
    for directory in directories:
        for stem in stems:
            stem_path = Path(stem)
            if stem_path.suffix.lower() in IMAGE_SUFFIXES:
                candidates.append(directory / stem_path.name)
            else:
                candidates.extend(directory / f"{stem}{suffix}" for suffix in IMAGE_SUFFIXES)
    return candidates


def _resolve_image(images_root: Path, set_id: str, item: dict[str, Any]) -> Path | None:
    root = images_root.resolve()
    for candidate in _candidate_paths(root, set_id, item):
        if _inside(candidate, root) and candidate.is_file():
            return candidate.resolve()
    return None


def load_polyvore_outfits(
    annotation_path: str | Path,
    images_root: str | Path,
    *,
    min_items: int = 2,
    max_items: int = 12,
) -> tuple[list[OutfitRecord], LoadReport]:
    """Load common Polyvore JSON variants and resolve local item images.

    Missing images are reported and omitted. An outfit is usable only when at
    least ``min_items`` images resolve locally.
    """

    if min_items < 1 or max_items < min_items:
        raise ValueError("Expected 1 <= min_items <= max_items")
    rows = _read_json_list(Path(annotation_path))
    root = Path(images_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Images directory not found: {root}")

    outfits: list[OutfitRecord] = []
    issues: list[str] = []
    resolved_items = 0
    missing_items = 0
    seen_outfit_ids: set[str] = set()
    for row_index, row in enumerate(rows):
        outfit_id = _safe_component(
            row.get("set_id") or row.get("outfit_id") or row.get("id"),
            f"outfit-{row_index:06d}",
        )
        if outfit_id in seen_outfit_ids:
            issues.append(f"Duplicate outfit id skipped: {outfit_id}")
            continue
        seen_outfit_ids.add(outfit_id)
        raw_items = row.get("items")
        if not isinstance(raw_items, list):
            issues.append(f"{outfit_id}: items is not a list")
            continue
        if len(raw_items) > max_items:
            issues.append(f"{outfit_id}: truncated from {len(raw_items)} to {max_items} items")
        items: list[ItemRecord] = []
        for item_index, item in enumerate(raw_items[:max_items], start=1):
            if not isinstance(item, dict):
                issues.append(f"{outfit_id}: item {item_index} is not an object")
                missing_items += 1
                continue
            index = _safe_component(item.get("index"), str(item_index))
            explicit_id = item.get("item_id") or item.get("image_id") or item.get("id")
            item_id = _safe_component(explicit_id, f"{outfit_id}-{index}")
            image_path = _resolve_image(root, outfit_id, item)
            if image_path is None:
                missing_items += 1
                issues.append(f"{outfit_id}/{item_id}: image not found")
                continue
            resolved_items += 1
            items.append(
                ItemRecord(
                    item_id=item_id,
                    index=index,
                    name=str(item.get("name") or item.get("title") or "unknown item"),
                    category_id=str(item.get("categoryid") or item.get("category_id") or ""),
                    image_path=image_path,
                )
            )
        if len(items) >= min_items:
            outfits.append(OutfitRecord(outfit_id, tuple(items), row))
        else:
            issues.append(f"{outfit_id}: only {len(items)} usable item(s), skipped")

    return outfits, LoadReport(
        total_outfits=len(rows),
        usable_outfits=len(outfits),
        resolved_items=resolved_items,
        missing_items=missing_items,
        issues=tuple(issues),
    )


def split_records(
    records: Sequence[OutfitRecord],
    *,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    seed: int = 42,
) -> dict[str, list[OutfitRecord]]:
    """Return a deterministic, mutually exclusive train/val/test split."""

    if not (0 < train_ratio < 1 and 0 <= val_ratio < 1):
        raise ValueError("train_ratio must be in (0, 1); val_ratio must be in [0, 1)")
    if train_ratio + val_ratio >= 1:
        raise ValueError("train_ratio + val_ratio must be less than 1")
    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    count = len(shuffled)
    train_end = round(count * train_ratio)
    val_end = train_end + round(count * val_ratio)
    return {
        "train": shuffled[:train_end],
        "val": shuffled[train_end:val_end],
        "test": shuffled[val_end:],
    }


def write_split_annotations(splits: dict[str, Sequence[OutfitRecord]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, rows in splits.items():
        output = output_dir / f"{_safe_component(split_name, 'split')}.json"
        output.write_text(
            json.dumps([row.raw_record for row in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _open_rgb(path: Path) -> Image.Image:
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                source.verify()
            with Image.open(path) as source:
                return ImageOps.exif_transpose(source).convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError(f"Image exceeds safety limit: {path}") from exc
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Invalid image: {path}") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


def _contain_on_white(image: Image.Image, size: tuple[int, int], padding: int = 16) -> Image.Image:
    width = max(1, size[0] - 2 * padding)
    height = max(1, size[1] - 2 * padding)
    fitted = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "white")
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def compose_flat_lay(items: Sequence[ItemRecord], *, size: int = 512) -> Image.Image:
    if not items:
        raise ValueError("At least one item is required")
    if size < 128 or size > 4096:
        raise ValueError("size must be between 128 and 4096 pixels")
    columns = max(1, math.ceil(math.sqrt(len(items))))
    rows = math.ceil(len(items) / columns)
    outer = max(12, size // 28)
    gap = max(8, size // 48)
    cell_width = (size - 2 * outer - gap * (columns - 1)) // columns
    cell_height = (size - 2 * outer - gap * (rows - 1)) // rows
    canvas = Image.new("RGB", (size, size), "white")
    for position, item in enumerate(items):
        image = _open_rgb(item.image_path)
        tile = _contain_on_white(image, (cell_width, cell_height), padding=max(6, size // 64))
        row, column = divmod(position, columns)
        x = outer + column * (cell_width + gap)
        y = outer + row * (cell_height + gap)
        canvas.paste(tile, (x, y))
    return canvas


def _reference_item(outfit: OutfitRecord, policy: str, seed: int) -> ItemRecord:
    if policy not in {"apparel", "first", "random"}:
        raise ValueError("reference_policy must be apparel, first, or random")
    if policy == "first":
        return outfit.items[0]
    candidates = list(outfit.items)
    if policy == "apparel":
        apparel = [
            item
            for item in candidates
            if not (set(re.findall(r"[a-z]+", item.name.lower())) & NON_APPAREL_WORDS)
        ]
        candidates = apparel or candidates
    digest = hashlib.sha256(f"{seed}:{outfit.outfit_id}".encode()).digest()
    return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]


def build_pair_dataset(
    outfits: Sequence[OutfitRecord],
    output_dir: str | Path,
    *,
    size: int = 512,
    seed: int = 42,
    caption: str = DEFAULT_CAPTION,
    reference_policy: str = "apparel",
    overwrite: bool = False,
) -> BuildReport:
    """Write aligned reference, target, caption and metadata files."""

    if not caption.strip():
        raise ValueError("caption cannot be empty")
    root = Path(output_dir).resolve()
    directories = {name: root / name for name in ("reference", "target", "metadata")}
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)

    issues: list[str] = []
    created = 0
    seen_ids: set[str] = set()
    for outfit in outfits:
        pair_id = _safe_component(outfit.outfit_id, "pair")
        if pair_id in seen_ids:
            issues.append(f"{pair_id}: duplicate pair id skipped")
            continue
        seen_ids.add(pair_id)
        destinations = {
            "reference": directories["reference"] / f"{pair_id}.jpg",
            "target": directories["target"] / f"{pair_id}.jpg",
            "caption": directories["target"] / f"{pair_id}.txt",
            "metadata": directories["metadata"] / f"{pair_id}.json",
        }
        temporary = {name: path.with_name(f".{path.name}.tmp") for name, path in destinations.items()}
        if not overwrite and any(path.exists() for path in destinations.values()):
            issues.append(f"{pair_id}: output already exists; use overwrite to replace it")
            continue
        try:
            reference = _reference_item(outfit, reference_policy, seed)
            reference_image = _contain_on_white(_open_rgb(reference.image_path), (size, size), size // 12)
            target_image = compose_flat_lay(outfit.items, size=size)
            reference_image.save(temporary["reference"], "JPEG", quality=95)
            target_image.save(temporary["target"], "JPEG", quality=95)
            temporary["caption"].write_text(caption.strip() + "\n", encoding="utf-8")
            temporary["metadata"].write_text(
                json.dumps(
                    {
                        "pair_id": pair_id,
                        "outfit_id": outfit.outfit_id,
                        "reference_item_id": reference.item_id,
                        "target_item_ids": [item.item_id for item in outfit.items],
                        "size": [size, size],
                        "caption": caption.strip(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            for name in ("reference", "target", "caption", "metadata"):
                temporary[name].replace(destinations[name])
            created += 1
        except (OSError, ValueError) as exc:
            for path in temporary.values():
                if path.exists():
                    path.unlink()
            issues.append(f"{pair_id}: {exc}")
    return BuildReport(len(outfits), created, len(outfits) - created, tuple(issues))


def _stems(directory: Path, suffixes: Iterable[str]) -> set[str]:
    allowed = {suffix.lower() for suffix in suffixes}
    if not directory.is_dir():
        return set()
    return {path.stem for path in directory.iterdir() if path.is_file() and path.suffix.lower() in allowed}


def validate_processed_split(
    split_dir: str | Path,
    *,
    expected_size: int | None = None,
) -> DatasetValidation:
    root = Path(split_dir).resolve()
    reference_dir = root / "reference"
    target_dir = root / "target"
    metadata_dir = root / "metadata"
    issues: list[str] = []
    reference_ids = _stems(reference_dir, IMAGE_SUFFIXES)
    target_ids = _stems(target_dir, IMAGE_SUFFIXES)
    caption_ids = _stems(target_dir, (".txt",))
    metadata_ids = _stems(metadata_dir, (".json",))
    all_ids = reference_ids | target_ids | caption_ids | metadata_ids

    if not all_ids:
        issues.append(f"No pairs found in {root}")

    for label, values in (
        ("reference image", reference_ids),
        ("target image", target_ids),
        ("caption", caption_ids),
        ("metadata", metadata_ids),
    ):
        missing = sorted(all_ids - values)
        if missing:
            issues.append(f"Missing {label} for: {', '.join(missing[:10])}")

    for pair_id in sorted(reference_ids & target_ids & caption_ids & metadata_ids):
        for label, directory in (("reference", reference_dir), ("target", target_dir)):
            matches = [directory / f"{pair_id}{suffix}" for suffix in IMAGE_SUFFIXES]
            path = next((candidate for candidate in matches if candidate.is_file()), None)
            if path is None:
                continue
            try:
                image = _open_rgb(path)
                if expected_size is not None and image.size != (expected_size, expected_size):
                    issues.append(f"{pair_id}: {label} size is {image.size}, expected {expected_size}x{expected_size}")
            except ValueError as exc:
                issues.append(f"{pair_id}: {exc}")
        caption = (target_dir / f"{pair_id}.txt").read_text(encoding="utf-8").strip()
        if not caption:
            issues.append(f"{pair_id}: caption is empty")
        try:
            metadata = json.loads((metadata_dir / f"{pair_id}.json").read_text(encoding="utf-8"))
            if metadata.get("pair_id") != pair_id:
                issues.append(f"{pair_id}: metadata pair_id does not match filename")
            if metadata.get("reference_item_id") not in metadata.get("target_item_ids", []):
                issues.append(f"{pair_id}: target does not declare the reference item")
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            issues.append(f"{pair_id}: invalid metadata ({exc})")

    return DatasetValidation(not issues and bool(all_ids), len(all_ids), tuple(issues))


def validate_split_disjointness(processed_root: str | Path, splits: Sequence[str]) -> tuple[str, ...]:
    """Report pair or source-item identifiers occurring in multiple splits."""

    root = Path(processed_root).resolve()
    split_ids: dict[str, set[str]] = {}
    split_item_ids: dict[str, set[str]] = {}
    for split in splits:
        metadata_dir = root / _safe_component(split, "split") / "metadata"
        split_ids[split] = _stems(metadata_dir, (".json",))
        item_ids: set[str] = set()
        for metadata_path in metadata_dir.glob("*.json") if metadata_dir.is_dir() else ():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                values = metadata.get("target_item_ids", [])
                if isinstance(values, list):
                    item_ids.update(str(value) for value in values)
            except (OSError, json.JSONDecodeError, AttributeError):
                continue
        split_item_ids[split] = item_ids
    issues: list[str] = []
    names = list(split_ids)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap = sorted(split_ids[left] & split_ids[right])
            if overlap:
                issues.append(
                    f"Cross-split duplicate in {left}/{right}: {', '.join(overlap[:10])}"
                )
            item_overlap = sorted(split_item_ids[left] & split_item_ids[right])
            if item_overlap:
                issues.append(
                    f"Cross-split source item in {left}/{right}: {', '.join(item_overlap[:10])}"
                )
    return tuple(issues)


def make_qa_sheets(
    split_dir: str | Path,
    output_dir: str | Path,
    *,
    sample_size: int = 50,
    seed: int = 42,
    rows_per_sheet: int = 5,
) -> list[Path]:
    """Create side-by-side reference/target contact sheets for manual review."""

    root = Path(split_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    ids = sorted(_stems(root / "reference", IMAGE_SUFFIXES) & _stems(root / "target", IMAGE_SUFFIXES))
    random.Random(seed).shuffle(ids)
    ids = ids[: max(0, sample_size)]
    paths: list[Path] = []
    thumb = 220
    label_band = 28
    for sheet_index in range(0, len(ids), rows_per_sheet):
        batch = ids[sheet_index : sheet_index + rows_per_sheet]
        canvas = Image.new("RGB", (thumb * 2, (thumb + label_band) * len(batch)), "white")
        for row, pair_id in enumerate(batch):
            for column, folder in enumerate(("reference", "target")):
                candidates = [root / folder / f"{pair_id}{suffix}" for suffix in IMAGE_SUFFIXES]
                path = next(candidate for candidate in candidates if candidate.is_file())
                tile = _contain_on_white(_open_rgb(path), (thumb, thumb), 6)
                canvas.paste(tile, (column * thumb, row * (thumb + label_band)))
        destination = output / f"qa-sheet-{len(paths) + 1:03d}.jpg"
        canvas.save(destination, "JPEG", quality=92)
        paths.append(destination)
    return paths
