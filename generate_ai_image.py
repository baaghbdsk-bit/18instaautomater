"""
generate_ai_image.py — theme-aware AI image generation via Perchance.

Flow:
  1. pick a not-recently-used prompt template for the chosen theme
  2. POST it to the local Perchance-API wrapper (free, no key)
  3. on any failure -> fast locally-rendered placeholder (pipeline still works;
     CI runs with --strict and refuses to post a placeholder)

Usage:
  python generate_ai_image.py                 # random theme
  python generate_ai_image.py --theme beach_golden
  python generate_ai_image.py --force-local   # skip Perchance
"""

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path

import requests

import db
from config import (
    IMAGES_DIR,
    PERCHANCE_ASPECT,
    PERCHANCE_GUIDANCE,
    PERCHANCE_NEGATIVE,
    PERCHANCE_STYLE,
    PERCHANCE_URL,
)
from themes import THEME_KEYS, pick_prompt, theme_meta

# Kept for backward compatibility with scripts that import PROMPTS.
PROMPTS = [
    "beautiful woman, elegant evening dress, soft romantic lighting, "
    "cinematic portrait, shallow depth of field, warm tones, highly detailed, "
    "fashion photography",
]


def _try_perchance(prompt: str) -> Path | None:
    """Generate via the local Perchance-API wrapper. Returns path or None."""
    try:
        r = requests.get(f"{PERCHANCE_URL}/v1/health", timeout=5)
        if r.status_code != 200:
            print(f"    [!] Perchance server unhealthy (HTTP {r.status_code})")
            return None
    except Exception:
        print(f"    [!] Perchance server not reachable at {PERCHANCE_URL}")
        print("        Start it with: python app.py  (in the Perchance-API folder)")
        return None

    payload = {
        "prompt": prompt,
        "negative_prompt": PERCHANCE_NEGATIVE,
        "style": PERCHANCE_STYLE,
        "aspect_ratio": PERCHANCE_ASPECT,
        "guidance_scale": PERCHANCE_GUIDANCE,
        "num_images": 1,
        "seed": random.randint(0, 2**31 - 1),
    }

    print(f"    [*] Perchance: {prompt[:70]}...")
    try:
        resp = requests.post(f"{PERCHANCE_URL}/api/v1/generate/raw",
                             json=payload, timeout=180)
    except requests.RequestException as e:
        print(f"    [!] Request failed: {e}")
        return None

    if resp.status_code != 200:
        print(f"    [!] API error {resp.status_code}: {resp.text[:300]}")
        return None
    if len(resp.content) < 10 * 1024:
        print(f"    [!] Response too small ({len(resp.content)} B), rejecting")
        return None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = IMAGES_DIR / f"perchance_{stamp}.jpg"
    out_path.write_bytes(resp.content)
    print(f"    [+] AI image saved: {out_path.name} "
          f"({len(resp.content) / 1024:.0f} KB)")
    return out_path


def _make_placeholder(prompt: str) -> Path:
    """Fast local gradient placeholder (no Perchance needed)."""
    from PIL import Image, ImageDraw, ImageFont

    # Small gradient, resized up — thousands of times faster than putpixel loops.
    grad = Image.new("RGB", (8, 1024))
    px = grad.load()
    for y in range(1024):
        r = int(20 + (y / 1024) * 60)
        g = int(15 + (y / 1024) * 30)
        b = int(40 + (y / 1024) * 70)
        for x in range(8):
            px[x, y] = (r, g, b)
    img = grad.resize((1024, 1024))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 1004, 1004], outline=(255, 215, 0), width=8)

    font_path = "C:/Windows/Fonts/arial.ttf"
    try:
        font_big = ImageFont.truetype(font_path, 50)
        font_small = ImageFont.truetype(font_path, 30)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = font_big

    draw.text((512, 480), "AI IMAGE", fill=(255, 255, 255),
              font=font_big, anchor="mm")
    draw.text((512, 550), "PLACEHOLDER", fill=(255, 215, 0),
              font=font_small, anchor="mm")
    draw.text((512, 600), "Perchance was unavailable",
              fill=(200, 200, 200), font=font_small, anchor="mm")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = IMAGES_DIR / f"placeholder_{stamp}.jpg"
    img.save(out_path, quality=90)
    print(f"    [+] Placeholder saved: {out_path.name}")
    return out_path


def generate(prompt: str | None = None, force_local: bool = False,
             theme: str | None = None) -> tuple[Path, str]:
    """Generate one AI image. Returns (path, source)."""
    if prompt is None:
        theme = theme or random.choice(THEME_KEYS)
        used = {r["key"] for r in db.asset_usage("prompt")}
        prompt = pick_prompt(theme, used)
        db.mark_asset("prompt", f"{theme}::{prompt[:80]}")
        print(f"    [*] Theme: {theme}")

    if not force_local:
        result = _try_perchance(prompt)
        if result is not None:
            return result, "perchance"

    print("    [*] Using local fallback placeholder...")
    return _make_placeholder(prompt), "placeholder"


def main():
    parser = argparse.ArgumentParser(
        description="Generate an AI image via Perchance (or placeholder)")
    parser.add_argument("prompt", nargs="?", help="Custom prompt (optional)")
    parser.add_argument("--theme", choices=THEME_KEYS, help="Content theme")
    parser.add_argument("--force-local", action="store_true",
                        help="Skip Perchance, use placeholder only")
    args = parser.parse_args()

    out, source = generate(prompt=args.prompt, force_local=args.force_local,
                           theme=args.theme)
    print(f"\n=== IMAGE READY ({source}) ===\nFile: {out}")


if __name__ == "__main__":
    main()
