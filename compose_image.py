"""
compose_image.py — static quote-on-image composition (Pillow only, no ffmpeg).

Produces the same look as the reel renderer (cover crop, gaussian scrim,
Anton quote with a dark outline, optional watermark) but writes a single
high-quality JPEG plus a JSON sidecar with the composition metadata.

Usage:
    from compose_image import compose_quote_image
    info = compose_quote_image(image, "Bet you can't look away", variant="lower")
"""

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import (
    ACCENT,
    COMPOSE_VARIANTS,
    FINAL_IMAGES_DIR,
    FONT_HEAD,
    FONT_QUOTE,
    MARGIN_X,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from generate_video import LINE_SPACING, ensure_scrim, layout

# Fractions of frame height where the text block centre sits. Kept in sync
# with config.VARIANTS / generate_video.build_ass.
_VARIANT_FRACTIONS = {"upper": 0.30, "center": 0.46, "lower": 0.63}

STROKE_WIDTH = 3          # dark outline around every glyph
HANDLE_SIZE = 38          # matches the ASS "Mark" style in generate_video
JPEG_QUALITY = 95


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _load_font(path, size: int):
    """Load a TrueType font, falling back to Pillow's bitmap font."""
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:  # noqa: BLE001 — font may be missing in dev checkouts
        return ImageFont.load_default()


def _accent_rgb() -> tuple:
    """'0xFFFFC61A' (AARRGGBB) -> (255, 198, 26)."""
    h = str(ACCENT).lower().replace("0x", "")
    if len(h) == 8:
        h = h[2:]                       # drop alpha, web style
    h = h.rjust(6, "0")[-6:]
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def _cover_resize(img: Image.Image, size: tuple) -> Image.Image:
    """Cover-fit (scale to fill, centre crop) — same as ffmpeg's increase+crop."""
    return ImageOps.fit(img.convert("RGB"), size, method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5))


def _scrim_path(variant: str) -> Path:
    """Reuse the renderer's cached gaussian band under assets/overlay."""
    return Path(ensure_scrim(VIDEO_WIDTH, VIDEO_HEIGHT, variant))


def _apply_scrim(img: Image.Image, variant: str) -> Image.Image:
    """Alpha-composite the cached gaussian scrim over the image."""
    with Image.open(_scrim_path(variant)) as scrim:
        scrim = scrim.convert("RGBA")
        if scrim.size != img.size:
            scrim = scrim.resize(img.size)
        merged = Image.alpha_composite(img.convert("RGBA"), scrim)
    return merged.convert("RGB")


