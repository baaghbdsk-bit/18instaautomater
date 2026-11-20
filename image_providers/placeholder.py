"""
image_providers/placeholder.py — local development-only placeholder images.

Placeholders are explicitly forbidden in production.  They are only produced
when ``config.ALLOW_PLACEHOLDER`` is enabled (local dev / tests); otherwise the
provider returns ``ok=False, status='unsupported'`` with an explicit message.
Every result carries ``metadata['is_placeholder'] = True``.
"""

import io
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

import config

from .base import ImageProvider, ImageRequest, ImageResult


def _atomic_save(data: bytes) -> str:
    images_dir = Path(config.IMAGES_DIR)
    tmp_dir = Path(config.TMP_DIR)
    images_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = f"placeholder_{stamp}_{uuid.uuid4().hex[:6]}.jpg"
    tmp_path = tmp_dir / f".{name}.part"
    final_path = images_dir / name

    tmp_path.write_bytes(data)
    os.replace(tmp_path, final_path)
    return str(final_path)


class PlaceholderProvider(ImageProvider):
    name = "placeholder"

    def generate(self, request: ImageRequest) -> ImageResult:
        metadata = {
            "is_placeholder": True,
            "prompt": request.prompt,
            "reference_images_supported": False,
        }

        if not config.ALLOW_PLACEHOLDER:
            return ImageResult(
                ok=False,
                provider=self.name,
                model="placeholder",
                seed=request.seed,
                metadata=metadata,
                error=(
                    "Placeholder images are forbidden in production. "
                    "Set ALLOW_PLACEHOLDER=1 only for local development/tests."
                ),
                status="unsupported",
            )

        started = time.monotonic()
        width = max(1, int(request.width or 1080))
        height = max(1, int(request.height or 1920))

        image = Image.new("RGB", (width, height), (18, 18, 26))
        draw = ImageDraw.Draw(image)
        # Clearly marked in the pixels themselves — impossible to mistake for
        # a real generated asset.
        label = "PLACEHOLDER - NOT A REAL IMAGE"
        draw.text((10, 10), label, fill=(255, 90, 90))
        draw.rectangle(
            [0, 0, width - 1, height - 1],
            outline=(255, 90, 90),
            width=max(1, min(width, height) // 100),
        )
        draw.line((0, 0, width, height), fill=(255, 90, 90), width=max(1, min(width, height) // 100))
        draw.line((width, 0, 0, height), fill=(255, 90, 90), width=max(1, min(width, height) // 100))

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        data = buffer.getvalue()

        path = _atomic_save(data)
        metadata.update({
            "width": width,
            "height": height,
            "duration": round(time.monotonic() - started, 3),
            "bytes": len(data),
        })
        return ImageResult(
            ok=True,
            path=path,
            provider=self.name,
            model="placeholder",
            seed=request.seed,
            metadata=metadata,
            status="generated",
        )
