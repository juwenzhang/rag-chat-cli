"""Image normalization helpers for uploaded assets."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

__all__ = ["NormalizedImage", "normalize_image_to_webp"]


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    data: bytes
    filename: str
    content_type: str
    description: str


async def normalize_image_to_webp(
    *,
    data: bytes,
    filename: str,
    content_type: str,
    max_dimension: int = 2048,
    quality: int = 82,
) -> NormalizedImage:
    """Convert an uploaded image to WebP using CPU-bound Pillow work in a thread."""

    return await asyncio.to_thread(
        _normalize_image_to_webp_sync,
        data=data,
        filename=filename,
        content_type=content_type,
        max_dimension=max_dimension,
        quality=quality,
    )


def _normalize_image_to_webp_sync(
    *,
    data: bytes,
    filename: str,
    content_type: str,
    max_dimension: int,
    quality: int,
) -> NormalizedImage:
    try:
        with Image.open(BytesIO(data)) as raw_image:
            original_format = raw_image.format or content_type.removeprefix("image/").upper()
            processed: Image.Image = ImageOps.exif_transpose(raw_image)
            processed.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            converted = _prepare_for_webp(processed)
            width, height = converted.size

            out = BytesIO()
            converted.save(out, format="WEBP", quality=quality, method=6)
            webp = out.getvalue()
    except UnidentifiedImageError as exc:
        raise ValueError("invalid image file") from exc
    except OSError as exc:
        raise ValueError("invalid image file") from exc

    safe_name = _webp_filename(filename)
    return NormalizedImage(
        data=webp,
        filename=safe_name,
        content_type="image/webp",
        description=(
            f"Uploaded image {filename} converted from {original_format} to WebP "
            f"({width}x{height}, {len(webp)} bytes). Vision analysis is not configured yet."
        ),
    )


def _prepare_for_webp(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "RGB"}:
        return image
    if image.mode in {"LA", "P"}:
        return image.convert("RGBA")
    return image.convert("RGB")


def _webp_filename(filename: str) -> str:
    path = Path(filename or "image")
    stem = path.stem.strip() or "image"
    return f"{stem}.webp"
