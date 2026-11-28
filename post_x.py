"""
post_x.py — Daily character-consistent X (Twitter) poster.

Uses ``character/profile.py`` + ``character/variations.py`` to pick a fresh
outfit/expression/setting, generates a reference-conditioned image via
``fal_kontext`` (falling back to configured ``IMAGE_PROVIDER``), and posts
directly to X via Playwright + ``x_session/cookies.json``.

Usage:
    python post_x.py --dry-run
    python post_x.py
"""

import argparse
import base64
import json
import os
import random
import sys
from pathlib import Path
from typing import Optional

from character.profile import MASTER_PROFILE
from character.variations import build_prompt, select_variation
from image_providers import ImageRequest, get_provider

ROOT = Path(__file__).resolve().parent
X_SESSION_DIR = ROOT / "x_session"
X_COOKIES_FILE = X_SESSION_DIR / "cookies.json"

CAPTIONS = [
    "New look today. Thoughts? 👀",
    "Which vibe suits me better—this or yesterday's?",
    "Caught the right light before heading out ✨",
    "Mood today: keeping it effortless.",
    "Rate tonight's outfit 1-10 👇",
    "Just checking in. How's your evening going?",
    "Obsessed with how this fit turned out 🔥",
    "Soft lighting, sharper mood.",
]


def restore_x_cookies() -> bool:
    """Decode X_COOKIES_BASE64 env var into x_session/cookies.json if present."""
    b64 = os.getenv("X_COOKIES_BASE64", "").strip()
    if b64:
        X_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        X_COOKIES_FILE.write_bytes(base64.b64decode(b64))
    return X_COOKIES_FILE.exists()


def _pick_caption() -> str:
    return random.choice(CAPTIONS)


def generate_character_image(provider_name: Optional[str] = None) -> Path:
    variation = select_variation([])
    prompt = build_prompt(MASTER_PROFILE, variation)
    req = ImageRequest(
        prompt=prompt,
        negative_prompt=MASTER_PROFILE.negative_prompt_text(),
        aspect_ratio="3:4",
        reference_images=list(MASTER_PROFILE.reference_images),
    )

    chosen = provider_name or ("fal_kontext" if os.getenv("FAL_KEY") else None)
    provider = get_provider(chosen)
    res = provider.generate(req)
    if not res.ok or not res.path:
        raise RuntimeError(f"Image generation failed ({provider.name}): {res.error}")
    return Path(res.path)


def post_to_x(text: str, media_path: Path, dry_run: bool = False) -> bool:
    if dry_run:
        print(f"[DRY RUN] Would post to X:\n  Caption: {text}\n  Media:   {media_path}")
        return True

    if not restore_x_cookies():
        raise RuntimeError("X session cookies missing (set X_COOKIES_BASE64 or x_session/cookies.json)")

    from playwright.sync_api import sync_playwright

    raw_state = json.loads(X_COOKIES_FILE.read_text(encoding="utf-8"))
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars",
    ]
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=args)
        if isinstance(raw_state, dict) and "cookies" in raw_state:
            ctx = browser.new_context(
                storage_state=str(X_COOKIES_FILE),
                viewport={"width": 1280, "height": 850},
                user_agent=user_agent,
            )
        else:
            ctx = browser.new_context(viewport={"width": 1280, "height": 850}, user_agent=user_agent)
            ctx.add_cookies(raw_state)
        page = ctx.new_page()
        page.goto("https://x.com/compose/post", timeout=35000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(str(media_path.resolve()))
        page.wait_for_timeout(3000)

        textbox = page.locator('[data-testid="tweetTextarea_0"]').first
        textbox.click()
        textbox.fill(text)
        page.wait_for_timeout(1000)

        post_btn = page.locator('[data-testid="tweetButton"]').first
        post_btn.click(force=True, timeout=5000)
        page.wait_for_timeout(5000)
        browser.close()
    print(f"[+] Posted to X: {text} ({media_path.name})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily character-consistent X poster")
    parser.add_argument("--dry-run", action="store_true", help="Generate image without posting to X")
    parser.add_argument("--provider", default=None, help="Override image provider (e.g. fal_kontext)")
    parser.add_argument("--caption", default=None, help="Optional custom X caption")
    args = parser.parse_args()

    img_path = generate_character_image(provider_name=args.provider)
    caption = args.caption or _pick_caption()
    post_to_x(caption, img_path, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
