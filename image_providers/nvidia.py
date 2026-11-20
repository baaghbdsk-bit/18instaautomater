"""
image_providers/nvidia.py — NVIDIA NIM Flux.1-schnell provider.

Verified endpoint (from ``gen_sample_nvidia.py``):

    POST NVIDIA_FLUX_URL
    headers: Authorization: Bearer <NVIDIA_API_KEY>, Accept/Content-Type json
    payload: {"prompt", "mode": "base", "cfg_scale": 0, "width", "height",
              "seed", "steps": 4}
    response: {"artifacts": [{"base64": "..."}]}

Requires ``NVIDIA_API_KEY``; without it the provider reports
``ok=False, status='unsupported'``.  Flux.1-schnell has no reference-image
input, so that capability is recorded as unsupported in the metadata.
"""

import base64
import io
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

import config
from net import HttpError, with_retry

from .base import ImageProvider, ImageRequest, ImageResult

MODEL = "flux.1-schnell"


def _safe_error(exc: Exception) -> str:
    message = str(exc).split("?", 1)[0]
    return f"{type(exc).__name__}: {message[:200]}"


def _extension(data: bytes) -> str:
    return ".png" if data.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg"


def _atomic_save(data: bytes) -> str:
    images_dir = Path(config.IMAGES_DIR)
    tmp_dir = Path(config.TMP_DIR)
    images_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = f"nvidia_{stamp}_{uuid.uuid4().hex[:6]}{_extension(data)}"
    tmp_path = tmp_dir / f".{name}.part"
    final_path = images_dir / name

    tmp_path.write_bytes(data)
    os.replace(tmp_path, final_path)
    return str(final_path)


def _as_seed(value) -> int:
    """Flux expects an integer seed; fall back to 0 for empty/invalid values."""
    try:
        return int(value) if value not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


class NvidiaProvider(ImageProvider):
    name = "nvidia"

    def generate(self, request: ImageRequest) -> ImageResult:
        started = time.monotonic()
        metadata = {
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "mode": "base",
            "cfg_scale": 0,
            "steps": 4,
            "reference_images_supported": False,
        }
        if request.reference_images:
            metadata["warning"] = (
                "NVIDIA NIM Flux.1-schnell has no reference-image parameter; "
                "reference_images were ignored."
            )

        def failed(error: str, status: str = "failed") -> ImageResult:
            metadata["duration"] = round(time.monotonic() - started, 3)
            return ImageResult(
                ok=False,
                provider=self.name,
                model=MODEL,
                seed=request.seed,
                metadata=metadata,
                error=error,
                status=status,
            )

        if not config.NVIDIA_API_KEY:
            return failed(
                "NVIDIA_API_KEY is not set; cannot call the NVIDIA NIM endpoint.",
                status="unsupported",
            )
        if not request.prompt or not request.prompt.strip():
            return failed("prompt must be a non-empty string")

        headers = {
            "Authorization": f"Bearer {config.NVIDIA_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": request.prompt,
            "mode": "base",
            "cfg_scale": 0,
            "width": request.width,
            "height": request.height,
            "seed": _as_seed(request.seed),
            "steps": 4,
        }
        url = config.NVIDIA_FLUX_URL

        def do_call() -> bytes:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=config.NVIDIA_TIMEOUT,
            )
            if resp.status_code != 200:
                raise HttpError(resp.status_code, getattr(resp, "text", ""), url)
            return resp.content

        try:
            raw = with_retry(
                do_call,
                attempts=4,
                label="nvidia.generate",
            )
            data = json.loads(raw.decode("utf-8"))
            artifacts = data.get("artifacts") or []
            if not artifacts or not artifacts[0].get("base64"):
                return failed("NVIDIA response contained no image artifact")
            image_bytes = base64.b64decode(artifacts[0]["base64"])
        except Exception as exc:  # noqa: BLE001 — surfaced as a safe result
            return failed(_safe_error(exc))

        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.verify()
        except Exception as exc:  # noqa: BLE001 — corrupt / non-image artifact
            return failed(f"invalid image data: {_safe_error(exc)}")

        path = _atomic_save(image_bytes)
        metadata.update({
            "duration": round(time.monotonic() - started, 3),
            "bytes": len(image_bytes),
        })
        return ImageResult(
            ok=True,
            path=path,
            provider=self.name,
            model=MODEL,
            seed=request.seed,
            metadata=metadata,
            status="generated",
        )
