"""
image_providers/perchance.py — local Perchance AI proxy provider.

IMPORTANT — what this backend actually is
-----------------------------------------
The Perchance server (see ``Perchance-API/app.py``) is a *local reverse proxy*
that drives a background Chromium session via DrissionPage/perchancy.  It does
not run local neural inference: it injects parameters into Perchance's cloud
generator and scrapes the resulting image stream.  It therefore needs the
wrapper service to be running (default ``http://127.0.0.1:8000``) and warm.

Verified contract used here (from API_DOCUMENTATION.md sections 2,3,5,6 and
app.py request models):

* No API key is required; any Bearer token is ignored.
* ``GET /v1/health`` -> JSON with a ``ready`` flag (short timeout).
* ``POST /api/v1/generate/raw`` -> raw JPEG/PNG bytes, HTTP 200 only.
* Accepted fields: ``prompt``, ``negative_prompt``, ``aspect_ratio``
  (``512x768|512x512|768x512|portrait|landscape|square``), ``style``,
  ``style_mix``, ``guidance_scale`` (1-20), ``seed`` (string), ``num_images``
  (1-6).

LIMITATION: there is **no reference-image parameter** in this API.  If a caller
supplies ``reference_images`` we do NOT pretend to honour them — we record
``reference_images_supported=False`` and a warning in the result metadata.
"""

import io
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

# Raw bytes smaller than this are almost certainly an error page / empty body.
MIN_IMAGE_BYTES = 10 * 1024
# Health check must be fast — it is a gate before a potentially long generation.
HEALTH_TIMEOUT = 5


def _is_retryable(exc: Exception) -> bool:
    """Custom classification: 503/504 + network errors only.

    400 (validation) and 500 (engine failure) are deterministic here — retrying
    them just wastes a generation slot — so they are explicitly non-retryable.
    """
    if isinstance(exc, HttpError):
        return exc.status in (503, 504)
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    name = type(exc).__name__.lower()
    return any(tok in name for tok in ("timeout", "connection", "network"))


def _safe_error(exc: Exception) -> str:
    """Never leak query strings (tokens live there)."""
    message = str(exc).split("?", 1)[0]
    return f"{type(exc).__name__}: {message[:200]}"


def _extension(data: bytes) -> str:
    return ".png" if data.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg"


def _atomic_save(data: bytes, prefix: str = "perchance") -> str:
    """Write to a temp file first, then atomically rename into IMAGES_DIR."""
    images_dir = Path(config.IMAGES_DIR)
    tmp_dir = Path(config.TMP_DIR)
    images_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = f"{prefix}_{stamp}_{uuid.uuid4().hex[:6]}{_extension(data)}"
    tmp_path = tmp_dir / f".{name}.part"
    final_path = images_dir / name

    tmp_path.write_bytes(data)
    os.replace(tmp_path, final_path)  # atomic on the same volume
    return str(final_path)


def _build_payload(request: ImageRequest) -> dict:
    """Exactly the verified NativeGenerateRequest fields used by /generate/raw."""
    return {
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt or config.PERCHANCE_NEGATIVE,
        "aspect_ratio": request.aspect_ratio or config.PERCHANCE_ASPECT,
        "style": config.PERCHANCE_STYLE,
        "style_mix": "Not Mix",
        "guidance_scale": config.PERCHANCE_GUIDANCE,
        "seed": request.seed or "",
        "num_images": request.num_images,
    }


class PerchanceProvider(ImageProvider):
    name = "perchance"

    def health(self) -> bool:
        """GET /v1/health — must return HTTP 200 and ``ready is True``."""
        url = config.PERCHANCE_URL.rstrip("/") + "/v1/health"
        try:
            resp = requests.get(url, timeout=HEALTH_TIMEOUT)
            if resp.status_code != 200:
                return False
            return resp.json().get("ready") is True
        except Exception:
            return False

    def generate(self, request: ImageRequest) -> ImageResult:
        started = time.monotonic()

        metadata = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt or config.PERCHANCE_NEGATIVE,
            "aspect_ratio": request.aspect_ratio or config.PERCHANCE_ASPECT,
            "style": config.PERCHANCE_STYLE,
            "guidance_scale": config.PERCHANCE_GUIDANCE,
            "num_images": request.num_images,
            # Honest capability flag — this API has no reference-image field.
            "reference_images_supported": False,
        }
        if request.reference_images:
            metadata["warning"] = (
                "Perchance API has no reference-image parameter; "
                "reference_images were ignored."
            )

        def failed(error: str) -> ImageResult:
            metadata["duration"] = round(time.monotonic() - started, 3)
            return ImageResult(
                ok=False,
                provider=self.name,
                model="perchance-image",
                seed=request.seed,
                metadata=metadata,
                error=error,
                status="failed",
            )

        if not request.prompt or not request.prompt.strip():
            return failed("prompt must be a non-empty string")

        # Gate on the browser-pool readiness flag before spending a generation.
        if not self.health():
            return failed("Perchance service is not ready (health check failed)")

        payload = _build_payload(request)
        url = config.PERCHANCE_URL.rstrip("/") + "/api/v1/generate/raw"

        def do_call() -> bytes:
            resp = requests.post(
                url,
                json=payload,
                timeout=config.PERCHANCE_TIMEOUT,
            )
            if resp.status_code != 200:
                raise HttpError(resp.status_code, getattr(resp, "text", ""), url)
            return resp.content

        try:
            data = with_retry(
                do_call,
                attempts=config.PERCHANCE_RETRIES + 1,
                label="perchance.generate",
                is_retryable=_is_retryable,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced as a safe result
            return failed(_safe_error(exc))

        if len(data) < MIN_IMAGE_BYTES:
            return failed(
                f"Perchance returned too little data "
                f"({len(data)} bytes < {MIN_IMAGE_BYTES})"
            )

        try:
            image = Image.open(io.BytesIO(data))
            image.verify()
        except Exception as exc:  # noqa: BLE001 — corrupt / non-image body
            return failed(f"invalid image data: {_safe_error(exc)}")

        path = _atomic_save(data)
        metadata.update({
            "duration": round(time.monotonic() - started, 3),
            "bytes": len(data),
        })
        return ImageResult(
            ok=True,
            path=path,
            provider=self.name,
            model="perchance-image",
            seed=request.seed,
            metadata=metadata,
            status="generated",
        )