def _atomic_save_jpeg(img: Image.Image, path: Path) -> None:
    """Write via a temp file in the same directory, then os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                               dir=str(path.parent))
    os.close(fd)
    try:
        img.save(tmp, format="JPEG", quality=JPEG_QUALITY, subsampling=0,
                 optimize=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                               dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_placeholder_image(path) -> bool:
    """
    Guard against accidentally publishing a development placeholder.

    True when the filename starts with 'placeholder_' or the JSON sidecar
    (path.with_suffix('.json')) marks the image as a placeholder.
    """
    p = Path(path)
    if p.name.lower().startswith("placeholder_"):
        return True
    sidecar = p.with_suffix(".json")
    if sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(meta, dict) and (meta.get("is_placeholder")
                                           or meta.get("placeholder")):
                return True
        except (OSError, ValueError):
            pass
    return False


# ---------------------------------------------------------------------------
# public composition API
# ---------------------------------------------------------------------------
def compose_quote_image(source_path, quote, output_path=None, variant="lower",
                        handle="", font_quote=None, font_head=None) -> dict:
    """
    Compose a quote onto a source image and save a high-quality JPEG.

    Returns a dict with ok/path/width/height/bytes/variant/lines/font_size/
    source/is_placeholder/sha256 (and 'error' when ok is False). Never raises:
    failures are reported in the returned dict.
    """
    variant = variant if variant in COMPOSE_VARIANTS else "lower"
    src = Path(source_path)
    result = {
        "ok": False,
        "path": str(output_path) if output_path is not None else None,
        "width": VIDEO_WIDTH,
        "height": VIDEO_HEIGHT,
        "bytes": 0,
        "variant": variant,
        "lines": [],
        "font_size": 0,
        "source": str(src),
        "is_placeholder": is_placeholder_image(src),
        "sha256": "",
    }
    try:
        # 1. Open + validate the source. convert() forces a full decode.
        with Image.open(src) as raw:
            source_img = raw.convert("RGB")
            source_img.load()

        # 2. Cover crop to the exact reel size (same fit as generate_video).
        frame = _cover_resize(source_img, (VIDEO_WIDTH, VIDEO_HEIGHT))

        # 3. Gaussian scrim band behind the text (cached PNG from renderer).
        frame = _apply_scrim(frame, variant)

        # 4. Typography — reuse the renderer's layout so sizing/wrapping match.
        quote_text = str(quote or "")
        laid_out = layout(quote_text, width=VIDEO_WIDTH, margin_x=MARGIN_X)
        lines = list(laid_out["lines"]) or [""]
        font_size = int(laid_out["size"])
        q_font = _load_font(font_quote or FONT_QUOTE, font_size)
        h_font = _load_font(font_head or FONT_HEAD, HANDLE_SIZE)

        draw = ImageDraw.Draw(frame)
        cx = VIDEO_WIDTH / 2
        cy = _VARIANT_FRACTIONS.get(variant, 0.63) * VIDEO_HEIGHT
        line_h = font_size * LINE_SPACING
        y0 = cy - (len(lines) - 1) * line_h / 2
        for i, line in enumerate(lines):
            draw.text(
                (cx, y0 + i * line_h), line, font=q_font,
                fill=(255, 255, 255), anchor="mm",
                stroke_width=STROKE_WIDTH, stroke_fill=(0, 0, 0),
            )

        if handle:
            # Keep the handle OFF the face: bottom-centre on a dark pill.
            # The old top placement landed on the subject's forehead/hair.
            label = str(handle)
            hy = 0.94 * VIDEO_HEIGHT
            box = draw.textbbox((0, 0), label, font=h_font)
            tw, th = box[2] - box[0], box[3] - box[1]
            pad_x, pad_y = 22, 12
            draw.rounded_rectangle(
                (cx - tw / 2 - pad_x, hy - th / 2 - pad_y,
                 cx + tw / 2 + pad_x, hy + th / 2 + pad_y),
                radius=16, fill=(8, 8, 8),
            )
            draw.text(
                (cx, hy), label, font=h_font,
                fill=_accent_rgb(), anchor="mm",
            )

        # 5. Save atomically with a unique timestamp name when unspecified.
        if output_path is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out = Path(FINAL_IMAGES_DIR) / f"compose_{stamp}_{uuid.uuid4().hex[:6]}.jpg"
        else:
            out = Path(output_path)
        _atomic_save_jpeg(frame, out)

        digest = _sha256_file(out)
        data = out.stat().st_size
        placeholder = is_placeholder_image(src) or is_placeholder_image(out)
        meta = {
            "lines": lines,
            "quote": quote_text,
            "variant": variant,
            "sha256": digest,
            "source": str(src),
            "is_placeholder": placeholder,
            "handle": str(handle or ""),
            "font_size": font_size,
            "width": VIDEO_WIDTH,
            "height": VIDEO_HEIGHT,
            "bytes": data,
        }
        _atomic_write_json(out.with_suffix(".json"), meta)

        result.update({
            "ok": True,
            "path": str(out),
            "bytes": data,
            "variant": variant,
            "lines": lines,
            "font_size": font_size,
            "source": str(src),
            "is_placeholder": placeholder,
            "sha256": digest,
        })
        return result
    except Exception as e:  # noqa: BLE001 — report, never silently swallow
        result["error"] = f"{type(e).__name__}: {e}"
        return result
