"""Strict admission for uploaded photos and provider-returned images.

Every check fails closed with a fixed, locally written message; provider
response content never appears in these errors.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_RESULT_BYTES = 20 * 1024 * 1024
# Checked from the header before any pixel data is decoded, so a decompression
# bomb costs one header parse, not gigabytes of RAM.
MAX_PIXELS = 30 * 1024 * 1024
MAX_SIDE = 2048
ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}


class InvalidImage(ValueError):
    """Only ever carries fixed, locally written messages."""


def ensure_image_bytes(data: bytes, *, max_bytes: int = MAX_RESULT_BYTES) -> bytes:
    """Validate bytes claimed to be an image before storing or rendering them."""
    if not data or len(data) > max_bytes:
        raise InvalidImage("图片数据大小无效。")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise InvalidImage("返回图片像素过大，请降低生成分辨率。")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImage("返回的内容不是有效图片。") from exc
    return data


def validate_upload(data: bytes) -> tuple[bytes, str]:
    """Decode, bound and normalize an uploaded garment photo.

    Normalizing to JPEG guarantees the announced mime type matches the actual
    bytes, corrects EXIF orientation and strips metadata such as GPS tags.
    """
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise InvalidImage("图片必须大于 0 且不超过 10 MB。")
    try:
        image = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise InvalidImage("图片像素过大，请缩小后重新上传。") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage("文件不是有效图片；请上传正常的 JPG、PNG 或 WEBP。") from exc
    with image:
        if image.format not in ACCEPTED_FORMATS:
            raise InvalidImage("仅支持 JPG、PNG 或 WEBP 图片。")
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
            raise InvalidImage("图片像素过大，请缩小后重新上传。")
        try:
            image.load()
            straightened = ImageOps.exif_transpose(image)
            # Reduce before allocating the RGBA compositing buffers.
            if max(straightened.size) > MAX_SIDE:
                straightened.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            rgba = straightened.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            flat = Image.alpha_composite(background, rgba).convert("RGB")
            if max(flat.size) > MAX_SIDE:
                flat.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            buffer = io.BytesIO()
            flat.save(buffer, format="JPEG", quality=90)
        except (OSError, Image.DecompressionBombError) as exc:
            raise InvalidImage("图片已损坏或无法读取；请重新上传。") from exc
    return buffer.getvalue(), "image/jpeg"
