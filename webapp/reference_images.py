"""Validation of brand images uploaded with a job."""

from __future__ import annotations

import tempfile
from enum import Enum
from pathlib import Path

from scripts.compositor import imagem_tem_pixels_transparentes

DEFAULT_IMAGE_SUFFIX = ".png"


class TransparencyCheck(str, Enum):
    TRANSPARENT = "transparent"
    OPAQUE = "opaque"
    UNREADABLE = "unreadable"


def check_transparency(data: bytes, filename: str | None) -> TransparencyCheck:
    suffix = Path(filename or "").suffix or DEFAULT_IMAGE_SUFFIX
    with tempfile.TemporaryDirectory() as temp_dir:
        image_path = Path(temp_dir) / f"upload{suffix}"
        image_path.write_bytes(data)
        has_transparent_pixels = imagem_tem_pixels_transparentes(image_path)
    if has_transparent_pixels is None:
        return TransparencyCheck.UNREADABLE
    return TransparencyCheck.TRANSPARENT if has_transparent_pixels else TransparencyCheck.OPAQUE
