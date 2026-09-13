import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

from stylegen.dataset import (
    build_pair_dataset,
    load_polyvore_outfits,
    split_records,
    validate_split_disjointness,
    validate_processed_split,
)


def _image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 120), color).save(path)


def _polyvore_fixture(tmp_path: Path) -> tuple[Path, Path]:
    images = tmp_path / "images"
    annotations = tmp_path / "outfits.json"
    records = []
    for outfit_index in range(10):
        set_id = f"look-{outfit_index:02d}"
        items = []
        for item_index, name in enumerate(("shirt", "trousers", "shoes"), start=1):
            _image(
                images / set_id / f"{item_index}.jpg",
                (40 * item_index, 20 * outfit_index, 120),
            )
            items.append(
                {
                    "index": item_index,
                    "name": name,
                    "categoryid": str(10 + item_index),
                }
            )
        records.append({"set_id": set_id, "items": items})
    annotations.write_text(json.dumps(records), encoding="utf-8")
    return annotations, images


def test_loads_nested_polyvore_images(tmp_path: Path) -> None:
    annotations, images = _polyvore_fixture(tmp_path)

    outfits, report = load_polyvore_outfits(annotations, images)

    assert report.total_outfits == 10
    assert report.resolved_items == 30
    assert report.missing_items == 0
    assert outfits[0].items[0].item_id == "look-00-1"
    assert outfits[0].items[0].image_path == images / "look-00" / "1.jpg"


def test_split_is_deterministic_and_disjoint(tmp_path: Path) -> None:
    annotations, images = _polyvore_fixture(tmp_path)
    outfits, _ = load_polyvore_outfits(annotations, images)

    first = split_records(outfits, train_ratio=0.8, val_ratio=0.1, seed=42)
    second = split_records(outfits, train_ratio=0.8, val_ratio=0.1, seed=42)

    assert {name: [item.outfit_id for item in rows] for name, rows in first.items()} == {
        name: [item.outfit_id for item in rows] for name, rows in second.items()
    }
    assert {name: len(rows) for name, rows in first.items()} == {
        "train": 8,
        "val": 1,
        "test": 1,
    }
    ids = [{item.outfit_id for item in rows} for rows in first.values()]
    assert not (ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2])


def test_build_and_validate_pair_dataset(tmp_path: Path) -> None:
    annotations, images = _polyvore_fixture(tmp_path)
    outfits, _ = load_polyvore_outfits(annotations, images)
    destination = tmp_path / "processed" / "train"

    result = build_pair_dataset(
        outfits[:3],
        destination,
        size=512,
        seed=7,
        caption="Create a coordinated flat-lay outfit containing the reference item.",
    )
    validation = validate_processed_split(destination, expected_size=512)

    assert result.created == 3
    assert validation.valid
    assert validation.pair_count == 3
    with Image.open(destination / "reference" / "look-00.jpg") as image:
        assert image.size == (512, 512)
    metadata = json.loads(
        (destination / "metadata" / "look-00.json").read_text(encoding="utf-8")
    )
    assert metadata["reference_item_id"] in metadata["target_item_ids"]


def test_validator_detects_broken_one_to_one_alignment(tmp_path: Path) -> None:
    annotations, images = _polyvore_fixture(tmp_path)
    outfits, _ = load_polyvore_outfits(annotations, images)
    destination = tmp_path / "processed" / "train"
    build_pair_dataset(outfits[:1], destination, size=512, seed=7)
    (destination / "target" / "look-00.txt").unlink()

    validation = validate_processed_split(destination, expected_size=512)

    assert not validation.valid
    assert any("caption" in issue for issue in validation.issues)


def test_validator_rejects_empty_and_cross_split_duplicates(tmp_path: Path) -> None:
    empty = validate_processed_split(tmp_path / "empty", expected_size=512)
    assert not empty.valid
    assert any("No pairs" in issue for issue in empty.issues)

    annotations, images = _polyvore_fixture(tmp_path)
    outfits, _ = load_polyvore_outfits(annotations, images)
    processed = tmp_path / "processed"
    build_pair_dataset(outfits[:2], processed / "train")
    build_pair_dataset(outfits[1:3], processed / "val")

    issues = validate_split_disjointness(processed, ("train", "val"))

    assert any("look-01" in issue for issue in issues)


def test_command_line_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    annotations, images = _polyvore_fixture(tmp_path)
    project_root = Path(__file__).resolve().parents[1]
    splits = tmp_path / "splits"
    processed = tmp_path / "processed"
    qa = tmp_path / "qa"
    archive = tmp_path / "stylegen.zip"

    subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts/split_dataset.py"),
            "--annotations",
            str(annotations),
            "--images-root",
            str(images),
            "--output-dir",
            str(splits),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for split in ("train", "val", "test"):
        subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts/build_pairs.py"),
                "--annotations",
                str(splits / f"{split}.json"),
                "--images-root",
                str(images),
                "--output-root",
                str(processed),
                "--split",
                split,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts/check_dataset.py"),
            "--root",
            str(processed),
            "--sample",
            "2",
            "--qa-dir",
            str(qa),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts/package_dataset.py"),
            "--root",
            str(processed),
            "--output",
            str(archive),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert archive.is_file()
    assert list((qa / "train").glob("qa-sheet-*.jpg"))
