"""
ig_web.py — Cookie-only Playwright Instagram web uploader (ported from Media-Studio-Automater).

Uses ``INSTAGRAM_COOKIES_BASE64`` or ``instagram_session/cookies.json`` directly
on https://www.instagram.com/ in real Chromium with anti-detect flags.
Never calls username/password login() and never uses instagrapi's private Android API.
"""

import base64
import json
import os
import time
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
IG_SESSION_DIR = ROOT / "instagram_session"
IG_COOKIES_FILE = IG_SESSION_DIR / "cookies.json"


def ensure_ig_cookies() -> bool:
    """Restore instagram_session/cookies.json from INSTAGRAM_COOKIES_BASE64 if present."""
    env_b64 = os.environ.get("INSTAGRAM_COOKIES_BASE64", "").strip()
    if env_b64 and not IG_COOKIES_FILE.exists():
        IG_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        raw = base64.b64decode(env_b64).decode("utf-8")
        IG_COOKIES_FILE.write_text(raw, encoding="utf-8")
    return IG_COOKIES_FILE.exists()


def _cookie_records() -> list:
    if not IG_COOKIES_FILE.exists():
        return []
    try:
        data = json.loads(IG_COOKIES_FILE.read_text(encoding="utf-8"))
        raw = data.get("cookies", data) if isinstance(data, dict) else data
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def is_web_session_available() -> bool:
    """Check that valid, non-expired sessionid + ds_user_id cookies are present."""
    ensure_ig_cookies()
    cookies = _cookie_records()
    if not cookies:
        return False
    by_name = {c.get("name"): c for c in cookies if isinstance(c, dict)}
    session = by_name.get("sessionid")
    user_id = by_name.get("ds_user_id")
    if not session or not session.get("value") or not user_id or not user_id.get("value"):
        return False
    now = time.time()
    for c in (session, user_id):
        exp = c.get("expires", c.get("expirationDate", -1))
        try:
            exp = float(exp)
        except (TypeError, ValueError):
            exp = -1
        if exp > 0 and exp <= now:
            return False
    return True


def _select_crop_ratio(page, preferred_ratios: list[str]) -> None:
    try:
        crop_trigger = page.locator(
            'div[role="dialog"] svg[aria-label="Select crop"], '
            'div[role="dialog"] button:has(svg[aria-label="Select crop"]), '
            'div[role="dialog"] svg[aria-label="Crop"]'
        ).first
        if crop_trigger.is_visible(timeout=3000):
            crop_trigger.click()
            page.wait_for_timeout(800)
            for ratio in preferred_ratios:
                opt = page.locator(
                    f'div[role="dialog"] span:text-is("{ratio}"), '
                    f'div[role="dialog"] button:has-text("{ratio}"), '
                    f'div[role="dialog"] div:text-is("{ratio}")'
                ).first
                if opt.is_visible(timeout=1500):
                    opt.click()
                    page.wait_for_timeout(800)
                    return
            crop_trigger.click()
    except Exception:
        pass


def _await_share_confirmation(page, timeout_ms: int = 90000) -> Tuple[bool, str]:
    deadline = time.time() + (timeout_ms / 1000)
    phrases = (
        "your post has been shared",
        "your reel has been shared",
        "your post has been published",
        "your reel has been published",
        "post shared",
        "reel shared",
    )
    while time.time() < deadline:
        try:
            url = page.url.lower()
            if "create" not in url and ("/reel/" in url or "/p/" in url):
                return True, page.url
        except Exception:
            pass
        try:
            body = page.locator("body").inner_text(timeout=2000).lower()
            if any(p in body for p in phrases):
                return True, page.url
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return False, ""


def publish_media_web(media_path: str, caption: str, mode: str = "reel", headless: bool = True) -> dict:
    """Upload a video reel or photo post to Instagram via Playwright web session."""
    if not is_web_session_available():
        return {"ok": False, "error": "Instagram web cookies missing or expired", "code": "", "pk": ""}

    resolved = Path(media_path).resolve()
    if not resolved.exists():
        return {"ok": False, "error": f"Media file not found: {media_path}", "code": "", "pk": ""}

    from playwright.sync_api import sync_playwright

    raw_cookies = _cookie_records()
    args = ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"]
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=args)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, user_agent=ua)
        ctx.add_cookies(raw_cookies)
        page = ctx.new_page()

        try:
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(4000)
            if "login" in page.url.lower():
                return {"ok": False, "error": "Instagram web session expired (redirected to login)", "code": "", "pk": ""}

            for dismiss in ("Not Now", "Cancel", "Decline optional cookies"):
                try:
                    btn = page.locator(f'button:has-text("{dismiss}")')
                    if btn.is_visible(timeout=1500):
                        btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

            create_link = page.locator('svg[aria-label="New post"]').locator(
                'xpath=ancestor::a | ancestor::div[@role="button"]'
            ).first
            create_link.click()
            page.wait_for_timeout(1500)

            post_item = page.locator('span:text-is("Post")').first
            if post_item.is_visible(timeout=5000):
                post_item.click()
                page.wait_for_timeout(2000)

            file_input = page.locator('div[role="dialog"] input[type="file"], input[type="file"]').first
            file_input.wait_for(state="attached", timeout=15000)
            file_input.set_input_files(str(resolved))
            page.wait_for_timeout(6000 if mode == "reel" else 3500)

            try:
                ok_btn = page.locator('div[role="dialog"] button:has-text("OK"), button:has-text("OK")').first
                if ok_btn.is_visible(timeout=3000):
                    ok_btn.click()
                    page.wait_for_timeout(1500)
            except Exception:
                pass

            ratios = ["9:16", "Original"] if mode == "reel" else ["4:5", "Original"]
            _select_crop_ratio(page, ratios)

            for _ in range(2):
                next_btn = page.locator(
                    'div[role="dialog"] div:text-is("Next"), div[role="dialog"] button:has-text("Next")'
                ).last
                next_btn.click()
                page.wait_for_timeout(3500)

            caption_area = page.locator(
                'div[role="dialog"] [aria-label*="caption" i], div[role="dialog"] div[role="textbox"]'
            ).first
            caption_area.click()
            page.wait_for_timeout(500)
            caption_area.fill(caption)
            page.wait_for_timeout(1500)

            share_btn = None
            for sel in (
                'div[role="dialog"] button:has-text("Share")',
                'div[role="dialog"] div:text-is("Share")',
                'div[role="dialog"] [role="button"]:has-text("Share")',
            ):
                loc = page.locator(sel).last
                if loc.count() > 0 and loc.is_visible():
                    share_btn = loc
                    break
            if not share_btn:
                share_btn = page.locator('div[role="dialog"] button:has-text("Share")').last
            try:
                share_btn.click()
            except Exception:
                share_btn.click(force=True)

            ok, url = _await_share_confirmation(page, timeout_ms=90000)
            if not ok:
                return {"ok": False, "error": "Instagram share confirmation timed out", "code": "", "pk": ""}
            print(f"[ig_web] Published {mode} via Playwright: {url or 'confirmed'}")
            return {"ok": True, "pk": url or "web_ok", "code": url, "error": None}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "code": "", "pk": ""}
        finally:
            browser.close()
