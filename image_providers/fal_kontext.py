"""
image_providers/fal_kontext.py — reference-conditioned FLUX Kontext provider via fal.ai.

Preserves canonical facial identity and body proportions from ``request.reference_images``
using ``fal-ai/flux-pro/kontext`` (or ``fal-ai/flux-pulid``). Requires ``FAL_KEY``.
"""

import base64
import io
import os
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

from config import IMAGES_DIR
from .base import ImageProvider, ImageRequest, ImageResult

FAL_KONTEXT_URL = "https://fal.run/fal-ai/flux-pro/kontext"
DEFAULT_REF = Path(__file__).resolve().parent.parent / "character" / "references" / "master.jpg"


def _to_data_uri(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".") or "jpeg"
    if ext == "jpg":
        ext = "jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{ext};base64,{b64}"


class FalKontextProvider(ImageProvider):
    name = "fal_kontext"

    def generate(self, request: ImageRequest) -> ImageResult:
        api_key = os.getenv("FAL_KEY", "").strip()
        if not api_key:
            return ImageResult(
                ok=False,
                provider=self.name,
                status="skipped",
                error="FAL_KEY is not set",
            )

        ref_path = None
        for candidate in (request.reference_images or []):
            p = Path(candidate)
            if not p.is_absolute():
                p = Path(__file__).resolve().parent.parent / p
            if p.exists():
                ref_path = p
                break
        if ref_path is None and DEFAULT_REF.exists():
            ref_path = DEFAULT_REF
        if ref_path is None:
            return ImageResult(
                ok=False,
                provider=self.name,
                status="failed",
                error="No reference image found for fal_kontext",
            )

        payload = {
            "prompt": (
                f"Keep the exact same woman's face, hazel-green eyes, freckles, nose rings, "
                f"and curvy hourglass body with fuller bust from the reference image. {request.prompt}"
            ),
            "image_url": _to_data_uri(ref_path),
            "aspect_ratio": "3:4",
            "guidance_scale": 3.5,
            "output_format": "jpeg",
            "safety_tolerance": "5",
        }
        headers = {
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(FAL_KONTEXT_URL, json=payload, headers=headers, timeout=120)
            if resp.status_code != 200:
                return ImageResult(
                    ok=False,
                    provider=self.name,
                    status="failed",
                    error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                )
            data = resp.json()
            images = data.get("images") or []
            if not images or not images[0].get("url"):
                return ImageResult(
                    ok=False,
                    provider=self.name,
                    status="failed",
                    error="fal.ai response contained no image URL",
                )
            img_resp = requests.get(images[0]["url"], timeout=60)
            img_resp.raise_for_status()
            img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")

            IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out_path = IMAGES_DIR / f"fal_{stamp}.jpg"
            img.save(out_path, format="JPEG", quality=95)

            return ImageResult(
                ok=True,
                path=str(out_path),
                provider=self.name,
                model="fal-ai/flux-pro/kontext",
                seed=str(data.get("seed") or ""),
                status="generated",
                metadata={
                    "provider_supports_reference": True,
                    "reference_image": str(ref_path),
                },
            )
        except Exception as exc:
            return ImageResult(
                ok=False,
                provider=self.name,
                status="failed",
                error=str(exc),
            )
