import io
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from stylemate.runtime import safe_connection_error
from stylemate.uploads import InvalidImage, ensure_image_bytes, validate_upload

ROOT = Path(__file__).resolve().parents[1]


def jpeg_bytes(size=(8, 6), color=(200, 120, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def png_bytes(size=(8, 6)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, (10, 20, 30, 140)).save(buffer, format="PNG")
    return buffer.getvalue()


def webp_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6)).save(buffer, format="WEBP")
    return buffer.getvalue()


def test_normal_jpeg_png_webp_are_accepted_and_normalized_to_rgb_jpeg():
    for data in (jpeg_bytes(), png_bytes(), webp_bytes()):
        out, mime = validate_upload(data)
        assert mime == "image/jpeg"
        with Image.open(io.BytesIO(out)) as image:
            assert image.format == "JPEG"
            assert image.mode == "RGB"
            image.verify()


def test_fake_jpg_is_rejected():
    with pytest.raises(InvalidImage, match="不是有效图片"):
        validate_upload(b"MZ fake executable pretending to be a .jpg")


def test_oversized_upload_is_rejected_before_decoding():
    with pytest.raises(InvalidImage, match="10 MB"):
        validate_upload(b"\x89PNG" + b"\x00" * (10 * 1024 * 1024 + 1))


def test_decompression_bomb_header_is_rejected_without_decoding():
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", 40000, 40000, 8, 2, 0, 0, 0)
    bomb = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"\x00" * 120003)) + chunk(b"IEND", b""))
    assert len(bomb) < 10 * 1024 * 1024
    with pytest.raises(InvalidImage, match="像素过大"):
        validate_upload(bomb)


def test_exif_orientation_is_corrected():
    buffer = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # portrait shot stored landscape; display needs rotation
    Image.new("RGB", (40, 20), "white").save(buffer, format="JPEG", exif=exif.tobytes())
    out, _ = validate_upload(buffer.getvalue())
    with Image.open(io.BytesIO(out)) as corrected:
        assert corrected.size == (20, 40)


def test_transparent_png_flattens_onto_white_rgb():
    transparent, opaque = io.BytesIO(), io.BytesIO()
    Image.new("RGBA", (8, 6), (255, 0, 0, 0)).save(transparent, format="PNG")
    Image.new("RGBA", (8, 6), (10, 20, 30, 255)).save(opaque, format="PNG")
    out, _ = validate_upload(transparent.getvalue())
    with Image.open(io.BytesIO(out)) as image:
        assert image.mode == "RGB"
        assert image.getpixel((0, 0)) == (255, 255, 255)
    out, _ = validate_upload(opaque.getvalue())
    with Image.open(io.BytesIO(out)) as image:
        assert image.getpixel((0, 0)) == (10, 20, 30)


def test_oversized_dimensions_are_downscaled():
    out, _ = validate_upload(jpeg_bytes(size=(2600, 1500)))
    with Image.open(io.BytesIO(out)) as image:
        assert max(image.size) == 2048
        ratio = image.size[0] / image.size[1]
        assert abs(ratio - 2600 / 1500) < 0.01


def test_provider_results_are_verified_before_display():
    data = jpeg_bytes()
    assert ensure_image_bytes(data) == data


def test_provider_result_pixel_limit_is_checked_before_display(monkeypatch):
    monkeypatch.setattr("stylemate.uploads.MAX_PIXELS", 100)
    with pytest.raises(InvalidImage, match="像素"):
        ensure_image_bytes(jpeg_bytes(size=(20, 20)))


def test_provider_results_reject_corrupt_and_oversized_bytes():
    with pytest.raises(InvalidImage, match="不是有效图片"):
        ensure_image_bytes(b"not an image at all")
    with pytest.raises(InvalidImage, match="大小"):
        ensure_image_bytes(b"\x00" * (20 * 1024 * 1024 + 1))


def test_locally_fixed_errors_pass_through_http_status_errors_do_not():
    assert safe_connection_error(InvalidImage("仅支持 JPG、PNG 或 WEBP 图片。")) == "仅支持 JPG、PNG 或 WEBP 图片。"
    http = RuntimeError("provider response must not be exposed")
    http.status_code = 401  # type: ignore[attr-defined]
    assert "Key" in safe_connection_error(http)
    assert "provider response" not in safe_connection_error(http)


def test_spoofed_upload_never_reaches_the_provider(monkeypatch):
    from streamlit.testing.v1 import AppTest

    calls = []

    class FakeAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def close(self):
            pass

    monkeypatch.setattr("stylemate.openai_service.StyleMateAI", FakeAI)
    script = f'''
import runpy
import streamlit as st
ns = runpy.run_path({str(ROOT / "app.py")!r}, init_globals={{"PUBLIC_DEPLOYMENT": True}})
if st.session_state.plan is None:
    st.session_state.api_key = "test-only-key"
    try:
        ns["_start_analysis"](b"pretend jpg payload", "上班", "韩系简约")
    except Exception as exc:
        from stylemate.runtime import safe_connection_error
        st.error(safe_connection_error(exc))
'''
    app = AppTest.from_string(script).run()
    assert not calls
    assert not app.exception
    assert any("不是有效图片" in error.value for error in app.error)
