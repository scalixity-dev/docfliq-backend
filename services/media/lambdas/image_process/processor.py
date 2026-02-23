"""
Image processor — resize, compress, convert to WebP.

Uses Pillow for image manipulation. Produces multiple output sizes
from a single input image.

Output sizes:
  General images:
    - thumbnail: 150x150 (center crop, square)
    - medium:    600x600 (fit within, maintain aspect ratio)
    - large:     1200x1200 (fit within, maintain aspect ratio)

  Profile avatars (additional):
    - avatar_s:  48x48 (center crop, square)
    - avatar_m:  120x120 (center crop, square)
    - avatar_l:  300x300 (center crop, square)

  Course thumbnails (additional):
    - course_thumb: 400x225 (16:9, center crop)
"""
from __future__ import annotations

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

# Standard output sizes: (name, width, height, crop_mode)
# crop_mode: "crop" = center crop to exact size, "fit" = fit within maintaining aspect ratio
STANDARD_SIZES = [
    ("thumbnail", 150, 150, "crop"),
    ("medium", 600, 600, "fit"),
    ("large", 1200, 1200, "fit"),
]

AVATAR_SIZES = [
    ("avatar_s", 48, 48, "crop"),
    ("avatar_m", 120, 120, "crop"),
    ("avatar_l", 300, 300, "crop"),
]

COURSE_THUMB_SIZES = [
    ("course_thumb", 400, 225, "crop"),
]

# WebP quality for output
WEBP_QUALITY = 85


class ImageProcessor:
    """Process a single image into multiple sizes."""

    def __init__(self, image_data: bytes) -> None:
        self._image = Image.open(io.BytesIO(image_data))
        # Convert to RGB if necessary (e.g., CMYK, RGBA with transparency)
        if self._image.mode in ("RGBA", "LA", "PA"):
            # Composite onto white background for WebP
            background = Image.new("RGB", self._image.size, (255, 255, 255))
            background.paste(self._image, mask=self._image.split()[-1])
            self._image = background
        elif self._image.mode != "RGB":
            self._image = self._image.convert("RGB")

    def process(
        self,
        *,
        is_avatar: bool = False,
        is_course_thumbnail: bool = False,
    ) -> dict[str, bytes]:
        """Generate all required sizes. Returns {size_name: webp_bytes}."""
        results: dict[str, bytes] = {}

        # Always generate standard sizes
        for name, width, height, mode in STANDARD_SIZES:
            results[name] = self._resize(width, height, mode)

        # Avatar sizes for profile images
        if is_avatar:
            for name, width, height, mode in AVATAR_SIZES:
                results[name] = self._resize(width, height, mode)

        # Course thumbnail
        if is_course_thumbnail:
            for name, width, height, mode in COURSE_THUMB_SIZES:
                results[name] = self._resize(width, height, mode)

        return results

    def _resize(self, width: int, height: int, mode: str) -> bytes:
        """Resize the image and return WebP bytes."""
        if mode == "crop":
            resized = self._center_crop(width, height)
        else:
            resized = self._fit_within(width, height)

        buf = io.BytesIO()
        resized.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
        return buf.getvalue()

    def _center_crop(self, width: int, height: int) -> Image.Image:
        """Crop from center to exact dimensions, then resize."""
        img = self._image.copy()
        img_ratio = img.width / img.height
        target_ratio = width / height

        if img_ratio > target_ratio:
            # Image is wider — crop horizontally
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            # Image is taller — crop vertically
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        return img.resize((width, height), Image.LANCZOS)

    def _fit_within(self, max_width: int, max_height: int) -> Image.Image:
        """Resize to fit within max dimensions, maintaining aspect ratio."""
        img = self._image.copy()
        img.thumbnail((max_width, max_height), Image.LANCZOS)
        return img
