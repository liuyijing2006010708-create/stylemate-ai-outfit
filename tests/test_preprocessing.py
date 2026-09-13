import io
import sys
import types

import numpy as np
import pytest
from PIL import Image

from stylemate.preprocessing import (
    adjust,
    background_removal_available,
    quality_notes,
)


def jpeg_bytes(size=(40, 20), color=(200, 120, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def noise_jpeg(size=(1200, 900)) -> bytes:
    rng = np.random.default_rng(7)
    array = rng.integers(0, 255, size=(size[1], size[0], 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="JPEG", quality=98)
    return buffer.getvalue()


def dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def test_adjust_rotates_clockwise():
    assert dimensions(adjust(jpeg_bytes(), rotation=90)) == (20, 40)
    assert dimensions(adjust(jpeg_bytes(), rotation=360)) == (40, 20)


def test_adjust_crops_by_percentage_edges():
    cropped = adjust(jpeg_bytes(size=(200, 100)), crop=(25, 50, 75, 100))
    assert dimensions(cropped) == (100, 50)


def test_adjust_without_background_removal_still_normalizes():
    out = adjust(jpeg_bytes(), remove_background=True)
    with Image.open(io.BytesIO(out)) as image:
        assert image.format == "JPEG" and image.mode == "RGB"


def test_adjust_with_fake_rembg_flattens_onto_white(monkeypatch):
    fake = types.ModuleType("rembg")

    def remove(data: bytes) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGBA", (40, 20), (255, 0, 0, 0)).save(buffer, format="PNG")
        return buffer.getvalue()

    fake.remove = remove
    monkeypatch.setitem(sys.modules, "rembg", fake)
    out = adjust(jpeg_bytes(), remove_background=True)
    with Image.open(io.BytesIO(out)) as image:
        assert image.getpixel((0, 0)) == (255, 255, 255)


def test_background_removal_unavailable_reports_cleanly(monkeypatch):
    monkeypatch.setitem(sys.modules, "rembg", None)  # import will fail
    assert background_removal_available() is False


def test_quality_notes_flag_small_and_blurry_photos():
    small = quality_notes(jpeg_bytes(size=(100, 60)))
    assert any("分辨率" in note for note in small)
    blurry = quality_notes(jpeg_bytes(size=(1200, 900), color=(128, 128, 128)))
    assert any("模糊" in note for note in blurry)


def test_quality_notes_pass_a_detailed_photo():
    assert quality_notes(noise_jpeg()) == []


def test_quality_notes_handle_broken_bytes():
    assert quality_notes(b"not an image") == ["图片无法读取，请重新上传。"]


def test_quality_warnings_come_before_the_continue_hint():
    notes = quality_notes(jpeg_bytes(size=(100, 60)))
    assert notes[-1].startswith("仍可继续")
