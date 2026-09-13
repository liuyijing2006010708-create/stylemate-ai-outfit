"""Optional photo adjustments before recognition.

Rotate, crop, optional background removal and a light quality check, so a
messy shot can be fixed without re-uploading. All outputs are normalized
JPEG with the same bounds as validate_upload.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, UnidentifiedImageError

from .uploads import MAX_SIDE, InvalidImage

MIN_SIDE_PX = 320
BLUR_VARIANCE = 100.0


def background_removal_available() -> bool:
    try:
        import rembg  # noqa: F401
    except ImportError:
        return False
    return True


def _load(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImage("图片已损坏或无法读取；请重新上传。") from exc
    return image


def _remove_background(image: Image.Image) -> Image.Image | None:
    try:
        from rembg import remove
    except ImportError:
        return None
    source = io.BytesIO()
    image.save(source, format="PNG")
    try:
        result = remove(source.getvalue())
    except Exception:
        return None
    try:
        return Image.open(io.BytesIO(result)).convert("RGBA")
    except (UnidentifiedImageError, OSError):
        return None


def adjust(
    data: bytes,
    *,
    rotation: int = 0,
    crop: tuple[float, float, float, float] = (0.0, 0.0, 100.0, 100.0),
    remove_background: bool = False,
) -> bytes:
    """Rotate clockwise by `rotation` degrees, crop by percentage edges,
    optionally strip the background, and return normalized JPEG bytes."""

    image = _load(data)
    if rotation % 360:
        image = image.rotate(-rotation, expand=True)
    left, top, right, bottom = crop
    width, height = image.size
    box = (
        round(width * left / 100),
        round(height * top / 100),
        round(width * right / 100),
        round(height * bottom / 100),
    )
    if box[2] - box[0] >= 8 and box[3] - box[1] >= 8 and box != (0, 0, width, height):
        image = image.crop(box)
    if remove_background:
        stripped = _remove_background(image)
        if stripped is not None:
            image = stripped
    rgba = image.convert("RGBA")
    flat = Image.alpha_composite(
        Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba
    ).convert("RGB")
    if max(flat.size) > MAX_SIDE:
        flat.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buffer = io.BytesIO()
    flat.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def quality_notes(data: bytes) -> list[str]:
    """Fixed, user-presentable hints; empty list means the photo looks fine."""

    try:
        image = _load(data)
    except InvalidImage:
        return ["图片无法读取，请重新上传。"]
    notes: list[str] = []
    width, height = image.size
    if min(width, height) < MIN_SIDE_PX:
        notes.append("分辨率偏低（短边不足 320px），主体可能太小，建议重新拍摄或放大后裁剪。")
    gray = np.asarray(image.convert("L"), dtype=float)
    if gray.size >= 64:
        laplacian = (
            4 * gray[1:-1, 1:-1]
            - gray[:-2, 1:-1] - gray[2:, 1:-1]
            - gray[1:-1, :-2] - gray[1:-1, 2:]
        )
        if laplacian.var() < BLUR_VARIANCE:
            notes.append("图片可能偏模糊或对比度太低，建议在光线充足、背景干净处重新拍摄。")
    if notes:
        notes.append("仍可继续识别，但识别与效果图质量可能受影响。")
    return notes
