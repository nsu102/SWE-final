"""Images -> JPEG data URLs, stored inline in the DB (search thumbnails, profile avatars).

ponytail: inline data URLs (~20-60KB) keep Lambda free of S3 writes and network access;
move to an S3 bucket if images grow or need a CDN.
"""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps, UnidentifiedImageError

AVATAR_SIZE = 256
MAX_PIXELS = 20_000_000


def jpeg_data_url(image: Image.Image, quality: int = 88) -> str:
    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def preview_data_url(image: Image.Image) -> str:
    preview = image.copy()
    preview.thumbnail((480, 480))
    return jpeg_data_url(preview)


def avatar_data_url(body: bytes) -> str:
    """Center-cropped AVATAR_SIZE square JPEG. ValueError for anything that isn't a sane image."""
    try:
        with Image.open(io.BytesIO(body)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("image resolution is too large")
            square = ImageOps.fit(ImageOps.exif_transpose(image), (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid image") from exc
    return jpeg_data_url(square, quality=85)
