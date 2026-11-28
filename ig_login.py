"""
ig_login.py — Interactive Instagram login & cookie exporter (matching Media-Studio-Automater).

Opens real Chrome to https://www.instagram.com/, waits for ``sessionid`` and
``ds_user_id`` cookies, saves ``instagram_session/cookies.json``, writes base64
to ``instagram_session/ig_cookies_b64.txt``, and copies it to clipboard for
GitHub Secret ``INSTAGRAM_COOKIES_BASE64``.

Usage:
    python ig_login.py
"""

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IG_SESSION_DIR = ROOT / "instagram_session"
PROFILE_DIR = IG_SESSION_DIR / "browser_profile"
COOKIES_PATH = IG_SESSION_DIR / "cookies.json"
B64_PATH = IG_SESSION_DIR / "ig_cookies_b64.txt"


def _copy_to_clipboard(text: str) -> bool:
    try:
        subprocess.run(["clip"], input=text, text=True, check=True)
        return True
    except Exception:
        return False


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[!] playwright is not installed. Run: pip install playwright && playwright install chromium")
        return 1

    IG_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("Instagram Web Session Setup (Playwright Cookie-Only)")
    print("=" * 60)
    print("1. Log in to your Instagram account in the browser window.")
    print("2. Complete any 2FA / Save Info prompt until you see your IG Feed.")
    print("3. Auto-detecting sessionid + ds_user_id cookies (up to 5 min)...")
    print("=" * 60 + "\n")

    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1280, "height": 850},
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--start-maximized",
        ],
    }

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
        except Exception:
            context = p.chromium.launch_persistent_context(**launch_kwargs)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.instagram.com/", timeout=60000)

        deadline = time.time() + 300
        logged_in = False
        while time.time() < deadline:
            cookies = context.cookies()
            by_name = {
                c.get("name"): c.get("value")
                for c in cookies
                if "instagram.com" in c.get("domain", "")
            }
            if by_name.get("sessionid") and by_name.get("ds_user_id"):
                page.wait_for_timeout(2500)
                logged_in = True
                break
            time.sleep(1.5)

        if not logged_in:
            print("[!] Timed out waiting for Instagram login.")
            context.close()
            return 1

        context.storage_state(path=str(COOKIES_PATH))
        b64 = base64.b64encode(COOKIES_PATH.read_bytes()).decode("ascii")
        B64_PATH.write_text(b64, encoding="utf-8")
        copied = _copy_to_clipboard(b64)
        context.close()

    print(f"\n[+] Saved IG storage_state -> {COOKIES_PATH}")
    print(f"[+] Saved base64 string -> {B64_PATH}")
    if copied:
        print("[+] Copied INSTAGRAM_COOKIES_BASE64 to clipboard!")
    else:
        print(f"[*] Copy {B64_PATH} into GitHub Secret: INSTAGRAM_COOKIES_BASE64")
    return 0


if __name__ == "__main__":
    sys.exit(main())
